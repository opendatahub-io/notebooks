from __future__ import annotations

from scripts.ci import prepare_ci_run_context as prepare


def test_strip_gh_log_prefix_removes_job_columns_and_timestamp() -> None:
    line = "job name\tUNKNOWN STEP\t2026-06-05T17:33:52.4163444Z Error: FetchError: exception_name: ClientResponseError"

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
        {"status": "completed", "conclusion": "skipped"},
        {"status": "in_progress", "conclusion": None},
        {"status": "queued", "conclusion": None},
    ]

    assert prepare.progress_counts(jobs) == {
        "cancelled": 1,
        "completed": 4,
        "failed": 1,
        "in_progress": 1,
        "passed": 1,
        "queued": 1,
        "skipped": 1,
        "total": 6,
    }


def test_matrix_job_counts() -> None:
    jobs = [
        {"name": "Generate job matrix", "conclusion": "success"},
        {"name": "foo · linux/amd64 [odh]", "conclusion": "success"},
        {"name": "bar · linux/amd64 [rhoai]", "conclusion": "skipped"},
        {"name": "${{ matrix.target }} · ${{ matrix.platform }} [odh]", "conclusion": "skipped"},
    ]

    assert prepare.matrix_job_counts(jobs) == {
        "cancelled": 0,
        "failed": 0,
        "passed": 1,
        "skipped": 2,
        "total": 3,
    }


def test_build_context_uses_pull_request_and_trigger_job_name(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace/notebooks")
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
    pr_context = {
        "base_ref": "main",
        "body": "description",
        "changed_files": [{"filename": "foo.py", "patch_excerpt": "@@ diff"}],
        "changed_files_omitted": 0,
        "head_ref": "feature",
        "head_sha": "abc123",
        "number": 123,
        "title": "Example PR",
    }

    context = prepare.build_context(
        "owner/repo",
        run,
        jobs,
        pr_context,
        123,
        "abc123",
        trigger_job_id=2,
        include_logs=False,
    )

    assert context["github_repository"] == "owner/repo"
    assert context["pr_number"] == 123
    assert context["mode"] == "failure"
    assert context["matrix_progress"] == {
        "cancelled": 0,
        "failed": 0,
        "passed": 0,
        "skipped": 0,
        "total": 0,
    }
    assert context["pull_request"] == pr_context
    assert context["source_head_sha"] == "abc123"
    assert context["source_workspace"] == "/workspace/notebooks"
    assert context["trigger_job_name"] == "jupyter-datascience · linux/arm64 [odh]"
    assert context["progress"]["failed"] == 1  # type: ignore[index]


def test_build_context_allows_push_runs_without_pull_request(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace/notebooks")
    run = {
        "conclusion": "failure",
        "event": "push",
        "head_sha": "deadbeef",
        "html_url": "https://example.invalid/run/56",
        "id": 56,
        "name": "Build Notebooks (push)",
        "pull_requests": [],
        "status": "completed",
    }
    jobs = [
        {
            "conclusion": "failure",
            "html_url": "https://example.invalid/job/1",
            "id": 1,
            "name": "build job",
            "status": "completed",
            "steps": [{"name": "Build: make image", "conclusion": "failure", "status": "completed"}],
        }
    ]

    context = prepare.build_context(
        "owner/repo",
        run,
        jobs,
        {},
        None,
        "deadbeef",
        trigger_job_id=None,
        include_logs=False,
    )

    assert context["pr_number"] is None
    assert context["pull_request"] == {}
    assert context["source_head_sha"] == "deadbeef"


def test_pull_request_context_caps_patch_and_counts_omitted(monkeypatch) -> None:
    monkeypatch.setattr(
        prepare,
        "gh_api_json",
        lambda path: {
            "base": {"ref": "main"},
            "body": "body",
            "head": {"ref": "feature", "sha": "abc123"},
            "title": "Example PR",
        },
    )
    long_patch = "\n".join(f"line {index}" for index in range(100))
    monkeypatch.setattr(
        prepare,
        "gh_api_list_pages",
        lambda path, timeout=180: [
            {"filename": "a.py", "status": "modified", "additions": 10, "deletions": 2, "patch": long_patch},
            {"filename": "b.py", "status": "modified", "additions": 1, "deletions": 0, "patch": "@@ tiny"},
        ],
    )

    context = prepare.pull_request_context("owner/repo", 123)

    assert context["number"] == 123
    assert context["title"] == "Example PR"
    assert context["changed_files_omitted"] == 0
    assert context["changed_files"][0]["filename"] == "a.py"  # type: ignore[index]
    assert context["changed_files"][0]["patch_excerpt"] is not None  # type: ignore[index]


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


def test_whole_log_error_contexts_filter_kernel_noise_and_keep_anchor_context() -> None:
    log_text = (
        "2026-06-05T17:29:14.4672415Z Current runner version: '2.334.0'\n"
        "2026-06-05T17:33:52.4125864Z ERROR Unsuccessful download\n"
        "2026-06-05T17:33:52.4163444Z Error: FetchError: exception_name: ClientResponseError\n"
        "2026-06-05T17:33:52.7335858Z rm: cannot remove '/tmp/foo': Permission denied\n"
        "2026-06-05T17:33:52.8002162Z ##[error]Process completed with exit code 1.\n"
        "2026-06-05T17:33:52.8163978Z ##[group]Run df -h\n"
        "2026-06-05T17:33:52.8165000Z df -h\n"
        "2026-06-05T17:33:55.9332372Z Jun 05 17:30:44 kernel: docker0 entered disabled state\n"
    )

    contexts = prepare.whole_log_error_contexts(log_text)

    assert contexts
    joined = "\n".join(contexts)
    assert "ERROR Unsuccessful download" in joined
    assert "Permission denied" in joined
    assert "Process completed with exit code 1." in joined
    assert "Run df -h" not in joined
    assert "kernel: docker0" not in joined
