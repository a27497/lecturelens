"""The single-call wire contract for the experimental Tutor."""

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass

import httpx

from lecturelens_agent.study.store import StudyError

from .light import Reply

MODEL = "deepseek-flash"
MODEL_VERSION = "DeepSeek-V4.1-Flash-1017"
URL = "https://api.deepseek.com/chat/completions"
OUTPUT_TOKENS = 4096
CONTEXT_BOUND = 1_048_576
# Peak USD per million tokens converted to integer nanoUSD per token.
RATES = {"prompt_cache_hit_tokens": 6, "prompt_cache_miss_tokens": 300, "completion_tokens": 1200}
PRICE_ID = "deepseek-flash-peak-usd-2026-11-09"
RESERVE_NANO_USD = CONTEXT_BOUND * RATES["prompt_cache_miss_tokens"] + (
    OUTPUT_TOKENS * RATES["completion_tokens"]
)
JSON_INSTRUCTION = (
    '\nUse a JSON object, for example {"outcome":"answered","text":"Explanation [example_id]","focus":""}. '
    "The example id is illustrative. Use actual current Evidence ids."
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload(messages):
    system, user = messages
    return json.dumps(
        {
            "model": MODEL,
            "messages": [{**system, "content": system["content"] + JSON_INSTRUCTION}, user],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0.2,
            "max_tokens": OUTPUT_TOKENS,
            "stream": False,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


def checked_usage(raw):
    fields = (*RATES, "prompt_tokens", "total_tokens")
    if not isinstance(raw, dict):
        return None
    usage = {key: raw.get(key) for key in fields}
    if any(type(value) is not int or not 0 <= value <= 2**31 - 1 for value in usage.values()):
        return None
    if (
        usage["prompt_tokens"] == 0
        or usage["prompt_tokens"] != usage["prompt_cache_hit_tokens"] + usage["prompt_cache_miss_tokens"]
        or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]
    ):
        return None
    return usage


@dataclass(frozen=True)
class Completion:
    usage: dict | None
    response_sha256: str
    fingerprint: str | None = None
    provider_id: str | None = None
    reply: dict | None = None
    error: str | None = None
    raw_content: str | None = None


def safe_id(value):
    return value if isinstance(value, str) and re.fullmatch(r"[\w.-]{1,128}", value, re.ASCII) else None


def unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate JSON member")
    return result


def parse(body):
    response_hash = digest(body)
    try:
        envelope = json.loads(body, object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        envelope = None
    if not isinstance(envelope, dict):
        return Completion(None, response_hash, error="TUTOR_FLASH_INVALID_ENVELOPE")
    usage = checked_usage(envelope.get("usage"))
    fingerprint = safe_id(envelope.get("system_fingerprint"))
    provider_id = safe_id(envelope.get("id"))
    result = (usage, response_hash, fingerprint, provider_id)
    if usage is None:
        return Completion(*result, error="TUTOR_FLASH_USAGE_UNKNOWN")
    if envelope.get("model") != MODEL or not fingerprint or not provider_id:
        return Completion(*result, error="TUTOR_FLASH_IDENTITY_CHANGED")
    if usage["prompt_tokens"] > CONTEXT_BOUND or usage["completion_tokens"] > OUTPUT_TOKENS:
        return Completion(*result, error="TUTOR_FLASH_USAGE_OVERRUN")
    choices = envelope.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return Completion(*result, error="TUTOR_FLASH_INVALID_ENVELOPE")
    choice = choices[0]
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    raw = {}
    if isinstance(content, str):
        raw["raw_content"] = content[:16384].encode("utf-8", "replace").decode().replace("\x00", "\ufffd")
    if choice.get("finish_reason") == "length":
        return Completion(*result, error="TUTOR_FLASH_TRUNCATED", **raw)
    if choice.get("finish_reason") != "stop":
        return Completion(*result, error="TUTOR_FLASH_INTERRUPTED", **raw)
    if not isinstance(message, dict) or message.get("tool_calls") or message.get("reasoning_content"):
        return Completion(*result, error="TUTOR_FLASH_INVALID_ENVELOPE")
    if isinstance(content, str) and not content.strip():
        return Completion(*result, error="TUTOR_FLASH_BLANK")
    if usage["completion_tokens"] == 0:
        return Completion(None, response_hash, fingerprint, provider_id, error="TUTOR_FLASH_USAGE_UNKNOWN")
    try:
        reply = Reply.model_validate(json.loads(content, object_pairs_hook=unique_object)).model_dump()
        for key in ("text", "focus"):
            reply[key].encode("utf-8")
            if "\x00" in reply[key]:
                raise ValueError("Invalid JSONB text")
    except (ValueError, TypeError, RecursionError):
        return Completion(*result, error="TUTOR_FLASH_INVALID_JSON", **raw)
    return Completion(*result, reply=reply)


class FlashProvider:
    def __init__(self, api_key, *, transport=None, observer=None):
        if not api_key or not re.fullmatch(r"[!-~]{1,512}", api_key):
            raise RuntimeError("TUTOR_FLASH_KEY_REQUIRED")
        self._key = api_key
        self._transport = transport
        self._observer = observer

    @property
    def offline(self):
        return self._transport is not None

    def complete(self, body, timeout):
        if self._observer is not None:
            if self._key.encode() in body:
                raise StudyError("TUTOR_FLASH_SECRET_IN_REQUEST")
            deadline = time.monotonic() + timeout
            self._observer(body)
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                raise StudyError("TUTOR_FLASH_TIMEOUT")
        return asyncio.run(self._complete(body, timeout))

    async def _complete(self, body, timeout):
        headers = {
            "Authorization": "Bearer " + self._key,
            "Content-Type": "application/json",
            "Accept-Encoding": "identity",
        }
        buffer = bytearray()
        status, complete = None, False
        try:
            async with (
                asyncio.timeout(timeout),
                httpx.AsyncClient(
                    timeout=timeout, follow_redirects=False, trust_env=False, transport=self._transport
                ) as client,
                client.stream("POST", URL, content=body, headers=headers) as response,
            ):
                status = response.status_code
                if status != 200 and self._observer is None:
                    raise self.http_error(status)
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise StudyError("TUTOR_FLASH_UNEXPECTED_ENCODING")
                async for chunk in response.aiter_bytes():
                    if len(buffer) + len(chunk) > 128 * 1024:
                        raise StudyError("TUTOR_FLASH_RESPONSE_LIMIT")
                    buffer.extend(chunk)
                complete = True
                if status != 200:
                    raise self.http_error(status)
        except (TimeoutError, httpx.TimeoutException):
            raise StudyError("TUTOR_FLASH_TIMEOUT") from None
        except httpx.RequestError:
            raise StudyError("TUTOR_UNKNOWN_MODEL_OUTCOME") from None
        finally:
            if self._observer is not None:
                if self._key.encode() in buffer:
                    self._observer(body, b"", status, False)
                    raise StudyError("TUTOR_FLASH_SECRET_IN_RESPONSE")
                self._observer(body, bytes(buffer), status, complete)
        return parse(buffer)

    @staticmethod
    def http_error(status):
        return StudyError(
            {
                429: "TUTOR_FLASH_RATE_LIMITED",
                503: "TUTOR_FLASH_UNAVAILABLE",
            }.get(status, "TUTOR_FLASH_HTTP_FAILURE")
        )
