"""Step 6 lane adaptation (schema v3): in-memory fakes only, no service or socket."""

import asyncio
import copy
import hashlib
import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import perf_app
import run
from fastapi import FastAPI
from lecturelens_agent.contracts import RetrieveRequest
from lecturelens_agent.retrieval import (
    DEFAULT_QUERY_CONCURRENCY,
    MAX_QUERY_CONCURRENCY,
    BusyError,
    IndexNotReady,
)
from lecturelens_agent.store import StaleSync
from lecturelens_agent.study.runtime import DEFAULT_RUN_CONCURRENCY, MAX_RUN_CONCURRENCY
from load import (
    OUTCOME_KEYS,
    OperationError,
    Paths,
    failure_class,
    group,
    outcome_delta,
    summary,
)
from test_harness import paths
from verify import verify

SHA = "a" * 40
LABEL = "DEV_SMOKE_NOT_RESUME"
ZERO = dict.fromkeys(OUTCOME_KEYS, 0)


def java(data):
    return httpx.Response(200, json={"code": "0", "data": data})


class FailureClasses(unittest.IsolatedAsyncioTestCase):
    def test_three_classes_are_counted_separately_and_partition_failures(self):
        rows = [
            {"ok": True, "latency_ms": 5},
            {"ok": False, "latency_ms": 1, "error": "RETRIEVAL_BUSY_503"},
            {"ok": False, "latency_ms": 1, "error": "RETRIEVAL_BUSY_503"},
            {"ok": False, "latency_ms": 2, "error": "RETRIEVAL_INDEX_CHANGED_409"},
            {"ok": False, "latency_ms": 3, "error": "RETRIEVAL_HTTP_409"},
            {
                "ok": False,
                "latency_ms": 4,
                "error": "JAVA_HTTP_503_CODE_RETRIEVAL_UNAVAILABLE",
            },
            {"ok": False, "latency_ms": 60000, "error": "TIMEOUT"},
        ]
        result = summary(rows, 1, schema=3)
        self.assertEqual(
            result["failure_classes"],
            {
                "retrieval_busy_503": 2,
                "evidence_index_changed_409": 1,
                "other_unexpected": 3,
            },
        )
        self.assertEqual(sum(result["failure_classes"].values()), result["failed"])
        # The denominator rule is unchanged: every class is a failed attempt.
        self.assertEqual(result["error_rate"], 6 / 7)
        self.assertEqual(result["retrieval_busy_503"], 2)
        self.assertNotIn("failure_classes", summary(rows, 1, schema=2))

    async def test_direct_409_changed_is_distinct_from_not_ready_and_busy(self):
        cases = [
            (409, "Evidence index changed", "1", "RETRIEVAL_INDEX_CHANGED_409"),
            (409, "Evidence index not ready", "3", "RETRIEVAL_HTTP_409"),
            (503, "Retrieval busy", "1", "RETRIEVAL_BUSY_503"),
            (503, "Retrieval unavailable", None, "RETRIEVAL_HTTP_503"),
        ]
        for status, detail, retry, expected in cases:
            with self.subTest(detail=detail):
                headers = {"Retry-After": retry} if retry else {}
                response = httpx.Response(
                    status, json={"detail": detail}, headers=headers
                )
                row = {"http_requests": 0, "request_id": "r1"}
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda _, r=response: r)
                ) as client:
                    with self.assertRaisesRegex(OperationError, f"^{expected}$"):
                        await paths().run("S1", client, row)
                self.assertEqual(row["retry_after"], retry)

    async def test_group_rows_and_result_carry_the_classes(self):
        errors = iter(
            ["RETRIEVAL_BUSY_503", "RETRIEVAL_INDEX_CHANGED_409", "JAVA_HTTP_503", None]
        )

        class Fake:
            async def run(self, scenario, client, row):
                error = next(errors)
                if error:
                    raise OperationError(error)

        raw = io.StringIO()
        result = await group(Fake(), "S1", 1, requests=4, raw=raw)
        rows = [json.loads(line) for line in raw.getvalue().splitlines()]
        self.assertEqual(
            [r.get("failure_class") for r in rows],
            [
                "retrieval_busy_503",
                "evidence_index_changed_409",
                "other_unexpected",
                None,
            ],
        )
        self.assertEqual(result["schema_version"], 3)
        self.assertEqual(
            result["failure_classes"],
            {
                "retrieval_busy_503": 1,
                "evidence_index_changed_409": 1,
                "other_unexpected": 1,
            },
        )
        self.assertEqual(failure_class("TIMEOUT"), "other_unexpected")


