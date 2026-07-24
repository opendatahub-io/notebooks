"""Resolve workspace-relative paths for Antigravity CI artifacts."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SOURCE_WORKSPACE = "unsafe-pr-source"


def resolve_path_under_workspace(raw_path: str, *, label: str) -> Path:
    workspace_root = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())).resolve()
    if not raw_path.strip():
        raise SystemExit(f"Invalid {label}: {raw_path!r}")
    resolved = (workspace_root / raw_path).resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as err:
        raise SystemExit(f"{label} must stay under GITHUB_WORKSPACE: {raw_path!r}") from err
    return resolved


def resolve_source_workspace() -> Path:
    """Return the absolute path where PR source snapshots are extracted."""

    raw_destination = os.environ.get("SOURCE_WORKSPACE", DEFAULT_SOURCE_WORKSPACE).strip()
    if not raw_destination or raw_destination in {".", "/"}:
        raise SystemExit(f"Invalid SOURCE_WORKSPACE: {raw_destination!r}")

    destination = resolve_path_under_workspace(raw_destination, label="SOURCE_WORKSPACE")
    workspace_root = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())).resolve()
    if destination == workspace_root:
        raise SystemExit("SOURCE_WORKSPACE must not be the workspace root")
    return destination


def resolve_review_body_path() -> Path:
    raw_path = os.environ.get("REVIEW_BODY_PATH", "").strip()
    if not raw_path:
        raise SystemExit("Missing required environment variable: REVIEW_BODY_PATH")
    return resolve_path_under_workspace(raw_path, label="REVIEW_BODY_PATH")
