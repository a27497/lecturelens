import subprocess
import unittest
from unittest.mock import patch

from scripts.ci.eval_only import ci_route


class CiRouteTest(unittest.TestCase):
    def test_eval_reports_and_result_data(self):
        paths = b"eval/report\nwith-newline.md\0eval/example/freeze.json\0eval/example/results.jsonl\0"
        with patch.object(subprocess, "check_output", return_value=paths):
            self.assertEqual(ci_route("base", "head"), "eval-reports")

    def test_fixture_edit_with_report_still_runs_fixture_tests(self):
        paths = b"eval/example/RESULTS.md\0eval/p8-tutor/dialogues.json\0"
        with patch.object(subprocess, "check_output", return_value=paths):
            self.assertEqual(ci_route("base", "head"), "eval-fixtures")

    def test_managed_pilot_source_edit_runs_fixture_tests(self):
        with patch.object(subprocess, "check_output", return_value=b"eval/study-v2/sources.json\0"):
            self.assertEqual(ci_route("base", "head"), "eval-fixtures")

    def test_code_binary_and_empty_diffs_use_full_ci(self):
        for diff in (
            b"",
            b"eval/example/results.json\0scripts/ci/eval_only.py\0",
            b"eval/example/result.zip\0",
            b"backend/src/main/resources/config.json\0",
            b"evaluation/results.json\0",
        ):
            with self.subTest(diff=diff), patch.object(subprocess, "check_output", return_value=diff):
                self.assertEqual(ci_route("base", "head"), "full")

    def test_renames_consider_both_paths(self):
        paths = b"backend/src/main/resources/config.json\0eval/example/config.json\0"
        with patch.object(subprocess, "check_output", return_value=paths) as changed:
            self.assertEqual(ci_route("base", "head"), "full")
            changed.assert_called_once_with(
                ["git", "diff", "--name-only", "--no-renames", "-z", "base", "head", "--"]
            )