class LaneParameters(unittest.TestCase):
    def test_defaults_are_the_product_defaults_and_ranges_are_product_ranges(self):
        args = run.arguments(["--output", "unused"])
        self.assertEqual(args.retrieval_concurrency, DEFAULT_QUERY_CONCURRENCY)
        self.assertEqual(args.run_concurrency, DEFAULT_RUN_CONCURRENCY)
        self.assertEqual((DEFAULT_QUERY_CONCURRENCY, DEFAULT_RUN_CONCURRENCY), (4, 2))
        for flag, value in (
            ("--retrieval-concurrency", "0"),
            ("--retrieval-concurrency", str(MAX_QUERY_CONCURRENCY + 1)),
            ("--run-concurrency", "0"),
            ("--run-concurrency", str(MAX_RUN_CONCURRENCY + 1)),
        ):
            with (
                self.subTest(flag=flag, value=value),
                self.assertRaises(SystemExit),
                patch("sys.stderr", new=io.StringIO()),
            ):
                run.arguments(["--output", "unused", flag, value])

    def test_point_parameters_are_recorded_in_fingerprinted_metadata(self):
        args = run.arguments(
            [
                "--output",
                "unused",
                "--scenarios",
                "S4",
                "--retrieval-concurrency",
                "8",
                "--run-concurrency",
                "4",
            ]
        )
        config = run.config(args)
        self.assertEqual(config["agent_retrieval_concurrency"], 8)
        self.assertEqual(config["agent_run_concurrency"], 4)
        self.assertEqual(config["scenarios"], ["S4"])
        self.assertNotIn("retriever_lock", config)
        self.assertIn("503 Retrieval busy", config["retrieval_admission"])
        self.assertIn("409 Evidence index changed", config["retrieval_admission"])
        self.assertIn(
            "not governed by AGENT_RUN_CONCURRENCY", config["tutor_worker_model"]
        )
        other = run.config(run.arguments(["--output", "unused", "--scenarios", "S4"]))
        self.assertNotEqual(
            hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(other, sort_keys=True).encode()).hexdigest(),
        )

    def test_each_point_passes_its_lanes_to_the_agent_process_environment(self):
        for retrieval, lanes in ((4, 2), (8, 2), (4, 4), (1, 1)):
            with self.subTest(retrieval=retrieval, lanes=lanes):
                env = run.Environment.__new__(run.Environment)
                env.options = run.arguments(
                    [
                        "--output",
                        "unused",
                        "--allow-dirty",
                        "--retrieval-concurrency",
                        str(retrieval),
                        "--run-concurrency",
                        str(lanes),
                    ]
                )
                env.env = {"PYTHONPATH": ""}
                env.result = {"not_run": []}
                with (
                    patch.object(run.existing.Smoke, "preflight"),
                    # Host inventory spawns uname; it is covered by the rental guard tests.
                    patch("run.machine", return_value={}),
                ):
                    env.preflight()
                self.assertEqual(env.env["AGENT_RETRIEVAL_CONCURRENCY"], str(retrieval))
                self.assertEqual(env.env["AGENT_RUN_CONCURRENCY"], str(lanes))
                self.assertEqual(
                    env.result["config"]["agent_retrieval_concurrency"], retrieval
                )
                self.assertEqual(env.result["config"]["agent_run_concurrency"], lanes)

    def factory(self, environ):
        base = {
            "AGENT_LLM_MODE": "mock",
            "PERF_MOCK_MODEL_DELAY_MS": "0",
            "AGENT_DATABASE_URL": "postgresql://unused",
            "AGENT_SERVICE_SECRET": "s" * 64,
            "AGENT_JAVA_BASE_URL": "http://127.0.0.1:1",
        }
        captured = {}

        def product(**kwargs):
            captured.update(kwargs)
            return FastAPI()

        with (
            patch.dict("os.environ", {**base, **environ}, clear=True),
            patch("perf_app.VectorStore"),
            patch("perf_app.ModelRegistry"),
            patch("perf_app.product_app", side_effect=product),
            self.assertLogs("perf-p0", logging.WARNING) as logs,
        ):
            perf_app.create_app()
        return captured, "\n".join(logs.output)

    def test_agent_factory_builds_the_requested_lanes_and_logs_them(self):
        captured, logs = self.factory(
            {"AGENT_RETRIEVAL_CONCURRENCY": "8", "AGENT_RUN_CONCURRENCY": "4"}
        )
        self.assertEqual(captured["retriever"].query_concurrency, 8)
        self.assertEqual(captured["study_runtime"].concurrency, 4)
        self.assertIsInstance(captured["retriever"], perf_app.CountingRetriever)
        self.assertIsInstance(
            captured["study_runtime"].provider, perf_app.DelayedStudyMock
        )
        self.assertEqual(
            run.effective_lanes(logs),
            {"agent_retrieval_concurrency": 8, "agent_run_concurrency": 4},
        )
        captured, logs = self.factory({})
        self.assertEqual(captured["retriever"].query_concurrency, 4)
        self.assertEqual(captured["study_runtime"].concurrency, 2)

    def test_agent_factory_rejects_out_of_range_lanes_like_the_product(self):
        for name, value in (
            ("AGENT_RETRIEVAL_CONCURRENCY", "17"),
            ("AGENT_RUN_CONCURRENCY", "9"),
            ("AGENT_RUN_CONCURRENCY", "two"),
        ):
            with self.subTest(name=name, value=value), self.assertRaises(RuntimeError):
                self.factory({name: value})

    def test_lane_log_must_appear_exactly_once(self):
        line = "PERF_FACTORY hash384; retrieval_concurrency=4; run_concurrency=2; x"
        self.assertEqual(
            run.effective_lanes("noise\n" + line),
            {"agent_retrieval_concurrency": 4, "agent_run_concurrency": 2},
        )
        for text in ("", line + "\n" + line):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                run.effective_lanes(text)

    def test_study_delay_is_inside_the_provider_and_delegates(self):
        marker = object()
        with (
            patch("perf_app.time.sleep") as sleep,
            patch("perf_app.MockProvider.flashcards", return_value=marker) as delegate,
        ):
            self.assertIs(perf_app.DelayedStudyMock(150).flashcards([], [], 1), marker)
            sleep.assert_called_once_with(0.15)
            delegate.assert_called_once_with([], [], 1)
        with self.assertRaises(ValueError):
            perf_app.DelayedStudyMock(5001)


