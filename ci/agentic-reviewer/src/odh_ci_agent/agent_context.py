"""Helpers for preparing changed-file lists in agent review context."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def filter_changed_files(
    files: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], int]:
    """Return changed files for agent context and how many paths were omitted."""

    return [dict(file_info) for file_info in files], 0
