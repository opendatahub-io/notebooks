from __future__ import annotations

import shutil
import subprocess

import pytest
import yaml

from tests import PROJECT_ROOT

_OVERLAY = PROJECT_ROOT / "manifests" / "rhoai" / "overlays" / "additional" / "baseline"
_ODH_BASE_PREFIX = "../../../../odh/base/"

_IMAGESTREAM_FILES = (
    "jupyter-baseline-notebook-imagestream.yaml",
    "code-server-baseline-notebook-imagestream.yaml",
    "runtime-baseline-imagestream.yaml",
)


def _kustomize_bin() -> str | None:
    return shutil.which("kustomize")


def test_baseline_overlay_references_odh_base():
    """RHOAI opt-in overlay must reuse ODH ImageStreams and params, not copies."""
    kustomization = yaml.safe_load((_OVERLAY / "kustomization.yaml").read_text())
    resources = kustomization["resources"]
    expected = [f"{_ODH_BASE_PREFIX}{name}" for name in _IMAGESTREAM_FILES]
    assert resources == expected
    for resource in resources:
        assert (_OVERLAY / resource).resolve().is_file()

    env_files: list[str] = []
    for generator in kustomization.get("configMapGenerator", []):
        env_files.extend(generator.get("envs", []))
    assert env_files == [
        f"{_ODH_BASE_PREFIX}params-latest.env",
        f"{_ODH_BASE_PREFIX}commit-latest.env",
    ]
    for env_file in env_files:
        assert (_OVERLAY / env_file).resolve().is_file()

    for name in _IMAGESTREAM_FILES:
        assert not (_OVERLAY / name).exists(), f"do not duplicate {name} in the RHOAI overlay"


def test_baseline_overlay_kustomize_build_requires_load_restrictor():
    kustomize = _kustomize_bin()
    if kustomize is None:
        pytest.skip("kustomize not on PATH")
    restricted = subprocess.run(
        [kustomize, "build", str(_OVERLAY)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert restricted.returncode != 0
    assert "security" in restricted.stderr.lower() or "load-restrictor" in restricted.stderr.lower()


def test_baseline_overlay_kustomize_build_with_load_restrictor():
    kustomize = _kustomize_bin()
    if kustomize is None:
        pytest.skip("kustomize not on PATH")
    result = subprocess.run(
        [kustomize, "build", "--load-restrictor", "LoadRestrictionsNone", str(_OVERLAY)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "_PLACEHOLDER" not in result.stdout
    for digest_host in (
        "quay.io/opendatahub/odh-workbench-jupyter-baseline-cpu-py312-c9s:",
        "quay.io/opendatahub/odh-workbench-codeserver-baseline-cpu-py312-c9s:",
        "quay.io/opendatahub/odh-pipeline-runtime-baseline-cpu-py312-c9s:",
    ):
        assert digest_host in result.stdout
