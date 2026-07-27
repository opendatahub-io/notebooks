"""Shared helpers for bounding patch excerpts in CI context payloads."""

from __future__ import annotations


def _patch_lines(patch: str) -> list[str]:
    """Split a GitHub unified-diff patch into lines.

    Patches are ``\\n``-separated records. Do **not** use ``str.splitlines()``:
    it also splits on ``\\r``, which can appear inside file content and is not a
    patch-line boundary. A single trailing newline does not create an extra line.
    """
    lines = patch.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines


def capped_patch_excerpt(patch: str | None, *, max_lines: int) -> str | None:
    """Return ``patch`` capped to at most ``max_lines`` lines, or ``None`` if empty.

    When truncated (and ``max_lines > 1``), keeps a head/tail around a ``...``
    marker. The result may contain fewer than ``max_lines`` lines when a trailing
    empty segment is lost through ``"\\n".join`` — the contract is a line budget,
    not blank-line round-trips.
    """
    if max_lines < 1:
        raise ValueError("max_lines must be >= 1")
    if not patch:
        return None
    lines = _patch_lines(patch)
    if len(lines) <= max_lines:
        return patch
    if max_lines == 1:
        return lines[0]
    usable = max_lines - 1
    head_count = usable // 2
    tail_count = usable - head_count
    return "\n".join([*lines[:head_count], "...", *lines[-tail_count:]])
