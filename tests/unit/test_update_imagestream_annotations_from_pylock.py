"""Unit tests for lockfile resolution in update_imagestream_annotations_from_pylock.

Covers the fetch-on-miss path: when a tag's commit is missing from the local (shallow or
backport) clone, the tool must fetch it from the canonical notebook repo for ANY tag
suffix, not only ``-n`` (see issue #3987).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import manifests.tools.update_imagestream_annotations_from_pylock as mod

LOCK_TEXT = '[package]\nname = "numpy"\nversion = "1.26.4"\n'
RELPATHS = ["jupyter/minimal/c9s-python-3.12/pylock.toml"]
ODH_URL = mod._CANONICAL_REPO_URL["odh"]
RHOAI_URL = mod._CANONICAL_REPO_URL["rhoai"]


class _FetchRecorder:
    """Stand-in for ``_git_fetch_commit_from`` recording calls."""

    def __init__(self, ok: bool) -> None:
        self.ok = ok
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url: str, rev: str) -> bool:
        self.calls.append((url, rev))
        return self.ok


@pytest.fixture
def fetch(monkeypatch) -> _FetchRecorder:
    rec = _FetchRecorder(ok=True)
    monkeypatch.setattr(mod, "_git_fetch_commit_from", rec)
    monkeypatch.setattr(mod, "_git_show_first_existing", lambda sha, rels: (rels[0], LOCK_TEXT))
    return rec


@pytest.fixture
def local_commit_exists(monkeypatch) -> list[bool]:
    state: list[bool] = []

    def _exists(rev: str) -> bool:
        return bool(state) and state[-1]

    monkeypatch.setattr(mod, "_git_commit_exists", _exists)
    return state


def test_non_n_tag_fetches_missing_commit(fetch: _FetchRecorder, local_commit_exists: list[bool]) -> None:
    """A released tag (not -n) whose SHA is absent must be fetched from the canonical repo."""
    local_commit_exists.append(False)
    shown = mod._resolve_lockfile_for_tag("odh", "-2025-2", "deadbeefcafe", RELPATHS, "wb", "x.yaml", 1)
    assert shown == (RELPATHS[0], LOCK_TEXT)
    assert fetch.calls == [(ODH_URL, "deadbeefcafe")]


def test_non_n_tag_existing_commit_not_fetched(fetch: _FetchRecorder, local_commit_exists: list[bool]) -> None:
    """When the commit is already in the local object DB, no fetch happens."""
    local_commit_exists.append(True)
    shown = mod._resolve_lockfile_for_tag("rhoai", "-3-5", "0" * 40, RELPATHS, "wb", "x.yaml", 2)
    assert shown == (RELPATHS[0], LOCK_TEXT)
    assert fetch.calls == []


def test_non_n_tag_unfetchable_commit_skips(fetch: _FetchRecorder, local_commit_exists: list[bool]) -> None:
    """An invalid/unfetchable SHA still skips the tag gracefully (returns None)."""
    fetch.ok = False
    local_commit_exists.append(False)
    shown = mod._resolve_lockfile_for_tag("odh", "-2025-2", "badsha", RELPATHS, "wb", "x.yaml", 1)
    assert shown is None
    assert fetch.calls == [(ODH_URL, "badsha")]


def test_non_n_tag_missing_sha_skips(fetch: _FetchRecorder, local_commit_exists: list[bool]) -> None:
    """No SHA at all: skip without any git interaction."""
    shown = mod._resolve_lockfile_for_tag("odh", "-2025-2", None, RELPATHS, "wb", "x.yaml", 1)
    assert shown is None
    assert fetch.calls == []
    assert local_commit_exists == []


def test_n_tag_prefers_worktree_lockfile(monkeypatch, fetch: _FetchRecorder, local_commit_exists: list[bool]) -> None:
    """-n tags keep preferring the working-tree lockfile (pre-existing behavior)."""
    monkeypatch.setattr(mod, "_worktree_read_first_existing", lambda rels: (rels[0], LOCK_TEXT))
    local_commit_exists.append(False)
    shown = mod._resolve_lockfile_for_tag("odh", "-n", "deadbeefcafe", RELPATHS, "wb", "x.yaml", 0)
    assert shown == (RELPATHS[0], LOCK_TEXT)
    # Worktree hit: ensure/fetch path is never exercised.
    assert fetch.calls == []


def test_n_tag_missing_commit_fetched_from_odh(
    monkeypatch, fetch: _FetchRecorder, local_commit_exists: list[bool]
) -> None:
    """-n tag with no worktree file and missing SHA: fetched from the ODH canonical repo (unchanged)."""
    monkeypatch.setattr(mod, "_worktree_read_first_existing", lambda rels: None)
    local_commit_exists.append(False)
    shown = mod._resolve_lockfile_for_tag("odh", "-n", "deadbeefcafe", RELPATHS, "wb", "x.yaml", 0)
    assert shown == (RELPATHS[0], LOCK_TEXT)
    assert fetch.calls == [(ODH_URL, "deadbeefcafe")]


def test_n_tag_missing_commit_fetched_from_rhoai(
    monkeypatch, fetch: _FetchRecorder, local_commit_exists: list[bool]
) -> None:
    """-n tag under the rhoai variant fetches from the RHDS canonical repo (unchanged)."""
    monkeypatch.setattr(mod, "_worktree_read_first_existing", lambda rels: None)
    local_commit_exists.append(False)
    shown = mod._resolve_lockfile_for_tag("rhoai", "-n", "deadbeefcafe", RELPATHS, "wb", "x.yaml", 0)
    assert shown == (RELPATHS[0], LOCK_TEXT)
    assert fetch.calls == [(RHOAI_URL, "deadbeefcafe")]


def test_ensure_helper_prefers_existing_commit(fetch: _FetchRecorder, local_commit_exists: list[bool]) -> None:
    """_ensure_commit_from_canonical_upstream short-circuits when the commit exists locally."""
    local_commit_exists.append(True)
    assert mod._ensure_commit_from_canonical_upstream("odh", "deadbeef") is True
    assert fetch.calls == []
    local_commit_exists.append(False)
    assert mod._ensure_commit_from_canonical_upstream("odh", "deadbeef") is True
    assert fetch.calls == [(ODH_URL, "deadbeef")]
