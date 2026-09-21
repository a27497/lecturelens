import json

import httpx
import pytest

from lecturelens_agent.study.contracts import tool_schemas
from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.store import BudgetExceeded, StudyError


def test_compacted_tool_schema_preserves_every_required_business_field():
    def check(value):
        if isinstance(value, dict):
            if "required" in value:
                assert set(value["required"]) <= set(value["properties"])
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    for tool in tool_schemas():
        check(tool["function"]["parameters"])
        if tool["function"]["name"] == "create_practice_set":
            assert tool["function"]["parameters"]["properties"]["title"]["type"] == "string"


def test_standard_chat_tool_protocol_accepts_bounded_batches(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("AGENT_LLM_MODEL", "test-model")
    monkeypatch.setenv("AGENT_LLM_API_KEY", "test-only-key")
    recorded = []

    def handler(request):
        recorded.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": str(i),
                                    "type": "function",
                                    "function": {
                                        "name": "read_evidence_window",
                                        "arguments": json.dumps({"evidence_id": f"e{i}"}),
                                    },
                                }
                                for i in range(2)
                            ]
                        }
                    }
                ]
            },
        )

    client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)
    )
    result = ChatProvider().decide([{"role": "tool", "tool_call_id": "prior", "content": "test"}], 10)
    assert len(result["calls"]) == 2
    assert recorded[0]["tool_choice"] == "required"
    assert recorded[0]["parallel_tool_calls"] is False
    assert {tool["function"]["name"] for tool in recorded[0]["tools"]} == {
        "search_course_evidence",
        "read_evidence_window",
        "check_python_example",
        "create_practice_set",
        "create_python_practice",
        "create_interval_practice",
        "report_insufficient_evidence",
    }


def test_first_model_decision_exposes_only_search(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("AGENT_LLM_MODEL", "test-model")

    def handler(request):
        payload = json.loads(request.content)
        assert [tool["function"]["name"] for tool in payload["tools"]] == ["search_course_evidence"]
        assert "start_ms" not in payload["tools"][0]["function"]["parameters"]["properties"]
        assert payload["max_tokens"] == 900
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "search_course_evidence",
                                        "arguments": '{"query":"topic"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)
    )
    assert (
        ChatProvider().decide([{"role": "user", "content": "test"}], 10)["calls"][0]["name"]
        == "search_course_evidence"
    )


@pytest.mark.parametrize("count", [0, 4])
def test_unbounded_or_missing_tool_calls_are_rejected(monkeypatch, count):
    monkeypatch.setenv("AGENT_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("AGENT_LLM_MODEL", "test-model")
    client = httpx.Client
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"choices": [{"message": {"tool_calls": [{"type": "function"}] * count}}]}
        )
    )
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client(transport=transport, **kwargs))
    with pytest.raises(StudyError, match="MODEL_TOOL_CONTRACT"):
        ChatProvider().decide([], 10)


@pytest.mark.parametrize("elapsed,expected", [(5, StudyError), (11, BudgetExceeded)])
def test_provider_timeout_preserves_run_deadline_classification(monkeypatch, elapsed, expected):
    monkeypatch.setenv("AGENT_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("AGENT_LLM_MODEL", "test-model")
    now = [0]
    monkeypatch.setattr("lecturelens_agent.study.provider.time.monotonic", lambda: now[0])

    def handler(request):
        assert request.extensions["timeout"]["read"] == 10
        now[0] = elapsed
        raise httpx.ReadTimeout("test timeout", request=request)

    client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)
    )
    with pytest.raises(expected):
        ChatProvider().decide([], 10)


