from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"


def _load_pylock_version():
    spec = importlib.util.spec_from_file_location("pylock_version", SCRIPTS / "pylock_version.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_pylock_version = _load_pylock_version()
locked_version = _pylock_version.locked_version
format_version = _pylock_version.format_version

DATASCIENCE_PYLOCK = ROOT / "jupyter/datascience/ubi9-python-3.12/pylock.toml"


def test_locked_version_onnx_ppc64le() -> None:
    assert locked_version(DATASCIENCE_PYLOCK, "onnx", platform_machine="ppc64le") == "1.22.0"


def test_locked_version_pyarrow_s390x() -> None:
    assert locked_version(DATASCIENCE_PYLOCK, "pyarrow", platform_machine="s390x") == "17.0.0"


def test_format_git_tag() -> None:
    assert format_version("1.22.0", "git-tag") == "v1.22.0"


def test_format_apache_arrow_branch() -> None:
    assert format_version("17.0.0", "apache-arrow-branch") == "apache-arrow-17.0.0"


def test_cli_package_only_uses_cwd_pylock() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "pylock_version.py"), "onnx", "--platform", "ppc64le"],
        check=True,
        capture_output=True,
        text=True,
        cwd=DATASCIENCE_PYLOCK.parent,
    )
    assert result.stdout.strip() == "1.22.0"


def test_cli_explicit_pylock_path() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "pylock_version.py"),
            str(DATASCIENCE_PYLOCK),
            "onnx",
            "--platform",
            "ppc64le",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "1.22.0"


def test_missing_package_exits_nonzero() -> None:
    with pytest.raises(SystemExit):
        locked_version(DATASCIENCE_PYLOCK, "not-a-real-package", platform_machine="ppc64le")
