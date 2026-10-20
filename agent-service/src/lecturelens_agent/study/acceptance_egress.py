"""Separate loopback acceptance proxy. Only this process may hold a provider key.

The application does not start this proxy or select this provider automatically.
Fake upstreams need no credentials. Constructing OfficialSender requires an
explicit live policy, which this offline task never installs.
"""

import hmac
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import httpx

from .acceptance_cost import MAX_BODY, UPSTREAM, CostDenied, routes
from .models import RoutedProvider
from .provider import ChatProvider


class OfficialSender:
    def __init__(self, ledger, credential):
        policy = ledger.snapshot()["envelope"]["policy"]
        if policy["mode"] != "live" or not policy["authorization_id"] or not credential:
            raise CostDenied("COST_LIVE_AUTHORIZATION_REQUIRED")
        self.credential = credential

    def __call__(self, packed, timeout):
        deadline = time.monotonic() + timeout
        # No discovery/probe, redirect, environment proxy or transport retry.
        with httpx.Client(
            transport=httpx.HTTPTransport(retries=0, trust_env=False),
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            with client.stream(
                "POST",
                UPSTREAM,
                content=packed,
                headers={"Authorization": "Bearer " + self.credential, "Content-Type": "application/json"},
            ) as response:
                data = bytearray()
                for piece in response.iter_bytes():
                    data.extend(piece)
                    if len(data) > 128 * 1024 or time.monotonic() >= deadline:
                        raise CostDenied("COST_UPSTREAM_OUTCOME_UNKNOWN")
                return httpx.Response(response.status_code, content=bytes(data))


class CostGateway:
    def __init__(self, ledger, sender):
        self.ledger, self.sender = ledger, sender

    def forward(self, run_id, purpose, raw):
        claim, packed = self.ledger.admit(run_id, purpose, raw)
        timeout = self.ledger.dispatch(claim)
        try:
            response = self.sender(packed, max(0.001, timeout))
            if response.status_code != 200 or len(response.content) > 128 * 1024:
                raise CostDenied("COST_UPSTREAM_OUTCOME_UNKNOWN")
            try:
                data = response.json()
            except ValueError:
                data = None
        except Exception:  # noqa: BLE001 -- no request/response text escapes this process
            self.ledger.settle(claim, None, "COST_UPSTREAM_OUTCOME_UNKNOWN")
            raise AssertionError("settle must reject unknown outcome") from None
        self.ledger.settle(claim, data)
        return response.content


@contextmanager
def serve_gateway(gateway, token):
    """Loopback HTTP only; an opaque local token is unrelated to provider auth."""
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("An independent local capability is required")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Default access logging would expose paths and errors.

        def respond(self, status, body):
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # Client cancellation cannot refund a possibly billable send.
                pass

    def post(handler):
        run_id = None
        try:
            if not hmac.compare_digest(handler.headers.get("Authorization", ""), "Bearer " + token):
                gateway.ledger.deny("COST_LOCAL_AUTH_REQUIRED")
            path = urlsplit(handler.path)
            parts = path.path.strip("/").split("/")
            if (
                len(parts) != 5
                or parts[0] != "runs"
                or parts[3:] != ["chat", "completions"]
                or parts[2] not in {"decision", "review"}
                or path.query
                or path.fragment
            ):
                gateway.ledger.deny("COST_LOCAL_PATH_NOT_ALLOWED")
            run_id, purpose = parts[1:3]
            if handler.headers.get("Transfer-Encoding"):
                gateway.ledger.deny("COST_INPUT_LIMIT", run_id)
            try:
                length = int(handler.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 0 < length <= MAX_BODY:
                gateway.ledger.deny("COST_INPUT_LIMIT", run_id)
            handler.connection.settimeout(5)
            body = handler.rfile.read(length)
            if len(body) != length:
                gateway.ledger.deny("COST_INPUT_LIMIT", run_id)
            result = gateway.forward(run_id, purpose, body)
        except CostDenied as error:
            handler.respond(403, json.dumps({"error": error.code}).encode())
        except Exception:  # noqa: BLE001 -- never emit raw private payloads or DB/HTTP errors
            handler.respond(503, b'{"error":"COST_GATE_UNAVAILABLE"}')
        else:
            handler.respond(200, result)

    Handler.do_POST = post
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class AcceptanceProvider:
    mode = "real"

    def __init__(self, proxy_url, local_token):
        address = urlsplit(proxy_url)
        if address.scheme != "http" or address.hostname != "127.0.0.1" or address.path:
            raise CostDenied("COST_LOOPBACK_PROXY_REQUIRED")
        self.proxy_url, self.local_token = proxy_url, local_token

    def for_run(self, run):
        config = run.get("model_config")
        routes(config)  # No environment fallback or silent reviewer substitution.
        provider = object.__new__(RoutedProvider)
        provider.config = config
        provider.clients = {
            role: ChatProvider(
                base_url=f"{self.proxy_url}/runs/{run['run_id']}/{role}",
                model=route["model"],
                api_key=self.local_token,
            )
            for role, route in config.items()
        }
        return provider
