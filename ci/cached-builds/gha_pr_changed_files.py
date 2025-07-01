import fnmatch
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
    github_token = os.environ["GITHUB_TOKEN"]
    return github_token


def list_changed_files(from_ref: str, to_ref: str) -> list[str]:
    logging.debug("Getting list of changed files from git diff")

    # https://github.com/red-hat-data-services/notebooks/pull/361: add -- in case to_ref matches a file name in the repo
    files = subprocess.check_output(
        ["git", "diff", "--name-only", from_ref, to_ref, "--"], encoding="utf-8"
    ).splitlines()

    logging.debug(f"Determined {len(files)} changed files: {files[:100]} (..., printing up to 100 files)")
    return files


def _query_build(make_target: str, query: str, env: dict[str, str] | None = None) -> str:
    results = []

    if env is None:
        env = {}

    envs = []
    for k, v in env.items():
        envs.extend(("-e", f"{k}={v}"))

    pattern = re.compile(r"#\*# " + query + r": <(?P<result>[^>]+)> #\(MACHINE-PARSED LINE\)#\*#\.\.\.")
    try:
        logging.debug(f"Running make in --just-print mode for target {make_target}")
        for line in subprocess.check_output(
            [MAKE, make_target, "--just-print", *envs], encoding="utf-8", cwd=PROJECT_ROOT
        ).splitlines():
            if m := pattern.match(line):
                results.append(m["result"])
    except subprocess.CalledProcessError as e:
        print(e.stderr, e.stdout)
        raise

    if len(results) != 1:
        raise Exception(f"Expected a single query result for target '{make_target}': {results}")

    logging.debug(f"Target {make_target} builds from {results[0]}")
    return results[0]


def get_build_directory(make_target, env: dict[str, str] | None = None) -> str:
    return _query_build(make_target, "Image build directory", env=env)


def get_build_dockerfile(make_target: str, env: dict[str, str] | None = None) -> str:
    return _query_build(make_target, "Image build Dockerfile", env=env)


def find_dockerfiles(directory: str) -> list:
    """Finds and returns a list of files matching the pattern 'Dockerfile*' in the specified directory."""
    matching_files = []
    for filename in os.listdir(directory):
        if fnmatch.fnmatch(filename, "Dockerfile*") and filename != "Dockerfile.konflux":
            matching_files.append(filename)
    return matching_files


def should_build_target(changed_files: list[str], target_directory: str) -> str:
    """Returns truthy if there is at least one changed file necessitating a build.
    Falsy (empty) string is returned otherwise."""

    # detect change in the Dockerfile directory
    for changed_file in changed_files:
        if changed_file.startswith(target_directory):
            return changed_file
    # detect change in any of the files outside
    dockerfiles = find_dockerfiles(target_directory)
    for dockerfile in dockerfiles:
        stdout = subprocess.check_output(
            [PROJECT_ROOT / "bin/buildinputs", target_directory + "/" + dockerfile], text=True, cwd=PROJECT_ROOT
        )
        logging.debug(f"{target_directory=} {dockerfile=} {stdout=}")
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
        python_version = "3.11" if "-python-3.11" in target else "3.12" if "-python-3.12" in target else "invalid-python-version"
        build_directory = get_build_directory(target, env={"RELEASE_PYTHON_VERSION": python_version})
        if reason := should_build_target(changed_files, build_directory):
            logging.info(f"✅ Will build {target} because file {reason} has been changed")
            changed.append(target)
        else:
            logging.info(f"❌ Won't build {target}")
    return changed


class SelfTests(unittest.TestCase):
    def test_list_changed_files(self):
        """This is PR #556 in opendatahub-io/notebooks"""
        changed_files = list_changed_files(from_ref="4d4841f", to_ref="2c36c11")
        assert set(changed_files) == {
            "codeserver/ubi9-python-3.9/Dockerfile",
            "codeserver/ubi9-python-3.9/run-code-server.sh",
        }

    def test_get_build_directory(self):
        directory = get_build_directory("rocm-jupyter-pytorch-ubi9-python-3.11")
        assert directory == "jupyter/rocm/pytorch/ubi9-python-3.11"

    def test_get_build_dockerfile(self):
        dockerfile = get_build_dockerfile("rocm-jupyter-pytorch-ubi9-python-3.11")
        assert dockerfile == "jupyter/rocm/pytorch/ubi9-python-3.11/Dockerfile.rocm"

    def test_should_build_target(self):
        assert "" == should_build_target(["README.md"], "jupyter/datascience/ubi9-python-3.11")
