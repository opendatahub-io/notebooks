"""Helpers for mapping manifest param keys to commit ConfigMap keys and env files."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def commit_field_key(base_key: str, suffix: str) -> str:
    """ConfigMap key for a commit hash (e.g. ``...-commit-n``, ``...-commit-2025-2``)."""
    return f"{base_key}-commit{suffix}"


def parse_env_file(path: Path) -> dict[str, str]:
    """Load ``KEY=value`` lines from a ``*.env`` file."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def commit_env_path_for_suffix(suffix: str) -> str:
    """``-n`` (latest) uses ``commit-latest.env``; all other versions use ``commit.env``."""
    return "commit-latest.env" if suffix == "-n" else "commit.env"
