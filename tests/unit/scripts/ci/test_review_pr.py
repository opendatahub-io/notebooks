from __future__ import annotations

import pytest
from google.antigravity.types import McpStreamableHttpServer

from scripts.ci import review_pr

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
    )

    prompt = review_pr.build_prompt(inputs)

    assert "owner/repo" in prompt
    assert "99" in prompt
    assert "focus on tests" in prompt
    assert "empty body (inline comments only)" in prompt
    assert "not in the GitHub review body" in prompt
    assert "## 📋 Review Summary" in prompt


def test_build_config_disables_builtin_tools_and_scopes_mcp() -> None:
    inputs = review_pr.ReviewInputs(
        github_token=EXAMPLE_VALUE,
        repository="owner/repo",
        pull_request_number=99,
        additional_context="",
        model="gemini-3.5-flash",
        defense_in_depth_exclude_header=True,
    )

    config = review_pr.build_config(inputs)
    server = config.mcp_servers[0]

    assert config.capabilities is not None
    assert config.capabilities.enabled_tools == []
    assert config.capabilities.enable_subagents is False
    assert isinstance(server, McpStreamableHttpServer)
    assert server.name == "github"
    assert server.enabled_tools == [
        "pull_request_read",
        "pull_request_review_write",
        "add_comment_to_pending_review",
    ]
    assert server.headers is not None
    assert "X-MCP-Exclude-Tools" in server.headers


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
