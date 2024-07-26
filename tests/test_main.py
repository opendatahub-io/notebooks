from __future__ import annotations

import pathlib
import tomllib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest_subtests

PROJECT_ROOT = pathlib.Path(__file__).parent.parent


def test_image_pipfiles(subtests: pytest_subtests.plugin.SubTests):
    for file in PROJECT_ROOT.glob("**/Pipfile"):
        with subtests.test(msg="checking Pipfile", pipfile=file):
            directory = file.parent  # "ubi9-python-3.9"
            ubi, lang, python = directory.name.split("-")

            with open(file, "rb") as fp:
                pipfile = tomllib.load(fp)
            assert "requires" in pipfile, "Pipfile is missing a [[requires]] section"
            assert pipfile["requires"]["python_version"] == python, "Pipfile does not declare the expected Python version"
