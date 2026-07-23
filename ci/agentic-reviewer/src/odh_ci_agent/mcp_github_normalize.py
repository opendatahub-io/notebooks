"""Normalize agent-friendly GitHub MCP arguments before remote execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.antigravity.hooks import hooks
from google.antigravity.hooks.hooks import HookContext, HookResult
from google.antigravity.types import ToolCall

from odh_ci_agent.mcp_github import (
    GITHUB_REVIEW_SERVER_NAME,
    GITHUB_REVIEW_TOOLS,
    HARNESS_CALL_MCP_TOOL,
    MCP_TOOL_PREFIX,
    PULL_REQUEST_READ_METHODS,
    parse_github_repository,
    prefixed_tool_name,
)

PULL_NUMBER_KEYS = (
    "pullNumber",
    "pull_number",
    "pr_number",
    "pull_request_number",
    "number",
    "issue_number",
)
REPOSITORY_SLUG_KEYS = ("repository", "full_name", "repo_slug")
PULL_REQUEST_READ_METHOD_ALIASES = {
    "get": "get",
    "get_pull_request": "get",
    "get_pr": "get",
    "pull_request_read": "get",
    "fetch_pull_request": "get",
    "get_diff": "get_diff",
    "fetch_diff": "get_diff",
    "diff": "get_diff",
    "get_files": "get_files",
    "list_files": "get_files",
    "list_pull_request_files": "get_files",
    "get_status": "get_status",
    "get_commits": "get_commits",
    "get_review_comments": "get_review_comments",
    "get_reviews": "get_reviews",
    "get_comments": "get_comments",
    "get_check_runs": "get_check_runs",
}
REVIEW_WRITE_METHOD_ALIASES = {
    "create": "create",
    "create_pending": "create",
    "create_review": "create",
    "start_review": "create",
    "submit": "submit_pending",
    "submit_pending": "submit_pending",
    "submit_review": "submit_pending",
}
METHOD_HINT_KEYS = ("method", "action", "operation", "op")
PATH_KEYS = ("path", "file_path", "filename", "file")
BODY_KEYS = ("body", "comment", "message", "text")
SUBJECT_TYPE_KEYS = ("subjectType", "subject_type", "type")


@dataclass(frozen=True, slots=True)
class GitHubReviewDefaults:
    owner: str
    repo: str
    pull_number: int


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _drop_keys(mapping: dict[str, Any], *keys: str) -> None:
    for key in keys:
        mapping.pop(key, None)


def _resolve_owner_repo(args: dict[str, Any], defaults: GitHubReviewDefaults) -> tuple[str, str]:
    owner = _first_present(args, "owner")
    repo = _first_present(args, "repo", "repository", "repo_name")
    slug = _first_present(args, *REPOSITORY_SLUG_KEYS)
    if (not owner or not repo) and isinstance(slug, str) and "/" in slug:
        parsed_owner, parsed_repo = parse_github_repository(slug)
        owner = owner or parsed_owner
        repo = repo or parsed_repo
    return str(owner or defaults.owner), str(repo or defaults.repo)


def normalize_common_pr_args(args: dict[str, Any], defaults: GitHubReviewDefaults) -> dict[str, Any]:
    normalized = dict(args)
    pull_number = _coerce_int(_first_present(normalized, *PULL_NUMBER_KEYS)) or defaults.pull_number
    owner, repo = _resolve_owner_repo(normalized, defaults)

    normalized["owner"] = owner
    normalized["repo"] = repo
    normalized["pullNumber"] = pull_number

    _drop_keys(
        normalized,
        "pull_number",
        "pr_number",
        "pull_request_number",
        "number",
        "issue_number",
        "repository",
        "repo_slug",
        "full_name",
        "repo_name",
    )
    return normalized


def normalize_pull_request_read_args(
    args: dict[str, Any],
    defaults: GitHubReviewDefaults,
) -> dict[str, Any]:
    normalized = normalize_common_pr_args(args, defaults)
    method = _first_present(normalized, *METHOD_HINT_KEYS)
    mapped_method = None
    if isinstance(method, str):
        method_key = method.strip().lower()
        if method_key:
            mapped_method = PULL_REQUEST_READ_METHOD_ALIASES.get(method_key)
            if mapped_method is None and method_key in PULL_REQUEST_READ_METHODS:
                mapped_method = method_key
    normalized["method"] = mapped_method or "get"
    _drop_keys(normalized, "action", "operation", "op")
    return normalized


def normalize_pull_request_review_write_args(
    args: dict[str, Any],
    defaults: GitHubReviewDefaults,
) -> dict[str, Any]:
    normalized = normalize_common_pr_args(args, defaults)
    method = _first_present(normalized, *METHOD_HINT_KEYS)
    mapped_method = None
    if isinstance(method, str):
        method_key = method.strip().lower()
        if method_key:
            mapped_method = REVIEW_WRITE_METHOD_ALIASES.get(method_key)
    normalized["method"] = mapped_method or "create"
    _drop_keys(normalized, "action", "operation", "op")
    return normalized


def normalize_add_comment_args(args: dict[str, Any], defaults: GitHubReviewDefaults) -> dict[str, Any]:
    normalized = normalize_common_pr_args(args, defaults)
    path = _first_present(normalized, *PATH_KEYS)
    if isinstance(path, str):
        normalized["path"] = path
    body = _first_present(normalized, *BODY_KEYS)
    if isinstance(body, str):
        normalized["body"] = body
    subject_type = _first_present(normalized, *SUBJECT_TYPE_KEYS)
    if isinstance(subject_type, str):
        normalized["subjectType"] = subject_type.upper()
    elif "subjectType" not in normalized and "line" in normalized:
        normalized["subjectType"] = "LINE"
    _drop_keys(normalized, "file_path", "filename", "file", "comment", "message", "text", "subject_type", "type")
    return normalized


def normalize_github_review_tool_args(
    tool_name: str,
    args: dict[str, Any],
    defaults: GitHubReviewDefaults,
) -> dict[str, Any]:
    if tool_name == "pull_request_read":
        return normalize_pull_request_read_args(args, defaults)
    if tool_name == "pull_request_review_write":
        return normalize_pull_request_review_write_args(args, defaults)
    if tool_name == "add_comment_to_pending_review":
        return normalize_add_comment_args(args, defaults)
    return args


def resolve_review_tool_name(tool_call: ToolCall) -> str | None:
    name = str(tool_call.name)
    if name == HARNESS_CALL_MCP_TOOL:
        tool_name = _first_present(tool_call.args or {}, "ToolName", "tool_name")
        return str(tool_name) if isinstance(tool_name, str) else None
    if tool_call.server_name == GITHUB_REVIEW_SERVER_NAME and name in GITHUB_REVIEW_TOOLS:
        return name
    for review_tool in GITHUB_REVIEW_TOOLS:
        if name == prefixed_tool_name(GITHUB_REVIEW_SERVER_NAME, review_tool):
            return review_tool
    if name in GITHUB_REVIEW_TOOLS:
        return name
    if name.startswith(f"{MCP_TOOL_PREFIX}_"):
        suffix = name.removeprefix(f"{MCP_TOOL_PREFIX}_{GITHUB_REVIEW_SERVER_NAME}_")
        if suffix in GITHUB_REVIEW_TOOLS:
            return suffix
    return None


def normalize_tool_call(tool_call: ToolCall, defaults: GitHubReviewDefaults) -> None:
    review_tool = resolve_review_tool_name(tool_call)
    if review_tool is None:
        return

    if str(tool_call.name) == HARNESS_CALL_MCP_TOOL:
        args = tool_call.args or {}
        for key in ("Arguments", "arguments"):
            nested = args.get(key)
            if isinstance(nested, dict):
                args[key] = normalize_github_review_tool_args(review_tool, nested, defaults)
        return

    tool_call.args = normalize_github_review_tool_args(
        review_tool,
        dict(tool_call.args or {}),
        defaults,
    )


class NormalizeGitHubReviewMcpToolCallHook(hooks.PreToolCallDecideHook):
    """Rewrite guessed GitHub MCP arguments into the remote schema."""

    def __init__(self, defaults: GitHubReviewDefaults) -> None:
        self._defaults = defaults

    async def run(self, context: HookContext, data: ToolCall) -> HookResult:
        del context
        normalize_tool_call(data, self._defaults)
        return HookResult(allow=True)


def make_github_review_normalize_hook(
    *,
    owner: str,
    repo: str,
    pull_number: int,
) -> NormalizeGitHubReviewMcpToolCallHook:
    return NormalizeGitHubReviewMcpToolCallHook(
        GitHubReviewDefaults(owner=owner, repo=repo, pull_number=pull_number),
    )
