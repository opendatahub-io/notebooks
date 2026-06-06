"""Shared helpers for bounding patch excerpts in CI context payloads."""

from __future__ import annotations


def capped_patch_excerpt(patch: str | None, *, max_lines: int) -> str | None:
    if not patch:
        return None
    if max_lines < 1:
        raise ValueError("max_lines must be >= 1")
    lines = patch.splitlines()
    if len(lines) <= max_lines:
        return patch
    if max_lines == 1:
        return lines[0]
    usable = max_lines - 1
    head_count = usable // 2
    tail_count = usable - head_count
    return "\n".join([*lines[:head_count], "...", *lines[-tail_count:]])
