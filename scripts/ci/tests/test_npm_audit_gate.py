"""Offline npm audit samples only: no npm, network or registry access."""

import copy
import datetime as dt
import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
GATE_PATH = HERE.parent / "npm_audit_gate.py"
SPEC = importlib.util.spec_from_file_location("npm_audit_gate", GATE_PATH)
gate = importlib.util.module_from_spec(SPEC)
# dataclasses resolves annotations through sys.modules.
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

# Real `npm audit --json` for frontend/package-lock.json on 2026-11-17.
PICOMATCH_REPORT = json.loads(
    (HERE / "fixtures" / "npm-audit-picomatch-2026-11-17.json").read_text()
)
TODAY = dt.date(2026, 11, 17)
PICOMATCH = "GHSA-fc5q-39xc-vjpf"


def clean_report():
    return {
        "auditReportVersion": 2,
        "vulnerabilities": {},
        "metadata": {"vulnerabilities": {"total": 0}},
    }


def with_advisory(report, package, ghsa, severity, effects=()):
    report = copy.deepcopy(report)
    report["vulnerabilities"][package] = {
        "name": package,
        "severity": severity,
        "isDirect": False,
        "via": [
            {
                "source": 1,
                "name": package,
                "dependency": package,
                "title": f"{package} sample advisory",
                "url": f"https://github.com/advisories/{ghsa}",
                "severity": severity,
                "range": "<1.0.0",
            }
        ],
        "effects": list(effects),
        "range": "<1.0.0",
        "nodes": [f"node_modules/{package}"],
        "fixAvailable": True,
    }
    for parent in effects:
        report["vulnerabilities"][parent] = {
            "name": parent,
            "severity": severity,
            "via": [package],
            "effects": [],
        }
    return report


def entry(ghsa=PICOMATCH, package="picomatch", added="2026-11-17", expires="2026-12-17"):
    return {
        "id": ghsa,
        "package": package,
        "reason": "build-time only, no fixed release",
        "added": added,
        "expires": expires,
        "owner": "a27497",
    }


def allowlist(*entries):
    return {"advisories": list(entries)}


SAMPLE_ALLOWLIST = allowlist(entry())


class GateCases(unittest.TestCase):
    def test_no_vulnerabilities_passes(self):
        result = gate.evaluate(clean_report(), allowlist(), TODAY)
        self.assertEqual((result.exit_code, result.errors, result.warnings), (0, [], []))

    def test_only_exempted_advisory_passes_with_remaining_days(self):
        result = gate.evaluate(PICOMATCH_REPORT, SAMPLE_ALLOWLIST, TODAY)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])
        self.assertEqual(len(result.exempted), 1)
        self.assertIn(PICOMATCH, result.exempted[0])
        self.assertIn("30 days left", result.exempted[0])

    def test_last_valid_day_still_exempts(self):
        result = gate.evaluate(PICOMATCH_REPORT, SAMPLE_ALLOWLIST, dt.date(2026, 12, 17))
        self.assertEqual(result.exit_code, 0)
        self.assertIn("0 days left", result.exempted[0])

    def test_real_report_without_exemption_fails(self):
        result = gate.evaluate(PICOMATCH_REPORT, allowlist(), TODAY)
        self.assertEqual(result.exit_code, 1)
        # Eleven package entries collapse to the single root advisory.
        self.assertEqual(len(result.errors), 1)
        self.assertIn(PICOMATCH, result.errors[0])

    def test_unexempted_high_fails_next_to_exempted_one(self):
        report = with_advisory(
            PICOMATCH_REPORT, "left-pad", "GHSA-2222-3333-4444", "high", effects=("vite",)
        )
        result = gate.evaluate(report, SAMPLE_ALLOWLIST, TODAY)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("GHSA-2222-3333-4444 high in left-pad", result.errors[0])
        self.assertEqual(len(result.exempted), 1)

    def test_expired_exemption_fails_while_advisory_present(self):
        result = gate.evaluate(PICOMATCH_REPORT, SAMPLE_ALLOWLIST, dt.date(2026, 12, 18))
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("expired on 2026-12-17", result.errors[0])
        self.assertEqual(result.exempted, [])

    def test_expired_exemption_fails_after_advisory_is_gone(self):
        result = gate.evaluate(clean_report(), SAMPLE_ALLOWLIST, dt.date(2026, 12, 18))
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("expired", result.errors[0])

    def test_stale_exemption_warns_without_failing(self):
        result = gate.evaluate(clean_report(), SAMPLE_ALLOWLIST, TODAY)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("remove it from the allowlist", result.warnings[0])

    def test_critical_fails(self):
        report = with_advisory(clean_report(), "minimist", "GHSA-5555-6666-7777", "critical")
        result = gate.evaluate(report, allowlist(), TODAY)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("GHSA-5555-6666-7777 critical in minimist", result.errors[0])

    def test_unexempted_moderate_and_low_fail(self):
        for severity in ("moderate", "low"):
            with self.subTest(severity=severity):
                report = with_advisory(
                    PICOMATCH_REPORT, "minimist", "GHSA-5555-6666-7777", severity
                )
                result = gate.evaluate(report, SAMPLE_ALLOWLIST, TODAY)
                self.assertEqual(result.exit_code, 1)
                self.assertEqual(len(result.errors), 1)
                self.assertIn(f"GHSA-5555-6666-7777 {severity} in minimist", result.errors[0])
                self.assertEqual(len(result.exempted), 1)

    def test_info_is_not_gated(self):
        report = with_advisory(clean_report(), "minimist", "GHSA-5555-6666-7777", "info")
        result = gate.evaluate(report, allowlist(), TODAY)
        self.assertEqual((result.exit_code, result.below_threshold), (0, 1))

    def test_exemption_for_other_package_does_not_match(self):
        result = gate.evaluate(PICOMATCH_REPORT, allowlist(entry(package="micromatch")), TODAY)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("high in picomatch", result.errors[-1])


