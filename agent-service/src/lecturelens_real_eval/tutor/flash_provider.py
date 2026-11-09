"""The single-call wire contract for the experimental Tutor."""

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass

import httpx

from lecturelens_agent.study.store import StudyError

from .contracts import ABSTENTION
from .light import GROUNDING, REPLY_LIMITS, TEACHING, Reply

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


TEXT_SYSTEM = (
    TEACHING
    + GROUNDING
    + REPLY_LIMITS
    + """Use exactly one of these plain-text forms. Write the status at the start of the first line.
When socratic is false and you can teach the topic, write answered on the first line and the teaching text next.
When socratic is true and you can guide the learner, write socratic_prompt on the first line, a literal phrase
from the current learner question (up to 120 characters) on the second line, and the guiding question including
that phrase from the third line onward.
If the course evidence is insufficient to teach the requested topic, write only insufficient_evidence.
Keep the teaching text within 1600 characters and use at most four distinct citations.
Write code, Markdown and line breaks directly in the teaching text.
"""
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload(messages, *, text_reply=False):
    system, user = messages
    return json.dumps(
        {
            "model": MODEL,
            "messages": [
                {**system, "content": TEXT_SYSTEM if text_reply else system["content"] + JSON_INSTRUCTION},
                user,
            ],
            "response_format": {"type": "text" if text_reply else "json_object"},
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


def parse_text(content):
    if not isinstance(content, str):
        raise ValueError("Expected text")
    if content in {"insufficient_evidence", "insufficient_evidence\n", "insufficient_evidence\r\n"}:
        return Reply(outcome="insufficient_evidence", text=ABSTENTION)
    outcome, _, text = content.partition("\n")
    outcome = outcome.removesuffix("\r")
    focus = ""
    if outcome == "socratic_prompt":
        focus, _, text = text.partition("\n")
        focus = focus.removesuffix("\r")
        if not focus or focus != focus.strip():
            raise ValueError("Expected a focus line")
    if outcome not in {"answered", "socratic_prompt"} or not text.strip() or ABSTENTION in text:
        raise ValueError("Invalid teaching frame")
    return Reply(outcome=outcome, text=text, focus=focus)


def parse(body, *, text_reply=False):
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
        if text_reply and message.get("refusal"):
            raise ValueError("Provider refusal")
        reply = (
            parse_text(content)
            if text_reply
            else Reply.model_validate(json.loads(content, object_pairs_hook=unique_object))
        ).model_dump()
        for key in ("text", "focus"):
            reply[key].encode("utf-8")
            if "\x00" in reply[key]:
                raise ValueError("Invalid JSONB text")
    except (ValueError, TypeError, RecursionError):
        error = "TUTOR_PROTOCOL_FAILURE" if text_reply else "TUTOR_FLASH_INVALID_JSON"
        return Completion(*result, error=error, **raw)
    return Completion(*result, reply=reply)


class FlashProvider:
    def __init__(self, api_key, *, transport=None, observer=None, text_reply=False):
        if not api_key or not re.fullmatch(r"[!-~]{1,512}", api_key):
            raise RuntimeError("TUTOR_FLASH_KEY_REQUIRED")
        self._key = api_key
        self._transport = transport
        self._observer = observer
        self._text_reply = text_reply

    @property
    def offline(self):
        return self._transport is not None

    def request_body(self, messages):
        return payload(messages, text_reply=self._text_reply)

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
        return parse(buffer, text_reply=self._text_reply)

    @staticmethod
    def http_error(status):
        return StudyError(
            {
                429: "TUTOR_FLASH_RATE_LIMITED",
                503: "TUTOR_FLASH_UNAVAILABLE",
            }.get(status, "TUTOR_FLASH_HTTP_FAILURE")
        )