@pytest.mark.parametrize("tool_name", ["assess_study_candidate", "create_practice_set"])
def test_review_uses_isolated_tool_contract_and_accepts_null_usage(monkeypatch, tool_name):
    from test_study_quality import accepted_verdict, review_input

    messages = [{"role": "user", "content": json.dumps(review_input())}]
    monkeypatch.setenv("AGENT_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("AGENT_LLM_MODEL", "test-model")

    def handler(request):
        payload = json.loads(request.content)
        assert [t["function"]["name"] for t in payload["tools"]] == ["assess_study_candidate"]
        assert payload["max_tokens"] == 300
        return httpx.Response(
            200,
            json={
                "usage": None,
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(accepted_verdict()),
                                    },
                                }
                            ]
                        }
                    }
                ],
            },
        )

    client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)
    )
    if tool_name == "assess_study_candidate":
        result = ChatProvider().review(messages, 10)
        assert result["usage"] == {} and result["review"]["issues"] == []
        assert result["review"]["feedback"] == "OK"
        assert result["review"]["grounds"] == {} and result["review"]["rubric_observations"] == []
        assert len(result["review"]["answer_observations"]) == 2
    else:
        with pytest.raises(StudyError, match="MODEL_TOOL_CONTRACT"):
            ChatProvider().review(messages, 10)


@pytest.mark.parametrize("model", ["qwen-plus", "qwen3-max", "qwen-flash"])
def test_bailian_routes_single_tool_and_multi_tool_without_required(monkeypatch, model):
    recorded = []

    def handler(request):
        payload = json.loads(request.content)
        recorded.append(payload)
        name = payload["tools"][0]["function"]["name"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {"name": name, "arguments": '{"query":"函数返回值"}'},
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)
    )
    provider = ChatProvider("https://dashscope.aliyuncs.com/compatible-mode/v1", model, "not-a-real-key")
    provider.decide([{"role": "user", "content": '{"goal":"解释函数"}'}], 10)
    history = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c0",
                    "type": "function",
                    "function": {"name": "search_course_evidence", "arguments": '{"query":"函数"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c0", "content": "课程资料"},
    ]
    provider.decide(history, 10)
    assert all(payload["enable_thinking"] is False for payload in recorded)
    assert recorded[0]["tool_choice"] == {"type": "function", "function": {"name": "search_course_evidence"}}
    assert recorded[1]["tool_choice"] == "auto"
    assert recorded[1]["messages"] == history


@pytest.mark.parametrize(
    "url,model,expected",
    [
        ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", True),
        ("https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-max", True),
        ("https://my-workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", "qwen-plus", True),
        ("https://dashscope.aliyuncs.com.evil.example/compatible-mode/v1", "qwen-plus", False),
        ("https://api.openrouter.ai/v1", "qwen-plus", False),
        ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwq-plus", False),
        ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3.8-2.4t-a95b", False),
    ],
)
def test_bailian_profile_is_scoped_to_known_non_thinking_capable_models(url, model, expected):
    from lecturelens_agent.study.provider import bailian_nonthinking

    assert bailian_nonthinking(url, model) is expected


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "MODEL_AUTH_FAILED"),
        (403, "MODEL_AUTH_FAILED"),
        (429, "MODEL_RATE_LIMITED"),
        (500, "MODEL_UNAVAILABLE"),
        (400, "MODEL_REQUEST_REJECTED"),
    ],
)
def test_http_failures_are_actionable_and_redacted(monkeypatch, status, code):
    client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, text="secret-provider-message")
            ),
            **kwargs,
        ),
    )
    with pytest.raises(StudyError, match=code) as failure:
        ChatProvider("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", "secret").decide(
            [], 10
        )
    assert "secret" not in str(failure.value)


