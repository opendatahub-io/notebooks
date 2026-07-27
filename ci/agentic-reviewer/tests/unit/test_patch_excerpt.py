from __future__ import annotations

import pytest
from odh_ci_agent import patch_excerpt


def test_respects_max_lines_including_ellipsis() -> None:
    patch = "\n".join(f"line {index}" for index in range(60))
    excerpt = patch_excerpt.capped_patch_excerpt(patch, max_lines=50)

    assert excerpt is not None
    assert len(excerpt.split("\n")) == 50
    assert "..." in excerpt.split("\n")


def test_max_lines_one_returns_first_line_only() -> None:
    patch = "first line\nsecond line"
    excerpt = patch_excerpt.capped_patch_excerpt(patch, max_lines=1)

    assert excerpt == "first line"


def test_short_patch_unchanged() -> None:
    patch = "line one\nline two\nline three"
    excerpt = patch_excerpt.capped_patch_excerpt(patch, max_lines=50)

    assert excerpt == patch


def test_empty_patch_returns_none() -> None:
    assert patch_excerpt.capped_patch_excerpt(None, max_lines=50) is None
    assert patch_excerpt.capped_patch_excerpt("", max_lines=50) is None


@pytest.mark.parametrize("max_lines", [0, -1])
def test_invalid_max_lines_raises(max_lines: int) -> None:
    with pytest.raises(ValueError, match="max_lines"):
        patch_excerpt.capped_patch_excerpt(None, max_lines=max_lines)
    with pytest.raises(ValueError, match="max_lines"):
        patch_excerpt.capped_patch_excerpt("line\n", max_lines=max_lines)


def test_cr_in_content_is_not_a_line_break() -> None:
    # GitHub patches are \n-separated; \r is content, not a record boundary.
    patch = "a\rb\nc"
    assert patch_excerpt._patch_lines(patch) == ["a\rb", "c"]
    assert patch_excerpt.capped_patch_excerpt(patch, max_lines=1) == "a\rb"


def test_trailing_newline_does_not_add_a_line() -> None:
    patch = "one\ntwo\n"
    assert patch_excerpt.capped_patch_excerpt(patch, max_lines=2) == patch
