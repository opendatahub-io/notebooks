import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import unittest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent.resolve()
MAKE = shutil.which("gmake") or shutil.which("make")


def get_github_token() -> str:
    github_token = os.environ['GITHUB_TOKEN']
    return github_token


def list_changed_files(from_ref: str, to_ref: str) -> list[str]:
    logging.debug("Getting list of changed files from git diff")

    # https://github.com/red-hat-data-services/notebooks/pull/361: add -- in case to_ref matches a file name in the repo
    files = subprocess.check_output(["git", "diff", "--name-only", from_ref, to_ref, '--'],
                                    encoding='utf-8').splitlines()

    logging.debug(f"Determined {len(files)} changed files: {files[:100]} (..., printing up to 100 files)")
    return files


def analyze_build_directories(make_target) -> list[str]:
    directories = []

    pattern = re.compile(r"#\*# Image build directory: <(?P<dir>[^>]+)> #\(MACHINE-PARSED LINE\)#\*#\.\.\.")
    try:
        logging.debug(f"Running make in --just-print mode for target {make_target}")
        for line in subprocess.check_output([MAKE, make_target, "--just-print"], encoding="utf-8",
                                            cwd=PROJECT_ROOT).splitlines():
            if m := pattern.match(line):
                directories.append(m["dir"])
    except subprocess.CalledProcessError as e:
        print(e.stderr, e.stdout)
        raise

    logging.debug(f"Target {make_target} depends on files in directories {directories}")
    return directories


def should_build_target(changed_files: list[str], target_directories: list[str]) -> str:
    """Returns truthy if there is at least one changed file necessitating a build.
    Falsy (empty) string is returned otherwise."""
    for directory in target_directories:
        # detect change in the Dockerfile directory
        for changed_file in changed_files:
            if changed_file.startswith(directory):
                return changed_file
        # detect change in any of the files outside
        stdout = subprocess.check_output([PROJECT_ROOT / "bin/buildinputs", directory + "/Dockerfile"],
                                         text=True, cwd=PROJECT_ROOT)
        logging.debug(f"{directory=} {stdout=}")
        if stdout == "\n":
            # no dependencies
            continue
        dependencies: list[str] = json.loads(stdout)
        for dependency in dependencies:
            for changed_file in changed_files:
                if changed_file.startswith(dependency):
                    return changed_file
    return ""


def filter_out_unchanged(targets: list[str], changed_files: list[str]) -> list[str]:
    changed = []
    for target in targets:
        target_directories = analyze_build_directories(target)
        if reason := should_build_target(changed_files, target_directories):
            logging.info(f"✅ Will build {target} because file {reason} has been changed")
            changed.append(target)
        else:
            logging.info(f"❌ Won't build {target}")
    return changed


class SelfTests(unittest.TestCase):
    def test_list_changed_files(self):
        """This is PR #556 in opendatahub-io/notebooks"""
        changed_files = list_changed_files(from_ref="4d4841f", to_ref="2c36c11")
        assert set(changed_files) == {'codeserver/ubi9-python-3.9/Dockerfile',
                                      'codeserver/ubi9-python-3.9/run-code-server.sh'}

    def test_analyze_build_directories(self):
        directories = analyze_build_directories("jupyter-intel-pytorch-ubi9-python-3.9")
        assert set(directories) == {"base/ubi9-python-3.9",
                                    "intel/base/gpu/ubi9-python-3.9",
                                    "jupyter/intel/pytorch/ubi9-python-3.9"}

    def test_should_build_target(self):
        assert "" == should_build_target(["README.md"], ["jupyter/datascience/ubi9-python-3.11"])
