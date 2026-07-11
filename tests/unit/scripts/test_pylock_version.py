from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
DATASCIENCE_PYLOCK = ROOT / "jupyter/datascience/ubi9-python-3.12/pylock.toml"


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


def test_unsupported_marker_syntax_fails_fast(pylock_version) -> None:
    with pytest.raises(ValueError, match="unsupported marker comparison"):
        pylock_version.evaluate_marker("python_version >= '3.12'", pylock_version.marker_env(python_minor="3.12", platform_machine="x86_64"))


def test_cli_runs_without_third_party_deps() -> None:
    result = subprocess.run(
        [sys.executable, "-S", str(SCRIPTS / "pylock_version.py"), "onnx", "--platform", "ppc64le"],
        check=True,
        capture_output=True,
        text=True,
        cwd=DATASCIENCE_PYLOCK.parent,
    )
    assert result.stdout.strip() == "1.22.0"


@pytest.mark.parametrize(
    ("pylock", "package", "platform_machine", "expected"),
    [
        (DATASCIENCE_PYLOCK, "onnx", "ppc64le", "1.22.0"),
        (DATASCIENCE_PYLOCK, "pyarrow", "s390x", "17.0.0"),
        (ROOT / "jupyter/trustyai/ubi9-python-3.12/pylock.toml", "torch", "x86_64", "2.7.1+cu128"),
        (ROOT / "jupyter/trustyai/ubi9-python-3.12/pylock.toml", "pyarrow", "ppc64le", "20.0.0"),
        (ROOT / "codeserver/ubi9-python-3.12/pylock.toml", "pillow", "ppc64le", "12.3.0"),
    ],
)
def test_locked_versions_for_dockerfile_packages(pylock_version, pylock: Path, package: str, platform_machine: str, expected: str) -> None:
    assert pylock_version.locked_version(pylock, package, platform_machine=platform_machine) == expected
