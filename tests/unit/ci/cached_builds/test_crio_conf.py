"""The CI kubelet must not confine pods with crio-default."""

from __future__ import annotations

import tomllib
from pathlib import Path

_CRIO_CONF = Path(__file__).resolve().parents[4] / "ci" / "cached-builds" / "crio.conf"


def test_ci_crio_disables_apparmor() -> None:
    """Ubuntu 26.04 denies signals from crio-default to the stacked peer.

    Papermill shuts the kernel down with SIGINT. That kill returns EPERM and
    fails Run image tests after the notebook itself has passed.
    """
    config = tomllib.loads(_CRIO_CONF.read_text())

    assert config["crio"]["runtime"]["apparmor_profile"] == "unconfined"