class InputValidation(unittest.TestCase):
    def test_window_longer_than_limit_is_rejected(self):
        with self.assertRaisesRegex(gate.GateInputError, "limit is 30"):
            gate.evaluate(clean_report(), allowlist(entry(expires="2026-12-18")), TODAY)

    def test_missing_expiry_is_rejected(self):
        broken = entry()
        del broken["expires"]
        with self.assertRaisesRegex(gate.GateInputError, "missing expires"):
            gate.evaluate(clean_report(), allowlist(broken), TODAY)

    def test_duplicate_entry_is_rejected(self):
        with self.assertRaisesRegex(gate.GateInputError, "duplicate"):
            gate.evaluate(clean_report(), allowlist(entry(), entry()), TODAY)

    def test_npm_error_report_fails_closed(self):
        report = {"error": {"code": "ENOAUDIT", "summary": "registry unavailable"}}
        with self.assertRaisesRegex(gate.GateInputError, "registry unavailable"):
            gate.evaluate(report, allowlist(), TODAY)

    def test_unknown_report_version_fails_closed(self):
        with self.assertRaisesRegex(gate.GateInputError, "auditReportVersion"):
            gate.evaluate({"vulnerabilities": {}}, allowlist(), TODAY)


class CommandLine(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.allowlist_path = Path(directory.name) / "allowlist.json"
        self.allowlist_path.write_text(json.dumps(SAMPLE_ALLOWLIST))

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = gate.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_pass_output_lists_exemption(self):
        code, out, _ = self.run_main(
            "--audit-json",
            str(HERE / "fixtures" / "npm-audit-picomatch-2026-11-17.json"),
            "--allowlist",
            str(self.allowlist_path),
            "--today",
            "2026-11-20",
        )
        self.assertEqual(code, 0)
        self.assertIn("EXEMPT  GHSA-fc5q-39xc-vjpf", out)
        self.assertIn("27 days left", out)
        self.assertIn("npm audit gate: PASS", out)

    def test_unreadable_input_exits_nonzero(self):
        code, _, err = self.run_main(
            "--audit-json",
            str(HERE / "fixtures" / "missing.json"),
            "--allowlist",
            str(self.allowlist_path),
        )
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)


if __name__ == "__main__":
    unittest.main()
