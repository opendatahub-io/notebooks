from __future__ import annotations

from scripts.ci import prepare_ci_run_context as prepare


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
