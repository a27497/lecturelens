"""Official DeepSeek tool requests must not inherit its thinking-mode default."""

import json

import httpx
import pytest

from lecturelens_agent.study.provider import ChatProvider

TOOL = {
    "type": "function",
    "function": {
        "name": "connection_check",
        "parameters": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
    },
}
RESPONSE = {
    "choices": [
        {
            "message": {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "connection_check",
                            "arguments": '{"ok":true}',
                        },
                    }
                ]
            }
        }
    ],
}


def transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-pro"])
@pytest.mark.parametrize(
    "url",
    [
        "https://api.deepseek.com",
        "https://api.deepseek.com/v1",
        "https://api.deepseek.com/v1/",
        "https://api.deepseek.com:443/v1",
    ],
)
@pytest.mark.parametrize("output_limit", [300, 900, 1200])
def test_official_tool_requests_disable_thinking_without_changing_budgets(
    monkeypatch, model, url, output_limit
):
    def handler(request):
        payload = json.loads(request.content)
        if payload.get("thinking") != {"type": "disabled"}:
            return httpx.Response(400, json={"error": {"code": "invalid_tool_choice"}})
        assert payload["tool_choice"] == "required"
        assert payload["max_tokens"] == output_limit
        assert payload["parallel_tool_calls"] is False
        assert payload["tools"] == [TOOL]
        assert request.extensions["timeout"]["read"] == 10
        return httpx.Response(200, json=RESPONSE)

    transport(monkeypatch, handler)
    result = ChatProvider(base_url=url, model=model, api_key="")._request([], [TOOL], 10, output_limit)
    assert result["calls"] == [{"name": "connection_check", "arguments": {"ok": True}}]


@pytest.mark.parametrize(
    "url,model",
    [
        ("https://api.deepseek.com.evil.example", "deepseek-flash"),
        ("https://third-party.example/v1", "deepseek-flash"),
        ("http://127.0.0.1:8091/v1", "deepseek-flash"),
        ("https://api.deepseek.com/beta", "deepseek-flash"),
        ("https://api.deepseek.com:8443", "deepseek-flash"),
        ("https://api.deepseek.com", "unknown-model"),
        ("https://api.deepseek.com/v1?token=offline", "deepseek-flash"),
        ("https://api.deepseek.com/v1#other", "deepseek-flash"),
        ("https://user@api.deepseek.com/v1", "deepseek-flash"),
        ("https://api.deepseek.com", "deepseek-reasoner"),
    ],
)
def test_profile_does_not_change_other_providers_or_models(monkeypatch, url, model):
    def handler(request):
        payload = json.loads(request.content)
        assert "thinking" not in payload
        assert payload["tool_choice"] == "required"
        return httpx.Response(200, json=RESPONSE)

    transport(monkeypatch, handler)
    ChatProvider(base_url=url, model=model, api_key="")._request([], [TOOL], 10, 900)
