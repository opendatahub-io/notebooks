from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.with_subtests import with_subtests

if TYPE_CHECKING:
    from pytest import Subtests

ROOT = Path(__file__).resolve().parents[1]

NATIVE_IMAGE_DIRS = (
    ROOT / "jupyter/datascience/ubi9-python-3.12",
    ROOT / "runtimes/datascience/ubi9-python-3.12",
)


@pytest.mark.parametrize("image_dir", NATIVE_IMAGE_DIRS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_dockerfiles_read_native_versions_from_pylock(image_dir: Path, subtests: Subtests) -> None:
    dockerfiles = sorted(image_dir.glob("Dockerfile*"))
    assert dockerfiles, f"no Dockerfiles under {image_dir}"
    forbidden = (
        re.compile(r"ARG ONNX_VERSION"),
        re.compile(r"ARG PYARROW_VERSION"),
        re.compile(r"ONNX_VERSION=1\.20\.1"),
        re.compile(r"apache-arrow-17\.0\.0"),
    )

    @with_subtests(subtests, dockerfiles, msg="dockerfile")
    def _(dockerfile: Path) -> None:
        text = dockerfile.read_text()

        @with_subtests(subtests, forbidden, msg="forbidden-pattern")
        def _(pattern: re.Pattern[str]) -> None:
            assert not pattern.search(text), f"{dockerfile.name} still uses {pattern.pattern}"

        assert "pylock_version.py" in text, f"{dockerfile.name} should copy pylock_version.py"

        @with_subtests(subtests, ("onnx", "pyarrow"), msg="package")
        def _(package: str) -> None:
            # Same-line resolver only: [ \t]+ (not \s+) so newlines cannot join unrelated tokens.
            lookup = re.compile(rf"\bpylock_version\.py[ \t]+(?:[^\s\n]+[ \t]+)?{re.escape(package)}\b")
            assert lookup.search(text), f"{dockerfile.name} should resolve {package} via pylock_version.py"


@pytest.mark.parametrize("image_dir", NATIVE_IMAGE_DIRS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_pylock_pins_resolve_for_native_arches(
    image_dir: Path,
    pylock_version,
    subtests: Subtests,
) -> None:
    pylock = image_dir / "pylock.toml"
    locked_version = pylock_version.locked_version
    # Resolve per-arch independently; versions may diverge across arches in future lockfiles.
    cases = (
        ("onnx", "ppc64le"),
        ("pyarrow", "ppc64le"),
        ("pyarrow", "s390x"),
    )

    @with_subtests(subtests, cases, msg="pylock-pin")
    def _(case: tuple[str, str]) -> None:
        package, platform_machine = case
        assert locked_version(pylock, package, platform_machine=platform_machine), (
            f"{package} should resolve for {platform_machine}"
        )
