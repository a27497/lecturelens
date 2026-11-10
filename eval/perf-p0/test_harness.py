"""Harness mechanics only; these tests are not the real-service smoke evidence."""

import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from load import OperationError, Paths, group, loopback, signed_headers, summary
from perf_app import DelayedMockTutor, HashEmbedding
from run import arguments
from verify import verify


def paths():
    return Paths(
        "http://127.0.0.1:1234",
        "http://127.0.0.1:1235",
        "synthetic-token",
        "a" * 64,
        1,
        "synthetic-course",
        2,
        ["ev-1"],
        poll_seconds=0.001,
    )


class Metrics(unittest.TestCase):
    def test_failure_denominator_and_fast_failures_do_not_hide_success_latency(self):
        rows = [
            {
                "ok": False,
                "latency_ms": 1,
                "error": "RETRIEVAL_BUSY_503",
                "http_status": 503,
                "retry_after": "1",
            },
            {"ok": True, "latency_ms": 200, "http_status": 200},
            {"ok": False, "latency_ms": 60000, "error": "TIMEOUT"},
        ]
        result = summary(rows, 60)
        self.assertEqual(result["error_rate"], 2 / 3)
        self.assertEqual(result["latency_ms"]["all"], {"p50": 200, "p95": 60000})
        self.assertEqual(result["latency_ms"]["success"]["p95"], 200)
        self.assertEqual(result["successful_per_second"], 1 / 60)
        self.assertEqual(result["retrieval_busy_503"], 1)
        self.assertEqual(result["retry_after_counts"], {"1": 1})
        self.assertIsNone(summary([], 0)["error_rate"])
        self.assertIsNone(summary([], 0)["latency_ms"]["all"]["p95"])

    def test_loopback_and_argument_guards(self):
        for url in (
            "https://127.0.0.1",
            "http://example.com",
            "http://127.0.0.1/x",
            "http://a:b@127.0.0.1",
            "http://169.254.169.254",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                loopback(url)
        self.assertEqual(loopback("http://127.0.0.1:8090"), "http://127.0.0.1:8090")
        for extra in (
            ("--seconds", "nan"),
            ("--concurrency", "0"),
            ("--requests", "201"),
            ("--scenarios", "S4"),
            ("--timeout", "inf"),
        ):
            with (
                self.subTest(extra=extra),
                self.assertRaises(SystemExit),
                patch("sys.stderr", new=io.StringIO()),
            ):
                arguments(["--output", "unused", *extra])

    def test_eval_embedding_is_deterministic_nonzero_and_versioned(self):
        model = HashEmbedding()
        self.assertEqual(
            model.embed(["Course evidence"]), model.embed(["Course evidence"])
        )
        self.assertEqual(len(model.embed([""])[0]), 384)
        self.assertGreater(sum(model.embed([""])[0]), 0)
        self.assertTrue(model.index_version.startswith("perf-p0-"))

    def test_mock_delay_is_inside_provider_and_delegates(self):
        marker = object()
        with (
            patch("perf_app.time.sleep") as sleep,
            patch("perf_app.MockTutor.decide", return_value=marker) as delegate,
        ):
            self.assertIs(DelayedMockTutor(75).decide([], [], 1), marker)
            sleep.assert_called_once_with(0.075)
            delegate.assert_called_once_with([], [], 1)


class HttpPaths(unittest.IsolatedAsyncioTestCase):
    async def test_direct_retrieve_signature_and_busy_classification(self):
        def handler(request):
            body = request.content
            expected = signed_headers("a" * 64, body)
            self.assertEqual(
                request.headers["X-LectureLens-Signature"],
                expected["X-LectureLens-Signature"],
            )
            self.assertEqual(json.loads(body)["allowed_evidence_ids"], ["ev-1"])
            return httpx.Response(
                503, json={"detail": "Retrieval busy"}, headers={"Retry-After": "1"}
            )

        row = {"http_requests": 0, "request_id": "synthetic-request"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(OperationError, "RETRIEVAL_BUSY_503"):
                await paths().run("S1", client, row)
        self.assertEqual(row["retry_after"], "1")
        self.assertEqual(row["http_requests"], 1)

    async def test_qa_http200_business_error_is_failure(self):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"code": "RETRIEVAL_UNAVAILABLE"})
            )
        ) as client:
            with self.assertRaisesRegex(OperationError, "RETRIEVAL_UNAVAILABLE"):
                await paths().run("S2", client, {"http_requests": 0})

    async def test_tutor_acceptance_is_not_completion(self):
        reads = 0

        def handler(request):
            nonlocal reads
            if request.method == "POST":
                data = (
                    {"session": {"session_id": "s1"}}
                    if not request.url.path.endswith("/turns")
                    else {"turns": [{"status": "queued"}]}
                )
            else:
                reads += 1
                data = {
                    "turns": [
                        {
                            "client_turn_id": "turn1",
                            "status": "queued" if reads == 1 else "completed",
                            "model_calls": 2,
                            "answer": "cited text [ev-1]",
                            "citations": [{"evidence_id": "ev-1"}],
                            "outcome": "answered",
                        }
                    ]
                }
            return httpx.Response(200, json={"code": "0", "data": data})

        row = {"http_requests": 0, "polls": 0, "request_id": "turn1"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await paths().run("S3", client, row)
        self.assertEqual(reads, 2)
        self.assertEqual(row["turn_status"], "completed")
        self.assertEqual(row["model_calls"], 2)

    async def test_tutor_timeout_cancels_own_work_before_return(self):
        cancelled = False

        def handler(request):
            nonlocal cancelled
            if request.url.path.endswith("/cancel"):
                cancelled = True
            data = {
                "session": {"session_id": "s1"},
                "turns": [
                    {
                        "client_turn_id": "turn1",
                        "status": "cancelled" if cancelled else "queued",
                    }
                ],
            }
            return httpx.Response(200, json={"code": "0", "data": data})

        row = {"http_requests": 0, "polls": 0, "request_id": "turn1"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(TimeoutError):
                async with asyncio.timeout(0.015):
                    await paths().run("S3", client, row)
        self.assertTrue(cancelled)
        self.assertTrue(row["cleanup_ok"])
        self.assertEqual(row["cleanup_http_requests"], 2)

    async def test_closed_loop_exact_request_cap_and_raw_output(self):
        class FakePaths:
            active = 0
            maximum = 0

            async def run(self, scenario, client, row):
                self.active += 1
                self.maximum = max(self.maximum, self.active)
                await asyncio.sleep(0.001)
                self.active -= 1
                row["http_status"] = 200

        fake = FakePaths()
        raw = io.StringIO()
        result = await group(fake, "S1", 4, requests=13, raw=raw)
        self.assertEqual(result["attempted"], 13)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(fake.maximum, 4)
        self.assertEqual(len(raw.getvalue().splitlines()), 13)
        self.assertNotIn("synthetic-token", raw.getvalue())

    async def test_duration_stops_admission_and_drains_in_flight_work(self):
        class SlowPath:
            active = 0

            async def run(self, scenario, client, row):
                self.active += 1
                await asyncio.sleep(0.04)
                self.active -= 1

        fake = SlowPath()
        result = await group(fake, "S1", 2, seconds=0.01)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(fake.active, 0)
        self.assertGreater(result["wall_seconds"], 0.04)


class Provenance(unittest.TestCase):
    def test_verifier_rejects_dirty_source_wrong_sha_and_changed_metrics(self):
        import hashlib

        row = {
            "scenario": "S1",
            "concurrency": 1,
            "warmup": False,
            "request_id": "r1",
            "source_sha": "a" * 40,
            "label": "DEV_SMOKE_NOT_RESUME",
            "ok": True,
            "latency_ms": 10,
            "http_status": 200,
        }
        metrics = summary([row], 1)
        item = dict(
            scenario="S1",
            concurrency=1,
            warmup=False,
            undrained_tutor=False,
            stop={"requests": 1, "admission_seconds": None, "timeout_seconds": 60},
            **metrics,
        )
        source = {"sha": "a" * 40, "source_dirty": False}
        config = {
            "scenarios": ["S1"],
            "concurrency": [1],
            "requests_per_group": 1,
            "admission_seconds": None,
            "operation_timeout_seconds": 60,
        }
        result = {
            "head": "a" * 40,
            "source": source,
            "end_source": source,
            "success": True,
            "valid_clean_source_evidence": True,
            "stages": {"cleanup": {"status": "PASS"}},
            "config": config,
            "config_sha256": hashlib.sha256(
                json.dumps(config, sort_keys=True).encode()
            ).hexdigest(),
            "warmups": [dict(item, warmup=True)],
            "groups": [item],
            "label": "DEV_SMOKE_NOT_RESUME",
        }
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "requests.jsonl").write_text(
                json.dumps(row)
                + "\n"
                + json.dumps(dict(row, warmup=True, request_id="warmup"))
                + "\n"
            )

            def write():
                (directory / "result.json").write_text(json.dumps(result))

            write()
            self.assertEqual(verify(directory, "a" * 40)["status"], "PASS")
            with self.assertRaisesRegex(AssertionError, "SHA"):
                verify(directory, "wrong-sha")
            with self.assertRaisesRegex(AssertionError, "No genuine"):
                verify(directory, "a" * 40, require_busy=True)
            result["source"]["source_dirty"] = True
            write()
            with self.assertRaisesRegex(AssertionError, "Dirty"):
                verify(directory, "a" * 40)
            result["source"]["source_dirty"] = False
            item["succeeded"] = 99
            write()
            with self.assertRaisesRegex(AssertionError, "succeeded"):
                verify(directory, "a" * 40)


if __name__ == "__main__":
    unittest.main()
