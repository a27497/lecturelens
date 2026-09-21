"""Run with python -m lecturelens_agent.course_mcp.server (stdio only).

No database, identity registry, signing key or Evidence cache. The exact signed
request is forwarded to Java, which checks ownership, revision and deletion.
"""

import json
import logging
import os

import anyio
import httpx
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import ValidationError

from ..study.authority import EvidenceAuthority, forward_signed
from ..study.store import StudyError
from .contracts import TOOLS, CourseResult, authority_payload


def tool_list():
    return [
        types.Tool(
            name=name,
            description=description,
            inputSchema=schema.model_json_schema(),
            outputSchema=CourseResult.model_json_schema(),
            annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        for name, (_, schema, description) in TOOLS.items()
    ]


def error_result(code):
    return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text=code)])


def create_server(java_url):
    # Reuse URL validation only; MCP never receives the Java signing secret.
    url = EvidenceAuthority(java_url, "").url
    server = Server("lecturelens-course", version="1.0.0")

    @server.list_tools()
    async def list_tools():
        return tool_list()

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        try:
            payload, proof = authority_payload(name, arguments)
        except (KeyError, ValidationError, TypeError):
            return error_result("MCP_INVALID_REQUEST")
        try:
            result = await anyio.to_thread.run_sync(
                forward_signed,
                url,
                payload,
                proof["timestamp"],
                proof["signature"],
                abandon_on_cancel=True,
            )
            CourseResult.model_validate(result)
        except StudyError as error:
            return error_result(error.code)
        except httpx.TimeoutException:
            return error_result("MCP_AUTHORITY_TIMEOUT")
        except httpx.HTTPError:
            return error_result("MCP_AUTHORITY_UNAVAILABLE")
        except (ValidationError, ValueError, KeyError, TypeError, AttributeError):
            return error_result("MCP_MALFORMED_AUTHORITY_RESPONSE")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
            structuredContent=result,
            isError=False,
        )

    return server


async def main():
    server = create_server(os.environ.get("AGENT_JAVA_BASE_URL", "http://127.0.0.1:8080"))
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)  # stdout is exclusively MCP JSON-RPC
    anyio.run(main)
