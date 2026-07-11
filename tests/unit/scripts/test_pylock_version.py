from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
DATASCIENCE_PYLOCK = ROOT / "jupyter/datascience/ubi9-python-3.12/pylock.toml"


def test_locked_version_onnx_ppc64le(pylock_version) -> None:
    assert pylock_version.locked_version(DATASCIENCE_PYLOCK, "onnx", platform_machine="ppc64le") == "1.22.0"


def test_locked_version_pyarrow_s390x(pylock_version) -> None:
    assert pylock_version.locked_version(DATASCIENCE_PYLOCK, "pyarrow", platform_machine="s390x") == "17.0.0"


def test_format_git_tag_strips_local_version(pylock_version) -> None:
    assert pylock_version.format_version("2.7.1+cu128", "git-tag") == "v2.7.1"


def test_format_apache_arrow_branch(pylock_version) -> None:
    assert pylock_version.format_version("17.0.0", "apache-arrow-branch") == "apache-arrow-17.0.0"


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


def test_missing_package_raises_lookup_error(pylock_version) -> None:
    with pytest.raises(LookupError):
        pylock_version.locked_version(DATASCIENCE_PYLOCK, "not-a-real-package", platform_machine="ppc64le")