class ServerOutcomes(unittest.IsolatedAsyncioTestCase):
    def request(self):
        return RetrieveRequest(
            request_id="r1",
            owner_id=1,
            course_id="c1",
            revision=2,
            query="pipeline",
            allowed_evidence_ids=["ev-1"],
        )

    def retriever(self, *, ready=True, stale=False, slots=1):
        class Store:
            def ready_snapshot(self, request, version):
                return "snap-1" if ready else None

            def search(self, key, request, version, vector):
                if stale:
                    raise StaleSync("Index changed during retrieval")
                return []

        return perf_app.CountingRetriever(
            Store(), perf_app.HashEmbedding(), query_concurrency=slots
        )

    def test_search_outcomes_are_counted_without_changing_admission(self):
        ok = self.retriever()
        ok.search(self.request())
        busy = self.retriever()
        busy.query_slots.acquire()
        with self.assertRaises(BusyError):
            busy.search(self.request())
        changed = self.retriever(stale=True)
        with self.assertRaises(StaleSync):
            changed.search(self.request())
        missing = self.retriever(ready=False)
        with self.assertRaises(IndexNotReady):
            missing.search(self.request())
        self.assertEqual(ok.outcomes(), {**ZERO, "ok": 1})
        self.assertEqual(busy.outcomes(), {**ZERO, "busy_503": 1})
        self.assertEqual(changed.outcomes(), {**ZERO, "index_changed_409": 1})
        self.assertEqual(missing.outcomes(), {**ZERO, "index_not_ready_409": 1})
        # The slot taken by a rejected attempt is never released by the wrapper.
        self.assertFalse(busy.query_slots.acquire(blocking=False))

    async def test_signed_counter_route_round_trip_and_rejection(self):
        retriever = self.retriever()
        retriever.search(self.request())
        app = FastAPI()
        app.state.secret = "a" * 64
        perf_app.add_outcome_route(app, retriever)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:1235"
        ) as client:
            self.assertEqual(
                await paths().retrieval_outcomes(client), {**ZERO, "ok": 1}
            )
            forged = Paths(
                "http://127.0.0.1:1234",
                "http://127.0.0.1:1235",
                "t",
                "b" * 64,
                1,
                "c",
                2,
                ["ev-1"],
            )
            with self.assertRaises(httpx.HTTPStatusError):
                await forged.retrieval_outcomes(client)

    def test_outcome_delta_is_per_group_and_monotonic(self):
        before = {**ZERO, "ok": 3, "busy_503": 1}
        after = {**ZERO, "ok": 10, "busy_503": 4, "index_changed_409": 1}
        self.assertEqual(
            outcome_delta(before, after),
            {**ZERO, "ok": 7, "busy_503": 3, "index_changed_409": 1},
        )
        with self.assertRaises(ValueError):
            outcome_delta(after, before)
        with self.assertRaises(ValueError):
            outcome_delta(before, {**after, "extra": 0})