@pytest.mark.parametrize(
    "choice,code",
    [
        ({"message": {"content": "plain response"}}, "MODEL_TOOL_CONTRACT"),
        ({"finish_reason": "length", "message": {"tool_calls": []}}, "MODEL_OUTPUT_TRUNCATED"),
        (
            {
                "message": {
                    "tool_calls": [
                        {"type": "function", "function": {"name": "search_course_evidence", "arguments": "{"}}
                    ]
                }
            },
            "MODEL_TOOL_CONTRACT",
        ),
        (
            {
                "message": {
                    "tool_calls": [
                        {"type": "function", "function": {"name": "create_practice_set", "arguments": "{}"}}
                    ]
                }
            },
            "MODEL_TOOL_CONTRACT",
        ),
        (
            {
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "search_course_evidence", "arguments": "[]"},
                        }
                    ]
                }
            },
            "MODEL_TOOL_CONTRACT",
        ),
        ({"message": None}, "MODEL_INVALID_RESPONSE"),
    ],
)
def test_bailian_auto_never_accepts_text_or_unoffered_tools(monkeypatch, choice, code):
    client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [choice]})),
            **kwargs,
        ),
    )
    with pytest.raises(StudyError, match=code):
        ChatProvider("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", "secret").decide(
            [], 10
        )


@pytest.mark.parametrize(
    "arguments,kind",
    [
        ({"issues": ["unknown_private_issue"]}, "practice"),
        ({"issues": [], "feedback": "PRIVATE secret output"}, "practice"),
        ({"issues": ["incorrect_answer"]}, "insufficient_evidence"),
        ({}, "practice"),
    ],
)
def test_review_failures_preserve_usage_and_only_safe_diagnostics(monkeypatch, arguments, kind):
    from lecturelens_agent.study.provider import ModelResponseError

    client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
                        "choices": [
                            {
                                "message": {
                                    "tool_calls": [
                                        {
                                            "type": "function",
                                            "function": {
                                                "name": "assess_study_candidate",
                                                "arguments": json.dumps(arguments),
                                            },
                                        }
                                    ]
                                }
                            }
                        ],
                    },
                )
            ),
            **kwargs,
        ),
    )
    with pytest.raises(ModelResponseError, match="MODEL_REVIEW_CONTRACT") as failure:
        ChatProvider("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-max", "private-key").review(
            [{"role": "user", "content": json.dumps({"candidate": {"kind": kind}})}], 10
        )
    assert failure.value.usage == {"prompt_tokens": 12, "completion_tokens": 7}
    assert failure.value.diagnostics["stage"] == "review_schema"
    assert "private" not in json.dumps(failure.value.diagnostics).lower()
    assert "secret" not in str(failure.value)


def test_truncated_response_keeps_metered_usage_without_accepting_partial_tools(monkeypatch):
    from lecturelens_agent.study.provider import ModelResponseError

    client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "usage": {"prompt_tokens": 123, "completion_tokens": 300},
                        "choices": [{"finish_reason": "length", "message": {"content": "PRIVATE partial"}}],
                    },
                )
            ),
            **kwargs,
        ),
    )
    with pytest.raises(ModelResponseError) as failure:
        ChatProvider("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-max", "private-key").review(
            [], 10
        )
    assert failure.value.code == "MODEL_OUTPUT_TRUNCATED"
    assert failure.value.usage["completion_tokens"] == 300
    assert failure.value.diagnostics == {"stage": "response", "finish_reason": "length"}


def test_unverifiable_rejection_preserves_usage_without_forwarding_fabricated_feedback(monkeypatch):
    from test_study_quality import factual_verdict, review_input

    from lecturelens_agent.study.provider import ModelResponseError

    arguments = factual_verdict()
    arguments["findings"][0]["anchors"][1] = "PRIVATE invented anchor"
    usage = {"prompt_tokens": 100, "completion_tokens": 80}
    monkeypatch.setattr(
        ChatProvider,
        "_request",
        lambda *args: {"calls": [{"name": "assess_study_candidate", "arguments": arguments}], "usage": usage},
    )
    provider = ChatProvider("http://127.0.0.1:9/v1", "test-model", "private-key")
    with pytest.raises(ModelResponseError, match="MODEL_REVIEW_CONTRACT") as failure:
        provider.review([{"role": "user", "content": json.dumps(review_input())}], 10)
    assert failure.value.usage == usage
    assert "PRIVATE" not in str(failure.value) + json.dumps(failure.value.diagnostics)
    arguments["findings"][0]["anchors"][1] = "e1:1"
    result = provider.review([{"role": "user", "content": json.dumps(review_input())}], 10)
    assert result["review"]["issues"] == ["unsupported_explanation"]
    assert result["review"]["grounds"]["explanation"][1]["quote"] == "Implicitly returns None"


