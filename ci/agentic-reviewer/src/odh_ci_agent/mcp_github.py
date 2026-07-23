"""Shared GitHub MCP configuration for Antigravity CI agents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from google.antigravity.hooks import policy
from google.antigravity.types import BaseMcpServerConfig, McpStreamableHttpServer

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

GITHUB_MCP_BASE_URL = "https://api.githubcopilot.com/mcp"
GITHUB_MCP_PULL_REQUESTS_URL = f"{GITHUB_MCP_BASE_URL}/x/pull_requests"
GITHUB_MCP_ACTIONS_READONLY_URL = f"{GITHUB_MCP_BASE_URL}/x/actions/readonly"

GITHUB_REVIEW_SERVER_NAME = "github"
GITHUB_ACTIONS_SERVER_NAME = "github_actions"

GITHUB_REVIEW_TOOLS = (
    "pull_request_read",
    "pull_request_review_write",
    "add_comment_to_pending_review",
)

GITHUB_ACTIONS_READ_TOOLS = (
    "actions_get",
    "get_job_logs",
)

# The SDK now supports per-server MCP allowlists. Keep the remote denylist only as
# optional server-side defense in depth for environments where the remote MCP
# still exposes more tools than expected.
GITHUB_REVIEW_DISABLED_TOOLS = (
    "merge_pull_request",
    "create_pull_request",
    "update_pull_request",
    "update_pull_request_branch",
    "list_pull_requests",
    "search_pull_requests",
    "add_reply_to_pull_request_comment",
)

MCP_TOOL_PREFIX = "mcp"


def prefixed_tool_name(server_name: str, tool_name: str) -> str:
    """Return the SDK-visible MCP tool name for a server/tool pair."""

    return f"{MCP_TOOL_PREFIX}_{server_name}_{tool_name}"


def prefixed_tool_names(server_name: str, tool_names: Sequence[str]) -> tuple[str, ...]:
    """Return the SDK-visible MCP tool names for a server/tool set."""

    return tuple(prefixed_tool_name(server_name, tool_name) for tool_name in tool_names)


class NamedToolCall(Protocol):
    """Minimal tool-call protocol used for logging and auditing."""

    name: str


def build_auth_headers(token: str, *, exclude_tools: Sequence[str] | None = None) -> dict[str, str]:
    """Build remote GitHub MCP headers for bearer auth."""

    headers = {"Authorization": f"Bearer {token}"}
    if exclude_tools:
        headers["X-MCP-Exclude-Tools"] = ",".join(exclude_tools)
    return headers


def make_review_server(
    token: str,
    *,
    defense_in_depth_exclude_header: bool = False,
) -> McpStreamableHttpServer:
    """Return the pull-request MCP config used by CI review agents."""

    exclude_tools = GITHUB_REVIEW_DISABLED_TOOLS if defense_in_depth_exclude_header else None
    return McpStreamableHttpServer(
        name=GITHUB_REVIEW_SERVER_NAME,
        url=GITHUB_MCP_PULL_REQUESTS_URL,
        headers=build_auth_headers(token, exclude_tools=exclude_tools),
        enabled_tools=list(GITHUB_REVIEW_TOOLS),
    )


def make_actions_readonly_server(token: str) -> McpStreamableHttpServer:
    """Return the read-only actions MCP config used by CI summarizers."""

    return McpStreamableHttpServer(
        name=GITHUB_ACTIONS_SERVER_NAME,
        url=GITHUB_MCP_ACTIONS_READONLY_URL,
        headers=build_auth_headers(token),
        enabled_tools=list(GITHUB_ACTIONS_READ_TOOLS),
    )


def tool_allow_policies(
    server: BaseMcpServerConfig,
    tool_names: Sequence[str],
) -> list[policy.Policy]:
    """Allow MCP tools using the SDK ``server/tool`` policy target format."""

    return list(policy.allow(server, tool_names))


def review_policies(server: BaseMcpServerConfig) -> list[policy.Policy]:
    """Deny by default and allow only PR review MCP tools."""

    return [policy.deny_all(), *tool_allow_policies(server, GITHUB_REVIEW_TOOLS)]


def actions_read_policies(server: BaseMcpServerConfig) -> list[policy.Policy]:
    """Deny by default and allow only read-only GitHub Actions MCP tools."""

    return [policy.deny_all(), *tool_allow_policies(server, GITHUB_ACTIONS_READ_TOOLS)]


def tool_call_names(tool_calls: Iterable[NamedToolCall]) -> list[str]:
    """Return the invoked tool names in call order."""

    return [tool_call.name for tool_call in tool_calls]


def unexpected_tool_calls(
    tool_calls: Iterable[NamedToolCall],
    allowed_tools: Sequence[str],
    *,
    server_name: str | None = None,
) -> list[str]:
    """Return invoked tool names that are not in the allowed set."""

    allowed = set(allowed_tools)
    if server_name is not None:
        allowed.update(prefixed_tool_names(server_name, allowed_tools))
    return sorted({tool_call.name for tool_call in tool_calls if tool_call.name not in allowed})
