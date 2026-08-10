"""In-process GitHub Actions tools (gh api) with MCP-aligned schemas for CI summary."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any

from google.antigravity.hooks import policy
from google.antigravity.tools.tool_runner import ToolWithSchema

from odh_ci_agent.github_api import gh_api_bytes, gh_api_json, gh_job_log, split_repository
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


def _safe_path_segment(resource_id: str, *, label: str) -> str:
    if not resource_id or resource_id in {".", ".."}:
        raise ValueError(f"Invalid {label}: {resource_id!r}")
    if "/" in resource_id or "\\" in resource_id or ".." in resource_id:
        raise ValueError(f"Invalid {label}: {resource_id!r}")
    return resource_id


def _safe_numeric_id(resource_id: str, *, label: str) -> int:
    safe = _safe_path_segment(resource_id, label=label)
    if not safe.isdigit():
        raise ValueError(f"{label} must be a numeric id, got {resource_id!r}")
    return int(safe)


def _workflow_run_id_from_payload(payload: object) -> int:
    if not isinstance(payload, dict):
        raise TypeError("Expected workflow run response to be a JSON object")
    run_id = payload.get("id")
    if not isinstance(run_id, int):
        raise TypeError("Expected workflow run response to include integer id")
    return run_id


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

    @property
    def _actions_base(self) -> str:
        return f"repos/{self.context.owner}/{self.context.repo}/actions"

    def _require_current_workflow_run(self, run_id: int) -> None:
        if run_id != self.context.workflow_run_id:
            raise ValueError(f"Workflow run {run_id} is outside the current run {self.context.workflow_run_id}")

    def _workflow_job(self, job_id: int) -> dict[str, object]:
        job = gh_api_json(f"{self._actions_base}/jobs/{job_id}")
        if not isinstance(job, dict):
            raise TypeError("Expected workflow job response to be a JSON object")
        run_id = job.get("run_id")
        if not isinstance(run_id, int):
            raise TypeError("Expected workflow job response to include integer run_id")
        self._require_current_workflow_run(run_id)
        return job

    def _workflow_run(self, run_id: int) -> dict[str, object]:
        self._require_current_workflow_run(run_id)
        run = gh_api_json(f"{self._actions_base}/runs/{run_id}")
        if not isinstance(run, dict):
            raise TypeError("Expected workflow run response to be a JSON object")
        return run

    def _artifact_in_current_run(self, artifact_id: int) -> dict[str, object]:
        artifact = gh_api_json(f"{self._actions_base}/artifacts/{artifact_id}")
        if not isinstance(artifact, dict):
            raise TypeError("Expected workflow artifact response to be a JSON object")
        workflow_run = artifact.get("workflow_run")
        if not isinstance(workflow_run, dict):
            raise TypeError("Expected workflow artifact response to include workflow_run")
        self._require_current_workflow_run(_workflow_run_id_from_payload(workflow_run))
        return artifact

    def get_job_logs(self, **kwargs: Any) -> dict[str, object]:
        job_id = int(kwargs["job_id"])
        tail_lines = int(kwargs.get("tail_lines", DEFAULT_TAIL_LINES))
        tail_lines = max(1, min(tail_lines, MAX_TAIL_LINES))
        self._workflow_job(job_id)
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
        base = self._actions_base

        if method == "get_workflow":
            safe_id = _safe_path_segment(resource_id, label="workflow resource_id")
            return gh_api_json(f"{base}/workflows/{safe_id}")
        if method == "get_workflow_run":
            return self._workflow_run(_safe_numeric_id(resource_id, label="workflow run id"))
        if method == "get_workflow_job":
            return self._workflow_job(_safe_numeric_id(resource_id, label="job id"))
        if method == "get_workflow_run_usage":
            run_id = _safe_numeric_id(resource_id, label="workflow run id")
            self._require_current_workflow_run(run_id)
            return gh_api_json(f"{base}/runs/{run_id}/timing")
        if method == "get_workflow_run_logs_url":
            run = self._workflow_run(_safe_numeric_id(resource_id, label="workflow run id"))
            return {"logs_url": run.get("logs_url")}
        if method == "download_workflow_run_artifact":
            return self._download_workflow_run_artifact(
                _safe_numeric_id(resource_id, label="artifact id"),
            )
        raise ValueError(f"Unsupported actions_get method: {method}")

    def _download_workflow_run_artifact(self, artifact_id: int) -> dict[str, object]:
        """Return artifact ZIP bytes as base64 for JSON-safe tool output.

        Return shape::

            {
                "artifact_id": int,
                "content_type": "application/zip",
                "encoding": "base64",
                "size_bytes": int,
                "content_base64": str,
            }
        """

        self._artifact_in_current_run(artifact_id)
        zip_bytes = gh_api_bytes(f"{self._actions_base}/artifacts/{artifact_id}/zip")
        return {
            "artifact_id": artifact_id,
            "content_type": "application/zip",
            "encoding": "base64",
            "size_bytes": len(zip_bytes),
            "content_base64": base64.standard_b64encode(zip_bytes).decode("ascii"),
        }


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
