from __future__ import annotations

import pytest

from odh_ci_agent.source_workspace import resolve_source_workspace


def test_resolve_source_workspace_relative_under_github_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    workspace = tmp_path / "notebooks"
    workspace.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("SOURCE_WORKSPACE", "unsafe-pr-source")

    assert resolve_source_workspace() == workspace / "unsafe-pr-source"


def test_resolve_source_workspace_defaults_to_unsafe_pr_source(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    workspace = tmp_path / "notebooks"
    workspace.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.delenv("SOURCE_WORKSPACE", raising=False)

    assert resolve_source_workspace() == workspace / "unsafe-pr-source"


def test_resolve_source_workspace_rejects_workspace_root(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    workspace = tmp_path / "notebooks"
    workspace.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("SOURCE_WORKSPACE", ".")

    with pytest.raises(SystemExit, match="Invalid SOURCE_WORKSPACE"):
        resolve_source_workspace()


def test_resolve_source_workspace_rejects_path_outside_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    workspace = tmp_path / "notebooks"
    workspace.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("SOURCE_WORKSPACE", "../outside")

    with pytest.raises(SystemExit, match="must stay under GITHUB_WORKSPACE"):
        resolve_source_workspace()
