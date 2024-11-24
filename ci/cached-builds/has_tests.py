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
    args = typing.cast(Args, parser.parse_args())

    has_tests = check_tests(args.target)

    if "GITHUB_ACTIONS" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "at") as f:
            print(f"tests={json.dumps(has_tests)}", file=f)

    print(f"{has_tests=}")


def check_tests(target: str) -> bool:
    if target.startswith("rocm-jupyter-minimal-") or target.startswith("rocm-jupyter-datascience-"):
        return False  # we don't have specific tests for -minimal-, ... in ci-operator/config
    if '-intel-' in target:
        return False  # RHOAIENG-8388: Intel tensorflow notebook failed to get tested on OCP-CI

    has_tests = False
    dirs = gha_pr_changed_files.analyze_build_directories(target)
    for d in reversed(dirs):  # (!)
        kustomization = pathlib.Path(gha_pr_changed_files.PROJECT_ROOT) / d / "kustomize/base/kustomization.yaml"
        has_tests = has_tests or kustomization.is_file()
        break  # TODO: check only the last directory (the top level layer) for now
    return has_tests


class TestCheckTests(unittest.TestCase):
    def test_has_tests(self):
        assert check_tests("base-c9s-python-3.11") is False
        assert check_tests("jupyter-minimal-ubi9-python-3.9") is True


if __name__ == "__main__":
    main()
