"""Credential-free terminal handoff regression; never invokes native execution."""

import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import terminal_once as launch

RUNNER = Path(launch.risk_once.authority()["execution_root"])
sys.path.insert(0, str(RUNNER / "agent-service/src"))
HEAD = "a" * 40
NOW = datetime(2026, 11, 8, 15, tzinfo=timezone.utc)


class FixedTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


class NoCredentialValues(dict):
    def __getitem__(self, key):
        if key == "AGENT_LLM_API_KEY":
            raise AssertionError("CREDENTIAL_VALUE_READ")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key == "AGENT_LLM_API_KEY":
            raise AssertionError("CREDENTIAL_VALUE_READ")
        return super().get(key, default)


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.receipts = Path(self.temp.name) / "receipts"
        self.price = Path(self.temp.name) / "price.json"
        self.price.write_text(
            json.dumps({"reviewed_utc": datetime.now(timezone.utc).isoformat()})
        )
        self.patches = [
            patch.object(launch, "RECEIPTS", self.receipts),
            patch.object(launch, "PRICE", self.price),
            patch.object(
                launch.os, "environ", NoCredentialValues(AGENT_LLM_API_KEY=None)
            ),
            patch.object(launch.admission, "preparation_head", return_value=HEAD),
            patch.object(launch.admission, "inspect", return_value={"frozen": {}}),
            patch.object(launch.admission, "handoff"),
            patch.object(launch, "database_identity"),
        ]
        self.mocks = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)
        for p in [
            patch.object(launch, "datetime", FixedTime),
            patch.object(launch.risk_once, "available"),
            patch.object(launch.risk_once, "utcnow", return_value=NOW),
        ]:
            p.start()
            self.addCleanup(p.stop)
        self.native = SimpleNamespace(live_admission=unittest.mock.Mock())
        p = patch.dict(
            sys.modules,
            {"lecturelens_real_eval.tutor.selection_smoke": self.native},
        )
        p.start()
        self.addCleanup(p.stop)

    def test_missing_key_stops_before_database_or_issuance(self):
        with patch.object(launch.os, "environ", {}), self.assertRaises(ValueError):
            launch.issue_and_handoff(HEAD)
        self.mocks[-1].assert_not_called()
        self.assertFalse(self.receipts.exists())

    def test_changed_preparation_head_stops(self):
        with self.assertRaises(ValueError):
            launch.issue_and_handoff("b" * 40)
        self.mocks[-1].assert_not_called()
        self.assertFalse(self.receipts.exists())

    def test_stale_price_stops_before_database_or_issuance(self):
        self.price.write_text(
            json.dumps(
                {
                    "reviewed_utc": (
                        datetime.now(timezone.utc) - timedelta(days=2)
                    ).isoformat()
                }
            )
        )
        with self.assertRaises(ValueError):
            launch.issue_and_handoff(HEAD)
        self.mocks[-1].assert_not_called()
        self.assertFalse(self.receipts.exists())

    def test_database_failure_stops_before_issuance(self):
        self.mocks[-1].side_effect = ValueError("DATABASE_NOT_READY")
        with self.assertRaises(ValueError):
            launch.issue_and_handoff(HEAD)
        self.assertFalse(self.receipts.exists())

    def test_expired_outer_authority_stops_without_issuance(self):
        class Expired(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 8, 20, tzinfo=timezone.utc)

        with patch.object(launch, "datetime", Expired), self.assertRaises(ValueError):
            launch.issue_and_handoff(HEAD)
        self.assertFalse(self.receipts.exists())

    def test_bound_receipts_and_unchanged_admission_handoff(self):
        launch.issue_and_handoff(HEAD)
        risk = json.loads((self.receipts / "risk.json").read_bytes())
        grant = json.loads((self.receipts / "grant.json").read_bytes())
        launch.risk_once.validate(risk, grant, HEAD)
        expected = launch.risk_once.authority()
        for key in launch.risk_once.SCOPE_KEYS:
            self.assertEqual(grant[key], expected[key])
            self.assertEqual(risk[key], expected[key])
        self.assertEqual(grant["preparation_git_head"], HEAD)
        self.assertEqual(
            grant["cost_assurance_sha256"],
            launch.admission.digest(self.receipts / "risk.json"),
        )
        self.assertEqual(
            grant["review_plan_sha256"],
            launch.admission.digest(launch.admission.POLICY),
        )
        self.assertTrue(grant["authorized"])
        self.assertEqual(os.stat(self.receipts / "grant.json").st_mode & 0o777, 0o600)
        self.native.live_admission.assert_called_once()
        self.mocks[-2].assert_called_once_with(
            RUNNER,
            RUNNER / ".data" / launch.risk_once.RUN_ID,
            self.receipts / "grant.json",
            self.receipts / "pricing.json",
            self.receipts / "risk.json",
        )

    def test_repeated_issuance_cannot_renew(self):
        launch.issue_and_handoff(HEAD)
        before = (self.receipts / "grant.json").read_bytes()
        with self.assertRaises(FileExistsError):
            launch.issue_and_handoff(HEAD)
        self.assertEqual(before, (self.receipts / "grant.json").read_bytes())
        self.mocks[-2].assert_called_once()

    def test_failed_native_check_leaves_receipts_and_blocks_reissue(self):
        self.native.live_admission.side_effect = ValueError("DENIED")
        with self.assertRaises(ValueError):
            launch.issue_and_handoff(HEAD)
        self.assertTrue((self.receipts / "grant.json").exists())
        with self.assertRaises(FileExistsError):
            launch.issue_and_handoff(HEAD)
        self.mocks[-2].assert_not_called()


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.expected = launch.admission.load(launch.DATABASE)
        self.valid = {
            "id": self.expected["id"],
            "image": self.expected["image"],
            "running": True,
            "run_id": launch.risk_once.RUN_ID,
            "restart": "no",
            "ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "25841"}]},
            "mounts": [
                {
                    "Type": "volume",
                    "Name": self.expected["volume"],
                    "Destination": "/var/lib/postgresql/data",
                    "RW": True,
                }
            ],
        }

    def test_identity_and_minimal_docker_environment(self):
        with (
            patch.object(
                launch.subprocess,
                "check_output",
                return_value=json.dumps(self.valid).encode(),
            ) as child,
            patch.object(launch.admission, "database_ready") as sql,
        ):
            launch.database_identity()
        self.assertEqual(child.call_args.kwargs["env"], {"PATH": "/usr/bin:/bin"})
        self.assertNotIn(".Config.Env", child.call_args.args[0][3])
        sql.assert_called_once()

    def test_changed_identity_loopback_or_persistence_rejected(self):
        for field, value in [
            ("id", "other"),
            ("image", "other"),
            ("running", False),
            ("run_id", "other"),
            ("restart", "always"),
            ("ports", {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "25841"}]}),
            ("mounts", []),
        ]:
            with self.subTest(field=field):
                altered = copy.deepcopy(self.valid)
                altered[field] = value
                with (
                    patch.object(
                        launch.subprocess,
                        "check_output",
                        return_value=json.dumps(altered).encode(),
                    ),
                    patch.object(launch.admission, "database_ready") as sql,
                ):
                    with self.assertRaises(ValueError):
                        launch.database_identity()
                    sql.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
