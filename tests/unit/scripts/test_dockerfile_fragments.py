"""Unit tests for dockerfile_fragments.sanity_check."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.dockerfile_fragments as df


def test_sanity_check_accepts_known_suffix(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile.cpu"
    dockerfile.write_text("### BEGIN known\nsome line\n### END known\n", encoding="utf-8")

    df.sanity_check(dockerfile, {"known": "replacement"})


def test_sanity_check_raises_for_unknown_suffix(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile.cpu"
    dockerfile.write_text("### BEGIN missing\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Expected replacement for '### BEGIN missing'"):
        df.sanity_check(dockerfile, {"known": "replacement"})


@pytest.mark.parametrize("marker", ["### BEGIN", "### END"])
def test_sanity_check_rejects_marker_without_suffix(tmp_path: Path, marker: str) -> None:
    dockerfile = tmp_path / "Dockerfile.cpu"
    dockerfile.write_text(marker + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="without a suffix"):
        df.sanity_check(dockerfile, {})
