#!/usr/bin/env python3
"""Create or update the single Antigravity PR review summary issue comment."""

from __future__ import annotations

import os

from scripts.ci.ci_summary import int_value, render_superseded_comment
from scripts.ci.github_api import gh_api_json, gh_api_list_pages
from scripts.ci.pr_review_summary import (
    REVIEW_SUMMARY_MARKER_PREFIX,
    comment_contains_run_marker,
    ensure_marker,
    marker_for_run,
)


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise SystemExit(f"Missing required environment variable: {name}")


def load_body(path: str) -> str:
    with open(path, encoding="utf-8") as file_handle:
        return file_handle.read().strip()


def latest_prior_summary_comment(comments: list[dict[str, object]], *, run_id: int) -> dict[str, object] | None:
    prior_comments = [
        comment
        for comment in comments
        if REVIEW_SUMMARY_MARKER_PREFIX in str(comment.get("body", ""))
        and not comment_contains_run_marker(str(comment.get("body", "")), run_id)
    ]
    if not prior_comments:
        return None
    return max(prior_comments, key=lambda comment: int_value(comment["id"]))


def latest_matching_run_comment(
    comments: list[dict[str, object]],
    *,
    run_id: int,
) -> dict[str, object] | None:
    matching_comments = [
        comment
        for comment in comments
        if comment_contains_run_marker(str(comment.get("body", "")), run_id)
    ]
    if not matching_comments:
        return None
    return max(
        matching_comments,
        key=lambda comment: (
            str(comment.get("updated_at") or comment.get("created_at") or ""),
            int_value(comment["id"]),
        ),
    )


def write_step_summary(comment_url: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as file_handle:
        file_handle.write(
            "\n".join(
                [
                    "## Antigravity review summary comment",
                    "",
                    f"- Comment: {comment_url}",
                    "",
                ]
            )
        )


def main() -> None:
    repository = required_env("GITHUB_REPOSITORY")
    issue_number = int(required_env("PULL_REQUEST_NUMBER"))
    run_id = int(required_env("GITHUB_RUN_ID"))
    body_path = required_env("REVIEW_BODY_PATH")
    workflow_run_url = required_env("WORKFLOW_RUN_URL")

    body = load_body(body_path)
    marker = marker_for_run(run_id)
    body = ensure_marker(body, marker, run_id=run_id)

    comments = gh_api_list_pages(f"repos/{repository}/issues/{issue_number}/comments")
    comment_objects = [comment for comment in comments if isinstance(comment, dict)]

    existing_comment = latest_matching_run_comment(comment_objects, run_id=run_id)

    if existing_comment is None:
        created = gh_api_json(
            f"repos/{repository}/issues/{issue_number}/comments",
            method="POST",
            input_json={"body": body},
            timeout=180,
        )
        if not isinstance(created, dict):
            raise SystemExit("Expected GitHub create comment response to be a JSON object")
        comment_url = str(created["html_url"])

        prior_comment = latest_prior_summary_comment(comment_objects, run_id=run_id)
        if prior_comment is not None:
            superseded_body = render_superseded_comment(str(prior_comment.get("body", "")), new_run_url=workflow_run_url)
            gh_api_json(
                f"repos/{repository}/issues/comments/{int_value(prior_comment['id'])}",
                method="PATCH",
                input_json={"body": superseded_body},
                timeout=180,
            )
    else:
        updated = gh_api_json(
            f"repos/{repository}/issues/comments/{int_value(existing_comment['id'])}",
            method="PATCH",
            input_json={"body": body},
            timeout=180,
        )
        if not isinstance(updated, dict):
            raise SystemExit("Expected GitHub update comment response to be a JSON object")
        comment_url = str(updated["html_url"])

    write_step_summary(comment_url)
    print(comment_url)


if __name__ == "__main__":
    main()
