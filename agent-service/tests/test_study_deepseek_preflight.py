"""Real protocol/parser and PostgreSQL; every model response is synthetic HTTP."""

import json
import uuid

import httpx
import pytest
import test_models
from test_study import Authority

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.models import RegistryProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyStore

registry = test_models.registry


class Course(Authority):
    def __init__(self):
        super().__init__()
        self.searches = []
        self.sources = [
            {
                "evidence_id": f"owned-caption-{i}-" + "x" * 60,
                "text": "算法需要停止条件。计数达到上限时停止，否则继续。例：计数2、上限3，继续。" * 12,
                "start_ms": i * 10000,
                "end_ms": i * 10000 + 1000,
                "source_type": "OCR",
            }
            for i in range(8)
        ]

    def read(self, scope, action="CHECK", **arguments):
        response = super().read(scope, action, **arguments)
        if action == "SEARCH":
            ids = [0, 1, 2, 3, 4, 5] if not self.searches else [0, 1, 2, 3, 4, 6]
            self.searches.append(ids)
        elif action == "WINDOW":
            ids = [4, 6, 7]
        else:
            ids = [
                i
                for i, item in enumerate(self.sources)
                if item["evidence_id"] in arguments.get("evidence_ids", [])
            ]
        return response | {"evidence": [dict(self.sources[i]) for i in ids]}


class Wire:
    def __init__(self, store, scope, *, fault=None):
        self.store, self.scope, self.fault = store, scope, fault
        self.requests = []

    def command(self, operation, **values):
        return self.store.command(StudyCommand(**self.scope, operation=operation, **values), "real")

    def __call__(self, request):
        data = json.loads(request.content)
        assert request.url.host == "api.deepseek.com"
        assert request.headers["authorization"] == "Bearer offline-only-key"
        assert data["thinking"] == {"type": "disabled"}
        assert data["tool_choice"] == "required" and data["parallel_tool_calls"] is False
        assert data["max_tokens"] in (900, 1200)
        assert request.extensions["timeout"]["read"] <= 90
        self.requests.append(data)
        body = json.loads(data["messages"][-1]["content"])
        names = [tool["function"]["name"] for tool in data["tools"]]
        if names == ["assess_study_candidate"]:
            if "fields" not in body:
                assert "candidate" not in body and "learner_answer" not in body
                call = {
                    "name": names[0],
                    "arguments": {
                        "course_fact": "Check a stopping condition",
                        "evidence_ids": ["e1"],
                        "support": "direct",
                        "missing_goal_quote": "",
                        "methods": [
                            {
                                "operation": "Check count against limit",
                                "input": "Count and limit",
                                "output": "Continue or stop",
                                "evidence_id": "e1",
                            }
                        ],
                    },
                }
            else:
                assert data["max_tokens"] == 1200
                call = {
                    "name": names[0],
                    "arguments": {
                        "explanation_checks": [
                            {
                                "id": c["id"],
                                "course_fact": "计数达到上限时停止，否则继续。",
                                "supported": True,
                            }
                            for c in body["explanation_claims"]
                        ],
                        "goal_checks": [
                            {"id": c["id"], "observation": "解释及两道练习均已给出。", "matches": True}
                            for c in body["goal_constraints"]
                        ],
                        "application_method_check": {
                            "operation": "Check count against limit",
                            "output": "Continue or stop",
                            "matches": self.fault != "quality",
                        },
                        **{
                            field["field"]: {
                                "course_fact": "计数达到上限时停止，否则继续。",
                                "issue": "unsupported_question"
                                if self.fault == "quality" and field["field"] == "question_2"
                                else "none",
                                "correction": "使用已观察的方法。"
                                if self.fault == "quality" and field["field"] == "question_2"
                                else "",
                                **(
                                    {
                                        "answer_check": {
                                            "answer": "\n".join(field["answer_points"]),
                                            "matches": True,
                                        }
                                    }
                                    if "answer_points" in field
                                    else {}
                                ),
                            }
                            for field in body["fields"]
                        },
                    },
                }
                if self.fault == "cancel":
                    self.command("CANCEL")
        elif names == ["derive_feedback_basis"]:
            assert "learner_answer" not in body and "candidate" not in body
            assert set(body["question"]) == {"question", "evidence_ids"}
            call = {
                "name": names[0],
                "arguments": {
                    "course_covers_topic": True,
                    "explanation": "计数达到上限时停止，否则继续。",
                    "evidence_ids": [body["evidence"][0]["evidence_id"]],
                },
            }
        elif names == ["review_answer_feedback"]:
            assert request.extensions["timeout"]["read"] <= 20
            call = {
                "name": names[0],
                "arguments": {
                    "checks": [
                        {
                            "index": 0,
                            "source_fact": "达到上限时停止。",
                            "learner_meaning": "计数达到上限，应停止。",
                            "observation_verdict": "accept",
                            "next_step_verdict": "accept",
                            "reason": "回答与课程规则一致。",
                        }
                    ]
                },
            }
        elif "learner_answer" in body:
            if not body["observations"]:
                call = {"name": "read_question_evidence", "arguments": {}}
            else:
                call = {
                    "name": "submit_answer_feedback",
                    "arguments": {
                        "observations": [
                            {
                                "learner_quote": body["learner_answer"],
                                "observation": "计数等于上限时停止，与你的回答一致。",
                                "action": "retain",
                                "evidence_ids": [body["evidence"][0]["evidence_id"]],
                            }
                        ]
                    },
                }
        elif not body["history"]:
            calls = [
                {"name": "search_course_evidence", "arguments": {"query": query, "practice_kind": "general"}}
                for query in ("stopping condition", "check count against limit")
            ]
            return self.response(calls)
        elif len(body["history"]) == 2:
            call = {
                "name": "read_evidence_window",
                "arguments": {"evidence_id": body["evidence"][0]["evidence_id"]},
            }
        else:
            ref = (
                "foreign"
                if self.fault == "citation"
                else body["course_coverage"]["methods"]["m1"]["evidence_id"]
            )
            call = {
                "name": "create_practice_set",
                "arguments": {
                    "title": "停止条件练习",
                    "explanation": "算法需要停止条件。计数达到上限时停止，否则继续。",
                    "evidence_ids": [ref],
                    "concept": {
                        "question": "停止条件有什么作用？",
                        "answer_points": ["判断算法继续还是停止。"],
                        "evidence_ids": [ref],
                    },
                    "application": {
                        "question": "计数为3、上限为3，此时应继续还是停止？",
                        "answer_points": ["计数达到上限，应停止。"],
                        "evidence_ids": [ref],
                    },
                    "method_id": "m1",
                },
            }
        return self.response([call])

    @staticmethod
    def response(calls):
        return httpx.Response(
            200,
            json={
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "id": f"stub-{i}",
                                    "type": "function",
                                    "function": {
                                        "name": call["name"],
                                        "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                                    },
                                }
                                for i, call in enumerate(calls)
                            ]
                        },
                    }
                ],
            },
        )


