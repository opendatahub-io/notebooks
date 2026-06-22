"""Small helpers for GitHub CLI calls used by CI scripts."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlencode

DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(slots=True)
class GitHubCommandError(RuntimeError):
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    def __str__(self) -> str:
        return (
            f"GitHub CLI command failed with exit code {self.returncode}: {' '.join(self.command)}\n"
            f"stdout:\n{self.stdout}\n"
            f"stderr:\n{self.stderr}"
        )


def split_repository(repository: str) -> tuple[str, str]:
    owner, separator, repo = repository.partition("/")
    if not separator or not owner or not repo:
        raise ValueError(f"Repository must be in owner/repo format, got {repository!r}")
    return owner, repo


def _query_path(path: str, query: Mapping[str, object] | None = None) -> str:
    if not query:
        return path

    encoded = urlencode(
        {
            key: json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value)
            for key, value in query.items()
            if value is not None
        },
        doseq=True,
    )
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{encoded}"


def run_command(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise GitHubCommandError(tuple(command), result.returncode, result.stdout, result.stderr)
    return result


def gh_api_json(
    path: str,
    *,
    method: str = "GET",
    query: Mapping[str, object] | None = None,
    input_json: object | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> object:
    command = ["gh", "api", _query_path(path, query), "--method", method, "-H", "Accept: application/vnd.github+json"]
    input_text = None
    if input_json is not None:
        command.extend(["--input", "-"])
        input_text = json.dumps(input_json, separators=(",", ":"), sort_keys=True)
    result = run_command(command, input_text=input_text, timeout=timeout)
    return json.loads(result.stdout)


def _validate_per_page(per_page: int) -> None:
    if per_page <= 0:
        raise ValueError(f"per_page must be a positive integer, got {per_page}")


def gh_api_pages(
    path: str,
    *,
    item_key: str,
    query: Mapping[str, object] | None = None,
    per_page: int = 100,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> list[object]:
    _validate_per_page(per_page)
    results: list[object] = []
    page = 1
    while True:
        page_query: dict[str, object] = {"page": page, "per_page": per_page}
        if query:
            page_query.update(query)
        response = gh_api_json(path, query=page_query, timeout=timeout)
        if not isinstance(response, dict):
            raise TypeError(f"Expected dict response for paginated endpoint, got {type(response).__name__}")
        items = response.get(item_key, [])
        if not isinstance(items, list):
            raise TypeError(f"Expected list at {item_key!r}, got {type(items).__name__}")
        results.extend(items)
        if len(items) < per_page:
            return results
        page += 1


def gh_api_list_pages(
    path: str,
    *,
    query: Mapping[str, object] | None = None,
    per_page: int = 100,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> list[object]:
    _validate_per_page(per_page)
    results: list[object] = []
    page = 1
    while True:
        page_query: dict[str, object] = {"page": page, "per_page": per_page}
        if query:
            page_query.update(query)
        response = gh_api_json(path, query=page_query, timeout=timeout)
        if not isinstance(response, list):
            raise TypeError(f"Expected list response for paginated endpoint, got {type(response).__name__}")
        results.extend(response)
        if len(response) < per_page:
            return results
        page += 1


def gh_run_job_log(run_id: int, job_id: int, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    result = run_command(
        ["gh", "run", "view", str(run_id), "--job", str(job_id), "--log"],
        timeout=timeout,
    )
    return result.stdout


def gh_job_log(repository: str, job_id: int, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    result = run_command(
        [
            "gh",
            "api",
            f"repos/{repository}/actions/jobs/{job_id}/logs",
            "--method",
            "GET",
            "-H",
            "Accept: application/vnd.github+json",
        ],
        timeout=timeout,
    )
    return result.stdout


def gh_pr_diff(pr_number: int, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    result = run_command(["gh", "pr", "diff", str(pr_number)], timeout=timeout)
    return result.stdout
