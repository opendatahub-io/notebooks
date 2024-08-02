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


def test_files_that_should_be_same_are_same(subtests: pytest_subtests.plugin.SubTests):
    file_groups = {
        "ROCm de-vendor script":
            [PROJECT_ROOT / "jupyter/rocm/pytorch/ubi9-python-3.9/de-vendor-torch.sh",
             PROJECT_ROOT / "runtimes/rocm-pytorch/ubi9-python-3.9/de-vendor-torch.sh"]
    }
    for group_name, (first_file, *rest) in file_groups.items():
        with subtests.test(msg=f"Checking {group_name}"):
            for file in rest:
                assert first_file.read_text() == file.read_text(), f"The files {first_file} and {file} do not match"
