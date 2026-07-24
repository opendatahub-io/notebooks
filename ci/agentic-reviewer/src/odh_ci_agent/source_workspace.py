"""Resolve the local PR source snapshot directory for Antigravity workspaces."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SOURCE_WORKSPACE = "unsafe-pr-source"


def resolve_source_workspace() -> Path:
    """Return the absolute path where PR source snapshots are extracted."""

    workspace_root = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())).resolve()
    raw_destination = os.environ.get("SOURCE_WORKSPACE", DEFAULT_SOURCE_WORKSPACE).strip()
    if not raw_destination or raw_destination in {".", "/"}:
        raise SystemExit(f"Invalid SOURCE_WORKSPACE: {raw_destination!r}")

    destination = (workspace_root / raw_destination).resolve()
    if destination == workspace_root:
        raise SystemExit("SOURCE_WORKSPACE must not be the workspace root")
    try:
        destination.relative_to(workspace_root)
    except ValueError as err:
        raise SystemExit(f"SOURCE_WORKSPACE must stay under GITHUB_WORKSPACE: {raw_destination!r}") from err
    return destination
