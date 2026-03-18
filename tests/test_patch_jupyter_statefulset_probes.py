"""Tests for RHAIENG-2818 CI probe widening script."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from ruamel.yaml import YAML

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "patch_jupyter_probes",
    _REPO_ROOT / "ci/cached-builds/patch_jupyter_statefulset_probes_emulated_arch.py",
)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["patch_jupyter_probes"] = _mod
_SPEC.loader.exec_module(_mod)
patch_statefulset = _mod.patch_statefulset


@pytest.fixture
def minimal_statefulset_src() -> Path:
    p = _REPO_ROOT / "jupyter/minimal/ubi9-python-3.12/kustomize/base/statefulset.yaml"
    assert p.is_file()
    return p


def test_patch_statefulset_updates_probes(minimal_statefulset_src: Path) -> None:
    yaml = YAML()
    yaml.preserve_quotes = True
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "statefulset.yaml"
        shutil.copy(minimal_statefulset_src, path)
        assert patch_statefulset(path, yaml) is True
        with path.open() as f:
            doc = yaml.load(f)
        c0 = doc["spec"]["template"]["spec"]["containers"][0]
        assert c0["livenessProbe"]["initialDelaySeconds"] == 480
        assert c0["livenessProbe"]["failureThreshold"] == 48
        assert c0["readinessProbe"]["initialDelaySeconds"] == 480
        assert c0["readinessProbe"]["failureThreshold"] == 60
        assert "tcpSocket" in c0["livenessProbe"]
        assert "httpGet" in c0["readinessProbe"]
