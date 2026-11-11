"""Scoped reads must fail at old authorities before a whole-course retrieval occurs."""

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lecturelens_agent.course_mcp.client import McpEvidenceAuthority
from lecturelens_agent.study.authority import (
    AUTHORITY_PATH,
    SCOPED_AUTHORITY_PATH,
    EvidenceAuthority,
    signature,
)
from lecturelens_agent.study.store import StudyError

SECRET = "test-scoped-transport-path-secret-32bytes"
SCOPE = {
    "owner_id": 42,
    "course_id": "course",
    "revision": 1,
    "learning_scope": {
        "version": 1,
        "kind": "segments",
        "policy": "strict",
        "revision": 1,
        "evidence_ids": ["e1"],
    },
}


@pytest.fixture
def authority_server():
    state = {"legacy": False, "requests": [], "retrievals": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            payload = json.loads(body)
            state["requests"].append((self.path, payload))
            valid = hmac.compare_digest(
                self.headers.get("X-LectureLens-Signature", ""),
                signature(SECRET, self.headers["X-LectureLens-Timestamp"], body, self.path),
            )
            if not valid:
                status, result = 401, {}
            elif state["legacy"] and self.path == SCOPED_AUTHORITY_PATH:
                status, result = 404, {}
            else:
                status = 200
                result = {key: payload[key] for key in ("owner_id", "course_id", "revision")}
                if "learning_scope" in payload and not state["legacy"]:
                    result["learning_scope"] = payload["learning_scope"]
                if payload["action"] != "CHECK":
                    state["retrievals"] += 1
                result["evidence"] = []
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"data": result}).encode())

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize("factory", [EvidenceAuthority, McpEvidenceAuthority])
def test_scoped_path_and_signature_survive_direct_and_mcp_transport(authority_server, factory):
    url, state = authority_server
    client = factory(url, SECRET)
    try:
        for scope, expected in [
            (SCOPE, SCOPED_AUTHORITY_PATH),
            (SCOPE | {"learning_scope": None}, AUTHORITY_PATH),
        ]:
            client.read(scope)
            assert state["requests"][-1][0] == expected
        client.read(SCOPE, "SEARCH", query="condition")
        assert state["requests"][-1][0] == SCOPED_AUTHORITY_PATH
        assert state["requests"][-1][1]["learning_scope"] == SCOPE["learning_scope"]
    finally:
        if hasattr(client, "close"):
            client.close()


@pytest.mark.parametrize("factory", [EvidenceAuthority, McpEvidenceAuthority])
def test_authority_downgrade_after_check_never_retrieves_or_falls_back(authority_server, factory):
    url, state = authority_server
    client = factory(url, SECRET)
    try:
        client.read(SCOPE)  # The first request can reach a compatible instance.
        state["legacy"] = True
        with pytest.raises(StudyError, match="COURSE_UNAVAILABLE_OR_CHANGED"):
            client.read(SCOPE, "SEARCH", query="outside topic")
        assert state["retrievals"] == 0
        assert [path for path, _ in state["requests"]] == [SCOPED_AUTHORITY_PATH] * 2
    finally:
        if hasattr(client, "close"):
            client.close()
