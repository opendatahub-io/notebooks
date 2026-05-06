"""Fail when tracked user-facing pins in image pylocks regress vs a git baseline (typically main).

Compares each ``pylock*.toml`` to the same path at ``NOTEBOOKS_DOWNGRADE_BASE_REF`` (default:
``origin/main`` if present) so accidental downgrades (e.g. pandas 2.3 → 2.1) are caught in
``make test`` once the baseline ref is available locally or in CI.
"""

from __future__ import annotations

import os
import subprocess
import tomllib
from typing import TYPE_CHECKING

import packaging.markers
import packaging.utils
import packaging.version
import pytest

from tests import PROJECT_ROOT
from tests.test_main import _iter_image_pyproject_pylock_files

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

# PyPI names for packages we advertise in ImageStream ``notebook-python-dependencies``
# (same intent as ``tests.test_main`` / ``manifests/tools/update_imagestream_annotations_from_pylock``).
_TRACKED_PYPI_RAW: tuple[str, ...] = (
    "accelerate",
    "boto3",
    "codeflare-sdk",
    "datasets",
    "feast",
    "jupyterlab",
    "kafka-python-ng",
    "kfp",
    "kubeflow-training",
    "matplotlib",
    "mlflow",
    "numpy",
    "odh-elyra",
    "pandas",
    "psycopg",
    "pymongo",
    "pyodbc",
    "scikit-learn",
    "scipy",
    "tensorboard",
    "tensorflow",
    "tensorflow-rocm",
    "torch",
    "torchvision",
    "transformers",
    "trustyai",
    "llmcompressor",
    "skl2onnx",
    "nvidia-cuda-runtime-cu12",
    "mysql-connector-python",
)

TRACKED_PACKAGES_CANONICAL: frozenset[str] = frozenset(packaging.utils.canonicalize_name(n) for n in _TRACKED_PYPI_RAW)


def _resolve_base_ref() -> str | None:
    env = (os.environ.get("NOTEBOOKS_DOWNGRADE_BASE_REF") or "").strip()
    candidates: list[str | None] = [
        env or None,
        "origin/main",
        "main",
    ]
    for ref in candidates:
        if not ref:
            continue
        if _git_commit_exists(ref):
            return ref
    return None


def _git_commit_exists(ref: str) -> bool:
    p = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    return p.returncode == 0


def _git_show_text(ref: str, rel_path: str) -> str | None:
    p = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "show", f"{ref}:{rel_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        return None
    return p.stdout


def _python_full_from_image_dir(directory: pathlib.Path) -> str:
    name = directory.name
    try:
        _ubi, _lang, pyver = name.split("-")
    except ValueError as e:
        raise ValueError(f"Expected ubi9-python-X.Y directory name, got {name!r}") from e
    return pyver


def _parse_pylock_versions_for_linux(pylock_text: str, python_full: str) -> dict[str, str]:
    doc = tomllib.loads(pylock_text)
    marker_env = {
        "python_full_version": f"{python_full}.0",
        "python_version": python_full,
        "implementation_name": "cpython",
        "sys_platform": "linux",
    }
    out: dict[str, str] = {}
    for p in doc.get("packages", []):
        name = p.get("name")
        version = p.get("version")
        if name is None or version is None:
            continue
        if "marker" in p and not packaging.markers.Marker(p["marker"]).evaluate(marker_env):
            continue
        # Last wins when the lockfile lists the same name multiple times for overlapping markers.
        prev = out.get(name)
        if prev is not None and prev != version:
            raise AssertionError(
                f"Ambiguous pylock for {name!r} under linux/{python_full}: "
                f"matched multiple versions ({prev}, {version})"
            )
        out[name] = version
    return out


def _iter_downgrades(
    current: dict[str, str], baseline: dict[str, str]
) -> Iterator[tuple[str, packaging.version.Version, packaging.version.Version]]:
    for raw_name, cur_s in current.items():
        cn = packaging.utils.canonicalize_name(raw_name)
        if cn not in TRACKED_PACKAGES_CANONICAL:
            continue
        base_s = baseline.get(raw_name)
        if base_s is None:
            # Baseline may use a different normalized spelling; try canonical key scan
            for bk, bv in baseline.items():
                if packaging.utils.canonicalize_name(bk) == cn:
                    base_s = bv
                    break
            else:
                continue
        try:
            cur_v = packaging.version.parse(cur_s)
            base_v = packaging.version.parse(base_s)
        except packaging.version.InvalidVersion:
            continue
        if cur_v < base_v:
            yield (raw_name, cur_v, base_v)


def test_pylock_tracked_packages_not_downgraded_vs_git_base(subtests):
    if os.environ.get("NOTEBOOKS_DOWNGRADE_CHECK", "").strip().lower() in ("0", "false", "no"):
        pytest.skip("NOTEBOOKS_DOWNGRADE_CHECK disabled")

    if not (PROJECT_ROOT / ".git").exists():
        pytest.skip("Not a git checkout; downgrade check skipped")

    base_ref = _resolve_base_ref()
    if base_ref is None:
        pytest.skip(
            "No git baseline ref found (tried NOTEBOOKS_DOWNGRADE_BASE_REF, origin/main, main). "
            "Fetch the default branch, e.g. `git fetch origin main:refs/remotes/origin/main`, "
            "or set NOTEBOOKS_DOWNGRADE_BASE_REF to a local commit."
        )

    for lock_path in sorted(_iter_image_pyproject_pylock_files()):
        if not lock_path.is_file():
            continue
        rel = str(lock_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        pyproject_dir = lock_path.parent
        if pyproject_dir.name == "uv.lock.d":
            pyproject_dir = pyproject_dir.parent
        try:
            python_full = _python_full_from_image_dir(pyproject_dir)
        except ValueError:
            continue

        base_text = _git_show_text(base_ref, rel)
        if base_text is None:
            continue

        current_text = lock_path.read_text(encoding="utf-8")
        try:
            cur_map = _parse_pylock_versions_for_linux(current_text, python_full)
        except tomllib.TOMLDecodeError as e:
            with subtests.test(msg=rel):
                raise AssertionError(f"Invalid TOML in current pylock (downgrade check): {rel}") from e
            continue
        except AssertionError as e:
            with subtests.test(msg=rel):
                raise AssertionError(f"Failed to parse current pylock for downgrade check: {rel}") from e
            continue

        try:
            base_map = _parse_pylock_versions_for_linux(base_text, python_full)
        except tomllib.TOMLDecodeError:
            # Baseline ref may not have valid TOML at this path (e.g. older lockfile format).
            continue
        except AssertionError as e:
            with subtests.test(msg=rel):
                raise AssertionError(f"Failed to parse baseline pylock for downgrade check: {rel}") from e
            continue

        downgrades = list(_iter_downgrades(cur_map, base_map))
        with subtests.test(msg=rel):
            if not downgrades:
                continue
            lines = [
                f"Tracked package downgrade(s) vs {base_ref} in {rel}:",
                "  (pin is older than baseline — if intentional, bump baseline or adjust pins explicitly)",
            ]
            for name, cur_v, base_v in sorted(downgrades, key=lambda t: t[0].lower()):
                lines.append(f"  - {name}: {cur_v} < {base_v} (baseline)")
            pytest.fail("\n".join(lines))