class QueueAndExecution(unittest.IsolatedAsyncioTestCase):
    async def run_with_clock(self, scenario, handler, request_id="r1"):
        clock = [0.0]
        row = {"http_requests": 0, "polls": 0, "request_id": request_id}

        def timed(request):
            clock[0] += 1
            return handler(request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(timed)) as client:
            with patch("load.time.perf_counter", side_effect=lambda: clock[0]):
                try:
                    await paths().run(scenario, client, row)
                except OperationError as error:
                    row["error"] = str(error)
        return row

    async def test_tutor_turn_splits_queue_and_execution(self):
        states = iter(["queued", "queued", "running", "running", "completed"])

        def handler(request):
            if request.url.path.endswith("/sessions"):
                return java({"session": {"session_id": "s1"}})
            if request.method == "POST":
                return java({"turns": []})
            return java(
                {
                    "turns": [
                        {
                            "client_turn_id": "r1",
                            "status": next(states),
                            "model_calls": 2,
                            "outcome": "answered",
                            "answer": "text [ev-1]",
                            "citations": [{"evidence_id": "ev-1"}],
                        }
                    ]
                }
            )

        row = await self.run_with_clock("S3", handler)
        self.assertNotIn("error", row)
        # Clock ticks once per HTTP response: submit at t=1, first running poll at
        # t=5, completed poll at t=7.
        self.assertTrue(row["running_observed"])
        self.assertEqual(row["queue_ms"], 4000)
        self.assertEqual(row["execution_ms"], 2000)
        self.assertLessEqual(
            row["queue_ms"] + row["execution_ms"], row["turn_latency_ms"]
        )

    async def test_unobserved_running_state_is_not_invented(self):
        def handler(request):
            if request.url.path.endswith("/sessions"):
                return java({"session": {"session_id": "s1"}})
            if request.method == "POST":
                return java({"turns": []})
            return java(
                {
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
            )

        row = await self.run_with_clock("S3", handler)
        self.assertIs(row["running_observed"], False)
        self.assertNotIn("queue_ms", row)
        result = summary([dict(row, ok=True, latency_ms=1)], 1, schema=3)
        self.assertEqual(result["running_unobserved"], 1)
        self.assertEqual(result["queue_ms"], {"p50": None, "p95": None})

    def study_handler(self, statuses, *, deck=True, error_code=None):
        states = iter(statuses)
        sent = []
        cancelled = []

        def handler(request):
            body = json.loads(request.content)
            sent.append(body["operation"])
            self.assertTrue(request.url.path.endswith("/study/command"))
            if body["operation"] == "CREATE_SESSION":
                self.assertEqual(body["request_key"], "r1")
                return java({"session_id": "s1", "revision": 2, "mode": "mock"})
            if body["operation"] == "GENERATE_CARDS":
                self.assertEqual(body["session_id"], "s1")
                return java({"run": {"run_id": "run-1", "status": "queued"}})
            if body["operation"] == "EVENTS":
                events = [{"event_type": "run_finished", "payload": {}}]
                if deck:
                    events.append(
                        {"event_type": "deck_created", "payload": {"card_count": 1}}
                    )
                return java({"events": events, "status": "succeeded"})
            if body["operation"] == "CANCEL":
                cancelled.append(True)
            status = "cancelled" if cancelled else next(states, statuses[-1])
            return java(
                {
                    "run": {
                        "run_id": "run-1",
                        "status": status,
                        "model_calls": 2,
                        "error_code": error_code,
                    }
                }
            )

        return handler, sent

    async def test_study_run_splits_lane_queue_and_execution_and_needs_a_deck(self):
        handler, sent = self.study_handler(["queued", "queued", "running", "succeeded"])
        row = await self.run_with_clock("S4", handler)
        self.assertNotIn("error", row)
        self.assertEqual(row["run_status"], "succeeded")
        # Submit at t=1, first running READ at t=5, succeeded READ at t=6.
        self.assertEqual(row["queue_ms"], 4000)
        self.assertEqual(row["execution_ms"], 1000)
        self.assertEqual(
            sent,
            [
                "CREATE_SESSION",
                "GENERATE_CARDS",
                "READ",
                "READ",
                "READ",
                "READ",
                "EVENTS",
            ],
        )
        handler, _ = self.study_handler(["running", "succeeded"], deck=False)
        row = await self.run_with_clock("S4", handler)
        self.assertEqual(row["error"], "STUDY_MISSING_DECK")
        handler, _ = self.study_handler(
            ["running", "failed"], error_code="STUDY_EXECUTION_FAILED"
        )
        row = await self.run_with_clock("S4", handler)
        self.assertEqual(row["error"], "STUDY_STUDY_EXECUTION_FAILED")
        self.assertNotIn("cleanup_ms", row)

    async def test_study_timeout_cancels_its_own_run(self):
        handler, sent = self.study_handler(["queued"])
        row = {"http_requests": 0, "polls": 0, "request_id": "r1"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(TimeoutError):
                async with asyncio.timeout(0.02):
                    await paths().run("S4", client, row)
        self.assertIn("CANCEL", sent)
        self.assertTrue(row["cleanup_ok"])
        self.assertEqual(row["cleanup_http_requests"], 2)

    async def test_lost_submit_response_is_hidden_backlog(self):
        def handler(request):
            body = json.loads(request.content)
            if body["operation"] == "CREATE_SESSION":
                return java({"session_id": "s1"})
            raise httpx.ReadTimeout("lost", request=request)

        row = {"http_requests": 0, "polls": 0, "request_id": "r1"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(httpx.ReadTimeout):
                await paths().run("S4", client, row)
        self.assertIs(row["cleanup_ok"], False)

    async def test_rejected_submit_has_nothing_to_drain(self):
        def handler(request):
            body = json.loads(request.content)
            if body["operation"] == "CREATE_SESSION":
                return java({"session_id": "s1"})
            return httpx.Response(409, json={"code": "SESSION_BUSY"})

        row = {"http_requests": 0, "polls": 0, "request_id": "r1"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(OperationError, "SESSION_BUSY"):
                await paths().run("S4", client, row)
        self.assertNotIn("cleanup_ok", row)


def v3_bundle(directory, *, retrieval=4, run_lanes=2, levels=(1,)):
    config = {
        "scenarios": ["S1", "S4"],
        "concurrency": list(levels),
        "requests_per_group": 1,
        "admission_seconds": None,
        "operation_timeout_seconds": 1,
        "agent_retrieval_concurrency": retrieval,
        "agent_run_concurrency": run_lanes,
    }
    rows, warmups, groups = [], [], []
    for scenario in ("S1", "S4"):
        for warmup, concurrency in [(True, 1)] + [(False, c) for c in levels]:
            row = {
                "scenario": scenario,
                "concurrency": concurrency,
                "warmup": warmup,
                "request_id": f"{scenario}-{warmup}-{concurrency}",
                "ok": True,
                "latency_ms": 10,
                "wall_latency_ms": 10,
                "start_offset_ms": 0,
                "finish_offset_ms": 10,
                "http_status": 200,
                "http_requests": 1,
                "http_response_status_counts": {"200": 1},
                "schema_version": 3,
                "source_sha": SHA,
                "label": LABEL,
            }
            if scenario == "S4":
                row.update(
                    run_status="succeeded",
                    turn_latency_ms=9,
                    running_observed=True,
                    queue_ms=4,
                    execution_ms=5,
                )
            rows.append(row)
            (warmups if warmup else groups).append(
                dict(
                    scenario=scenario,
                    concurrency=concurrency,
                    warmup=warmup,
                    schema_version=3,
                    undrained_tutor=False,
                    stop={
                        "requests": 1,
                        "admission_seconds": None,
                        "timeout_seconds": 1,
                    },
                    agent_retrieval_outcomes={**ZERO, "ok": 1},
                    **summary([row], 0.1, schema=3),
                )
            )
    source = {"sha": SHA, "source_dirty": False}
    result = {
        "schema_version": 3,
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
        "effective_agent_lanes": {
            "agent_retrieval_concurrency": retrieval,
            "agent_run_concurrency": run_lanes,
        },
        "warmups": warmups,
        "groups": groups,
        "label": LABEL,
    }
    write(directory, result, rows)
    return result, rows


def write(directory, result, rows):
    result["config_sha256"] = hashlib.sha256(
        json.dumps(result["config"], sort_keys=True).encode()
    ).hexdigest()
    (directory / "result.json").write_text(json.dumps(result))
    (directory / "requests.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows)
    )


class VerifyV3(unittest.TestCase):
    def test_valid_v3_bundle_and_mutations(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            original, raw = v3_bundle(directory)
            self.assertEqual(verify(directory, SHA)["schema_version"], 3)

            def fail_busy(result, rows):
                rows[1].update(
                    ok=False,
                    error="RETRIEVAL_BUSY_503",
                    failure_class="retrieval_busy_503",
                    http_status=503,
                )
                result["groups"][0].update(summary([rows[1]], 0.1, schema=3))

            mutations = {
                "class_mismatch": lambda r, rows: (
                    fail_busy(r, rows),
                    rows[1].update(failure_class="other_unexpected"),
                ),
                "class_counts": lambda r, rows: r["groups"][0][
                    "failure_classes"
                ].update(other_unexpected=1),
                "lanes_drift": lambda r, rows: r["effective_agent_lanes"].update(
                    agent_run_concurrency=4
                ),
                "lanes_missing": lambda r, rows: r.pop("effective_agent_lanes"),
                "retrieval_range": lambda r, rows: (
                    r["config"].update(agent_retrieval_concurrency=17),
                    r["effective_agent_lanes"].update(agent_retrieval_concurrency=17),
                ),
                "run_range": lambda r, rows: (
                    r["config"].update(agent_run_concurrency=0),
                    r["effective_agent_lanes"].update(agent_run_concurrency=0),
                ),
                "split_exceeds_turn": lambda r, rows: rows[3].update(queue_ms=100),
                "split_unobserved": lambda r, rows: rows[3].update(
                    running_observed=False
                ),
                "queue_metric": lambda r, rows: r["groups"][1]["queue_ms"].update(
                    p95=1
                ),
                "study_not_succeeded": lambda r, rows: rows[3].update(
                    run_status="failed"
                ),
                "server_outcomes_missing": lambda r, rows: r["groups"][0].pop(
                    "agent_retrieval_outcomes"
                ),
                "server_outcomes_negative": lambda r, rows: r["groups"][0][
                    "agent_retrieval_outcomes"
                ].update(busy_503=-1),
                "changed_not_direct": lambda r, rows: rows[3].update(
                    ok=False, error="RETRIEVAL_INDEX_CHANGED_409", http_status=409
                ),
                "row_schema": lambda r, rows: rows[1].update(schema_version=2),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    result, rows = copy.deepcopy(original), copy.deepcopy(raw)
                    mutate(result, rows)
                    write(directory, result, rows)
                    with self.assertRaises(AssertionError):
                        verify(directory, SHA)

    def test_require_busy_needs_more_direct_concurrency_than_slots(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            v3_bundle(directory, retrieval=4, levels=(1, 4))
            with self.assertRaisesRegex(AssertionError, "cannot exceed"):
                verify(directory, SHA, require_busy=True)
            v3_bundle(directory, retrieval=4, levels=(1, 8))
            with self.assertRaisesRegex(AssertionError, "No genuine"):
                verify(directory, SHA, require_busy=True)


class ReportV3(unittest.TestCase):
    def test_report_shows_classes_server_counts_and_split(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result, _ = v3_bundle(directory)
            env = run.Environment.__new__(run.Environment)
            env.out = directory
            env.result = {**result, "not_run": ["rental-machine full baseline"]}
            env.report()
            text = (directory / "REPORT.md").read_text()
            self.assertIn("Changed 409", text)
            self.assertIn("Server busy/changed", text)
            self.assertIn("| S4 | 1 | 1 | 0 | 0 | 0 | 0 | 0/0 |", text)
            self.assertIn("| 4/4 | 5/5 |", text)
            self.assertIn("agent_run_concurrency': 2", text)


if __name__ == "__main__":
    unittest.main()
