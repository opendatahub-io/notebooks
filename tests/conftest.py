from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest

logging.basicConfig(level=logging.DEBUG)

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture(scope="session")
def pylock_version():
    spec = importlib.util.spec_from_file_location("pylock_version", _SCRIPTS / "pylock_version.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
