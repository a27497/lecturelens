"""Bounded pre-parse entity capture; never persist authorization or raw exceptions."""

import hashlib
import json
import os
import time
from pathlib import Path

import httpx

from lecturelens_real_eval.tutor_channel import EvalError


def private_file(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    directory = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class CaptureTransport(httpx.BaseTransport):
    def __init__(self, inner, output):
        self.inner, self.output, self.calls = inner, Path(output), 0
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)

    def handle_request(self, request):
        self.calls += 1
        prefix = self.output / f"{self.calls:03d}"
        secret = request.headers.get("authorization", "").removeprefix("Bearer ")

        def clean(value):
            if secret:

                def redact(item):
                    if isinstance(item, str):
                        return item.replace(secret, "[REDACTED]")
                    if isinstance(item, list):
                        return [redact(v) for v in item]
                    if isinstance(item, dict):
                        return {redact(k): redact(v) for k, v in item.items()}
                    return item

                try:
                    decoded = json.loads(value)
                    sanitized_json = redact(decoded)
                    if decoded != sanitized_json:
                        return json.dumps(sanitized_json, ensure_ascii=True).encode()
                except (ValueError, UnicodeError):
                    pass
                for token in {secret.encode(), json.dumps(secret, ensure_ascii=True)[1:-1].encode()}:
                    value = value.replace(token, b"[REDACTED]")
            return value

        raw_request = request.content
        sanitized = clean(raw_request)
        private_file(str(prefix) + "-request.body", sanitized)
        record = {
            "body_kind": "HTTP_DECODED_ENTITY_BEFORE_JSON_PARSE_NOT_TLS_FRAMES",
            "request_sha256": hashlib.sha256(sanitized).hexdigest(),
            "request_secret_redacted": raw_request != sanitized,
            "headers_retained": False,
            "response_state": "NOT_OBSERVED",
        }
        captured, response = bytearray(), None
        started = time.monotonic()
        code = None
        try:
            response = self.inner.handle_request(request)
            record["http_status"] = response.status_code
            for part in response.iter_bytes():
                if len(captured) + len(part) > 128 * 1024:
                    record["response_state"] = "PARTIAL_OVER_LIMIT"
                    raise EvalError("DIAGNOSTIC_CAPTURE_LIMIT")
                captured.extend(part)
                if time.monotonic() - started >= 20:
                    record["response_state"] = "PARTIAL_TIMEOUT"
                    raise EvalError("DIAGNOSTIC_CAPTURE_TIMEOUT")
            record["response_state"] = "COMPLETE"
        except Exception:  # noqa: BLE001 -- no exception text or provider headers retained
            code = "DIAGNOSTIC_CAPTURE_FAILED"
            if record["response_state"] == "NOT_OBSERVED":
                record["response_state"] = "INCOMPLETE_OR_UNKNOWN"
        finally:
            if response is not None:
                response.close()
            body = clean(bytes(captured))
            record.update(
                response_sha256=hashlib.sha256(body).hexdigest(),
                response_secret_redacted=body != captured,
                original_entity_bytes_retained=body == captured,
                response_bytes=len(body),
                error=code,
            )
            private_file(str(prefix) + "-response.body", body)
            private_file(str(prefix) + "-capture.json", json.dumps(record, sort_keys=True).encode())
        if code:
            raise EvalError(code) from None
        # Decode once. Preserved bytes are pre-JSON HTTP entity bytes; redaction
        # affects only the private artifact, never the actual provider response.
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in {"content-encoding", "content-length"}
        }
        return httpx.Response(response.status_code, headers=headers, content=bytes(captured))

    def close(self):
        self.inner.close()
