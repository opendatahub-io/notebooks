"""Helpers for filtering agent-plugin metadata out of review context."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

AGENT_META_PREFIXES = (".agents/plugins/", ".agents/skills/")


def is_agent_meta_path(filename: str) -> bool:
    normalized = filename.replace("\\", "/").removeprefix("./").lstrip("/")
    return any(normalized.startswith(prefix) for prefix in AGENT_META_PREFIXES)


def filter_changed_files(
    files: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], int]:
    """Return agent-facing changed files and how many meta paths were omitted."""

    kept: list[dict[str, object]] = []
    omitted = 0
    for file_info in files:
        filename = file_info.get("filename")
        if isinstance(filename, str) and is_agent_meta_path(filename):
            omitted += 1
            continue
        kept.append(dict(file_info))
    return kept, omitted
