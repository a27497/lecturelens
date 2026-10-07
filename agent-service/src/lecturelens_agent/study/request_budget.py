"""Price the actual JSON transport plus the unchanged output-token ceiling."""

import json

import httpx


def schema_transport(schemas):
    """Remove schema annotations, retaining every validation keyword and tool.

    Protocol bindings keep their instructions. Atomic/source constraints and
    server validators are unchanged; schema titles and repeated prose are not
    evidence or a verification result.
    """

    def project(value, field=None):
        if isinstance(value, list):
            return [project(item, field) for item in value]
        if not isinstance(value, dict):
            return value
        return {
            key: (
                {
                    name: project(schema, name if key == "properties" else field)
                    for name, schema in item.items()
                }
                if key in {"properties", "$defs"}
                else project(item, field)
            )
            for key, item in value.items()
            if key != "title"
            and (
                key != "description"
                or field
                in {
                    "resolved_goal",
                    "revision_edits",
                    "evidence_ids",
                    "program_plan",
                    "request_revision",
                    "explanation",
                }
            )
        }

    return [
        {**tool, "function": {**tool["function"], "parameters": project(tool["function"]["parameters"])}}
        for tool in schemas
    ]


def chat_payload(model, messages, schemas, max_tokens, *, nonthinking=False):
    compact = False
    for message in messages:
        if message.get("role") not in {"user", "tool"}:
            continue
        try:
            body = json.loads(message.get("content") or "")
        except (ValueError, TypeError):
            continue
        if not isinstance(body, dict):
            continue
        if len(schemas) == 1 and schemas[0]["function"]["name"] == "assess_study_candidate":
            compact = body.get("review_mode") in {"atomic_answer_spans_v2", "atomic_delta_spans_v2"}
        elif body.get("revision_transaction") or body.get("semantic_context", {}).get("previous_turns"):
            compact = True
    payload = {
        "model": model,
        "messages": messages,
        "tools": schema_transport(schemas) if compact else schemas,
        "tool_choice": "required",
        "parallel_tool_calls": False,
        "temperature": 0
        if len(schemas) == 1 and schemas[0]["function"]["name"] == "assess_study_candidate"
        else 0.2,
        "max_tokens": max_tokens,
    }
    if nonthinking:
        payload["enable_thinking"] = False
        payload["tool_choice"] = (
            {"type": "function", "function": {"name": schemas[0]["function"]["name"]}}
            if len(schemas) == 1
            else "auto"
        )
    return payload


def request_cost(provider, purpose, messages, schemas, max_tokens):
    from .provider import bailian_nonthinking

    client = getattr(provider, "clients", {}).get(purpose, provider)
    method = client.review if purpose == "review" else client.decide
    client = getattr(method, "__self__", client)
    model = getattr(client, "model", "mock")
    url = getattr(client, "url", "")
    payload = chat_payload(model, messages, schemas, max_tokens, nonthinking=bailian_nonthinking(url, model))
    # HTTPX is the provider's encoder. Count its UTF-8 bytes, including the
    # envelope; schema ASCII escapes/default JSON spaces are not sent bytes.
    size = len(httpx.Request("POST", "https://budget.invalid", json=payload).content)
    return {"request_bytes": size, "output_tokens": max_tokens, "cost": size + max_tokens}
