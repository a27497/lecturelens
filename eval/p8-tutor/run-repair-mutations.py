"""Offline repair mutants: patch, run one guarded PG test, restore and verify bytes."""

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "agent-service/src/lecturelens_real_eval/tutor/runtime.py"
RUNNER = ROOT / "agent-service/src/lecturelens_real_eval/tutor_runner.py"
CHECKS = ROOT / ".data/p8-tutor/checks"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--label",
        default="repair",
        help="Fresh artifact prefix; prior outputs are immutable",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        parser.error("Invalid artifact label")
    manifest = CHECKS / f"{args.label}-mutations.json"
    assert not manifest.exists()
    originals = {path: path.read_bytes() for path in (RUNTIME, RUNNER)}
    environment = {
        k: os.environ[k]
        for k in ("PATH", "HOME", "USER", "LANG", "LC_ALL")
        if k in os.environ
    }
    environment["AGENT_TEST_DATABASE_URL"] = (
        "postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test"
    )
    cases = [
        (
            "schema-immediate-hard-failure",
            RUNTIME,
            "            if inline_not_declared or declared_not_inline or duplicates or size_violations:\n",
            (
                '            if size_violations:\n                raise StudyError("TUTOR_FINISH_LIMIT_EXCEEDED")\n'
                "            if inline_not_declared or declared_not_inline or duplicates or size_violations:\n"
            ),
            "tests/test_tutor.py::test_finish_limit_observation_then_unchanged_repair_publishes[ids]",
        ),
        (
            "silent-id-truncation",
            RUNTIME,
            '            ids = args["evidence_ids"]\n',
            (
                '            ids = args["evidence_ids"][:4]\n'
                '            args["evidence_ids"] = ids\n'
                '            for field in ("text", "evaluation"):\n'
                "                for eid in inline_citation_ids(args[field]):\n"
                "                    if eid not in ids:\n"
                '                        args[field] = args[field].replace(f"[{eid}]", "")\n'
            ),
            "tests/test_tutor.py::test_finish_limit_observation_then_unchanged_repair_publishes[ids]",
        ),
        (
            "silent-inline-dropping",
            RUNTIME,
            '            inline = inline_citation_ids(args["text"] + " " + args["evaluation"])\n',
            (
                '            for field in ("text", "evaluation"):\n'
                "                for eid in inline_citation_ids(args[field]):\n"
                "                    if eid not in ids:\n"
                '                        args[field] = args[field].replace(f"[{eid}]", "")\n'
                '            inline = inline_citation_ids(args["text"] + " " + args["evaluation"])\n'
            ),
            "tests/test_tutor.py::test_unified_format_repair_reports_exact_faults_and_never_truncates[inline_extra]",
        ),
        (
            "unlimited-format-repairs-after-restart",
            RUNTIME,
            "                if self.repaired(state, FORMAT_REPAIRS):\n",
            "                if False:\n",
            "tests/test_tutor.py::test_second_finish_limit_violation_is_fatal_even_after_restart[True]",
        ),
        (
            "socratic-immediate-hard-failure",
            RUNTIME,
            "                if self.repaired(state, SOCRATIC_REPAIRS):\n",
            (
                '                raise StudyError("TUTOR_SOCRATIC_CONTRACT")\n'
                "                if self.repaired(state, SOCRATIC_REPAIRS):\n"
            ),
            "tests/test_tutor.py::test_socratic_one_shot_repair_and_restart[False-True-outcome]",
        ),
        (
            "no-repair-budget-reservation",
            RUNTIME,
            '            if state["observations"][-1].get("error") in REPAIRS:\n',
            "            if False:\n",
            "tests/test_tutor.py::test_two_searches_then_repairs_have_prepaid_finish_only_budget[repairs2]",
        ),
        (
            "over-abstain-always-zero",
            RUNNER,
            '        "over_abstain_count": len(over_abstain),\n',
            '        "over_abstain_count": 0,\n',
            "tests/test_p8_tutor_eval.py::test_over_abstain_metric_counts_only_completed_unexpected_abstentions_and_is_report_only",
        ),
    ]
    results = []
    for name, source, before, after, node in cases:
        original = originals[source]
        text = original.decode()
        assert text.count(before) == 1, name
        mutant = text.replace(before, after)
        prefix = CHECKS / f"{args.label}-mutation-{name}"
        # Prior evidence is immutable. Reruns require a new output prefix.
        assert not any(
            prefix.with_suffix(s).exists() for s in (".patch", ".log", ".xml")
        )
        prefix.with_suffix(".patch").write_text(
            "".join(
                difflib.unified_diff(
                    text.splitlines(True),
                    mutant.splitlines(True),
                    fromfile=str(source.relative_to(ROOT)),
                    tofile=str(source.relative_to(ROOT)),
                )
            )
        )
        try:
            source.write_text(mutant)
            command = [
                sys.executable,
                "scripts/eval/check-study-offline.py",
                "--database-port",
                "25741",
                "--network-records",
                str(prefix.relative_to(ROOT)) + "-network",
                "--",
                "-q",
                node,
                "--junitxml=../" + str(prefix.relative_to(ROOT)) + ".xml",
            ]
            run = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            prefix.with_suffix(".log").write_text(run.stdout)
            suite = ET.parse(prefix.with_suffix(".xml")).getroot().find("testsuite")
            result = {
                "mutation": name,
                "returncode": run.returncode,
                **{
                    k: int(suite.attrib.get(k, 0))
                    for k in ("tests", "failures", "errors", "skipped")
                },
                "node": node,
                "command": command,
                "mutant_sha256": hashlib.sha256(mutant.encode()).hexdigest(),
                "patch_sha256": hashlib.sha256(
                    prefix.with_suffix(".patch").read_bytes()
                ).hexdigest(),
            }
            assert (
                result["returncode"],
                result["tests"],
                result["failures"],
                result["errors"],
                result["skipped"],
            ) == (1, 1, 1, 0, 0), result
            result["killed"] = True
            results.append(result)
            print(
                json.dumps(
                    {
                        k: result[k]
                        for k in (
                            "mutation",
                            "killed",
                            "tests",
                            "failures",
                            "errors",
                            "skipped",
                        )
                    }
                ),
                flush=True,
            )
        finally:
            source.write_bytes(original)
            assert all(p.read_bytes() == data for p, data in originals.items())
    manifest.write_text(
        json.dumps(
            {
                "restored_sha256": {
                    str(p.relative_to(ROOT)): hashlib.sha256(data).hexdigest()
                    for p, data in originals.items()
                },
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
