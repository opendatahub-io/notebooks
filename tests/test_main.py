from __future__ import annotations

import os
import logging
import pathlib
import subprocess
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


def test_make_building_only_specified_images(subtests: pytest_subtests.plugin.SubTests):
    for goals in (["rocm-jupyter-tensorflow-ubi9-python-3.9"], ["rocm-jupyter-tensorflow-ubi9-python-3.9", "base-ubi9-python-3.9"]):
        with subtests.test(msg="Running goals", goals=goals):
            lines = dryrun_make(goals, env={"BUILD_DEPENDENT_IMAGES": "no"})
            builds_number = 0
            for line in lines:
                if "podman build" in line:
                    builds_number += 1
            assert builds_number == len(goals)


def test_make_disable_pushing():
    lines = dryrun_make(["rocm-jupyter-tensorflow-ubi9-python-3.9"], env={"PUSH_IMAGES": ""})
    for line in lines:
        assert "podman push" not in line


def dryrun_make(make_args: list[str], env: dict[str, str] | None = None) -> list[str]:
    env = env or {}

    try:
        logging.info(f"Running make in --just-print mode for target(s) {make_args} with env {env}")
        lines = subprocess.check_output(["make", "--just-print", *make_args], encoding="utf-8",
                                        env={**os.environ, **env},
                                        cwd=PROJECT_ROOT).splitlines()
        for line in lines:
            logging.debug(line)
        return lines
    except subprocess.CalledProcessError as e:
        print(e.stderr, e.stdout)
        raise
