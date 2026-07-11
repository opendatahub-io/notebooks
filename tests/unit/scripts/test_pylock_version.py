from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
DATASCIENCE_PYLOCK = ROOT / "jupyter/datascience/ubi9-python-3.12/pylock.toml"
_PEP440_VERSION = re.compile(r"^\d+(\.\d+)*([A-Za-z0-9.+]+)?$")

# (pylock, package, platform_machine) tuples mirror pylock_version.py call sites in Dockerfiles.
_DOCKERFILE_PIN_CASES = (
    (DATASCIENCE_PYLOCK, "onnx", "ppc64le"),
    (DATASCIENCE_PYLOCK, "pyarrow", "s390x"),
    (ROOT / "jupyter/trustyai/ubi9-python-3.12/pylock.toml", "torch", "x86_64"),
    (ROOT / "jupyter/trustyai/ubi9-python-3.12/pylock.toml", "pyarrow", "ppc64le"),
    (ROOT / "codeserver/ubi9-python-3.12/pylock.toml", "pillow", "ppc64le"),
)


def _versions_in_pylock(pylock: Path, package: str) -> set[str]:
    doc = tomllib.loads(pylock.read_text())
    return {entry["version"] for entry in doc.get("packages", []) if entry["name"] == package}


@pytest.fixture
def datascience_onnx_ppc64le(pylock_version) -> str:
    return pylock_version.locked_version(DATASCIENCE_PYLOCK, "onnx", platform_machine="ppc64le")


@pytest.mark.parametrize(
    ("argv", "cwd"),
    [
        ([str(SCRIPTS / "pylock_version.py"), "onnx", "--platform", "ppc64le"], DATASCIENCE_PYLOCK.parent),
        (
            [
                str(SCRIPTS / "pylock_version.py"),
                str(DATASCIENCE_PYLOCK),
                "onnx",
                "--platform",
                "ppc64le",
            ],
            None,
        ),
        (["-S", str(SCRIPTS / "pylock_version.py"), "onnx", "--platform", "ppc64le"], DATASCIENCE_PYLOCK.parent),
    ],
    ids=["package-only", "explicit-pylock", "stdlib-only"],
)
def test_cli_resolves_onnx_for_ppc64le(argv: list[str], cwd: Path | None, datascience_onnx_ppc64le: str) -> None:
    result = subprocess.run(
        [sys.executable, *argv],
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    assert result.stdout.strip() == datascience_onnx_ppc64le


def test_missing_package_raises_lookup_error(pylock_version) -> None:
    with pytest.raises(LookupError):
        pylock_version.locked_version(DATASCIENCE_PYLOCK, "not-a-real-package", platform_machine="ppc64le")


def test_unsupported_marker_syntax_fails_fast(pylock_version) -> None:
    env = pylock_version.marker_env(python_minor="3.12", platform_machine="x86_64")
    with pytest.raises(ValueError, match="unsupported marker comparison operator"):
        pylock_version.evaluate_marker("python_version >= '3.12'", env)
    with pytest.raises(ValueError, match="double-quoted literals"):
        pylock_version.evaluate_marker('python_version == "3.12"', env)
    with pytest.raises(ValueError, match="nested marker disjunction"):
        pylock_version.evaluate_marker("(python_version == '3.12' or python_version == '3.11') and sys_platform == 'linux'", env)


@pytest.mark.parametrize(
    "pylock",
    [
        DATASCIENCE_PYLOCK,
        ROOT / "jupyter/trustyai/ubi9-python-3.12/pylock.toml",
        ROOT / "codeserver/ubi9-python-3.12/pylock.toml",
        ROOT / "runtimes/datascience/ubi9-python-3.12/pylock.toml",
    ],
)
def test_native_build_pylocks_use_supported_marker_format(pylock_version, pylock: Path) -> None:
    doc = tomllib.loads(pylock.read_text())
    markers = {entry["marker"] for entry in doc.get("packages", []) if entry.get("marker")}
    assert markers, f"expected markers in {pylock}"
    for marker in markers:
        pylock_version._assert_marker_format_supported(marker)


@pytest.mark.parametrize(("pylock", "package", "platform_machine"), _DOCKERFILE_PIN_CASES)
def test_locked_versions_for_dockerfile_packages(
    pylock_version,
    pylock: Path,
    package: str,
    platform_machine: str,
) -> None:
    version = pylock_version.locked_version(pylock, package, platform_machine=platform_machine)
    assert version in _versions_in_pylock(pylock, package)
    assert _PEP440_VERSION.match(version)
