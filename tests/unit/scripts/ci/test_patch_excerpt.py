from __future__ import annotations

from scripts.ci import patch_excerpt


def test_respects_max_lines_including_ellipsis() -> None:
    patch = "\n".join(f"line {index}" for index in range(60))
    excerpt = patch_excerpt.capped_patch_excerpt(patch, max_lines=50)

    assert excerpt is not None
    assert len(excerpt.splitlines()) == 50
    assert "..." in excerpt.splitlines()


def test_max_lines_one_returns_first_line_only() -> None:
    patch = "first line\nsecond line"
    excerpt = patch_excerpt.capped_patch_excerpt(patch, max_lines=1)

    assert excerpt == "first line"


def test_short_patch_unchanged() -> None:
    patch = "line one\nline two\nline three"
    excerpt = patch_excerpt.capped_patch_excerpt(patch, max_lines=50)

    assert excerpt == patch
