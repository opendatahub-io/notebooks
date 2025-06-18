#!/usr/bin/env python3

import argparse
import enum
import json
import logging
import os
import pathlib
import re
import sys
import unittest

import gha_pr_changed_files
import makefile_helper

"""Trivial Makefile parser that extracts target dependencies so that we can build each Dockerfile image target in its
own GitHub Actions job.

The parsing is not able to handle general Makefiles, it only works with the Makefile in this project.
Use https://pypi.org/project/py-make/ or https://github.com/JetBrains/intellij-plugins/tree/master/makefile/grammars if you look for general parser."""

project_dir = pathlib.Path(__file__).parent.parent.parent.absolute()


def extract_image_targets(makefile_dir: pathlib.Path | str | None = None) -> list[str]:
    if makefile_dir is None:
        makefile_dir = os.getcwd()

    makefile_all_target = "all-images"

    output = makefile_helper.dry_run_makefile(target=makefile_all_target, makefile_dir=makefile_dir)

    # Extract the 'all-images' entry and its values
    all_images = []
    match = re.search(rf"^{makefile_all_target}:\s+(.*)$", output, re.MULTILINE)
    if match:
        all_images = match.group(1).split()

    if len(all_images) < 1:
        raise Exception("No image dependencies found for 'all-images' Makefile target")

    return all_images


class RhelImages(enum.Enum):
    EXCLUDE = "exclude"
    INCLUDE = "include"
    INCLUDE_ONLY = "include-only"


class S390xImages(enum.Enum):
    EXCLUDE = "exclude"
    INCLUDE = "include"
    ONLY = "only"


def main() -> None:
    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "--from-ref", type=str, required=False, help="Git ref of the base branch (to determine changed files)"
    )
    argparser.add_argument(
        "--to-ref", type=str, required=False, help="Git ref of the PR branch (to determine changed files)"
    )
    argparser.add_argument(
        "--rhel-images",
        type=RhelImages,
        required=False,
        default=RhelImages.INCLUDE,
        nargs="?",
        help="Whether to `include` rhel images or `exclude` them or `include-only` them",
    )
    argparser.add_argument(
        "--s390x-images",
        type=S390xImages,
        required=False,
        default=S390xImages.EXCLUDE,
        nargs="?",
        help="Whether to include, exclude, or only include s390x images",
    )
    args = argparser.parse_args()

    targets = extract_image_targets()

    if args.from_ref:
        logging.info("Skipping targets not modified in the PR")
        changed_files = gha_pr_changed_files.list_changed_files(args.from_ref, args.to_ref)
        targets = gha_pr_changed_files.filter_out_unchanged(targets, changed_files)

    if args.rhel_images == RhelImages.INCLUDE:
        pass
    elif args.rhel_images == RhelImages.EXCLUDE:
        targets = [target for target in targets if "rhel" not in target]
    elif args.rhel_images == RhelImages.INCLUDE_ONLY:
        targets = [target for target in targets if "rhel" in target]
    else:
        raise Exception(f"Unknown value for --rhel-images: {args.rhel_images}")

    if args.s390x_images == S390xImages.INCLUDE:
        pass
    elif args.s390x_images == S390xImages.EXCLUDE:
        targets = [target for target in targets if "s390x" not in target]
    elif args.s390x_images == S390xImages.ONLY:
        targets = [target for target in targets if "s390x" in target]
    else:
        raise Exception(f"Unknown value for --s390x-images: {args.s390x_images}")

    # https://stackoverflow.com/questions/66025220/paired-values-in-github-actions-matrix
    output = [
        "matrix="
        + json.dumps(
            {
                "include": [
                    {
                        "target": target,
                        "subscription": "rhel" in target,
                        "s390x": ("s390x" in target) and (args.s390x_images != S390xImages.EXCLUDE),
                    }
                    for target in targets
                ],
            },
            separators=(",", ":"),
        ),
        "has_jobs=" + json.dumps(len(targets) > 0, separators=(",", ":")),
    ]

    print("targets", targets)
    print(*output, sep="\n")

    if "GITHUB_ACTIONS" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "at") as f:
            for entry in output:
                print(entry, file=f)
    else:
        logging.info("Not running on Github Actions, won't produce GITHUB_OUTPUT")


if __name__ == "__main__":
    main()


class SelfTests(unittest.TestCase):
    def test_select_changed_targets_dockerfile(self):
        targets = extract_image_targets(makefile_dir=project_dir)

        changed_files = ["jupyter/datascience/ubi9-python-3.11/Dockerfile.cpu"]

        targets = gha_pr_changed_files.filter_out_unchanged(targets, changed_files)
        assert set(targets) == {"jupyter-datascience-ubi9-python-3.11"}

    def test_select_changed_targets_shared_file(self):
        targets = extract_image_targets(makefile_dir=project_dir)

        changed_files = ["cuda/ubi9-python-3.11/NGC-DL-CONTAINER-LICENSE"]

        # With the removal of chained builds - which now potentially has multiple Dockerfiles defined in a given
        # directory, there is an inefficiency introduced to 'gha_pr_changed_files' as demonstrated by this unit test.
        # Even though this test only changes a (shared) CUDA file - you will notice the 'cpu' and 'rocm' targets
        # also being returned.  Odds of this inefficiency noticably "hurting us" is low - so of the opinion we can
        # simply treat this as technical debt.
        targets = gha_pr_changed_files.filter_out_unchanged(targets, changed_files)
        assert set(targets) == {
            "jupyter-minimal-ubi9-python-3.11",
            "cuda-jupyter-minimal-ubi9-python-3.11",
            "cuda-jupyter-pytorch-ubi9-python-3.11",
            "runtime-cuda-pytorch-ubi9-python-3.11",
            "cuda-jupyter-tensorflow-ubi9-python-3.11",
            "rocm-jupyter-minimal-ubi9-python-3.11",
            "runtime-cuda-tensorflow-ubi9-python-3.11",
        }
