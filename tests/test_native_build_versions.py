from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

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
    )
    for dockerfile in dockerfiles:
        text = dockerfile.read_text()
        for pattern in forbidden:
            assert not pattern.search(text), f"{dockerfile.name} still uses {pattern.pattern}"
        assert "pylock_version.py" in text, f"{dockerfile.name} should copy pylock_version.py"
        for package in ("onnx", "pyarrow"):
            # Same-line resolver only: [ \t]+ (not \s+) so newlines cannot join unrelated tokens.
            lookup = re.compile(rf"\bpylock_version\.py[ \t]+(?:[^\s\n]+[ \t]+)?{re.escape(package)}\b")
            assert lookup.search(text), f"{dockerfile.name} should resolve {package} via pylock_version.py"


@pytest.mark.parametrize("image_dir", NATIVE_IMAGE_DIRS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_pylock_pins_resolve_for_native_arches(image_dir: Path, pylock_version) -> None:
    pylock = image_dir / "pylock.toml"
    locked_version = pylock_version.locked_version
    # Resolve per-arch independently; versions may diverge across arches in future lockfiles.
    assert locked_version(pylock, "onnx", platform_machine="ppc64le"), "onnx should resolve for ppc64le"
    assert locked_version(pylock, "pyarrow", platform_machine="ppc64le"), "pyarrow should resolve for ppc64le"
    assert locked_version(pylock, "pyarrow", platform_machine="s390x"), "pyarrow should resolve for s390x"
