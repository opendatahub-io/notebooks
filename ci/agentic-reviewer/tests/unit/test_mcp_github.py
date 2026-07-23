from __future__ import annotations

from dataclasses import dataclass

from odh_ci_agent import mcp_github


@dataclass(slots=True)
class ToolCallLike:
    name: str


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


def test_review_policies_allow_server_prefixed_and_bare_tool_names() -> None:
    server = mcp_github.make_review_server("token")
    policies = mcp_github.review_policies(server)
    allowed_tools = {policy_item.tool for policy_item in policies if policy_item.decision.name == "APPROVE"}

    assert "github/pull_request_read" in allowed_tools
    assert "mcp_github_pull_request_read" in allowed_tools
    assert "pull_request_read" in allowed_tools


def test_unexpected_tool_calls_returns_only_disallowed_names() -> None:
    tool_calls = [
        ToolCallLike(name="mcp_github_pull_request_read"),
        ToolCallLike(name="pull_request_read"),
        ToolCallLike(name="merge_pull_request"),
    ]

    assert mcp_github.tool_call_names(tool_calls) == [
        "mcp_github_pull_request_read",
        "pull_request_read",
        "merge_pull_request",
    ]
    assert mcp_github.prefixed_tool_name("github", "pull_request_read") == "mcp_github_pull_request_read"
    assert mcp_github.unexpected_tool_calls(
        tool_calls,
        mcp_github.GITHUB_REVIEW_TOOLS,
        server_name=mcp_github.GITHUB_REVIEW_SERVER_NAME,
    ) == ["merge_pull_request"]
