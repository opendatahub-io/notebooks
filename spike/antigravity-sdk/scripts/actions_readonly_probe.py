#!/usr/bin/env python3
"""Probe the GitHub Actions readonly MCP tool exposure."""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass

from google.antigravity.mcp.bridge import McpBridge
from google.antigravity.types import McpStreamableHttpServer


@dataclass(slots=True)
class ProbeResult:
    enabled_tools: list[str]
    exposed_tools: list[str]
    server_name: str
    url: str


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise SystemExit(f"Missing required environment variable: {name}")


def tool_name(tool: object) -> str:
    for attr in ("name", "tool_name", "__name__"):
        value = getattr(tool, attr, None)
        if isinstance(value, str):
            return value
    fn = getattr(tool, "fn", None)
    fn_name = getattr(fn, "__name__", None)
    if isinstance(fn_name, str):
        return fn_name
    nested_tool = getattr(tool, "tool", None)
    nested_name = getattr(nested_tool, "name", None)
    if isinstance(nested_name, str):
        return nested_name
    raise TypeError(f"Could not determine tool name from {type(tool).__name__}")


async def run_probe() -> ProbeResult:
    enabled_tools = ["actions_get", "get_job_logs"]
    server = McpStreamableHttpServer(
        name="github_actions",
        url="https://api.githubcopilot.com/mcp/x/actions/readonly",
        headers={"Authorization": f"Bearer {required_env('GITHUB_TOKEN')}"},
        enabled_tools=enabled_tools,
    )

    bridge = McpBridge()
    await bridge.connect(server)
    try:
        exposed_tools = sorted(tool_name(tool) for tool in bridge.tools)
        return ProbeResult(
            enabled_tools=enabled_tools,
            exposed_tools=exposed_tools,
            server_name=server.name,
            url=server.url,
        )
    finally:
        await bridge.stop()


def main() -> None:
    result = asyncio.run(run_probe())
    print(asdict(result))


if __name__ == "__main__":
    main()
