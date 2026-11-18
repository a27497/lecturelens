"""Holdout execution helpers (PLAN v4 revision 3 "execution"): judge concurrency with a bounded
fallback, the judge-in-flight counter the product runner records, per-repetition packet
verification and merge, the course-split agreement sample and the repetition cost gate.

None of this changes what the judge sees: every judge request still carries one normalized
response without path, repetition, timing or cost.
"""

import fcntl
import json
import math
import os
import random
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import blind

HOLDOUT_JUDGE_CONCURRENCY = 8
FALLBACK_JUDGE_CONCURRENCY = 4
# Three in a row is the shortest run that separates a provider limit from one unlucky request.
CONSECUTIVE_PROVIDER_ERRORS = 3
ERROR_RATE_LIMIT = 0.05
# A rate needs a denominator: below 20 attempts one error alone would exceed 5%.
ERROR_RATE_MIN_ATTEMPTS = 20


def provider_error(status):
    """429, 5xx and transport failures (status None) count toward the fallback; 4xx refusals stop the run."""
    return status is None or status == 429 or status >= 500


class ProviderErrorsPersist(RuntimeError):
    """The fallback did not help: stop judging and report (PLAN stop_conditions)."""


class AdaptiveLimit:
    """At most `limit` judge requests in flight; drops once, permanently, to the fallback limit.

    The fallback fires on CONSECUTIVE_PROVIDER_ERRORS provider errors in a row, or when provider
    errors exceed ERROR_RATE_LIMIT of at least ERROR_RATE_MIN_ATTEMPTS attempts. The counters restart
    at the fallback; a second trigger raises ProviderErrorsPersist, so a provider limit stops the run
    instead of feeding retries. Retries per entry stay bounded by the caller (JUDGE_ATTEMPTS).
    """

    def __init__(self, limit, fallback=FALLBACK_JUDGE_CONCURRENCY, on_degrade=None):
        if not 1 <= fallback <= limit:
            raise ValueError("fallback must be between 1 and the limit")
        self.limit, self.fallback, self.on_degrade = limit, fallback, on_degrade
        self.in_flight = self.attempts = self.errors = self.consecutive = 0
        self.degraded = self.stopped = None
        self.cond = threading.Condition()

    def __enter__(self):
        with self.cond:
            while self.in_flight >= self.limit and not self.stopped:
                self.cond.wait()
            if self.stopped:
                raise ProviderErrorsPersist(self.stopped)
            self.in_flight += 1
        return self

    def __exit__(self, *exc):
        with self.cond:
            self.in_flight -= 1
            self.cond.notify_all()

    def record(self, status):
        with self.cond:
            self.attempts += 1
            if provider_error(status):
                self.errors += 1
                self.consecutive += 1
            else:
                self.consecutive = 0
            reason = None
            if self.consecutive >= CONSECUTIVE_PROVIDER_ERRORS:
                reason = f"{self.consecutive} consecutive provider errors"
            elif self.attempts >= ERROR_RATE_MIN_ATTEMPTS and self.errors / self.attempts > ERROR_RATE_LIMIT:
                reason = f"provider error rate {self.errors}/{self.attempts}"
            if reason and (self.degraded is not None or self.limit == self.fallback):
                self.stopped = reason
                self.cond.notify_all()
                raise ProviderErrorsPersist(reason)
            if reason:
                self.degraded = {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "from": self.limit,
                    "to": self.fallback,
                    "reason": reason,
                    "attempts": self.attempts,
                    "errors": self.errors,
                }
                self.limit = self.fallback
                self.attempts = self.errors = self.consecutive = 0
                self.cond.notify_all()
                if self.on_degrade:
                    self.on_degrade(self.degraded)


