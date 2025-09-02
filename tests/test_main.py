from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tomllib
from typing import TYPE_CHECKING

import packaging.requirements
import pytest

from tests import PROJECT_ROOT

if TYPE_CHECKING:
    from typing import Any
    import pytest_subtests

MAKE = shutil.which("gmake") or shutil.which("make")


def test_image_pyprojects(subtests: pytest_subtests.plugin.SubTests):
    for file in PROJECT_ROOT.glob("**/pyproject.toml"):
        logging.info(file)
        with subtests.test(msg="checking pyproject.toml", pipfile=file):
            directory = file.parent  # "ubi9-python-3.11"
            try:
                _ubi, _lang, python = directory.name.split("-")
            except ValueError:
                pytest.skip(f"skipping {directory.name}/pyproject.toml as it is not an image directory")

            pyproject = tomllib.loads(file.read_text())
            with subtests.test(msg="checking pyproject.toml", pyproject=file):
                assert "project" in pyproject, "pyproject.toml is missing a [project] section"
                assert "requires-python" in pyproject["project"], (
                    "pyproject.toml is missing a [project.requires-python] section"
                )
                assert pyproject["project"]["requires-python"] == f"=={python}.*", (
                    "pyproject.toml does not declare the expected Python version"
                )

                assert "dependencies" in pyproject["project"], (
                    "pyproject.toml is missing a [project.dependencies] section"
                )

            pylock = tomllib.loads(file.with_name("pylock.toml").read_text())
            pylock_packages: dict[str, dict[str, Any]] = {p["name"]: p for p in pylock["packages"]}
            with subtests.test(msg="checking pylock.toml consistency with pyproject.toml", pyproject=file):
                for d in pyproject["project"]["dependencies"]:
                    requirement = packaging.requirements.Requirement(d)

                    assert requirement.name in pylock_packages, f"Dependency {d} is not in pylock.toml"
                    version = pylock_packages[requirement.name]["version"]
                    assert requirement.specifier.contains(version), (
                        f"Version of {d} in pyproject.toml does not match {version=} in pylock.toml"
                    )


def test_files_that_should_be_same_are_same(subtests: pytest_subtests.plugin.SubTests):
    file_groups = {
        "ROCm de-vendor script": [
            PROJECT_ROOT / "jupyter/rocm/pytorch/ubi9-python-3.12/de-vendor-torch.sh",
            PROJECT_ROOT / "runtimes/rocm-pytorch/ubi9-python-3.12/de-vendor-torch.sh",
        ]
    }
    for group_name, (first_file, *rest) in file_groups.items():
        with subtests.test(msg=f"Checking {group_name}"):
            for file in rest:
                assert first_file.read_text() == file.read_text(), f"The files {first_file} and {file} do not match"


def test_make_disable_pushing():
    # NOTE: the image below needs to exist in the Makefile
    lines = dryrun_make(["rocm-jupyter-tensorflow-ubi9-python-3.12"], env={"PUSH_IMAGES": ""})
    for line in lines:
        assert "podman push" not in line


def dryrun_make(make_args: list[str], env: dict[str, str] | None = None) -> list[str]:
    env = env or {}

    try:
        logging.info(f"Running make in --just-print mode for target(s) {make_args} with env {env}")
        lines = subprocess.check_output(
            [MAKE, "--just-print", *make_args], encoding="utf-8", env={**os.environ, **env}, cwd=PROJECT_ROOT
        ).splitlines()
        for line in lines:
            logging.debug(line)
        return lines
    except subprocess.CalledProcessError as e:
        print(e.stderr, e.stdout)
        raise
