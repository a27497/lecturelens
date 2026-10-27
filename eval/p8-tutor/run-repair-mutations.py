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
CITATIONS = ROOT / "agent-service/src/lecturelens_real_eval/tutor/citations.py"
FROZEN = ROOT / "eval/p8-tutor/frozen.json"
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
    originals = {
        path: path.read_bytes() for path in (RUNTIME, RUNNER, CITATIONS, FROZEN)
    }
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
            "citable-last-search-only",
            RUNTIME,
            '                citable = list(dict.fromkeys([*state["selected"], *selected]))\n',
            "                citable = list(dict.fromkeys(selected))\n",
            "tests/test_tutor.py::test_citable_union_publishes_first_search_id_after_second_and_restart[None]",
        ),
        (
            "citable-includes-prior-turn-citations",
            RUNTIME,
            '                citable = list(dict.fromkeys([*state["selected"], *selected]))\n',
            (
                '                citable = list(dict.fromkeys([*state["selected"], *selected,\n'
                '                    *(eid for t in history for eid in assembled_citation_ids(t["answer"] or "", t["evaluation"] or ""))]))\n'
            ),
            "tests/test_tutor.py::test_citable_union_excludes_prior_turn_citations_and_fabricated_ids[v2-quantum-l2-p04-e00]",
        ),
        (
            "repair-keep-remove-missing",
            RUNTIME,
            "                    keep_ids=ids[:4],\n                    remove_ids=ids[4:],\n",
            "",
            "tests/test_tutor.py::test_excess_citations_repair_lists_order_and_every_excess_id[True]",
        ),
        (
            "silent-truncate-excess-ids",
            RUNTIME,
            '            ids = assembled_citation_ids(args["text"], args["evaluation"])\n',
            (
                '            ids = assembled_citation_ids(args["text"], args["evaluation"])\n'
                '            for key in ("text", "evaluation"):\n'
                "                for eid in ids[4:]:\n"
                '                    args[key] = args[key].replace("[" + eid + "]", "")\n'
                "            ids = ids[:4]\n"
            ),
            "tests/test_tutor.py::test_v8_failed_first_finish_replay[valid-algorithms-l1-3-turn-3]",
        ),
        (
            "math-bracket-counted",
            CITATIONS,
            " if EVIDENCE_ID.fullmatch(token)",
            "",
            "tests/test_tutor.py::test_math_brackets_publish_unchanged_but_strict_foreign_id_fails[None]",
        ),
        (
            "review-retry-removed",
            RUNNER,
            "                if attempt < 3:\n",
            "                if False:\n",
            "tests/test_p8_tutor_eval.py::test_reviewer_retry_is_bounded_audited_and_continues_suite[schema-2]",
        ),
        (
            "review-failure-kills-suite",
            RUNNER,
            '                    fatal = ledger.check()["blocked"] or fatal\n',
            '                    fatal = ledger.check()["blocked"] or ("REAL_EVAL_REVIEW_FAILED" if record.get("error") else fatal)\n',
            "tests/test_p8_tutor_eval.py::test_reviewer_retry_is_bounded_audited_and_continues_suite[schema-3]",
        ),
        (
            "silent-unobserved-dropping",
            RUNTIME,
            '            ids = assembled_citation_ids(args["text"], args["evaluation"])\n',
            '            ids = [i for i in assembled_citation_ids(args["text"], args["evaluation"]) if i in state["selected"]]\n',
            "tests/test_tutor.py::test_finish_limit_does_not_hide_authority_or_other_schema_failure[unobserved]",
        ),
        (
            "silent-id-truncation",
            RUNTIME,
            '            ids = assembled_citation_ids(args["text"], args["evaluation"])\n',
            '            ids = assembled_citation_ids(args["text"], args["evaluation"])[:4]\n',
            "tests/test_tutor.py::test_excess_citations_repair_lists_order_and_every_excess_id[False]",
        ),
        (
            "provider-declaration-authority",
            RUNTIME,
            '            ids = assembled_citation_ids(args["text"], args["evaluation"])\n',
            '            ids = response["arguments"].get("evidence_ids", [])\n',
            "tests/test_tutor.py::test_controller_publishes_extracted_order_dedupes_and_ignores_declarations[declared0]",
        ),
        (
            "unlimited-format-repairs-after-restart",
            RUNTIME,
            "                if self.repaired(state, FORMAT_REPAIRS):\n",
            "                if False:\n",
            "tests/test_tutor.py::test_second_finish_limit_violation_is_fatal_even_after_restart[True]",
        ),
        (
            "reviewer-cascade-rule-removed",
            RUNNER,
            '        judged["context_retained"] = False\n',
            "        pass\n",
            "tests/test_p8_tutor_eval.py::test_reviewer_cascade_only_downgrades_invented_antecedent[invented-True]",
        ),
        (
            "context-non-penalty-removed",
            RUNNER,
            '        judged["context_retained"] = True\n',
            "        pass\n",
            "tests/test_p8_tutor_eval.py::test_context_followup_non_penalty_preserves_other_judgments_and_failed_turns[clean_abstain-published_abstention]",
        ),
        (
            "cascade-split-always-zero",
            RUNNER,
            '        "over_abstain_cascade_count": len(cascade),\n',
            '        "over_abstain_cascade_count": 0,\n',
            "tests/test_p8_tutor_eval.py::test_over_abstain_cascade_split_preserves_total_and_denominator",
        ),
        (
            "schema-immediate-hard-failure",
            RUNTIME,
            "            if size_violations:\n",
            '            if size_violations:\n                raise StudyError("TUTOR_FINISH_LIMIT_EXCEEDED")\n',
            "tests/test_tutor.py::test_finish_limit_observation_then_unchanged_repair_publishes[ids]",
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
            # Exercise the mutant behavior past verify_inputs; otherwise integration
            # tests could kill it merely because its source digest changed.
            frozen = json.loads(originals[FROZEN])
            frozen["files"][str(source.relative_to(ROOT))] = hashlib.sha256(
                mutant.encode()
            ).hexdigest()
            FROZEN.write_text(json.dumps(frozen, indent=2) + "\n")
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
            FROZEN.write_bytes(originals[FROZEN])
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
