from __future__ import annotations

from scripts.ci import prepare_ci_run_context as prepare


def test_strip_gh_log_prefix_removes_job_columns_and_timestamp() -> None:
    line = (
        "job name\tUNKNOWN STEP\t2026-06-05T17:33:52.4163444Z "
        "Error: FetchError: exception_name: ClientResponseError"
    )

    assert prepare.strip_gh_log_prefix(line) == "Error: FetchError: exception_name: ClientResponseError"


def test_failed_step_name_prefers_failed_step() -> None:
    job = {
        "steps": [
            {"name": "Setup", "conclusion": "success", "status": "completed"},
            {"name": "Build", "conclusion": "failure", "status": "completed"},
        ]
    }

    assert prepare.failed_step_name(job) == "Build"


def test_run_mode() -> None:
    assert prepare.run_mode("completed", "success", 0) == "final"
    assert prepare.run_mode("in_progress", None, 0) == "progress"
    assert prepare.run_mode("in_progress", None, 1) == "failure"


def test_progress_counts() -> None:
    jobs = [
        {"status": "completed", "conclusion": "success"},
        {"status": "completed", "conclusion": "failure"},
        {"status": "completed", "conclusion": "cancelled"},
        {"status": "in_progress", "conclusion": None},
        {"status": "queued", "conclusion": None},
    ]

    assert prepare.progress_counts(jobs) == {
        "cancelled": 1,
        "completed": 3,
        "failed": 1,
        "in_progress": 1,
        "queued": 1,
        "total": 5,
    }


def test_build_context_uses_pull_request_and_trigger_job_name() -> None:
    run = {
        "conclusion": None,
        "html_url": "https://example.invalid/run/55",
        "id": 55,
        "name": "Build Notebooks (pr)",
        "pull_requests": [{"number": 123}],
        "status": "in_progress",
    }
    jobs = [
        {
            "conclusion": "success",
            "html_url": "https://example.invalid/job/1",
            "id": 1,
            "name": "Generate job matrix",
            "status": "completed",
            "steps": [],
        },
        {
            "conclusion": "failure",
            "html_url": "https://example.invalid/job/2",
            "id": 2,
            "name": "jupyter-datascience · linux/arm64 [odh]",
            "status": "completed",
            "steps": [{"name": "Build: make jupyter-datascience", "conclusion": "failure", "status": "completed"}],
        },
    ]

    context = prepare.build_context(
        "owner/repo",
        run,
        jobs,
        trigger_job_id=2,
        include_logs=False,
    )

    assert context["github_repository"] == "owner/repo"
    assert context["pr_number"] == 123
    assert context["mode"] == "failure"
    assert context["trigger_job_name"] == "jupyter-datascience · linux/arm64 [odh]"
    assert context["progress"]["failed"] == 1  # type: ignore[index]


def test_failed_step_excerpt_uses_failed_step_window_not_post_failure_dmesg() -> None:
    job = {
        "steps": [
            {
                "name": "Prefetch hermetic build dependencies",
                "status": "completed",
                "conclusion": "failure",
                "started_at": "2026-06-05T17:31:20Z",
                "completed_at": "2026-06-05T17:33:52Z",
            }
        ]
    }
    log_text = (
        "job\tUNKNOWN STEP\t2026-06-05T17:31:20.0000000Z ##[group]Run set -Eeuxo pipefail\n"
        "job\tUNKNOWN STEP\t2026-06-05T17:33:48.5264407Z INFO Reading RPM lockfile\n"
        "job\tUNKNOWN STEP\t2026-06-05T17:33:52.4125864Z ERROR Unsuccessful download\n"
        "job\tUNKNOWN STEP\t2026-06-05T17:33:52.4163444Z Error: FetchError: exception_name: ClientResponseError\n"
        "job\tUNKNOWN STEP\t2026-06-05T17:33:52.7335858Z rm: cannot remove '/tmp/foo': Permission denied\n"
        "job\tUNKNOWN STEP\t2026-06-05T17:33:52.8002162Z ##[error]Process completed with exit code 1.\n"
        "job\tUNKNOWN STEP\t2026-06-05T17:33:52.8163978Z ##[group]Run df -h\n"
        "job\tUNKNOWN STEP\t2026-06-05T17:33:55.9332372Z Jun 05 17:30:44 kernel: docker0 entered disabled state"
    )

    excerpt = prepare.failed_step_excerpt(log_text, job)

    assert "Error: FetchError" in excerpt
    assert "Permission denied" in excerpt
    assert "Process completed with exit code 1." in excerpt
    assert "Run df -h" not in excerpt
    assert "kernel: docker0" not in excerpt
    assert "UNKNOWN STEP" not in excerpt
