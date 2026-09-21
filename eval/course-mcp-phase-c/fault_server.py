"""Acceptance-only malformed SEARCH response, after the REAL Java authority call.

Never selected by app configuration. The normal server has no fault switch.
"""

import os

import anyio
from mcp import types
from mcp.server.stdio import stdio_server

from lecturelens_agent.course_mcp.server import create_server

server = create_server(os.environ["AGENT_JAVA_BASE_URL"])
original = server.request_handlers[types.CallToolRequest]


async def corrupt(request):
    result = await original(request)
    if request.params.name == "search_course_evidence" and not result.root.isError:
        return types.ServerResult(
            types.CallToolResult(
                structuredContent={"evidence": "malformed acceptance fixture"},
                content=[types.TextContent(type="text", text="{}")],
            )
        )
    return result


server.request_handlers[types.CallToolRequest] = corrupt


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


anyio.run(main)
