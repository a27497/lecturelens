import json

import httpx
import pytest
from test_study import read, setup, start  # noqa: F401 -- shared isolated PostgreSQL fixture

from lecturelens_agent.study.contracts import tool_schemas
from lecturelens_agent.study.protocol import protocol_shape
from lecturelens_agent.study.provider import ChatProvider, ModelResponseError, tool_arguments


@pytest.mark.parametrize(
    "calls,content,category,error",
    [
        ([], "private-secret-sentinel", "content_only", "call_count_or_type"),
        (
            [
                {
                    "type": "function",
                    "function": {"name": "search_course_evidence", "arguments": "{private-secret-sentinel"},
                }
            ],
            None,
            "tools_only",
            "arguments_json",
        ),
        (
            [{"type": "function", "function": {"name": "private-secret-sentinel", "arguments": "{}"}}],
            None,
            "tools_only",
            "unoffered_tool",
        ),
    ],
)
def test_provider_records_private_bounded_shape_without_changing_parser(
    monkeypatch, calls, content, category, error
):
    client = httpx.Client
    raw = json.dumps({"choices": [{"message": {"content": content, "tool_calls": calls}}]}).encode()
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=raw)), **kwargs
        ),
    )
    with pytest.raises(ModelResponseError) as failure:
        ChatProvider(
            "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-max", "private-secret-sentinel"
        ).decide([], 10)
    detail = failure.value.private_diagnostics
    assert detail["response_shape"] == category
    assert detail["parser_error"] == error
    assert detail["tool_call_count"] == len(calls)
    assert len(detail["fingerprint"]) == 32
    assert "private-secret-sentinel" not in json.dumps(detail)
    assert len(json.dumps(detail)) < 1000


def test_fingerprint_is_stable_private_and_tool_records_are_bounded():
    raw = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "search_course_evidence",
                                    "arguments": '{"query":"private-secret-sentinel"}',
                                }
                            }
                            for _ in range(20)
                        ]
                    }
                }
            ]
        }
    ).encode()
    detail = protocol_shape(raw, tool_schemas(), tool_arguments)
    assert detail == protocol_shape(raw, tool_schemas(), tool_arguments)
    assert detail["tool_call_count"] == 16 and detail["tool_calls_truncated"]
    assert len(detail["tool_calls"]) == 3
    assert detail["tool_calls"][0]["arguments_parse"] == "object"
    assert "private-secret-sentinel" not in json.dumps(detail)


def test_failed_protocol_shape_is_only_in_operator_trace(setup):  # noqa: F811
    store, _, runtime, _ = setup
    detail = protocol_shape(
        b'{"choices":[{"message":{"content":"private-secret-sentinel"}}]}',
        tool_schemas(),
        tool_arguments,
        "call_count_or_type",
    )

    def decide(messages, timeout):
        raise ModelResponseError("MODEL_TOOL_CONTRACT", {}, {"stage": "tool_contract"}, detail)

    runtime.provider.decide = decide
    run = start(setup)
    runtime.execute(run)
    public = read(setup, "EVENTS")
    assert "fingerprint" not in json.dumps(public)
    assert "response_shape" not in json.dumps(public)
    assert "private-secret-sentinel" not in json.dumps(public)
    with store.connect() as conn:
        events = conn.execute(
            "SELECT trace_detail FROM study_event WHERE run_id=%s AND event_type='model_failed'",
            (run["run_id"],),
        ).fetchall()
    assert events and events[0]["trace_detail"]["protocol"]["response_shape"] == "content_only"
