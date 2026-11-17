#!/usr/bin/env python3
"""Fail CI on low-or-higher npm advisories unless a dated allowlist entry covers them.

Input is the output of `npm audit --json` (auditReportVersion 2). Only advisory
objects inside `via` are judged. Package entries whose `via` lists only package
names are transitive consequences of those advisories, so exempting the root
advisory also clears them. An audit report that cannot be read, or that carries
an npm `error` object, fails closed.

Allowlist rules (see AGENTS.md): only advisories without a fixed release, each
with an expiry at most MAX_EXEMPTION_DAYS after it was added. An expired entry
fails the gate whether or not the advisory is still reported, so an exemption
is renewed by an explicit edit or removed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Every npm severity except info blocks, so the allowlist is the only loosening of
# what plain `npm audit` enforced before this gate.
BLOCKING_SEVERITIES = frozenset({"low", "moderate", "high", "critical"})
# Short enough that an exemption is re-reviewed against upstream every month.
MAX_EXEMPTION_DAYS = 30
REQUIRED_FIELDS = ("id", "package", "reason", "added", "expires", "owner")
GHSA_ID = re.compile(r"^GHSA(-[23456789cfghjmpqrvwx]{4}){3}$")


class GateInputError(Exception):
    pass


@dataclass(frozen=True)
class Advisory:
    id: str
    package: str
    severity: str
    title: str
    url: str


@dataclass(frozen=True)
class Exemption:
    id: str
    package: str
    reason: str
    added: dt.date
    expires: dt.date
    owner: str


@dataclass
class GateResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    exempted: list[str] = field(default_factory=list)
    below_threshold: int = 0

    @property
    def exit_code(self) -> int:
        return 1 if self.errors else 0


def _parse_date(value: object, label: str) -> dt.date:
    if not isinstance(value, str):
        raise GateInputError(f"{label}: expected YYYY-MM-DD string")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise GateInputError(f"{label}: {exc}") from None


def parse_allowlist(data: object) -> list[Exemption]:
    if not isinstance(data, dict) or not isinstance(data.get("advisories"), list):
        raise GateInputError('allowlist: expected {"advisories": [...]}')
    exemptions: list[Exemption] = []
    seen: set[str] = set()
    for index, entry in enumerate(data["advisories"]):
        label = f"allowlist entry {index}"
        if not isinstance(entry, dict):
            raise GateInputError(f"{label}: expected an object")
        missing = [name for name in REQUIRED_FIELDS if not entry.get(name)]
        if missing:
            raise GateInputError(f"{label}: missing {', '.join(missing)}")
        for name in ("id", "package", "reason", "owner"):
            if not isinstance(entry[name], str):
                raise GateInputError(f"{label}: {name} must be a string")
        advisory_id = entry["id"]
        if not GHSA_ID.match(advisory_id):
            raise GateInputError(f"{label}: id {advisory_id!r} is not a GHSA identifier")
        if advisory_id in seen:
            raise GateInputError(f"{label}: duplicate id {advisory_id}")
        seen.add(advisory_id)
        added = _parse_date(entry["added"], f"{label} added")
        expires = _parse_date(entry["expires"], f"{label} expires")
        if expires < added:
            raise GateInputError(f"{label}: expires {expires} is before added {added}")
        if (expires - added).days > MAX_EXEMPTION_DAYS:
            raise GateInputError(
                f"{label}: {advisory_id} spans {(expires - added).days} days; "
                f"the limit is {MAX_EXEMPTION_DAYS}"
            )
        exemptions.append(
            Exemption(
                advisory_id,
                entry["package"],
                entry["reason"],
                added,
                expires,
                entry["owner"],
            )
        )
    return exemptions


def _advisory_id(via: dict) -> str:
    url = via.get("url")
    if isinstance(url, str):
        tail = url.rstrip("/").rsplit("/", 1)[-1]
        if GHSA_ID.match(tail):
            return tail
    # Without a GHSA URL the entry cannot be allowlisted, but it is still judged.
    return f"npm-source-{via.get('source', 'unknown')}"


def collect_advisories(audit: object) -> dict[str, Advisory]:
    if not isinstance(audit, dict):
        raise GateInputError("audit report: expected a JSON object")
    if "error" in audit:
        error = audit["error"]
        summary = error.get("summary") if isinstance(error, dict) else error
        raise GateInputError(f"npm audit reported an error: {summary}")
    if audit.get("auditReportVersion") != 2:
        raise GateInputError(
            f"audit report: unsupported auditReportVersion {audit.get('auditReportVersion')!r}"
        )
    vulnerabilities = audit.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise GateInputError("audit report: missing vulnerabilities object")
    advisories: dict[str, Advisory] = {}
    for package, entry in vulnerabilities.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("via"), list):
            raise GateInputError(f"audit report: malformed entry for {package}")
        for via in entry["via"]:
            if not isinstance(via, dict):
                continue
            advisory_id = _advisory_id(via)
            severity = str(via.get("severity", "unknown"))
            advisory = Advisory(
                advisory_id,
                str(via.get("name", package)),
                severity,
                str(via.get("title", "")),
                str(via.get("url", "")),
            )
            previous = advisories.get(advisory_id)
            if previous is None or (
                severity in BLOCKING_SEVERITIES and previous.severity not in BLOCKING_SEVERITIES
            ):
                advisories[advisory_id] = advisory
    return advisories


def evaluate(audit: object, allowlist: object, today: dt.date) -> GateResult:
    result = GateResult()
    exemptions = {item.id: item for item in parse_allowlist(allowlist)}
    advisories = collect_advisories(audit)

    for exemption in exemptions.values():
        if exemption.expires < today:
            result.errors.append(
                f"{exemption.id} ({exemption.package}): allowlist entry expired on "
                f"{exemption.expires}; re-check upstream, then renew or remove it"
            )
        if exemption.id not in advisories:
            result.warnings.append(
                f"{exemption.id} ({exemption.package}) is no longer reported by npm audit; "
                "remove it from the allowlist"
            )

    for advisory in sorted(advisories.values(), key=lambda item: item.id):
        if advisory.severity not in BLOCKING_SEVERITIES:
            result.below_threshold += 1
            continue
        exemption = exemptions.get(advisory.id)
        if exemption is None or exemption.package != advisory.package:
            result.errors.append(
                f"{advisory.id} {advisory.severity} in {advisory.package}: "
                f"{advisory.title} {advisory.url}".rstrip()
            )
        elif exemption.expires >= today:
            remaining = (exemption.expires - today).days
            result.exempted.append(
                f"{advisory.id} {advisory.severity} in {advisory.package}: exempt until "
                f"{exemption.expires} ({remaining} days left, owner {exemption.owner})"
            )
    return result


def _read_json(path: str, label: str) -> object:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        return json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise GateInputError(f"{label}: cannot read {path}: {exc}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audit-json", default="-", help="npm audit --json output, or - for stdin")
    parser.add_argument("--allowlist", required=True)
    parser.add_argument("--today", help="override the current UTC date (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    try:
        today = (
            _parse_date(args.today, "--today")
            if args.today
            else dt.datetime.now(dt.timezone.utc).date()
        )
        result = evaluate(
            _read_json(args.audit_json, "audit report"),
            _read_json(args.allowlist, "allowlist"),
            today,
        )
    except GateInputError as exc:
        print(f"npm audit gate: FAIL: {exc}", file=sys.stderr)
        return 2

    for line in result.exempted:
        print(f"EXEMPT  {line}")
    for line in result.warnings:
        print(f"WARN    {line}")
    for line in result.errors:
        print(f"FAIL    {line}")
    if result.below_threshold:
        print(f"INFO    {result.below_threshold} info-severity advisories are not gated")
    status = "FAIL" if result.errors else "PASS"
    print(
        f"npm audit gate: {status} ({len(result.errors)} blocking, "
        f"{len(result.exempted)} exempted, {len(result.warnings)} warnings, today {today})"
    )
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
