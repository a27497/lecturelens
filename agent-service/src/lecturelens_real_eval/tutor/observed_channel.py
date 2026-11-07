"""Decoded, bounded evaluation telemetry. Frozen sender and accounting stay unchanged."""

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from lecturelens_real_eval.tutor_channel import Channel, EvalError

LIMIT = 128 * 1024


def metadata(data, secret=""):
    """Allowlisted identifiers/numeric usage only; no body, error text or arbitrary headers."""
    result = {"returned_model": None, "response_id": None, "system_fingerprint": None}
    issues = []

    def identifier(value):
        if value is None:
            return None
        if (
            isinstance(value, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", value)
            and (not secret or secret not in value)
        ):
            return value
        return None

    if not isinstance(data, dict):
        return {**result, "capture_status": "INVALID_JSON_OBJECT", "usage": None, "cache": None}
    for source, target in (
        ("model", "returned_model"),
        ("id", "response_id"),
        ("system_fingerprint", "system_fingerprint"),
    ):
        result[target] = identifier(data.get(source))
        if data.get(source) is not None and result[target] is None:
            issues.append("INVALID_" + source.upper())

    def numeric(value, prefix="", depth=0):
        clean = {}
        for key, item in value.items():
            if (
                not isinstance(key, str)
                or not re.fullmatch(r"[a-z_]{1,64}", key)
                or (secret and secret in key)
            ):
                issues.append("INVALID_USAGE_FIELD")
                continue
            if isinstance(item, dict) and depth < 2:
                clean[key] = numeric(item, prefix + key + ".", depth + 1)
            elif type(item) is int and 0 <= item <= 2**63 - 1:
                clean[key] = item
            else:
                issues.append("INVALID_USAGE_" + prefix + key)
        return clean

    usage = numeric(data["usage"]) if isinstance(data.get("usage"), dict) else None
    if usage is None:
        issues.append("USAGE_UNKNOWN")
    usage = usage or {}

    def count(key, container=usage):
        value = container.get(key)
        if value is not None and type(value) is not int:
            issues.append("INVALID_USAGE_" + key)
            return None
        return value

    hit = count("prompt_cache_hit_tokens")
    miss = count("prompt_cache_miss_tokens")
    details = usage.get("prompt_tokens_details")
    nested_hit = count("cached_tokens", details) if isinstance(details, dict) else None
    if hit is not None and nested_hit is not None and hit != nested_hit:
        issues.append("CACHE_HIT_CONFLICT")
    if hit is None:
        hit = nested_hit
    prompt, completion, total = (count(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
    if any(type(v) is not int for v in (prompt, completion)):
        issues.append("CORE_USAGE_UNKNOWN")
    if all(type(v) is int for v in (prompt, completion, total)) and prompt + completion != total:
        issues.append("TOKEN_TOTAL_MISMATCH")
    if prompt is not None and (
        any(v is not None and v > prompt for v in (hit, miss))
        or (hit is not None and miss is not None and hit + miss != prompt)
    ):
        issues.append("CACHE_TOTAL_MISMATCH")
    invalid_cache = any("CACHE" in issue.upper() for issue in issues)
    cache_status = (
        "INCONSISTENT"
        if invalid_cache
        else "UNKNOWN"
        if hit is None and miss is None
        else "PARTIAL"
        if hit is None or miss is None
        else "PROVIDER_REPORTED"
    )
    return {
        **result,
        "capture_status": "JSON_DECODED",
        "model_status": "PROVIDER_REPORTED_ALIAS_OR_VERSION" if result["returned_model"] else "UNKNOWN",
        "usage": usage or None,
        "cache": {"hit_tokens": hit, "miss_tokens": miss, "status": cache_status},
        "anomalies": sorted(set(issues)),
    }


class DecodedMetadataTransport(httpx.BaseTransport):
    """Let HTTPX decode once, tee decoded bytes, then present identity bytes to Channel.

    No eager read: deadlines/close/failure semantics remain with the frozen sender. Failed
    HTTP status bodies are deliberately unread, so their body metadata stays UNKNOWN.
    """

    def __init__(self, inner):
        self.inner = inner
        self.reset()

    def reset(self):
        self.metadata = {
            "capture_status": "NOT_SENT",
            "usage": None,
            "returned_model": None,
            "model_status": "UNKNOWN",
            "cache": None,
            "response_id": None,
            "request_id": None,
            "system_fingerprint": None,
            "anomalies": [],
        }

    def handle_request(self, request):
        self.reset()
        secret = request.headers.get("authorization", "").removeprefix("Bearer ")
        self.metadata.update(
            request_sha256=hashlib.sha256(request.content).hexdigest(), capture_status="TRANSPORT_FAILED"
        )
        response = self.inner.handle_request(request)
        self.metadata.update(http_status=response.status_code, capture_status="BODY_NOT_READ")
        # Only the association header is admitted, through the same restricted ID validator.
        header_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        self.metadata["request_id"] = metadata({"id": header_id}, secret)["response_id"]
        owner = self

        class Stream(httpx.SyncByteStream):
            def __iter__(self):
                captured = bytearray()
                owner.metadata["capture_status"] = "BODY_IN_PROGRESS"
                try:
                    # Preserve decoded chunk delivery so Channel's elapsed-time guard still
                    # runs per chunk; buffering small responses could delay that guard.
                    for chunk in response.iter_bytes():
                        if len(captured) + len(chunk) > LIMIT:
                            owner.metadata["capture_status"] = "DECODED_BODY_LIMIT"
                            raise EvalError("REAL_EVAL_BODY_LIMIT")
                        captured.extend(chunk)
                        yield chunk
                    try:
                        data = json.loads(captured)
                    except (ValueError, UnicodeError):
                        owner.metadata["capture_status"] = "INVALID_JSON"
                    else:
                        owner.metadata.update(metadata(data, secret))
                except Exception:  # noqa: BLE001 -- preserve sender error semantics, never log exception text
                    if owner.metadata["capture_status"] == "BODY_IN_PROGRESS":
                        owner.metadata["capture_status"] = "BODY_INCOMPLETE"
                    raise

            def close(self):
                if owner.metadata["capture_status"] == "BODY_IN_PROGRESS":
                    owner.metadata["capture_status"] = "BODY_INCOMPLETE"
                response.close()

        headers = [
            (k, v)
            for k, v in response.headers.multi_items()
            if k.lower() not in {"content-encoding", "content-length"}
        ]
        return httpx.Response(response.status_code, headers=headers, stream=Stream())

    def close(self):
        self.inner.close()


class ReservationObserver:
    """Observe the existing durable reservation without changing accounting decisions."""

    def __init__(self, ledger):
        self.inner, self.reservation = ledger, None

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def reserve(self, *args):
        self.reservation = self.inner.reserve(*args)
        return self.reservation


class ObservedChannel(Channel):
    def __init__(self, *args, records, pricing_source=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not isinstance(self.transport, DecodedMetadataTransport):
            raise ValueError("DECODED_METADATA_TRANSPORT_REQUIRED")
        self.ledger = ReservationObserver(self.ledger)
        self.records, self.pricing_source = Path(records), pricing_source
        self.turn_key, self.turn_calls = None, []

    def request(self, *args, **kwargs):
        if kwargs.get("purpose", "tutor") != "tutor":
            raise EvalError("PILOT_REVIEWER_DISABLED")
        self.transport.reset()  # A pre-reservation rejection must not inherit the previous response.
        self.ledger.reservation = None
        started = time.monotonic()
        row = dict(
            local_request_id=str(uuid.uuid4()),
            turn_key=self.turn_key,
            purpose="tutor",
            started_utc=datetime.now(timezone.utc).isoformat(),
            live=self.policy.live,
            requested_model=self.policy.model,
            status="FAILED",
            error=None,
            usage_source="PROVIDER" if self.policy.live else "MOCK_NOT_BILLABLE",
            pricing_source=self.pricing_source,
            rate_calculated_cost_status="NOT_RUN",
            supplier_bill_status="UNKNOWN_NOT_QUERIED",
            supplier_billed_usd=None,
        )
        try:
            result = super().request(*args, **kwargs)
            row["status"] = "SUCCEEDED"
            return result
        except Exception as error:
            row["error"] = error.code if isinstance(error, EvalError) else "CHANNEL_EXCEPTION"
            raise
        finally:
            row.update(self.transport.metadata)
            reservation = self.ledger.reservation or {}
            row.update(
                ledger_call_id=reservation.get("call_id"),
                local_reserved_nano_usd=reservation.get("reserved_nano_usd"),
                local_charge_source="ledger.jsonl_by_ledger_call_id",
            )
            row["latency_s"] = time.monotonic() - started
            row["finished_utc"] = datetime.now(timezone.utc).isoformat()
            self.turn_calls.append(row)
            # Evaluation paths are single-use and private; never dump request/response headers/bodies.
            fd = os.open(self.records, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "a") as output:
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
