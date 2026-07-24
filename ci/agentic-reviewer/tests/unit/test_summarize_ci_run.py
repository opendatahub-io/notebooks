from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from google.antigravity.types import BuiltinTools
from odh_ci_agent import ci_summary, summarize_ci_run

if TYPE_CHECKING:
    from pathlib import Path


def test_should_enable_actions_fallback_from_context() -> None:
    context = {"failed_jobs": [{"log_tail": ""}]}

    assert summarize_ci_run.should_enable_actions_fallback(context) is True


def test_should_enable_actions_fallback_accepts_log_excerpt() -> None:
    context = {"failed_jobs": [{"log_excerpt": "useful failure excerpt", "log_tail": ""}]}

    assert summarize_ci_run.should_enable_actions_fallback(context) is False


def test_should_enable_actions_fallback_accepts_error_contexts() -> None:
    context = {
        "failed_jobs": [{"error_contexts": ["Error: grounded whole-log context"], "log_excerpt": "", "log_tail": ""}]
    }

    assert summarize_ci_run.should_enable_actions_fallback(context) is False


def test_build_prompt_includes_mode_and_context() -> None:
    context = {
        "failed_jobs": [],
        "mode": "final",
        "pull_request": {"changed_files": [{"filename": "foo.py", "patch_excerpt": "@@ diff"}]},
        "progress": {"failed": 0},
        "workflow_run_id": 123,
    }

    prompt = summarize_ci_run.build_prompt(context)

    assert "Mode: final" in prompt
    assert '"workflow_run_id": 123' in prompt
    assert "## Procedure" in prompt
    assert "Tool-use policy" in prompt
    assert "Do not re-verify" in prompt
    assert "untrusted snapshot of PR code/data" in prompt


def test_build_prompt_notes_when_logs_are_fully_grounded() -> None:
    context = {
        "failed_jobs": [{"log_excerpt": "Error: boom", "log_tail": ""}],
        "mode": "failure",
        "progress": {"failed": 1},
        "source_workspace": "/workspace/notebooks/unsafe-pr-source",
        "workflow_run_id": 1,
    }

    prompt = summarize_ci_run.build_prompt(context)

    assert "prefer context-only analysis" in prompt


def test_logs_fully_grounded() -> None:
    assert ci_summary.logs_fully_grounded([]) is False
    assert ci_summary.logs_fully_grounded([{"log_excerpt": "x"}]) is True
    assert ci_summary.logs_fully_grounded([{"log_tail": ""}]) is False
    assert ci_summary.logs_fully_grounded([{"error_contexts": ["Error: x"]}]) is True


def test_build_config_enables_read_only_source_tools(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace/notebooks")
    monkeypatch.setenv("AGY_TRAJECTORY_DIR", "/workspace/notebooks/agy-trajectory")
    monkeypatch.delenv("SOURCE_WORKSPACE", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    context = {"failed_jobs": [{"log_excerpt": "grounded excerpt", "log_tail": ""}]}

    config = summarize_ci_run.build_config(context)

    assert config.workspaces == ["/workspace/notebooks/unsafe-pr-source"]
    assert config.capabilities is not None
    assert config.capabilities.enabled_tools == [
        BuiltinTools.LIST_DIR,
        BuiltinTools.SEARCH_DIR,
        BuiltinTools.FIND_FILE,
        BuiltinTools.VIEW_FILE,
    ]


def test_summarize_progress_mode_writes_deterministic_body(tmp_path: Path) -> None:
    body_path = tmp_path / "comment.md"
    context = {
        "failed_jobs": [],
        "in_progress_jobs": [],
        "mode": "progress",
        "progress": {"cancelled": 0, "completed": 1, "failed": 0, "in_progress": 0, "total": 2},
        "trigger_job_name": "Generate job matrix",
        "updated_at": "2026-06-05T22:00:00Z",
        "workflow_name": "Build Notebooks (pr)",
        "workflow_run_id": 123,
        "workflow_run_url": "https://example.invalid/run/123",
    }

    result = asyncio.run(summarize_ci_run.summarize(context, str(body_path)))

    assert result == 0
    assert "## CI status [antigravity]" in body_path.read_text(encoding="utf-8")


def test_summarize_final_success_mode_writes_deterministic_body(tmp_path: Path) -> None:
    body_path = tmp_path / "comment.md"
    context = {
        "failed_jobs": [],
        "matrix_progress": {"cancelled": 0, "failed": 0, "passed": 28, "skipped": 0, "total": 28},
        "mode": "final",
        "progress": {
            "cancelled": 0,
            "completed": 28,
            "failed": 0,
            "in_progress": 0,
            "passed": 28,
            "skipped": 0,
            "total": 28,
        },
        "updated_at": "2026-06-05T22:00:00Z",
        "workflow_name": "Build Notebooks (pr)",
        "workflow_run_id": 123,
        "workflow_run_url": "https://example.invalid/run/123",
    }

    result = asyncio.run(summarize_ci_run.summarize(context, str(body_path)))

    assert result == 0
    assert "_All matrix jobs completed successfully._" in body_path.read_text(encoding="utf-8")
