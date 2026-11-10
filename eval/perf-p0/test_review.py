"""P11-A independent regressions: all HTTP/Compose responses are in-memory fakes."""

import asyncio
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from cleanup import ROOT, cleanup
from load import OperationError, group, summary
from run import Environment, cgroup_limits, require_rental_host
from test_harness import paths
from verify import verify

SHA = "a" * 40
LABEL = "DEV_SMOKE_NOT_RESUME"


def bundle(directory):
    config = {
        "scenarios": ["S1"],
        "concurrency": [1],
        "requests_per_group": 1,
        "admission_seconds": None,
        "operation_timeout_seconds": 1,
    }
    rows = []
    items = []
    for warmup in (True, False):
        row = {
            "scenario": "S1",
            "concurrency": 1,
            "warmup": warmup,
            "request_id": str(warmup),
            "ok": True,
            "latency_ms": 10,
            "wall_latency_ms": 10,
            "start_offset_ms": 0,
            "finish_offset_ms": 10,
            "http_status": 200,
            "http_requests": 1,
            "http_response_status_counts": {"200": 1},
            "schema_version": 2,
            "source_sha": SHA,
            "label": LABEL,
        }
        rows.append(row)
        items.append(
            dict(
                scenario="S1",
                concurrency=1,
                warmup=warmup,
                schema_version=2,
                undrained_tutor=False,
                stop={"requests": 1, "admission_seconds": None, "timeout_seconds": 1},
                **summary([row], 0.1, schema=2),
            )
        )
    source = {"sha": SHA, "source_dirty": False}
    result = {
        "schema_version": 2,
        "head": SHA,
        "source": source,
        "end_source": source.copy(),
        "success": True,
        "valid_clean_source_evidence": True,
        "stages": {"cleanup": {"status": "PASS"}},
        "config": config,
        "config_sha256": hashlib.sha256(
            json.dumps(config, sort_keys=True).encode()
        ).hexdigest(),
        "warmups": items[:1],
        "groups": items[1:],
        "label": LABEL,
    }
    write_bundle(directory, result, rows)
    return result, rows


def write_bundle(directory, result, rows):
    (directory / "result.json").write_text(json.dumps(result))
    (directory / "requests.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows)
    )


