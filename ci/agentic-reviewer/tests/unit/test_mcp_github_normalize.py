from __future__ import annotations

from google.antigravity.types import ToolCall

from odh_ci_agent.mcp_github import HARNESS_CALL_MCP_TOOL
from odh_ci_agent.mcp_github_normalize import (
    GitHubReviewDefaults,
    normalize_pull_request_read_args,
    normalize_tool_call,
)

DEFAULTS = GitHubReviewDefaults(
    owner="opendatahub-io",
    repo="notebooks",
    pull_number=3806,
)


def test_normalize_pull_request_read_maps_get_pull_request() -> None:
    normalized = normalize_pull_request_read_args(
        {"method": "get_pull_request"},
        DEFAULTS,
    )

    assert normalized == {
        "owner": "opendatahub-io",
        "repo": "notebooks",
        "pullNumber": 3806,
        "method": "get",
    }


def test_normalize_pull_request_read_maps_list_files_and_pull_number() -> None:
    normalized = normalize_pull_request_read_args(
        {"method": "list_files", "pull_number": 99},
        DEFAULTS,
    )

    assert normalized["method"] == "get_files"
    assert normalized["pullNumber"] == 99


def test_normalize_pull_request_read_defaults_missing_method_and_pull_number() -> None:
    normalized = normalize_pull_request_read_args({}, DEFAULTS)

    assert normalized["method"] == "get"
    assert normalized["pullNumber"] == 3806


def test_normalize_pull_request_read_maps_list_pull_request_files() -> None:
    normalized = normalize_pull_request_read_args(
        {"method": "list_pull_request_files", "pr_number": 12},
        DEFAULTS,
    )

    assert normalized["method"] == "get_files"
    assert normalized["pullNumber"] == 12


def test_normalize_tool_call_updates_harness_arguments() -> None:
    tool_call = ToolCall(
        name=HARNESS_CALL_MCP_TOOL,
        args={
            "ServerName": "github",
            "ToolName": "pull_request_read",
            "Arguments": {"method": "get_pr"},
        },
    )

    normalize_tool_call(tool_call, DEFAULTS)

    assert tool_call.args["Arguments"] == {
        "owner": "opendatahub-io",
        "repo": "notebooks",
        "pullNumber": 3806,
        "method": "get",
    }


def test_normalize_tool_call_updates_direct_pull_request_read() -> None:
    tool_call = ToolCall(
        name="pull_request_read",
        server_name="github",
        args={"method": "pull_request_read"},
    )

    normalize_tool_call(tool_call, DEFAULTS)

    assert tool_call.args["method"] == "get"
    assert tool_call.args["pullNumber"] == 3806
