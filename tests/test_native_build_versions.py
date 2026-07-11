from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load_pylock_version():
    spec = importlib.util.spec_from_file_location("pylock_version", SCRIPTS / "pylock_version.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


locked_version = _load_pylock_version().locked_version

NATIVE_IMAGE_DIRS = (
    ROOT / "jupyter/datascience/ubi9-python-3.12",
    ROOT / "runtimes/datascience/ubi9-python-3.12",
)


@pytest.mark.parametrize("image_dir", NATIVE_IMAGE_DIRS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_dockerfiles_read_native_versions_from_pylock(image_dir: Path) -> None:
    dockerfiles = sorted(image_dir.glob("Dockerfile*"))
    assert dockerfiles, f"no Dockerfiles under {image_dir}"
    forbidden = (
        re.compile(r"ARG ONNX_VERSION"),
        re.compile(r"ARG PYARROW_VERSION"),
        re.compile(r"ONNX_VERSION=1\.20\.1"),
        re.compile(r"apache-arrow-17\.0\.0"),
        re.compile(r"ARG ONNX_VERSION=v1\.20\.1"),
    )
    required = (
        "pylock_version.py",
        "pylock.toml",
    )
    for dockerfile in dockerfiles:
        text = dockerfile.read_text()
        for pattern in forbidden:
            assert not pattern.search(text), f"{dockerfile.name} still uses {pattern.pattern}"
        for needle in required:
            assert needle in text, f"{dockerfile.name} should reference {needle}"


@pytest.mark.parametrize("image_dir", NATIVE_IMAGE_DIRS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_pylock_pins_onnx_and_pyarrow_for_native_arches(image_dir: Path) -> None:
    pylock = image_dir / "pylock.toml"
    onnx_ppc64le = locked_version(pylock, "onnx", platform_machine="ppc64le")
    pyarrow_ppc64le = locked_version(pylock, "pyarrow", platform_machine="ppc64le")
    pyarrow_s390x = locked_version(pylock, "pyarrow", platform_machine="s390x")
    assert onnx_ppc64le == "1.22.0"
    assert pyarrow_ppc64le == pyarrow_s390x == "17.0.0"