class Evidence(unittest.TestCase):
    def test_complete_valid_bundle_and_mutations(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            original, raw = bundle(directory)
            self.assertEqual(verify(directory, SHA)["status"], "PASS")
            mutations = {
                "missing_group": lambda r, rows: r["groups"].clear(),
                "missing_warmup": lambda r, rows: r["warmups"].clear(),
                "duplicate_group": lambda r, rows: r["groups"].append(r["groups"][0]),
                "row_sha": lambda r, rows: rows[1].update(source_sha="b" * 40),
                "row_label": lambda r, rows: rows[1].update(label="RESUME"),
                "nan_latency": lambda r, rows: rows[1].update(latency_ms=float("nan")),
                "negative_latency": lambda r, rows: rows[1].update(latency_ms=-1),
                "zero_wall": lambda r, rows: r["groups"][0].update(wall_seconds=0),
                "fake_throughput": lambda r, rows: r["groups"][0].update(
                    successful_per_second=999
                ),
                "request_cap": lambda r, rows: rows.append(
                    dict(rows[-1], request_id="extra")
                ),
                "cleanup_in_latency": lambda r, rows: rows[1].update(cleanup_ms=9),
                "wall_mismatch": lambda r, rows: rows[1].update(finish_offset_ms=99),
                "busy_success": lambda r, rows: rows[1].update(
                    error="RETRIEVAL_BUSY_503"
                ),
                "no_http_send": lambda r, rows: rows[1].update(http_requests=0),
                "undrained": lambda r, rows: rows[1].update(cleanup_ok=False),
                "stop_changed": lambda r, rows: r["groups"][0]["stop"].update(
                    timeout_seconds=2
                ),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    result, rows = copy.deepcopy(original), copy.deepcopy(raw)
                    mutate(result, rows)
                    write_bundle(directory, result, rows)
                    with self.assertRaises(AssertionError):
                        verify(directory, SHA)

    def test_busy_proof_must_be_same_failed_request(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result, rows = bundle(directory)
            rows[1].update(
                ok=False,
                error="RETRIEVAL_BUSY_503",
                http_status=503,
                http_response_status_counts={"503": 1},
                retry_after="2",
            )
            result["groups"][0].update(summary([rows[1]], 0.1, schema=2))
            write_bundle(directory, result, rows)
            with self.assertRaisesRegex(AssertionError, "No genuine"):
                verify(directory, SHA, True)
            rows[1]["retry_after"] = "1"
            result["groups"][0].update(summary([rows[1]], 0.1, schema=2))
            write_bundle(directory, result, rows)
            self.assertEqual(verify(directory, SHA, True)["status"], "PASS")

    def test_nearest_rank_twenty_samples_and_http_response_denominator(self):
        rows = [
            {
                "ok": True,
                "latency_ms": i,
                "http_status": 200,
                "http_requests": 3,
                "http_response_status_counts": {"200": 3},
            }
            for i in range(1, 21)
        ]
        result = summary(rows, 2, schema=2)
        self.assertEqual(result["latency_ms"]["all"], {"p50": 10, "p95": 19})
        self.assertEqual(result["successful_per_second"], 10)
        self.assertEqual(result["http_response_status_counts"], {"200": 60})
        self.assertEqual(result["http_requests_started"], 60)


class HttpErrors(unittest.IsolatedAsyncioTestCase):
    async def test_evidence_fences_reject_foreign_or_stale_qa_results(self):
        for evidence in (
            {"evidenceId": "foreign", "revision": 2},
            {"evidenceId": "ev-1", "revision": 1},
        ):
            response = httpx.Response(
                200,
                json={"code": "0", "data": {"answer": "text", "evidence": [evidence]}},
            )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _, response=response: response)
            ) as client:
                with self.assertRaisesRegex(
                    OperationError, "QA_EVIDENCE_SCOPE_MISMATCH"
                ):
                    await paths().run("S2", client, {"http_requests": 0})

    async def test_turn_timer_excludes_session_creation_and_waits_for_completion(self):
        clock = [0]

        def handler(request):
            if request.url.path.endswith("/sessions"):
                clock[0] = 100
                data = {"session": {"session_id": "s1"}}
            elif request.method == "POST":
                clock[0] = 105
                data = {"turns": []}
            else:
                clock[0] = 120
                data = {
                    "turns": [
                        {
                            "client_turn_id": "r1",
                            "status": "completed",
                            "model_calls": 2,
                            "outcome": "answered",
                            "answer": "text [ev-1]",
                            "citations": [{"evidence_id": "ev-1"}],
                        }
                    ]
                }
            return httpx.Response(200, json={"code": "0", "data": data})

        row = {"http_requests": 0, "polls": 0, "request_id": "r1"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("load.time.perf_counter", side_effect=lambda: clock[0]):
                await paths().run("S3", client, row)
        self.assertEqual(row["turn_latency_ms"], 20_000)
        self.assertEqual(row["turn_status"], "completed")

    async def test_429_503_non_json_and_untrusted_codes_never_become_success(self):
        cases = [
            ("S1", 429, None, "RETRIEVAL_HTTP_429_NON_JSON"),
            ("S1", 503, {"detail": "Retrieval unavailable"}, "RETRIEVAL_HTTP_503"),
            ("S2", 503, None, "JAVA_HTTP_503_NON_JSON"),
            (
                "S2",
                429,
                {"code": "TASK_RATE_LIMITED"},
                "JAVA_HTTP_429_CODE_TASK_RATE_LIMITED",
            ),
            (
                "S2",
                200,
                {"code": "Bearer secret payload"},
                "JAVA_HTTP_200_CODE_INVALID_CODE",
            ),
            ("S2", 200, [], "JAVA_HTTP_200_INVALID_ENVELOPE"),
        ]
        for scenario, status, payload, expected in cases:
            with self.subTest(scenario=scenario, status=status, expected=expected):
                row = {"http_requests": 0, "request_id": "r1"}
                response = (
                    httpx.Response(status, json=payload)
                    if payload is not None
                    else httpx.Response(status, text="not JSON")
                )
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda _, response=response: response)
                ) as client:
                    with self.assertRaisesRegex(OperationError, expected):
                        await paths().run(scenario, client, row)
                self.assertEqual(row["http_status"], status)
                self.assertEqual(row["http_response_status_counts"], {str(status): 1})
                self.assertEqual(row["http_requests"], 1)

    async def test_transport_timeout_counts_send_without_fabricating_http_status(self):
        def handler(request):
            raise httpx.ReadTimeout("not public", request=request)

        row = {"http_requests": 0, "request_id": "r1"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(httpx.ReadTimeout):
                await paths().run("S1", client, row)
        self.assertEqual(row["http_requests"], 1)
        self.assertNotIn("http_status", row)

    async def test_deadline_cannot_be_suppressed_into_success(self):
        class Suppressed:
            async def run(self, scenario, client, row):
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    return

        result = await group(Suppressed(), "S1", 1, requests=1, timeout=0.005)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["error_counts"], {"TIMEOUT": 1})

    async def test_undrained_work_stops_more_admission(self):
        class Undrained:
            async def run(self, scenario, client, row):
                row["cleanup_ok"] = False
                raise OperationError("TIMEOUT")

        result = await group(Undrained(), "S3", 1, requests=5)
        self.assertEqual(result["attempted"], 1)
        self.assertTrue(result["undrained_tutor"])

    async def test_tutor_failure_is_not_http_200_success_and_no_retries(self):
        calls = []

        def handler(request):
            calls.append(request.method)
            if request.method == "POST":
                data = {"session": {"session_id": "s1"}}
            else:
                data = {
                    "turns": [
                        {
                            "client_turn_id": "r1",
                            "status": "failed",
                            "error_code": "TUTOR_BUDGET_EXHAUSTED",
                            "model_calls": 1,
                        }
                    ]
                }
            return httpx.Response(200, json={"code": "0", "data": data})

        row = {"http_requests": 0, "request_id": "r1", "polls": 0}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(OperationError, "TUTOR_BUDGET_EXHAUSTED"):
                await paths().run("S3", client, row)
        self.assertEqual(calls, ["POST", "POST", "GET"])
        self.assertEqual(row["turn_status"], "failed")
        self.assertIn("turn_latency_ms", row)
        self.assertNotIn("cleanup_ms", row)

    async def test_cleanup_time_is_separate_from_business_timeout(self):
        class Cleanup:
            async def run(self, scenario, client, row):
                row["cleanup_ms"] = 20
                await asyncio.sleep(0.03)
                raise OperationError("TIMEOUT")

        raw = __import__("io").StringIO()
        await group(Cleanup(), "S3", 1, requests=1, raw=raw)
        row = json.loads(raw.getvalue())
        self.assertAlmostEqual(row["wall_latency_ms"] - row["latency_ms"], 20, places=3)


