"""Synthetic protocol fixtures adapted to current main, never real Provider evidence."""

import json

import httpx
from test_study import Authority

from lecturelens_agent.study.contracts import StudyCommand


class Course(Authority):
    def __init__(self):
        super().__init__()
        self.searches = []
        self.sources = [
            {
                "evidence_id": f"owned-caption-{i}-" + "x" * 60,
                "text": "算法需要停止条件。计数达到上限时停止，否则继续。例：计数2、上限3，继续。" * 2,
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
        return (
            response
            | {"evidence": [dict(self.sources[i]) for i in ids]}
            | ({"learning_scope": scope["learning_scope"]} if scope.get("learning_scope") else {})
        )


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
                for query in ("stopping condition",)
            ]
            return self.response(calls)
        elif len(body["history"]) == 1:
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


def execute(runtime, store, response):
    run = next(row for row in store.candidates() if row["run_id"] == response["run"]["run_id"])
    runtime.execute(run)
    return run
