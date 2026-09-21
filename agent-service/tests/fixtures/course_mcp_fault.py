"""Deliberately broken MCP peer, subprocess only. Never a runtime fallback."""

import json
import os
import sys

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from lecturelens_agent.course_mcp.server import tool_list

server = Server("lecturelens-course", version="test-fault")
mode = sys.argv[1]


@server.list_tools()
async def tools():
    return [] if mode == "catalog" else tool_list()


@server.call_tool()
async def call(name, args):
    fault = (
        mode.removeprefix("search_")
        if name != "get_course_revision" or not mode.startswith("search_")
        else "none"
    )
    if fault == "timeout":
        await anyio.sleep(60)
    if fault == "crash":
        os._exit(7)
    if fault == "error":
        return types.CallToolResult(
            isError=True, content=[types.TextContent(type="text", text="PRIVATE ERROR")]
        )
    result = {k: args[k] for k in ("owner_id", "course_id", "revision")} | {"evidence": []}
    if fault == "malformed":
        result["evidence"] = "not an Evidence array"
    if fault == "scope":
        result["revision"] += 1
    text = "{}" if fault == "mismatched_text" else json.dumps(result)
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], structuredContent=result)


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


anyio.run(main)