def environment(registry, monkeypatch, *, fault=None):
    reg, owner = registry
    saved = test_models.save(
        registry,
        connection={
            "name": "Offline DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "offline-only-key",
            "model_ids": ["deepseek-flash", "deepseek-v4-pro"],
        },
    )
    test_models.command(
        registry,
        "ROUTE",
        bindings={
            role: {"connection_id": saved["connection_id"], "model": model}
            for role, model in (("decision", "deepseek-flash"), ("review", "deepseek-v4-pro"))
        },
    )
    store = StudyStore(reg.store.dsn, reg.freeze)
    course = Course()
    runtime = StudyRuntime(store, course, RegistryProvider(reg))
    runtime.initialize()
    scope = {"owner_id": owner, "course_id": "offline-deepseek-" + uuid.uuid4().hex, "revision": 1}
    scope["session_id"] = store.command(
        StudyCommand(**scope, operation="CREATE_SESSION", request_key="session"), "real"
    )["session_id"]
    wire = Wire(store, scope, fault=fault)
    client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(wire), **kwargs)
    )
    return store, course, runtime, scope, wire


def execute(runtime, store, response):
    run = next(row for row in store.candidates() if row["run_id"] == response["run"]["run_id"])
    runtime.execute(run)
    return run


@pytest.mark.parametrize("recover", [False, True])
def test_managed_deepseek_wire_completes_overlapping_searches_then_saved_answer_feedback(
    registry, monkeypatch, recover
):
    monkeypatch.setenv("STUDY_FEEDBACK_ENABLED", "true")
    store, course, runtime, scope, wire = environment(registry, monkeypatch)
    original = store.save_tool
    interrupted = False

    def save(*args, **kwargs):
        nonlocal interrupted
        if recover and not interrupted and args[3] == "create_practice_set":
            interrupted = True
            raise SystemExit("after journaled review before publication")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "save_tool", save)
    response = wire.command("START", request_key="practice", goal="解释停止条件并出两道题")
    if recover:
        with pytest.raises(SystemExit):
            execute(runtime, store, response)
    run = execute(runtime, store, response)
    result = wire.command("READ")
    assert result["run"]["status"] == "succeeded", result["run"]
    assert len(result["artifact"]["questions"]) == 2
    assert (result["run"]["model_calls"], result["run"]["tool_calls"]) == (5, 4)
    assert len(wire.requests) == 5 and result["run"]["reserved_tokens"] <= 64000
    assert len(set(course.searches[0]) & set(course.searches[1])) == 5
    with store.connect() as conn:
        methods = conn.execute(
            "SELECT count(*) AS n FROM study_model_call WHERE run_id=%s AND metadata->>'review_stage'='course_methods_v1'",
            (run["run_id"],),
        ).fetchone()["n"]
        assert methods == 1
    artifact = result["artifact"]["artifact_id"]
    attempt = wire.command(
        "SAVE_ATTEMPT",
        run_id=run["run_id"],
        artifact_id=artifact,
        question_index=1,
        request_key="answer",
        expected_version=0,
        answer_text="计数达到上限，应停止。",
    )["attempt"]
    feedback_response = wire.command(
        "START_FEEDBACK",
        run_id=run["run_id"],
        artifact_id=artifact,
        question_index=1,
        attempt_id=attempt["attempt_id"],
        request_key="feedback",
    )
    feedback_run = execute(runtime, store, feedback_response)
    feedback = wire.command("READ", run_id=feedback_run["run_id"])
    assert feedback["run"]["status"] == "succeeded", feedback["run"]
    assert (feedback["run"]["model_calls"], feedback["run"]["tool_calls"]) == (4, 2)
    assert len(wire.requests) == 9 and feedback["run"]["reserved_tokens"] <= 64000
    assert feedback["feedback"]["attempt_id"] == attempt["attempt_id"]
    assert feedback["feedback"]["content"]["observations"][0]["action"] == "retain"
    restarted = StudyStore(store.dsn, registry[0].freeze)
    restored = restarted.command(
        StudyCommand(**scope, operation="READ", run_id=feedback_run["run_id"]), "real"
    )
    assert restored["feedback"] == feedback["feedback"]
    for row in (result["run"], feedback["run"]):
        assert row["model_selection"]["decision"]["model"] == "deepseek-flash"
        assert row["model_selection"]["review"]["model"] == "deepseek-v4-pro"
    events = wire.command("EVENTS", run_id=feedback_run["run_id"])["events"]
    assert "offline-only-key" not in json.dumps(events) and "计数达到上限，应停止。" not in json.dumps(
        events, ensure_ascii=False
    )
    print(
        "DEEPSEEK_OFFLINE_SMOKE",
        json.dumps(
            {
                "recovery": recover,
                "practice": {
                    k: result["run"][k] for k in ("status", "model_calls", "tool_calls", "reserved_tokens")
                },
                "feedback": {
                    k: feedback["run"][k] for k in ("status", "model_calls", "tool_calls", "reserved_tokens")
                },
                "mock_http_calls": len(wire.requests),
                "paid_calls": 0,
            }
        ),
    )


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("cancel", "cancelled"),
        ("quality", "budget_exceeded"),
        ("citation", "failed"),
        ("budget", "budget_exceeded"),
        ("version", "failed"),
    ],
)
def test_combined_candidate_keeps_failure_fences(registry, monkeypatch, fault, expected):
    store, course, runtime, scope, wire = environment(registry, monkeypatch, fault=fault)
    response = wire.command("START", request_key="practice", goal="解释停止条件并出两道题")
    if fault == "budget":
        with store.connect() as conn:
            conn.execute(
                "UPDATE study_run SET reserved_tokens=64000 WHERE run_id=%s", (response["run"]["run_id"],)
            )
    if fault == "version":
        course.valid = False
    execute(runtime, store, response)
    result = wire.command("READ")
    assert result["run"]["status"] == expected, result["run"]
    assert result["artifact"] is None
    if fault == "budget":
        assert wire.requests == [] and result["run"]["error_code"] == "RUN_BUDGET_EXCEEDED"
    if fault == "citation":
        assert result["run"]["error_code"] == "UNSUPPORTED_CITATION"
    if fault == "version":
        assert result["run"]["error_code"] == "COURSE_UNAVAILABLE_OR_CHANGED"
    if fault == "quality":
        events = wire.command("EVENTS")["events"]
        assert any(e["event_type"] == "quality_checked" and not e["payload"]["accepted"] for e in events)
