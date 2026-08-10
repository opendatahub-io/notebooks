from __future__ import annotations

import base64
from unittest.mock import patch

import pytest
from google.antigravity.tools.tool_runner import ToolWithSchema
from odh_ci_agent import github_actions_tools

JOB_IN_CURRENT_RUN = {"id": 7, "name": "build", "run_id": 99}
ARTIFACT_IN_CURRENT_RUN = {"id": 55, "workflow_run": {"id": 99}}


def _client() -> github_actions_tools.GitHubActionsClient:
    return github_actions_tools.GitHubActionsClient(
        github_actions_tools.GitHubActionsContext(repository="owner/repo", workflow_run_id=99)
    )


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
    client = _client()
    log_text = "\n".join(f"line {index}" for index in range(10))

    with (
        patch(
            "odh_ci_agent.github_actions_tools.gh_api_json",
            return_value=JOB_IN_CURRENT_RUN,
        ),
        patch("odh_ci_agent.github_actions_tools.gh_job_log", return_value=log_text + "\n") as mock_log,
    ):
        result = client.get_job_logs(job_id=42, tail_lines=3)

    mock_log.assert_called_once_with("owner/repo", 42)
    assert result["job_id"] == 42
    assert result["content"] == "line 7\nline 8\nline 9"


def test_get_job_logs_strips_ansi_codes() -> None:
    client = _client()

    with (
        patch(
            "odh_ci_agent.github_actions_tools.gh_api_json",
            return_value=JOB_IN_CURRENT_RUN,
        ),
        patch(
            "odh_ci_agent.github_actions_tools.gh_job_log",
            return_value="\x1b[31mFAILED\x1b[0m tests/test_foo.py\n",
        ),
    ):
        result = client.get_job_logs(job_id=7)

    assert result["content"] == "FAILED tests/test_foo.py"


def test_get_job_logs_rejects_job_from_other_run() -> None:
    client = _client()

    with patch(
        "odh_ci_agent.github_actions_tools.gh_api_json",
        return_value={"id": 7, "run_id": 100},
    ):
        with pytest.raises(ValueError, match="outside the current run"):
            client.get_job_logs(job_id=7)


def test_actions_get_workflow_job_uses_repository_context() -> None:
    client = _client()

    with patch(
        "odh_ci_agent.github_actions_tools.gh_api_json",
        return_value=JOB_IN_CURRENT_RUN,
    ) as mock_api:
        result = client.actions_get(method="get_workflow_job", resource_id="7")

    mock_api.assert_called_once_with("repos/owner/repo/actions/jobs/7")
    assert result == JOB_IN_CURRENT_RUN


def test_actions_get_rejects_path_traversal_resource_id() -> None:
    client = _client()

    with pytest.raises(ValueError, match="Invalid workflow run id"):
        client.actions_get(method="get_workflow_run", resource_id="../../issues")


def test_actions_get_rejects_other_workflow_run_id() -> None:
    client = _client()

    with pytest.raises(ValueError, match="outside the current run"):
        client.actions_get(method="get_workflow_run", resource_id="100")


def test_download_workflow_run_artifact_returns_base64_zip() -> None:
    client = _client()
    zip_bytes = b"PK\x03\x04fake-zip"

    with (
        patch(
            "odh_ci_agent.github_actions_tools.gh_api_json",
            return_value=ARTIFACT_IN_CURRENT_RUN,
        ),
        patch(
            "odh_ci_agent.github_actions_tools.gh_api_bytes",
            return_value=zip_bytes,
        ) as mock_bytes,
    ):
        result = client.actions_get(method="download_workflow_run_artifact", resource_id="55")

    mock_bytes.assert_called_once_with("repos/owner/repo/actions/artifacts/55/zip")
    assert result == {
        "artifact_id": 55,
        "content_type": "application/zip",
        "encoding": "base64",
        "size_bytes": len(zip_bytes),
        "content_base64": base64.standard_b64encode(zip_bytes).decode("ascii"),
    }


def test_download_workflow_run_artifact_rejects_other_run() -> None:
    client = _client()

    with patch(
        "odh_ci_agent.github_actions_tools.gh_api_json",
        return_value={"id": 55, "workflow_run": {"id": 100}},
    ):
        with pytest.raises(ValueError, match="outside the current run"):
            client.actions_get(method="download_workflow_run_artifact", resource_id="55")


def test_actions_get_rejects_unknown_method() -> None:
    client = _client()

    with pytest.raises(ValueError, match="Unsupported actions_get method"):
        client.actions_get(method="not_a_method", resource_id="1")
