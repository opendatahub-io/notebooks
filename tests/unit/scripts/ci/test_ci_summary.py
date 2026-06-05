from __future__ import annotations

from scripts.ci import ci_summary


def test_cluster_failed_job_detects_known_buckets() -> None:
    assert ci_summary.cluster_failed_job("Prefetch hermetic build dependencies", "cachi2 failed") == "hermeto_prefetch"
    assert ci_summary.cluster_failed_job("Build: make foo", "make target failed") == "make_build"
    assert ci_summary.cluster_failed_job("Run Trivy vulnerability scanner", "Trivy found issues") == "trivy_scan"
    assert ci_summary.cluster_failed_job("Check image with check-payload for FIPS compliance", "check-payload failure") == (
        "fips_check"
    )
    assert ci_summary.cluster_failed_job("Run Playwright tests", "playwright timed out") == "playwright"
    assert ci_summary.cluster_failed_job("Build: make foo", "Killed process 123") == "oom_or_killed"


def test_build_clusters_uses_error_contexts_when_excerpt_is_empty() -> None:
    failed_jobs = [
        {
            "error_contexts": ["ModuleNotFoundError: No module named 'onnxscript'"],
            "failed_step": "Run image tests",
            "log_excerpt": "",
            "log_tail": "",
            "name": "rocm-jupyter-pytorch-ubi9-python-3.12 · linux/amd64 [odh]",
        }
    ]

    clusters = ci_summary.build_clusters(failed_jobs)

    assert clusters == [
        {
            "jobs": ["rocm-jupyter-pytorch-ubi9-python-3.12 · linux/amd64 [odh]"],
            "pattern": "other",
        }
    ]


def test_string_list_filters_non_strings() -> None:
    assert ci_summary.string_list(["one", 2, None, "three"]) == ["one", "three"]


def test_render_progress_comment_includes_failures_running_jobs_and_marker() -> None:
    context = {
        "failed_jobs": [
            {
                "failed_step": "Prefetch hermetic build dependencies",
                "name": "jupyter-datascience · linux/arm64 [odh]",
                "url": "https://example.invalid/job/1",
            }
        ],
        "in_progress_jobs": ["codeserver-ubi9-python-3.12 · linux/amd64 [odh]"],
        "progress": {"cancelled": 0, "completed": 14, "failed": 1, "in_progress": 12, "total": 28},
        "trigger_job_name": "jupyter-datascience · linux/amd64 [odh]",
        "updated_at": "2026-06-05T22:00:00Z",
        "workflow_name": "Build Notebooks (pr)",
        "workflow_run_id": 12345,
        "workflow_run_url": "https://example.invalid/run/12345",
    }

    comment = ci_summary.render_progress_comment(context)

    assert "## CI status [antigravity]" in comment
    assert "**14/28 complete** · 1 failed · 12 running" in comment
    assert "### Failures so far" in comment
    assert "### Still running" in comment
    assert ci_summary.marker_token(12345) in comment


def test_render_superseded_comment_is_idempotent() -> None:
    body = "existing body"

    first = ci_summary.render_superseded_comment(body, new_run_url="https://example.invalid/run/2")
    second = ci_summary.render_superseded_comment(first, new_run_url="https://example.invalid/run/2")

    assert first == second


def test_render_final_success_comment_is_brief_and_marked() -> None:
    context = {
        "progress": {"cancelled": 0, "completed": 28, "failed": 0, "in_progress": 0, "total": 28},
        "updated_at": "2026-06-05T22:00:00Z",
        "workflow_name": "Build Notebooks (pr)",
        "workflow_run_id": 12345,
        "workflow_run_url": "https://example.invalid/run/12345",
    }

    comment = ci_summary.render_final_success_comment(context)

    assert "**28/28 passed**" in comment
    assert "_All matrix jobs completed successfully._" in comment
    assert ci_summary.marker_token(12345) in comment


def test_render_failure_comment_combines_deterministic_sections_with_analysis() -> None:
    context = {
        "failed_jobs": [
            {
                "failed_step": "Prefetch hermetic build dependencies",
                "name": "jupyter-datascience · linux/arm64 [odh]",
                "url": "https://example.invalid/job/1",
            }
        ],
        "in_progress_jobs": ["codeserver-ubi9-python-3.12 · linux/amd64 [odh]"],
        "progress": {"cancelled": 0, "completed": 14, "failed": 1, "in_progress": 12, "total": 28},
        "trigger_job_name": "jupyter-datascience · linux/amd64 [odh]",
        "updated_at": "2026-06-05T22:00:00Z",
        "workflow_name": "Build Notebooks (pr)",
        "workflow_run_id": 12345,
        "workflow_run_url": "https://example.invalid/run/12345",
    }

    comment = ci_summary.render_failure_comment(
        context,
        "### Likely root causes\n1. Likely shared prefetch cleanup problem.\n\n### Suggested next steps\n- Inspect the failing step logs.",
    )

    assert "**14/28 complete** · 1 failed · 12 running" in comment
    assert "| Job | Failed step | Link |" in comment
    assert "### Still running" in comment
    assert "Likely shared prefetch cleanup problem." in comment
    assert ci_summary.marker_token(12345) in comment