class Isolation(unittest.TestCase):
    def test_deterministic_guard_denies_ip_and_service_processes(self):
        import socket
        from types import SimpleNamespace

        from deterministic_tests import guard

        with self.assertRaisesRegex(RuntimeError, "IP sockets"):
            guard(
                "socket.bind",
                (SimpleNamespace(family=socket.AF_INET), ("127.0.0.1", 1)),
            )
        with self.assertRaisesRegex(RuntimeError, "read-only Git"):
            guard(
                "subprocess.Popen", ("docker", ["docker", "compose", "up"], None, None)
            )

    def test_unlimited_v2_mount_root_and_absent_controller(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "cg"
            root.mkdir()
            membership = Path(temp) / "self-cgroup"
            membership.write_text("0::/\n")
            self.assertFalse(cgroup_limits(root, membership)["verified"])
            (root / "cgroup.controllers").write_text("cpu memory")
            self.assertEqual(
                cgroup_limits(root, membership),
                {
                    "verified": True,
                    "cpu_limit": None,
                    "memory_limit": None,
                    "visible_ancestors": ["."],
                },
            )

    def environment(self, directory):
        env = Environment.__new__(Environment)
        env.out = directory
        env.result = {}
        env.children = []
        env.owned = [
            "lecturelens-perf-p0-aaaaaaaaaaaa-infra",
            "lecturelens-perf-p0-aaaaaaaaaaaa-pg",
        ]
        env.compose = lambda project, *args: ["docker", "compose", "-p", project, *args]
        env.capture = Mock(return_value="")
        env.stop = Mock()
        return env

    def test_logs_failure_does_not_suppress_down_or_other_project(self):
        with tempfile.TemporaryDirectory() as temp:
            env = self.environment(Path(temp))
            calls = []

            def run(command, *args):
                calls.append(command)
                if "logs" in command:
                    raise RuntimeError("simulated log failure")

            env.run = run
            env.cleanup()
            self.assertEqual(sum("down" in c for c in calls), 2)
            self.assertEqual(len(env.result["cleanup_log_errors"]), 2)
            self.assertEqual(env.capture.call_count, 6)

    def test_stop_failure_still_tears_down_owned_projects(self):
        with tempfile.TemporaryDirectory() as temp:
            env = self.environment(Path(temp))
            env.children = [(object(), None)]
            env.stop.side_effect = RuntimeError("simulated stop failure")
            env.run = Mock()
            with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                env.cleanup()
            self.assertEqual(
                sum("down" in c.args[0] for c in env.run.call_args_list), 2
            )

    def test_unowned_collision_is_never_cleaned(self):
        with tempfile.TemporaryDirectory() as temp:
            env = self.environment(Path(temp))
            env.owned = []
            env.run = Mock()
            env.cleanup()
            env.run.assert_not_called()
            env.capture.assert_not_called()

    def test_emergency_cleanup_uses_only_journal_and_refuses_copy_or_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            infra, pg = (
                "lecturelens-perf-p0-aaaaaaaaaaaa-infra",
                "lecturelens-perf-p0-aaaaaaaaaaaa-pg",
            )
            result = {
                "projects": [infra, pg],
                "owned_projects": [pg],
                "output_directory": str(directory),
                "repository_root": str(ROOT),
                "config": {"minio_source_build": False},
            }

            def write():
                (directory / "result.json").write_text(json.dumps(result))

            write()
            with (
                patch("cleanup.subprocess.run") as run,
                patch("cleanup.subprocess.check_output", return_value=""),
            ):
                cleanup(directory)
                self.assertEqual(run.call_count, 1)
                self.assertIn(pg, run.call_args.args[0])
                self.assertNotIn(infra, run.call_args.args[0])
            result["output_directory"] = "/other/worktree"
            write()
            with patch("cleanup.subprocess.run") as run, self.assertRaises(ValueError):
                cleanup(directory)
            run.assert_not_called()
            result["output_directory"] = str(directory)
            result["projects"] = [infra, infra]
            write()
            with patch("cleanup.subprocess.run") as run, self.assertRaises(ValueError):
                cleanup(directory)
            run.assert_not_called()

    def test_cgroup_ancestor_limits_and_unknown_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "cg"
            leaf = root / "tenant" / "worker"
            leaf.mkdir(parents=True)
            for folder, cpu in (
                (root, "max 100000"),
                (root / "tenant", "400000 100000"),
                (leaf, "max 100000"),
            ):
                (folder / "cpu.max").write_text(cpu)
                (folder / "memory.max").write_text("max")
            membership = Path(temp) / "membership"
            membership.write_text("0::/tenant/worker\n")
            limits = cgroup_limits(root, membership)
            self.assertEqual(limits["cpu_limit"], 4)
            host = {
                "affinity_cpus": 32,
                "memory_bytes": 128_000_000_000,
                "cgroup_limits": limits,
            }
            with self.assertRaises(RuntimeError):
                require_rental_host(host)
            host["cgroup_limits"] = {"verified": False}
            with self.assertRaises(RuntimeError):
                require_rental_host(host)
            host["cgroup_limits"] = {
                "verified": True,
                "cpu_limit": 16,
                "memory_limit": 64_000_000_000,
            }
            require_rental_host(host)
