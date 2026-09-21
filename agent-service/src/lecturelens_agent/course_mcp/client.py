"""Synchronous Authority interface over one reusable official MCP stdio session."""

import json
import sys
import threading
import time
from contextlib import ExitStack, asynccontextmanager
from datetime import timedelta

import anyio
from anyio.from_thread import start_blocking_portal
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from pydantic import ValidationError

from ..study.authority import AUTHORITY_PATH, EvidenceAuthority, request_body, signature
from ..study.store import StudyError
from .contracts import ACTION_TO_TOOL, TOOLS, CourseResult, authority_payload

ERRORS = {
    "COURSE_UNAVAILABLE_OR_CHANGED",
    "EVIDENCE_SCOPE_MISMATCH",
    "MCP_INVALID_REQUEST",
    "MCP_AUTHORITY_TIMEOUT",
    "MCP_AUTHORITY_UNAVAILABLE",
    "MCP_MALFORMED_AUTHORITY_RESPONSE",
}


def failure(error):
    if isinstance(error, BaseExceptionGroup):
        return failure(error.exceptions[0])
    if isinstance(error, StudyError):
        return error
    if isinstance(error, (TimeoutError,)) or isinstance(error, McpError) and error.error.code == 408:
        return StudyError("MCP_TIMEOUT", 503)
    if isinstance(error, (ValidationError, ValueError)):
        return StudyError("MCP_MALFORMED_RESPONSE", 503)
    return StudyError("MCP_SERVER_UNAVAILABLE", 503)


class McpEvidenceAuthority:
    transport = "mcp-stdio"

    def __init__(self, java_url, secret, *, timeout=10.0, parameters=None, observer=None):
        url = EvidenceAuthority(java_url, secret).url
        if not 0.05 <= timeout <= 30:
            raise ValueError("MCP timeout must be between 0.05 and 30 seconds")
        self.secret, self.timeout, self.observer = secret, timeout, observer
        self.parameters = parameters or StdioServerParameters(
            command=sys.executable,
            args=["-m", "lecturelens_agent.course_mcp.server"],
            # The SDK adds only its safe OS environment allowlist, not parent credentials.
            env={"AGENT_JAVA_BASE_URL": url},
        )
        self._lock, self._peer, self._closed = threading.Lock(), None, False

    @asynccontextmanager
    async def _connect(self):
        async with stdio_client(self.parameters) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=self.timeout)
            ) as session:
                with anyio.fail_after(self.timeout):
                    initialized = await session.initialize()
                    catalog = await session.list_tools()
                    if initialized.serverInfo.name != "lecturelens-course" or catalog.nextCursor:
                        raise StudyError("MCP_CONTRACT_MISMATCH", 503)
                    offered = {tool.name: tool for tool in catalog.tools}
                    if len(catalog.tools) != len(TOOLS) or set(offered) != set(TOOLS):
                        raise StudyError("MCP_CONTRACT_MISMATCH", 503)
                    for name, (_, schema, _) in TOOLS.items():
                        if (
                            offered[name].inputSchema != schema.model_json_schema()
                            or offered[name].outputSchema != CourseResult.model_json_schema()
                        ):
                            raise StudyError("MCP_CONTRACT_MISMATCH", 503)
                    if self.observer:
                        self.observer(
                            {
                                "event": "initialize",
                                "protocol_version": initialized.protocolVersion,
                                "server": initialized.serverInfo.model_dump(),
                                "tools": sorted(offered),
                            }
                        )
                yield session

    def _connection(self):
        with self._lock:
            if self._closed:
                raise StudyError("MCP_SERVER_UNAVAILABLE", 503)
            if self._peer is None:
                stack = ExitStack()
                try:
                    portal = stack.enter_context(start_blocking_portal())
                    session = stack.enter_context(portal.wrap_async_context_manager(self._connect()))
                    self._peer = (stack, portal, session)
                except Exception as error:  # noqa: BLE001 -- redact SDK/transport exceptions at the StudyError boundary
                    stack.close()
                    raise failure(error) from None
            return self._peer

    def _discard(self, peer):
        with self._lock:
            if self._peer is not peer:
                return
            self._peer = None
        try:
            peer[0].close()
        except Exception:  # noqa: BLE001 -- failed transport is already fenced; cleanup never masks its error
            pass

    def close(self):
        with self._lock:
            self._closed = True
            peer = self._peer
        if peer:
            self._discard(peer)

    async def _call(self, session, name, arguments):
        with anyio.fail_after(self.timeout):
            try:
                response = await session.call_tool(name, arguments)
            except RuntimeError:
                # SDK output-schema validation can include private response text; never expose it.
                raise StudyError("MCP_MALFORMED_RESPONSE", 503) from None
        if response.isError:
            code = (
                response.content[0].text
                if len(response.content) == 1 and isinstance(response.content[0], types.TextContent)
                else ""
            )
            raise StudyError(
                code if code in ERRORS else "MCP_TOOL_FAILED",
                409 if code in {"COURSE_UNAVAILABLE_OR_CHANGED", "EVIDENCE_SCOPE_MISMATCH"} else 503,
            )
        data = response.structuredContent
        CourseResult.model_validate(data)
        if (
            len(response.content) != 1
            or not isinstance(response.content[0], types.TextContent)
            or json.loads(response.content[0].text) != data
        ):
            raise StudyError("MCP_MALFORMED_RESPONSE", 503)
        return data

    def read(self, scope, action="CHECK", **arguments):
        if action not in ACTION_TO_TOOL or set(arguments) & {
            "owner_id",
            "course_id",
            "revision",
            "authorization",
            "action",
        }:
            raise StudyError("MCP_INVALID_REQUEST", 422)
        name = ACTION_TO_TOOL[action]
        payload = {k: scope[k] for k in ("owner_id", "course_id", "revision")} | {
            "action": action,
            **arguments,
        }
        peer = None
        started = time.monotonic()
        code = None
        result = None
        try:
            peer = self._connection()
            timestamp = str(int(time.time()))
            args = {k: v for k, v in payload.items() if k != "action"} | {
                "authorization": {
                    "timestamp": timestamp,
                    "signature": signature(self.secret, timestamp, request_body(payload), AUTHORITY_PATH),
                }
            }
            authority_payload(name, args)  # shape validation; authorization is exclusively Java's job
            result = peer[1].call(self._call, peer[2], name, args)
            if any(result[k] != scope[k] for k in ("owner_id", "course_id", "revision")):
                raise StudyError("EVIDENCE_SCOPE_MISMATCH")
            return result
        except Exception as error:  # noqa: BLE001 -- redact SDK/transport exceptions at the StudyError boundary
            mapped = failure(error)
            code = mapped.code
            if peer and code.startswith("MCP_"):
                self._discard(peer)
            raise mapped from None
        finally:
            if self.observer:
                self.observer(
                    {
                        "event": "tools/call",
                        "tool": name,
                        "action": action,
                        "duration_ms": round((time.monotonic() - started) * 1000, 3),
                        "error_code": code,
                        "evidence_ids": [e["evidence_id"] for e in (result or {}).get("evidence", [])],
                    }
                )
