from __future__ import annotations

from unittest.mock import patch

import pytest
from google.antigravity.tools.tool_runner import ToolWithSchema
from odh_ci_agent import github_actions_tools


def test_make_github_actions_tools_registers_schemas() -> None:
    tools, client = github_actions_tools.make_github_actions_tools(
        repository="owner/repo",
        workflow_run_id=123,
    )

    assert client.context.owner == "owner"
    assert client.context.repo == "repo"
    assert len(tools) == 2
    assert all(isinstance(tool, ToolWithSchema) for tool in tools)
    assert {tool.fn.__name__ for tool in tools} == {"get_job_logs", "actions_get"}


def test_get_job_logs_injects_repository_and_returns_tail() -> None:
    client = github_actions_tools.GitHubActionsClient(
        github_actions_tools.GitHubActionsContext(repository="owner/repo", workflow_run_id=99)
    )
    log_text = "\n".join(f"line {index}" for index in range(10))

    with patch("odh_ci_agent.github_actions_tools.gh_job_log", return_value=log_text + "\n") as mock_log:
        result = client.get_job_logs(job_id=42, tail_lines=3)

    mock_log.assert_called_once_with("owner/repo", 42)
    assert result["job_id"] == 42
    assert result["content"] == "line 7\nline 8\nline 9"


def test_get_job_logs_strips_ansi_codes() -> None:
    client = github_actions_tools.GitHubActionsClient(
        github_actions_tools.GitHubActionsContext(repository="owner/repo", workflow_run_id=99)
    )

    with patch(
        "odh_ci_agent.github_actions_tools.gh_job_log",
        return_value="\x1b[31mFAILED\x1b[0m tests/test_foo.py\n",
    ):
        result = client.get_job_logs(job_id=7)

    assert result["content"] == "FAILED tests/test_foo.py"


def test_actions_get_workflow_job_uses_repository_context() -> None:
    client = github_actions_tools.GitHubActionsClient(
        github_actions_tools.GitHubActionsContext(repository="owner/repo", workflow_run_id=99)
    )

    with patch(
        "odh_ci_agent.github_actions_tools.gh_api_json",
        return_value={"id": 7, "name": "build"},
    ) as mock_api:
        result = client.actions_get(method="get_workflow_job", resource_id="7")

    mock_api.assert_called_once_with("repos/owner/repo/actions/jobs/7")
    assert result == {"id": 7, "name": "build"}


def test_actions_get_rejects_unknown_method() -> None:
    client = github_actions_tools.GitHubActionsClient(
        github_actions_tools.GitHubActionsContext(repository="owner/repo", workflow_run_id=99)
    )

    with pytest.raises(ValueError, match="Unsupported actions_get method"):
        client.actions_get(method="not_a_method", resource_id="1")
