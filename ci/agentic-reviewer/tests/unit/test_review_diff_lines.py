from __future__ import annotations

from odh_ci_agent.review_diff_lines import (
    DiffLineIndex,
    format_line_range,
    parse_patch_commentable_lines,
)


def test_parse_patch_commentable_lines_tracks_right_and_left() -> None:
    patch = """@@ -10,4 +10,5 @@
 context
-removed
+added
 context
"""

    right_lines, left_lines = parse_patch_commentable_lines(patch)

    assert right_lines == {11}
    assert left_lines == {11}


def test_parse_patch_commentable_lines_empty_patch() -> None:
    right_lines, left_lines = parse_patch_commentable_lines(None)

    assert right_lines == set()
    assert left_lines == set()


def test_format_line_range_lists_small_sets() -> None:
    assert format_line_range({5, 7, 9}) == "5, 7, 9"


def test_format_line_range_summarizes_large_sets() -> None:
    assert format_line_range(set(range(1, 20))) == "1-19 (19 changed lines)"


def test_diff_line_index_validate_comment_rejects_out_of_range_line() -> None:
    index = DiffLineIndex.from_pull_files(
        [
            {
                "filename": "ci/agentic-reviewer/src/odh_ci_agent/fetch_pr_source_snapshot.py",
                "patch": "@@ -0,0 +1,3 @@\n+line one\n+line two\n+line three\n",
            }
        ]
    )

    error = index.validate_comment(
        path="ci/agentic-reviewer/src/odh_ci_agent/fetch_pr_source_snapshot.py",
        line=146,
        side="RIGHT",
    )

    assert error is not None
    assert "Line 146 could not be resolved" in error
    assert "1, 2, 3" in error


def test_diff_line_index_validate_comment_accepts_changed_line() -> None:
    index = DiffLineIndex.from_pull_files(
        [
            {
                "filename": "README.md",
                "patch": "@@ -0,0 +1,2 @@\n+hello\n+world\n",
            }
        ]
    )

    assert index.validate_comment(path="README.md", line=2, side="RIGHT") is None
