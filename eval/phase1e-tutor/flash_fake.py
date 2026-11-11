"""Offline-only ASGI factory for the Java/PG integration check."""

import json
import os
from pathlib import Path

import httpx
from lecturelens_real_eval.tutor.flash_app import experiment_app
from lecturelens_real_eval.tutor.flash_provider import MODEL, URL, digest


def create_app():
    request_log = Path(os.environ["PHASE1E_FAKE_REQUEST_LOG"])

    def fake(request):
        assert str(request.url) == URL
        assert request.headers["authorization"] == "Bearer synthetic-phase1e-http"
        payload = json.loads(request.content)
        assert payload["model"] == MODEL and payload["max_tokens"] == 4096
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["thinking"] == {"type": "disabled"}
        assert "tools" not in payload
        context = json.loads(payload["messages"][-1]["content"])
        eid = context["current_evidence"][0]["evidence_id"]
        answer = {
            "outcome": "answered",
            "text": f"Offline HTTP fixture: the background work and later result are separate steps [{eid}].",
            "focus": "",
        }
        with request_log.open("a") as stream:
            stream.write(
                json.dumps(
                    {"request_sha256": digest(request.content), "kind": "OFFLINE_FAKE"}
                )
                + "\n"
            )
        return httpx.Response(
            200,
            json={
                "id": "synthetic-e2e-completion",
                "model": MODEL,
                "system_fingerprint": "fp_offline_e2e",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(answer)},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                    "prompt_cache_hit_tokens": 20,
                    "prompt_cache_miss_tokens": 80,
                },
            },
        )

    return experiment_app(offline_transport=httpx.MockTransport(fake))
