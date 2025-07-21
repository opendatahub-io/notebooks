#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import typing
import unittest

import gha_pr_changed_files

"""Determines whether we have deploy Makefile tests for this target or not

https://github.com/openshift/release/blob/master/ci-operator/config/opendatahub-io/notebooks/opendatahub-io-notebooks-main.yaml#L1485
"""


class Args(argparse.Namespace):
    """Type annotation to have autocompletion for args"""

    target: str


def main() -> None:
    parser = argparse.ArgumentParser("make_test.py")
    parser.add_argument("--target", type=str)
    args = typing.cast("Args", parser.parse_args())

    has_tests = check_tests(args.target)

    if "GITHUB_ACTIONS" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "at") as f:
            print(f"tests={json.dumps(has_tests)}", file=f)

    print(f"{has_tests=}")


def check_tests(target: str) -> bool:
    if target.startswith(("rocm-jupyter-minimal-", "rocm-jupyter-datascience-")):
        return False  # we don't have specific tests for -minimal-, ... in ci-operator/config

    build_directory = gha_pr_changed_files.get_build_directory(target)
    kustomization = (
        pathlib.Path(gha_pr_changed_files.PROJECT_ROOT) / build_directory / "kustomize/base/kustomization.yaml"
    )

    return kustomization.is_file()


class TestCheckTests(unittest.TestCase):
    def test_has_tests(self):
        # This is a overly simplistic test - but with chained build removals - we don't have any targets that don't contain a kustomization.yaml file now
        # So relying on the internal validation of check_tests to return a Falsy value even if the argument doesn't belond to an actual target
        assert check_tests("rocm-jupyter-minimal-dummy") is False

        # TODO: figure out a way to dynamically seed this target so we don't need to change if/when python version updates
        assert check_tests("jupyter-minimal-ubi9-python-3.11") is True


if __name__ == "__main__":
    main()
