"""E3 ASGI factories for an anonymous key pipe and batch-only Mock HTTP."""

import ctypes
import json
import os
import signal
import stat
import sys

import httpx

from lecturelens_real_eval.tutor.contracts import ABSTENTION
from lecturelens_real_eval.tutor.flash_e3_app import experiment_app
from lecturelens_real_eval.tutor.flash_provider import MODEL, URL
from lecturelens_real_eval.tutor.light import MockLightTutor

from .e3_terminal import valid_key


def pipe_app():
    try:
        launcher = int(os.environ["TUTOR_E3_LAUNCHER_PID"])
    except (KeyError, ValueError):
        raise RuntimeError("E3_KEY_PIPE_LAUNCHER_REQUIRED") from None
    # Bind credential lifetime to the launcher even if SSH or the launcher dies.
    if (
        launcher <= 1
        or os.getppid() != launcher
        or ctypes.CDLL(None).prctl(1, signal.SIGTERM, 0, 0, 0) != 0
        or os.getppid() != launcher
    ):
        raise RuntimeError("E3_KEY_PIPE_LAUNCHER_LOST")
    if not stat.S_ISFIFO(os.fstat(0).st_mode):
        raise RuntimeError("E3_KEY_PIPE_REQUIRED")
    try:
        with sys.stdin.buffer as stream:
            key = stream.read(513).decode("ascii")
    except (UnicodeError, OSError):
        raise RuntimeError("E3_KEY_PIPE_INVALID") from None
    if not valid_key(key):
        raise RuntimeError("E3_KEY_PIPE_INVALID")
    return experiment_app(api_key=key)


def batch_mock_app():
    def fake(request):
        assert str(request.url) == URL
        payload = json.loads(request.content)
        assert payload["model"] == MODEL and "tools" not in payload
        messages = payload["messages"]
        context = json.loads(messages[-1]["content"])
        result = MockLightTutor().complete(messages, None, None)
        if "exact author email and timestamp" in context["learner_question"]:
            result = {"outcome": "insufficient_evidence", "text": ABSTENTION, "focus": ""}
        result.pop("usage", None)
        return httpx.Response(
            200,
            json={
                "id": "offline-batch-fixture",
                "model": MODEL,
                "system_fingerprint": "offline-batch",
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}],
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