@pytest.mark.parametrize(
    "raw,expected,repairs",
    [
        ('{"query":"plain"}', {"query": "plain"}, []),
        ('{"items":["one"]', {"items": ["one"]}, ["root_object_close"]),
        (r"""{"query":"print(\'hello\')"}""", {"query": "print('hello')"}, ["apostrophe_escape"]),
        (r'{"query":"literal \\n"}', {"query": r"literal \n"}, []),
    ],
)
def test_bounded_argument_compatibility_preserves_values_and_reports_changes(raw, expected, repairs):
    from lecturelens_agent.study.provider import tool_arguments

    assert tool_arguments(raw) == (expected, repairs)


@pytest.mark.parametrize(
    "raw",
    [
        '{"query":"unterminated',
        '{"query":12',
        '{"query":["unfinished"',
        '{"query":"a",}',
        '{"query":"a"} prose',
        '{"query":"a\nactual newline"}',
        '{"query":}',
        '{"query": [}',
        None,
    ],
)
def test_argument_compatibility_never_invents_content_or_nested_structure(raw):
    from lecturelens_agent.study.provider import tool_arguments

    with pytest.raises((ValueError, TypeError)):
        tool_arguments(raw)


def test_decision_schema_failure_can_use_the_existing_bounded_format_retry(monkeypatch):
    from test_study_answer_points import draft

    from lecturelens_agent.study.provider import ModelResponseError

    candidate = draft()
    candidate["questions"][0]["answer_points"] = ["PRIVATE MODEL TEXT " * 40]
    factory = httpx.Client
    response = {
        "usage": {"prompt_tokens": 9, "completion_tokens": 33},
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "create_practice_set", "arguments": json.dumps(candidate)},
                        }
                    ]
                }
            }
        ],
    }
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: factory(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response)), **kwargs
        ),
    )
    provider = ChatProvider("http://127.0.0.1:9/v1", "test", "private-key")
    with pytest.raises(ModelResponseError) as failure:
        provider.decide([{"role": "tool", "content": "{}", "tool_call_id": "prior"}], 10)
    assert failure.value.code == "MODEL_TOOL_CONTRACT"
    assert failure.value.usage == response["usage"]
    assert failure.value.diagnostics == {
        "stage": "tool_schema",
        "validation": [{"field": "questions", "type": "string_too_long"}],
    }
    assert "PRIVATE" not in json.dumps(failure.value.diagnostics)


def test_model_selected_practice_kind_bounds_tools_but_allows_evidence_and_stop():
    from lecturelens_agent.study.provider import decision_schemas

    first = [{"role": "user", "content": json.dumps({"goal": "compare methods"})}]
    search = decision_schemas(first)[0]["function"]["parameters"]
    assert "practice_kind" in search["required"]
    assert "auto" not in search["properties"]["practice_kind"]["enum"]
    for kind, expected in [
        ("general", "create_practice_set"),
        ("python_output", "create_python_practice"),
        ("python_strings_or_code", "create_python_practice"),
        ("interval_halving", "create_interval_practice"),
        ("selection_steps", "create_sequence_practice"),
    ]:
        messages = [*first, {"role": "tool", "content": json.dumps({"practice_kind": kind})}]
        names = {s["function"]["name"] for s in decision_schemas(messages)}
        assert {n for n in names if n.startswith("create_")} == {expected}
        assert {"search_course_evidence", "read_evidence_window", "report_insufficient_evidence"} <= names
        messages.append({"role": "user", "content": "Retry the invalid tool format."})
        assert names == {s["function"]["name"] for s in decision_schemas(messages)}
