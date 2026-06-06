#!/usr/bin/env python3
"""Prepare bounded PR review context for CI-gated Antigravity reviews."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from scripts.ci.github_api import gh_api_json, gh_api_list_pages, gh_api_pages
from scripts.ci.patch_excerpt import capped_patch_excerpt

SCRIPTS_CI = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_CI.parent.parent
CI_CACHED_BUILDS = REPO_ROOT / "ci" / "cached-builds"
if str(CI_CACHED_BUILDS) not in sys.path:
    sys.path.insert(0, str(CI_CACHED_BUILDS))

import gen_gha_matrix_jobs  # pyright: ignore[reportMissingImports]  # noqa: E402
import gha_pr_changed_files  # pyright: ignore[reportMissingImports]  # noqa: E402

MAX_PATCH_LINES = 50


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise SystemExit(f"Missing required environment variable: {name}")


def affected_image_targets(changed_files: list[str]) -> list[str]:
    targets = gen_gha_matrix_jobs.extract_image_targets(makefile_dir=REPO_ROOT, env={"RELEASE_PYTHON_VERSION": "3.12"})
    filtered_targets = gha_pr_changed_files.filter_out_unchanged(targets, changed_files)
    return sorted(filtered_targets)


def summarized_check_runs(check_runs: list[dict[str, object]]) -> list[dict[str, object]]:
    summarized: list[dict[str, object]] = []
    for check_run in check_runs:
        summarized.append(
            {
                "conclusion": check_run.get("conclusion"),
                "details_url": check_run.get("details_url"),
                "name": check_run.get("name"),
                "status": check_run.get("status"),
                "workflow_name": check_run.get("workflow_name"),
            }
        )
    return summarized


def main() -> None:
    repository = required_env("GITHUB_REPOSITORY")
    pr_number = int(required_env("PULL_REQUEST_NUMBER"))
    output_path = os.environ.get("REVIEW_CONTEXT_PATH", "review-context.json")

    pr = gh_api_json(f"repos/{repository}/pulls/{pr_number}")
    if not isinstance(pr, dict):
        raise SystemExit("Expected pull request response to be a JSON object")

    files = gh_api_list_pages(f"repos/{repository}/pulls/{pr_number}/files", timeout=180)
    if not all(isinstance(file_info, dict) for file_info in files):
        raise SystemExit("Expected pull request files response to contain JSON objects")

    head_sha = str(pr["head"]["sha"])
    check_runs = gh_api_pages(
        f"repos/{repository}/commits/{head_sha}/check-runs",
        item_key="check_runs",
        timeout=180,
    )
    if not all(isinstance(check_run, dict) for check_run in check_runs):
        raise SystemExit("Expected check runs response to contain JSON objects")

    changed_files = [str(file_info["filename"]) for file_info in files if isinstance(file_info, dict)]
    typed_check_runs: list[dict[str, object]] = [check_run for check_run in check_runs if isinstance(check_run, dict)]

    context = {
        "additional_context": os.environ.get("ADDITIONAL_CONTEXT", "").strip(),
        "affected_image_targets": affected_image_targets(changed_files),
        "base_ref": pr["base"]["ref"],
        "body": pr.get("body") or "",
        "changed_files": [
            {
                "additions": file_info.get("additions"),
                "deletions": file_info.get("deletions"),
                "excerpt": capped_patch_excerpt(
                    file_info.get("patch") if isinstance(file_info.get("patch"), str) else None,
                    max_lines=MAX_PATCH_LINES,
                ),
                "filename": file_info["filename"],
                "status": file_info.get("status"),
            }
            for file_info in files
            if isinstance(file_info, dict)
        ],
        "check_runs": summarized_check_runs(typed_check_runs),
        "head_ref": pr["head"]["ref"],
        "head_sha": head_sha,
        "pr_number": pr_number,
        "repository": repository,
        "title": pr["title"],
    }

    with open(output_path, "w", encoding="utf-8") as file_handle:
        json.dump(context, file_handle, indent=2, sort_keys=True)
        file_handle.write("\n")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as file_handle:
            print(f"review_context_path={output_path}", file=file_handle)

    print(output_path)


if __name__ == "__main__":
    main()
