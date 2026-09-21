import hashlib
import hmac
import json
import os
import time

import httpx

from .store import StudyError

AUDIENCE = "lecturelens-study-v1"
AUTHORITY_PATH = "/internal/v1/study/evidence"
COMMAND_PATH = "/internal/v1/study/command"


def signature(secret, timestamp, body, path):
    message = f"{AUDIENCE}\nPOST\n{path}\n{timestamp}\n{hashlib.sha256(body).hexdigest()}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def request_body(payload):
    # Stable bytes let MCP forward the Agent's signature without holding its key.
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()


def forward_signed(url, payload, timestamp, signed):
    """Same Java endpoint and scope check for direct and MCP transports."""
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
        response = client.post(
            url.rstrip("/") + AUTHORITY_PATH,
            content=request_body(payload),
            headers={
                "Content-Type": "application/json",
                "X-LectureLens-Timestamp": timestamp,
                "X-LectureLens-Signature": signed,
            },
        )
    if response.status_code in (401, 403, 404, 409):
        raise StudyError("COURSE_UNAVAILABLE_OR_CHANGED")
    response.raise_for_status()
    result = response.json()["data"]
    if any(result.get(k) != payload[k] for k in ("owner_id", "course_id", "revision")):
        raise StudyError("EVIDENCE_SCOPE_MISMATCH")
    return result


class EvidenceAuthority:
    def __init__(self, url, secret):
        if not url.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
            raise RuntimeError("Invalid AGENT_JAVA_BASE_URL")
        self.url, self.secret = url.rstrip("/"), secret

    def read(self, scope, action="CHECK", **arguments):
        payload = {
            "owner_id": scope["owner_id"],
            "course_id": scope["course_id"],
            "revision": scope["revision"],
            "action": action,
            **arguments,
        }
        body = request_body(payload)
        timestamp = str(int(time.time()))
        return forward_signed(
            self.url, payload, timestamp, signature(self.secret, timestamp, body, AUTHORITY_PATH)
        )


def course_authority(url, secret):
    transport = os.environ.get("AGENT_COURSE_TOOL_TRANSPORT", "internal")
    if transport == "internal":
        return EvidenceAuthority(url, secret)
    if transport == "mcp":
        from ..course_mcp.client import McpEvidenceAuthority

        return McpEvidenceAuthority(url, secret)
    raise RuntimeError("AGENT_COURSE_TOOL_TRANSPORT must be internal or mcp")
