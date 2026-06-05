from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from scripts.ci import summarize_ci_run

if TYPE_CHECKING:
    from pathlib import Path


def test_should_enable_actions_fallback_from_context() -> None:
    context = {"failed_jobs": [{"log_tail": ""}]}

    assert summarize_ci_run.should_enable_actions_fallback(context) is True


def test_should_enable_actions_fallback_accepts_log_excerpt() -> None:
    context = {"failed_jobs": [{"log_excerpt": "useful failure excerpt", "log_tail": ""}]}

    assert summarize_ci_run.should_enable_actions_fallback(context) is False


def test_build_prompt_includes_mode_and_context() -> None:
    context = {
        "failed_jobs": [],
        "mode": "final",
        "progress": {"failed": 0},
        "workflow_run_id": 123,
    }

    prompt = summarize_ci_run.build_prompt(context)

    assert "Mode: final" in prompt
    assert '"workflow_run_id": 123' in prompt


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
        "mode": "final",
        "progress": {"cancelled": 0, "completed": 28, "failed": 0, "in_progress": 0, "total": 28},
        "updated_at": "2026-06-05T22:00:00Z",
        "workflow_name": "Build Notebooks (pr)",
        "workflow_run_id": 123,
        "workflow_run_url": "https://example.invalid/run/123",
    }

    result = asyncio.run(summarize_ci_run.summarize(context, str(body_path)))

    assert result == 0
    assert "_All matrix jobs completed successfully._" in body_path.read_text(encoding="utf-8")
