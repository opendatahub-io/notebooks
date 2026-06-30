"""pyfakefs tests for Dockerfile symlink resolution in gha_pr_changed_files."""

from __future__ import annotations

import pathlib
import unittest.mock

import pytest

import gha_pr_changed_files as gha


@pytest.fixture
def dockerfile_symlink_fs(fs, monkeypatch, request):
    """Fake repo with Dockerfile.cpu → Dockerfile.konflux.cpu; clears symlink cache on teardown."""
    fake_root = "/fake-repo"
    component = "jupyter/minimal/ubi9-python-3.12"
    monkeypatch.setattr(gha, "PROJECT_ROOT", pathlib.Path(fake_root))
    gha._symlink_reverse_map.cache_clear()
    request.addfinalizer(gha._symlink_reverse_map.cache_clear)
    fs.create_file(f"{fake_root}/{component}/Dockerfile.konflux.cpu")
    fs.create_symlink(f"{fake_root}/{component}/Dockerfile.cpu", "Dockerfile.konflux.cpu")


def test_resolve_symlinks_expands_dockerfile_symlink_target(dockerfile_symlink_fs):
    """Editing a Dockerfile symlink target adds the symlink path."""
    result = gha._resolve_symlinks(["jupyter/minimal/ubi9-python-3.12/Dockerfile.konflux.cpu"])
    assert "jupyter/minimal/ubi9-python-3.12/Dockerfile.cpu" in result
    assert "jupyter/minimal/ubi9-python-3.12/Dockerfile.konflux.cpu" in result


def test_resolve_symlinks_dockerfile_symlink_pointer_change(dockerfile_symlink_fs):
    """Editing the symlink itself needs no expansion — already in list."""
    result = gha._resolve_symlinks(["jupyter/minimal/ubi9-python-3.12/Dockerfile.cpu"])
    assert result == ["jupyter/minimal/ubi9-python-3.12/Dockerfile.cpu"]


def test_should_build_with_symlinked_dockerfile_target_change(dockerfile_symlink_fs):
    """Dependency on Dockerfile.cpu matches when git reports the symlink target only."""
    fake_return = [pathlib.Path("jupyter/minimal/ubi9-python-3.12/Dockerfile.cpu")]
    with (
        unittest.mock.patch.object(gha, "buildinputs", return_value=fake_return),
        unittest.mock.patch.object(gha, "find_dockerfiles", return_value=["Dockerfile.konflux.cpu"]),
    ):
        changed = gha._resolve_symlinks(["jupyter/minimal/ubi9-python-3.12/Dockerfile.konflux.cpu"])
        assert "jupyter/minimal/ubi9-python-3.12/Dockerfile.cpu" in changed
        result = gha.should_build_target(changed, "jupyter/datascience/ubi9-python-3.12")
        assert result == "jupyter/minimal/ubi9-python-3.12/Dockerfile.cpu"
