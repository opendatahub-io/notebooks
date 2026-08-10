"""In-process GitHub Actions tools (gh api) with MCP-aligned schemas for CI summary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from google.antigravity.hooks import policy
from google.antigravity.tools.tool_runner import ToolWithSchema

from odh_ci_agent.github_api import gh_api_json, gh_job_log, split_repository
from odh_ci_agent.mcp_github import GITHUB_ACTIONS_READ_TOOLS

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
DEFAULT_TAIL_LINES = 500
MAX_TAIL_LINES = 2_000

ACTIONS_GET_METHODS = (
    "get_workflow",
    "get_workflow_run",
    "get_workflow_job",
    "download_workflow_run_artifact",
    "get_workflow_run_usage",
    "get_workflow_run_logs_url",
)

GET_JOB_LOGS_SCHEMA = {
    "type": "object",
    "description": (
        "Fetch workflow job logs for a failed job already listed in context. "
        "Repository owner/name and workflow run id are injected automatically."
    ),
    "properties": {
        "job_id": {
            "type": "number",
            "description": "Workflow job id from failed_jobs[*].id in the provided context.",
        },
        "tail_lines": {
            "type": "number",
            "description": "Number of lines to return from the end of the log.",
            "minimum": 1,
            "maximum": MAX_TAIL_LINES,
            "default": DEFAULT_TAIL_LINES,
        },
    },
    "required": ["job_id"],
}

ACTIONS_GET_SCHEMA = {
    "type": "object",
    "description": (
        "Get details about a GitHub Actions workflow, run, job, or artifact. "
        "Repository owner/name are injected automatically."
    ),
    "properties": {
        "method": {
            "type": "string",
            "description": "The GitHub Actions resource lookup to perform.",
            "enum": list(ACTIONS_GET_METHODS),
        },
        "resource_id": {
            "type": "string",
            "description": (
                "Resource identifier for the selected method: workflow id or file name, "
                "workflow run id, job id, or artifact id."
            ),
        },
    },
    "required": ["method", "resource_id"],
}


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def _tail_log_lines(log_text: str, tail_lines: int) -> str:
    lines = [_strip_ansi(line) for line in log_text.splitlines()]
    if tail_lines <= 0 or len(lines) <= tail_lines:
        return "\n".join(lines)
    return "\n".join(lines[-tail_lines:])


@dataclass(frozen=True, slots=True)
class GitHubActionsContext:
    repository: str
    workflow_run_id: int

    @property
    def owner(self) -> str:
        owner, _repo = split_repository(self.repository)
        return owner

    @property
    def repo(self) -> str:
        _owner, repo = split_repository(self.repository)
        return repo


@dataclass
class GitHubActionsClient:
    """Execute read-only GitHub Actions lookups via ``gh api``."""

    context: GitHubActionsContext

    def get_job_logs(self, **kwargs: Any) -> dict[str, object]:
        job_id = int(kwargs["job_id"])
        tail_lines = int(kwargs.get("tail_lines", DEFAULT_TAIL_LINES))
        tail_lines = max(1, min(tail_lines, MAX_TAIL_LINES))
        log_text = gh_job_log(self.context.repository, job_id)
        content = _tail_log_lines(log_text, tail_lines)
        return {
            "job_id": job_id,
            "repository": self.context.repository,
            "return_content": True,
            "tail_lines": tail_lines,
            "content": content,
        }

    def actions_get(self, **kwargs: Any) -> object:
        method = str(kwargs["method"])
        resource_id = str(kwargs["resource_id"])
        owner = self.context.owner
        repo = self.context.repo
        base = f"repos/{owner}/{repo}/actions"

        if method == "get_workflow":
            return gh_api_json(f"{base}/workflows/{resource_id}")
        if method == "get_workflow_run":
            return gh_api_json(f"{base}/runs/{resource_id}")
        if method == "get_workflow_job":
            return gh_api_json(f"{base}/jobs/{resource_id}")
        if method == "get_workflow_run_usage":
            return gh_api_json(f"{base}/runs/{resource_id}/timing")
        if method == "get_workflow_run_logs_url":
            run = gh_api_json(f"{base}/runs/{resource_id}")
            if isinstance(run, dict):
                return {"logs_url": run.get("logs_url")}
            return run
        if method == "download_workflow_run_artifact":
            return gh_api_json(f"{base}/artifacts/{resource_id}/zip")
        raise ValueError(f"Unsupported actions_get method: {method}")


def make_github_actions_tools(
    *,
    repository: str,
    workflow_run_id: int,
) -> tuple[list[ToolWithSchema], GitHubActionsClient]:
    client = GitHubActionsClient(GitHubActionsContext(repository=repository, workflow_run_id=workflow_run_id))
    tools = [
        ToolWithSchema(client.get_job_logs, GET_JOB_LOGS_SCHEMA),
        ToolWithSchema(client.actions_get, ACTIONS_GET_SCHEMA),
    ]
    return tools, client


def actions_tool_policies() -> list[policy.Policy]:
    return [policy.deny_all(), *[policy.allow(tool_name) for tool_name in GITHUB_ACTIONS_READ_TOOLS]]
