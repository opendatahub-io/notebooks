"""Shared GitHub MCP configuration for Antigravity CI agents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from google.antigravity.hooks import policy
from google.antigravity.types import BaseMcpServerConfig, McpStreamableHttpServer, ToolCall

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

GITHUB_MCP_BASE_URL = "https://api.githubcopilot.com/mcp"
GITHUB_MCP_PULL_REQUESTS_URL = f"{GITHUB_MCP_BASE_URL}/x/pull_requests"
GITHUB_MCP_ACTIONS_READONLY_URL = f"{GITHUB_MCP_BASE_URL}/x/actions/readonly"

GITHUB_REVIEW_SERVER_NAME = "github"
GITHUB_ACTIONS_SERVER_NAME = "github_actions"

# Harness builtins that wrap remote MCP calls in localharness.
HARNESS_CALL_MCP_TOOL = "call_mcp_tool"
HARNESS_LIST_RESOURCES = "list_resources"

PULL_REQUEST_READ_METHODS = (
    "get",
    "get_diff",
    "get_status",
    "get_files",
    "get_commits",
    "get_review_comments",
    "get_reviews",
    "get_comments",
    "get_check_runs",
)

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


def parse_github_repository(repository: str) -> tuple[str, str]:
    """Split ``owner/repo`` into owner and repository name."""

    owner, separator, repo = repository.partition("/")
    if not owner or not separator or not repo:
        raise ValueError(f"Invalid GitHub repository slug: {repository!r}")
    return owner, repo


def prefixed_tool_name(server_name: str, tool_name: str) -> str:
    """Return the SDK-visible MCP tool name for a server/tool pair."""

    return f"{MCP_TOOL_PREFIX}_{server_name}_{tool_name}"


def prefixed_tool_names(server_name: str, tool_names: Sequence[str]) -> tuple[str, ...]:
    """Return the SDK-visible MCP tool names for a server/tool set."""

    return tuple(prefixed_tool_name(server_name, tool_name) for tool_name in tool_names)


class NamedToolCall(Protocol):
    """Minimal tool-call protocol used for logging and auditing."""

    @property
    def name(self) -> str: ...

    @property
    def args(self) -> Mapping[str, Any]: ...

    @property
    def server_name(self) -> str | None: ...


def _arg_str(args: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def resolve_mcp_target(tool_call: NamedToolCall) -> tuple[str | None, str | None]:
    """Return the MCP server and tool targeted by a harness or direct tool call."""

    args = tool_call.args or {}
    server_name = tool_call.server_name or _arg_str(args, "ServerName", "server_name")
    if tool_call.name == HARNESS_LIST_RESOURCES:
        return server_name, HARNESS_LIST_RESOURCES
    if tool_call.name == HARNESS_CALL_MCP_TOOL:
        return server_name, _arg_str(args, "ToolName", "tool_name")
    return server_name, tool_call.name


def allows_harness_mcp_call(server_name: str, allowed_tools: Sequence[str]):
    """Return a policy predicate for scoped ``call_mcp_tool`` harness calls."""

    allowed = frozenset(allowed_tools)

    def _when(tool_call: ToolCall) -> bool:
        if tool_call.name != HARNESS_CALL_MCP_TOOL:
            return False
        target_server, target_tool = resolve_mcp_target(tool_call)
        return target_server == server_name and target_tool in allowed

    return _when


def allows_harness_list_resources(server_name: str):
    """Return a policy predicate for scoped ``list_resources`` harness calls."""

    def _when(tool_call: ToolCall) -> bool:
        if tool_call.name != HARNESS_LIST_RESOURCES:
            return False
        target_server, _ = resolve_mcp_target(tool_call)
        return target_server == server_name

    return _when


def is_permitted_tool_call(
    tool_call: NamedToolCall,
    allowed_tools: Sequence[str],
    *,
    server_name: str | None = None,
    allow_list_resources: bool = True,
) -> bool:
    """Return whether a completed tool call stayed within the allowed MCP surface."""

    target_server, target_tool = resolve_mcp_target(tool_call)
    if tool_call.name == HARNESS_LIST_RESOURCES:
        return allow_list_resources and target_server == server_name

    allowed = set(allowed_tools)
    if server_name is not None:
        allowed.update(prefixed_tool_names(server_name, allowed_tools))

    if tool_call.name in allowed:
        return True
    return target_server == server_name and target_tool in allowed_tools


def invoked_mcp_tools(
    tool_calls: Iterable[NamedToolCall],
    allowed_tools: Sequence[str],
    *,
    server_name: str,
) -> list[str]:
    """Return allowed MCP tool ids invoked during a run."""

    invoked: list[str] = []
    for tool_call in tool_calls:
        target_server, target_tool = resolve_mcp_target(tool_call)
        if target_tool == HARNESS_LIST_RESOURCES:
            continue
        if target_server == server_name and target_tool is not None and target_tool in allowed_tools:
            invoked.append(target_tool)
        elif tool_call.name in allowed_tools:
            invoked.append(tool_call.name)
    return invoked


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
    *,
    allow_list_resources: bool = True,
) -> list[policy.Policy]:
    """Allow MCP tools via SDK targets and localharness wrapper builtins."""

    policies: list[policy.Policy] = list(policy.allow(server, tool_names))
    policies.append(
        policy.allow(
            HARNESS_CALL_MCP_TOOL,
            when=allows_harness_mcp_call(server.name, tool_names),
            name=f"allow_{server.name}_call_mcp_tool",
        )
    )
    if allow_list_resources:
        policies.append(
            policy.allow(
                HARNESS_LIST_RESOURCES,
                when=allows_harness_list_resources(server.name),
                name=f"allow_{server.name}_list_resources",
            )
        )
    return policies


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
    allow_list_resources: bool = True,
) -> list[str]:
    """Return invoked tool names that are not in the allowed set."""

    if server_name is None:
        return sorted({tool_call.name for tool_call in tool_calls if tool_call.name not in set(allowed_tools)})
    return sorted(
        {
            tool_call.name
            for tool_call in tool_calls
            if not is_permitted_tool_call(
                tool_call,
                allowed_tools,
                server_name=server_name,
                allow_list_resources=allow_list_resources,
            )
        }
    )