class InflightCounter:
    """Judge requests in flight, per process, in one JSON file shared with the product runner."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _update(self, delta):
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            raw = os.read(fd, 1 << 16)
            counts = json.loads(raw) if raw else {}
            key = str(os.getpid())
            counts[key] = counts.get(key, 0) + delta
            if counts[key] <= 0:
                counts.pop(key)
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps(counts).encode())
        finally:
            os.close(fd)

    def __enter__(self):
        self._update(1)
        return self

    def __exit__(self, *exc):
        self._update(-1)


def judge_inflight(path):
    """Judge requests in flight now, counting only processes that are still alive."""
    try:
        counts = json.loads(Path(path).read_text() or "{}")
    except FileNotFoundError:
        return 0
    total = 0
    for pid, count in counts.items():
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            pass
        total += count
    return total


def verify_sources(judge_root, labels, ok_records):
    """Check every per-repetition packet before reveal.

    labels: packet labels under judge_root; ok_records: {(path, rep, item_id)} of status-ok run records.
    Returns per-label counts; raises ValueError on any mismatch or missing decision.
    """
    report, covered = {}, set()
    for label in labels:
        base = Path(judge_root) / label
        packet = json.loads((base / "packet.json").read_text())
        mapping = json.loads((base / "judge-only-mapping.json").read_text())
        decisions = json.loads((base / "decisions.json").read_text())
        joined = blind.reveal(packet, mapping, decisions)  # sha, mapping and completeness checks
        keys = {(r["path"], r["rep"], r["item_id"]) for r in joined}
        if keys & covered:
            raise ValueError(f"VERIFY_OVERLAP {label}")
        covered |= keys
        reps = sorted({r["rep"] for r in joined})
        expected = {k for k in ok_records if k[1] in reps}
        if keys != expected:
            raise ValueError(
                f"VERIFY_RECORDS_MISMATCH {label}: judged {len(keys)}, ok records {len(expected)}"
            )
        report[label] = {
            "reps": reps,
            "judged": len(keys),
            "undetermined": sum(r["decision"].get("verdict") == "UNDETERMINED" for r in joined),
        }
    if covered != set(ok_records):
        raise ValueError(f"VERIFY_UNJUDGED {len(set(ok_records) - covered)} ok records have no packet")
    return report


def merged(judge_root, labels):
    """(packet entries, mapping responses, decisions) over several verified per-repetition packets."""
    entries, mapping, decisions = [], {}, {}
    for label in labels:
        base = Path(judge_root) / label
        entries += json.loads((base / "packet.json").read_text())["entries"]
        mapping.update(json.loads((base / "judge-only-mapping.json").read_text())["responses"])
        decisions.update(json.loads((base / "decisions.json").read_text()))
    return entries, mapping, decisions


def course_of(item_id, lecture_by_item):
    lecture = lecture_by_item[item_id]
    return lecture.split("-")[1]  # mit-6.034-f10-lec11 -> 6.034


def agreement_by_course(entries, mapping, decisions, lecture_by_item, *, seed, fraction=0.2):
    """Seeded ceil(fraction) sample per (course, path), one review packet per course.

    Each review packet carries no path, repetition, judge label or cost; the judge-only key keeps them.
    """
    rng = random.Random(seed)
    cells = defaultdict(list)
    for rid, where in sorted(mapping.items()):
        cells[(course_of(where["item_id"], lecture_by_item), where["path"])].append(rid)
    by_id = {e["response_id"]: e for e in entries}
    out = {}
    for course in sorted({c for c, _ in cells}):
        chosen = []
        for path in sorted(p for c, p in cells if c == course):
            pool = cells[(course, path)]
            chosen += rng.sample(pool, max(1, math.ceil(len(pool) * fraction)))
        chosen.sort()
        review = {
            "version": "l4-agreement-packet-v2",
            "course": course,
            "seed": seed,
            "fraction": fraction,
            "entries": [by_id[rid] for rid in chosen],
        }
        rng.shuffle(review["entries"])
        key = {
            "packet_sha256": blind.sha256(review),
            "judge": {rid: decisions[rid] for rid in chosen},
            "paths": {rid: mapping[rid] for rid in chosen},
        }
        out[course] = (review, key)
    return out


def projected_spend(
    *, committed_nano, pending_judge, judge_mean_nano, remaining_reps, product_rep_nano, entries_per_rep
):
    """Spend projected to the end of the campaign for the repetition cost gate.

    committed: settled + uncertain + reserved so far; pending_judge: responses already run but not yet
    judged (the judge runs behind the product calls); each remaining repetition costs the observed
    product spend of a finished repetition plus its judged responses at the observed mean judge cost.
    """
    return (
        committed_nano
        + pending_judge * judge_mean_nano
        + remaining_reps * (product_rep_nano + entries_per_rep * judge_mean_nano)
    )
