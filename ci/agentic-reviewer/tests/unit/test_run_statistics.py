from __future__ import annotations

from odh_ci_agent import run_statistics


def test_build_run_statistics_includes_review_block() -> None:
    review_outcome = {
        "add_comment_attempts": 1,
        "deduplicated_comment_attempts": 0,
        "inline_comments_posted": True,
        "inline_comments_staged": 1,
        "review_submitted": True,
    }

    report = run_statistics.build_run_statistics(
        run_kind="pr-review",
        model="gemini-3.5-flash",
        turn_usage=None,
        conversation_usage=None,
        tool_names=["add_comment_to_pending_review"],
        conversation_id="conv-1",
        agent_succeeded=True,
        review_outcome=review_outcome,
    )

    assert report["review"] == review_outcome


def test_build_run_statistics_omits_review_block_when_not_provided() -> None:
    report = run_statistics.build_run_statistics(
        run_kind="ci-summary",
        model="gemini-3.5-flash",
        turn_usage=None,
        conversation_usage=None,
        tool_names=[],
        conversation_id=None,
        agent_succeeded=True,
    )

    assert "review" not in report


def test_append_github_step_summary_includes_review_counts(tmp_path, monkeypatch) -> None:
    summary_path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")

    report = run_statistics.build_run_statistics(
        run_kind="pr-review",
        model="gemini-3.5-flash",
        turn_usage=None,
        conversation_usage=None,
        tool_names=[],
        conversation_id=None,
        agent_succeeded=True,
        review_outcome={
            "inline_comments_staged": 2,
            "inline_comments_posted": False,
        },
    )
    run_statistics.append_github_step_summary(report)

    summary = summary_path.read_text(encoding="utf-8")
    assert "**Inline comments staged:** 2" in summary
    assert "**Inline comments posted:** False" in summary
