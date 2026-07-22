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
_LOOKS_LIKE_VERSION = re.compile(r"^\d+(\.\d+)*([A-Za-z0-9.+]+)?$")  # sanity check only, not strict PEP 440

# (pylock, package, platform_machine) tuples mirror pylock_version.py call sites in Dockerfiles.
_DOCKERFILE_PIN_CASES = (
    (DATASCIENCE_PYLOCK, "onnx", "ppc64le"),
    (DATASCIENCE_PYLOCK, "pyarrow", "s390x"),
    (ROOT / "jupyter/trustyai/ubi9-python-3.12/pylock.toml", "torch", "x86_64"),
    (ROOT / "jupyter/trustyai/ubi9-python-3.12/pylock.toml", "pyarrow", "ppc64le"),
    (ROOT / "jupyter/trustyai/ubi9-python-3.12/pylock.toml", "pillow", "ppc64le"),
    (ROOT / "jupyter/trustyai/ubi9-python-3.12/pylock.toml", "accelerate", "x86_64"),
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
    assert result.stdout.strip() == datascience_onnx_ppc64le, (
        f"unexpected CLI output for {argv!r}: {result.stdout.strip()!r}"
    )


def test_missing_package_raises_lookup_error(pylock_version) -> None:
    with pytest.raises(LookupError):
        pylock_version.locked_version(DATASCIENCE_PYLOCK, "not-a-real-package", platform_machine="ppc64le")


def test_unsupported_marker_syntax_fails_fast(pylock_version) -> None:
    env = pylock_version.marker_env(python_minor="3.12", platform_machine="x86_64")
    with pytest.raises(ValueError, match="comparison operator not supported"):
        pylock_version.evaluate_marker("python_version >= '3.12'", env)
    with pytest.raises(ValueError, match="unknown marker variable"):
        pylock_version.evaluate_marker("os_release == '9'", env)
    with pytest.raises(ValueError, match="unknown marker variable"):
        pylock_version.evaluate_marker("extra == 'cuda'", env)


def test_marker_env_sets_os_name(pylock_version) -> None:
    env = pylock_version.marker_env(python_minor="3.12", platform_machine="x86_64")
    assert pylock_version.evaluate_marker("os_name == 'posix'", env), (
        "expected os_name == 'posix' to evaluate true for UBI Linux marker_env"
    )


def test_marker_ast_evaluator_handles_nested_and_in(pylock_version) -> None:
    env = pylock_version.marker_env(python_minor="3.12", platform_machine="ppc64le")
    marker_or_and = "(python_version == '3.12' or python_version == '3.11') and sys_platform == 'linux'"
    assert pylock_version.evaluate_marker(marker_or_and, env), f"expected true for {marker_or_and!r}"
    marker_in = "platform_machine in ('ppc64le', 's390x')"
    assert pylock_version.evaluate_marker(marker_in, env), f"expected true for {marker_in!r}"
    marker_not_x86 = "not (platform_machine == 'x86_64')"
    assert pylock_version.evaluate_marker(marker_not_x86, env), f"expected true for {marker_not_x86!r}"
    marker_not_ppc = "not (platform_machine == 'ppc64le')"
    assert not pylock_version.evaluate_marker(marker_not_ppc, env), f"expected false for {marker_not_ppc!r}"


@pytest.mark.parametrize(
    "pylock",
    [
        DATASCIENCE_PYLOCK,
        ROOT / "jupyter/trustyai/ubi9-python-3.12/pylock.toml",
        ROOT / "codeserver/ubi9-python-3.12/pylock.toml",
        ROOT / "runtimes/datascience/ubi9-python-3.12/pylock.toml",
    ],
)
def test_native_build_pylocks_have_parseable_markers(pylock_version, pylock: Path) -> None:
    # Syntax/whitelist guard only: evaluates every marker on x86_64. Per-arch correctness
    # for native-build packages is covered by test_locked_versions_for_dockerfile_packages.
    doc = tomllib.loads(pylock.read_text())
    markers = {entry["marker"] for entry in doc.get("packages", []) if entry.get("marker")}
    assert markers, f"expected markers in {pylock}"
    env = pylock_version.marker_env(python_minor="3.12", platform_machine="x86_64")
    for marker in markers:
        pylock_version.evaluate_marker(marker, env)


@pytest.mark.parametrize(("pylock", "package", "platform_machine"), _DOCKERFILE_PIN_CASES)
def test_locked_versions_for_dockerfile_packages(
    pylock_version,
    pylock: Path,
    package: str,
    platform_machine: str,
) -> None:
    version = pylock_version.locked_version(pylock, package, platform_machine=platform_machine)
    assert version in _versions_in_pylock(pylock, package), (
        f"{package}@{platform_machine} resolved {version!r} not present in {pylock}"
    )
    assert _LOOKS_LIKE_VERSION.match(version), f"{package}@{platform_machine} resolved invalid version {version!r}"
