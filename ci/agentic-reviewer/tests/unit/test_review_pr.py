from __future__ import annotations

import pytest
from google.antigravity.tools.tool_runner import ToolWithSchema

from odh_ci_agent import mcp_github, review_pr
from odh_ci_agent.github_review_tools import GitHubReviewClient, ReviewToolInvocation, make_github_review_tools

EXAMPLE_VALUE = "placeholder-value"


def test_load_inputs_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", EXAMPLE_VALUE)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("PULL_REQUEST_NUMBER", "123")
    monkeypatch.setenv("ADDITIONAL_CONTEXT", "focus on security")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("GITHUB_MCP_USE_EXCLUDE_HEADER", "1")

    inputs = review_pr.load_inputs()

    assert inputs.github_token == EXAMPLE_VALUE
    assert inputs.repository == "owner/repo"
    assert inputs.pull_request_number == 123
    assert inputs.additional_context == "focus on security"
    assert inputs.model == "gemini-3.5-flash"
    assert inputs.defense_in_depth_exclude_header is True


def test_required_env_exits_for_missing_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_VALUE", raising=False)

    with pytest.raises(SystemExit, match="Missing required environment variable: MISSING_VALUE"):
        review_pr.required_env("MISSING_VALUE")


def test_build_prompt_includes_repository_pr_and_context() -> None:
    inputs = review_pr.ReviewInputs(
        github_token=EXAMPLE_VALUE,
        repository="owner/repo",
        pull_request_number=99,
        additional_context="focus on tests",
        model=None,
        review_context_json='{"title":"Example"}',
    )

    prompt = review_pr.build_prompt(inputs)

    assert "owner/repo" in prompt
    assert "Repository owner: owner" in prompt
    assert "Repository name: repo" in prompt
    assert "99" in prompt
    assert "focus on tests" in prompt
    assert "parameter schema" in prompt
    assert "get_diff" in prompt
    assert "Do not call `pull_request_read`" not in prompt
    assert "mcp_github_" not in prompt
    assert "REST-style" not in prompt
    assert "empty body (inline comments only)" in prompt
    assert "not in the GitHub review body" in prompt
    assert "## 📋 Review Summary" in prompt


def test_build_prompt_requires_pull_request_read_without_context() -> None:
    inputs = review_pr.ReviewInputs(
        github_token=EXAMPLE_VALUE,
        repository="owner/repo",
        pull_request_number=42,
        additional_context="",
        model=None,
    )

    prompt = review_pr.build_prompt(inputs)

    assert "Prepared review context is null" in prompt
    assert "Call `pull_request_read`" in prompt


def test_build_config_registers_python_review_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGY_TRAJECTORY_DIR", "agy-trajectory/pr-review")
    inputs = review_pr.ReviewInputs(
        github_token=EXAMPLE_VALUE,
        repository="owner/repo",
        pull_request_number=99,
        additional_context="",
        model="gemini-3.5-flash",
    )

    config, _client = review_pr.build_config(inputs)

    assert config.capabilities is not None
    assert config.save_dir == "agy-trajectory/pr-review"
    assert config.capabilities.enabled_tools == []
    assert config.capabilities.enable_subagents is False
    assert config.mcp_servers == []
    assert len(config.tools) == 3
    assert all(isinstance(tool, ToolWithSchema) for tool in config.tools)
    tool_names = {tool.fn.__name__ for tool in config.tools}
    assert tool_names == set(mcp_github.GITHUB_REVIEW_TOOLS)


def test_bool_env_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for truthy in ("1", "true", "yes", "on"):
        monkeypatch.setenv("FLAG", truthy)
        assert review_pr.bool_env("FLAG") is True


def test_bool_env_falsey_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for falsey in ("", "0", "false", "no", "off"):
        if falsey:
            monkeypatch.setenv("FLAG", falsey)
        else:
            monkeypatch.delenv("FLAG", raising=False)
        assert review_pr.bool_env("FLAG") is False


def test_persist_review_summary_writes_marked_body(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    body_path = tmp_path / "review-summary-body.md"
    monkeypatch.setenv("REVIEW_BODY_PATH", str(body_path))
    monkeypatch.setenv("GITHUB_RUN_ID", "123")

    review_pr.persist_review_summary("## 📋 Review Summary\n\nAll good.\n\nPosted a review with inline comments.")

    body = body_path.read_text(encoding="utf-8")
    assert "## 📋 Review Summary" in body
    assert "All good." in body
    assert "Posted a review" not in body
    assert "<!-- antigravity-pr-review run_id=123" in body


def test_format_usage_metadata_none() -> None:
    assert review_pr.format_usage_metadata(None) == "null"


def test_review_run_failed_detects_policy_denial() -> None:
    reason = review_pr.review_run_failed(
        "Denied by policy 'deny_all'.",
        [],
        has_prepared_context=False,
    )

    assert reason == "GitHub review tools were denied by policy"


def test_review_run_failed_detects_missing_tool_calls() -> None:
    reason = review_pr.review_run_failed("All good.", [], has_prepared_context=False)

    assert reason == "review completed without invoking GitHub review tools"


def test_review_run_failed_allows_prepared_context_without_tool_reads() -> None:
    reason = review_pr.review_run_failed("All good.", [], has_prepared_context=True)

    assert reason is None


def test_review_run_failed_detects_reported_fetch_failure() -> None:
    reason = review_pr.review_run_failed(
        "I am unable to retrieve the pull request details due to persistent errors.",
        [],
        has_prepared_context=True,
    )

    assert reason == "agent reported inability to fetch pull request data"


def test_review_run_failed_accepts_invoked_review_tool() -> None:
    class ToolCall:
        name = "pull_request_read"
        args = {}
        server_name = None

    assert review_pr.review_run_failed("done", [ToolCall()], has_prepared_context=False) is None


def test_make_github_review_tools_exposes_mcp_aligned_schemas() -> None:
    tools, _client = make_github_review_tools("owner/repo", 12)
    read_tool = next(tool for tool in tools if tool.fn.__name__ == "pull_request_read")

    assert read_tool.input_schema["properties"]["pullNumber"]["type"] == "number"
    assert "get_diff" in read_tool.input_schema["properties"]["method"]["enum"]


def test_review_run_failed_detects_failed_comment_posting() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client.invocations.append(
        ReviewToolInvocation(
            tool_name="add_comment_to_pending_review",
            method=None,
            success=False,
            error="Invalid request",
        )
    )

    reason = review_pr.review_run_failed(
        "No comments were posted.",
        [],
        has_prepared_context=True,
        review_client=client,
    )

    assert reason == "failed to post inline review comments (1 attempt(s))"


def test_parse_github_repository_splits_owner_and_repo() -> None:
    assert mcp_github.parse_github_repository("opendatahub-io/notebooks") == (
        "opendatahub-io",
        "notebooks",
    )


def test_parse_github_repository_rejects_invalid_slug() -> None:
    with pytest.raises(ValueError, match="Invalid GitHub repository slug"):
        mcp_github.parse_github_repository("invalid")
