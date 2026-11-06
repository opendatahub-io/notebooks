from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scripts.patch_tensorboard_pkg_resources import TensorBoardPatchError, patch_site_packages

if TYPE_CHECKING:
    import pathlib

_DEFAULT_220 = """\
import logging

import pkg_resources

from tensorboard.plugins.audio import audio_plugin


def get_dynamic_plugins():
    \"\"\"Returns dynamically loaded plugins.\"\"\"
    return [
        entry_point.resolve()
        for entry_point in pkg_resources.iter_entry_points(
            "tensorboard_plugins"
        )
    ]
"""

_SERVER_220 = """\
import grpc
import pkg_resources

from tensorboard.data import grpc_provider


class ServerBinary:
    def __init__(self, path, version):
        self._version = (
            pkg_resources.parse_version(version)
            if version is not None
            else version
        )

    def at_least_version(self, required_version):
        if self._version is None:
            return True
        return self._version >= pkg_resources.parse_version(required_version)
"""

_DEFAULT_221 = """\
import logging
from importlib import metadata


def get_dynamic_plugins():
    return [
        entry_point.load()
        for entry_point in _iter_entry_points("tensorboard_plugins")
    ]
"""

_SERVER_221 = """\
import grpc
from packaging import version as packaging_version


class ServerBinary:
    def __init__(self, path, version):
        self._version = packaging_version.parse(version) if version is not None else version
"""


def _install_tree(root: pathlib.Path, default_py: str, server_py: str) -> pathlib.Path:
    site = root / "site-packages"
    (site / "tensorboard" / "data").mkdir(parents=True)
    (site / "tensorboard" / "default.py").write_text(default_py, encoding="utf-8")
    (site / "tensorboard" / "data" / "server_ingester.py").write_text(server_py, encoding="utf-8")
    cache = site / "tensorboard" / "__pycache__"
    cache.mkdir()
    (cache / "default.cpython-312.pyc").write_bytes(b"stale")
    return site


def test_patch_replaces_tensorboard_220_pkg_resources(tmp_path: pathlib.Path) -> None:
    site = _install_tree(tmp_path, _DEFAULT_220, _SERVER_220)

    patch_site_packages(site)

    default_py = (site / "tensorboard" / "default.py").read_text(encoding="utf-8")
    server_py = (site / "tensorboard" / "data" / "server_ingester.py").read_text(encoding="utf-8")
    assert "pkg_resources" not in default_py
    assert "pkg_resources" not in server_py
    assert "def _iter_entry_points(group):" in default_py
    assert "entry_point.load()" in default_py
    assert "from importlib import metadata" in default_py
    assert "packaging_version.parse" in server_py
    assert "from packaging import version as packaging_version" in server_py
    assert "audio_plugin" in default_py
    assert not (site / "tensorboard" / "__pycache__" / "default.cpython-312.pyc").exists()

    patched_default = default_py
    patched_server = server_py
    patch_site_packages(site)
    assert (site / "tensorboard" / "default.py").read_text(encoding="utf-8") == patched_default
    assert (site / "tensorboard" / "data" / "server_ingester.py").read_text(encoding="utf-8") == patched_server


def test_patch_leaves_tensorboard_221_unchanged(tmp_path: pathlib.Path) -> None:
    site = _install_tree(tmp_path, _DEFAULT_221, _SERVER_221)

    patch_site_packages(site)

    assert (site / "tensorboard" / "default.py").read_text(encoding="utf-8") == _DEFAULT_221
    assert (site / "tensorboard" / "data" / "server_ingester.py").read_text(encoding="utf-8") == _SERVER_221


def test_patch_rejects_unexpected_pkg_resources_usage(tmp_path: pathlib.Path) -> None:
    site = _install_tree(tmp_path, "import pkg_resources\n", _SERVER_220)

    with pytest.raises(TensorBoardPatchError, match=r"default.py import"):
        patch_site_packages(site)


def test_patch_requires_tensorboard_sources(tmp_path: pathlib.Path) -> None:
    with pytest.raises(TensorBoardPatchError, match="TensorBoard source not found"):
        patch_site_packages(tmp_path)
