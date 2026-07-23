from __future__ import annotations

import asyncio
from dataclasses import dataclass

from google.antigravity.hooks import policy
from google.antigravity.types import ToolCall

from odh_ci_agent import mcp_github


@dataclass(slots=True)
class ToolCallLike:
    name: str
    args: dict[str, object] | None = None
    server_name: str | None = None


def test_make_review_server_uses_enabled_tools() -> None:
    server = mcp_github.make_review_server("token")

    assert server.name == mcp_github.GITHUB_REVIEW_SERVER_NAME
    assert server.url == mcp_github.GITHUB_MCP_PULL_REQUESTS_URL
    assert server.enabled_tools == list(mcp_github.GITHUB_REVIEW_TOOLS)
    assert server.headers == {"Authorization": "Bearer token"}


def test_make_review_server_can_add_defense_in_depth_header() -> None:
    server = mcp_github.make_review_server("token", defense_in_depth_exclude_header=True)

    assert server.headers is not None
    assert "X-MCP-Exclude-Tools" in server.headers


def test_make_actions_readonly_server_uses_enabled_tools() -> None:
    server = mcp_github.make_actions_readonly_server("token")

    assert server.name == mcp_github.GITHUB_ACTIONS_SERVER_NAME
    assert server.url == mcp_github.GITHUB_MCP_ACTIONS_READONLY_URL
    assert server.enabled_tools == list(mcp_github.GITHUB_ACTIONS_READ_TOOLS)


def test_review_policies_allow_server_tool_targets() -> None:
    server = mcp_github.make_review_server("token")
    policies = mcp_github.review_policies(server)
    allowed_tools = {policy_item.tool for policy_item in policies if policy_item.decision.name == "APPROVE"}

    assert allowed_tools == {
        "github/pull_request_read",
        "github/pull_request_review_write",
        "github/add_comment_to_pending_review",
        mcp_github.HARNESS_CALL_MCP_TOOL,
        mcp_github.HARNESS_LIST_RESOURCES,
    }


def test_review_policies_allow_harness_call_mcp_tool_from_trajectory() -> None:
    server = mcp_github.make_review_server("token")
    hook = policy.enforce(mcp_github.review_policies(server), mcp_servers=[server])

    async def allowed() -> bool:
        tool_call = ToolCall(
            name=mcp_github.HARNESS_CALL_MCP_TOOL,
            args={
                "ServerName": mcp_github.GITHUB_REVIEW_SERVER_NAME,
                "ToolName": "pull_request_read",
                "Arguments": {
                    "owner": "opendatahub-io",
                    "repo": "notebooks",
                    "pullNumber": 3806,
                    "method": "get",
                },
            },
        )
        result = await hook.run(None, tool_call)
        return result.allow

    assert asyncio.run(allowed()) is True


def test_review_policies_allow_harness_list_resources() -> None:
    server = mcp_github.make_review_server("token")
    hook = policy.enforce(mcp_github.review_policies(server), mcp_servers=[server])

    async def allowed() -> bool:
        tool_call = ToolCall(
            name=mcp_github.HARNESS_LIST_RESOURCES,
            args={"ServerName": mcp_github.GITHUB_REVIEW_SERVER_NAME},
        )
        result = await hook.run(None, tool_call)
        return result.allow

    assert asyncio.run(allowed()) is True


def test_review_policies_deny_harness_call_mcp_tool_for_disallowed_remote_tool() -> None:
    server = mcp_github.make_review_server("token")
    hook = policy.enforce(mcp_github.review_policies(server), mcp_servers=[server])

    async def denied() -> bool:
        tool_call = ToolCall(
            name=mcp_github.HARNESS_CALL_MCP_TOOL,
            args={
                "ServerName": mcp_github.GITHUB_REVIEW_SERVER_NAME,
                "ToolName": "merge_pull_request",
            },
        )
        result = await hook.run(None, tool_call)
        return result.allow

    assert asyncio.run(denied()) is False


def test_unexpected_tool_calls_returns_only_disallowed_names() -> None:
    tool_calls = [
        ToolCallLike(
            name=mcp_github.HARNESS_CALL_MCP_TOOL,
            args={
                "ServerName": mcp_github.GITHUB_REVIEW_SERVER_NAME,
                "ToolName": "pull_request_read",
            },
        ),
        ToolCallLike(
            name=mcp_github.HARNESS_CALL_MCP_TOOL,
            args={
                "ServerName": mcp_github.GITHUB_REVIEW_SERVER_NAME,
                "ToolName": "merge_pull_request",
            },
        ),
        ToolCallLike(name="pull_request_read", server_name=mcp_github.GITHUB_REVIEW_SERVER_NAME),
    ]

    assert mcp_github.tool_call_names(tool_calls) == [
        mcp_github.HARNESS_CALL_MCP_TOOL,
        mcp_github.HARNESS_CALL_MCP_TOOL,
        "pull_request_read",
    ]
    assert mcp_github.prefixed_tool_name("github", "pull_request_read") == "mcp_github_pull_request_read"
    assert mcp_github.unexpected_tool_calls(
        tool_calls,
        mcp_github.GITHUB_REVIEW_TOOLS,
        server_name=mcp_github.GITHUB_REVIEW_SERVER_NAME,
    ) == [mcp_github.HARNESS_CALL_MCP_TOOL]


def test_invoked_mcp_tools_counts_harness_wrapped_calls() -> None:
    tool_calls = [
        ToolCallLike(
            name=mcp_github.HARNESS_LIST_RESOURCES,
            args={"ServerName": mcp_github.GITHUB_REVIEW_SERVER_NAME},
        ),
        ToolCallLike(
            name=mcp_github.HARNESS_CALL_MCP_TOOL,
            args={
                "ServerName": mcp_github.GITHUB_REVIEW_SERVER_NAME,
                "ToolName": "pull_request_read",
            },
        ),
    ]

    assert mcp_github.invoked_mcp_tools(
        tool_calls,
        mcp_github.GITHUB_REVIEW_TOOLS,
        server_name=mcp_github.GITHUB_REVIEW_SERVER_NAME,
    ) == ["pull_request_read"]
