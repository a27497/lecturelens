"""Private, bounded protocol shape observations without model prose/arguments."""

import hashlib
import hmac
import json
import secrets

_KEY = secrets.token_bytes(32)


def protocol_shape(raw, schemas, decoder, parser_error="none"):
    result = {
        "fingerprint": hmac.new(_KEY, raw, hashlib.sha256).hexdigest()[:32],
        "parser_error": parser_error,
        "response_shape": "invalid_json",
        "tool_call_count": 0,
        "tool_calls": [],
    }
    try:
        body = json.loads(raw)
        message = body["choices"][0]["message"]
        if not isinstance(message, dict):
            raise TypeError
    except (ValueError, KeyError, IndexError, TypeError):
        return result
    calls = message.get("tool_calls") or []
    if not isinstance(calls, list):
        result["response_shape"] = "invalid_tool_container"
        return result
    has_content = bool(message.get("content"))
    result["response_shape"] = (
        ("content_and_tools" if has_content else "tools_only")
        if calls
        else ("content_only" if has_content else "empty_message")
    )
    result["tool_call_count"] = min(len(calls), 16)
    result["tool_calls_truncated"] = len(calls) > 3
    allowed = {s["function"]["name"] for s in schemas}
    for call in calls[:3]:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            result["tool_calls"].append({"tool_name": "invalid", "arguments_parse": "not_attempted"})
            continue
        name = function.get("name")
        entry = {
            "tool_name": name if isinstance(name, str) and name in allowed else "unoffered",
            "arguments_parse": "failure",
        }
        try:
            arguments, _ = decoder(function.get("arguments"))
            entry["arguments_parse"] = "object" if isinstance(arguments, dict) else "non_object"
        except (ValueError, TypeError):
            pass
        result["tool_calls"].append(entry)
    return result
