"""Reconstruct retained parsed decisions/metadata, never unavailable raw response bytes."""

import copy
import hashlib
import json
from pathlib import Path

import httpx


def read(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def frames(raw):
    raw = Path(raw)
    rows = jsonl(raw / "fresh-real16/turns.jsonl")
    result = []
    for turn in rows:
        proposals = iter(turn.get("proposals", []))
        for call in turn.get("calls", []):
            first = next(proposals)
            group = [first] + [next(proposals) for _ in range(first["dropped_tool_calls"])]
            assert all(p["usage"] == first["usage"] for p in group)
            assert first["usage"] == {k: call["usage"][k] for k in ("prompt_tokens", "completion_tokens")}
            index = len(result) + 1
            wire = raw / f"wire/{index:03d}-request.json"
            assert hashlib.sha256(wire.read_bytes()).hexdigest() == call["request_sha256"]
            result.append(
                dict(
                    turn_key=turn["turn_key"],
                    request=read(wire),
                    request_sha256=call["request_sha256"],
                    first=first,
                    response={
                        "id": call["response_id"],
                        "model": call["returned_model"],
                        "system_fingerprint": call["system_fingerprint"],
                        "usage": call["usage"],
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "tool_calls": [
                                        {
                                            "type": "function",
                                            "function": {
                                                "name": p["name"],
                                                "arguments": json.dumps(p["arguments"]),
                                            },
                                        }
                                        for p in group
                                    ]
                                },
                            }
                        ],
                    },
                )
            )
        assert next(proposals, None) is None
    assert len(result) == 17
    return result


class RetainedTransport(httpx.MockTransport):
    """Single pass over known decisions. No synthesized recovery response is hidden here."""

    def __init__(self, retained, *, strict=True):
        self.retained, self.strict, self.sent = retained, strict, []
        super().__init__(self.send_retained)

    def send_retained(self, request):
        index = len(self.sent)
        if index >= len(self.retained):
            raise AssertionError("REPLAY_EXHAUSTED_NO_RETRY_OR_INVENTED_RESPONSE")
        frame = self.retained[index]
        payload = json.loads(request.content)
        if self.strict:
            assert payload == frame["request"]
            assert hashlib.sha256(request.content).hexdigest() == frame["request_sha256"]
        self.sent.append(copy.deepcopy(payload))
        return httpx.Response(200, json=frame["response"])
