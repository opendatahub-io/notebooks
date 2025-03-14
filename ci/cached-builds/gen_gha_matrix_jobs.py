import argparse
import json
import logging
import platform
import subprocess
import os
import pathlib
import re
import string
import sys
import unittest

import gha_pr_changed_files

"""Trivial Makefile parser that extracts target dependencies so that we can build each Dockerfile image target in its
own GitHub Actions job.

The parsing is not able to handle general Makefiles, it only works with the Makefile in this project.
Use https://pypi.org/project/py-make/ or https://github.com/JetBrains/intellij-plugins/tree/master/makefile/grammars if you look for general parser."""

project_dir = pathlib.Path(__file__).parent.parent.parent.absolute()


def parse_makefile(target: str, makefile_dir: str) -> str:
    # Check if the operating system is macOS
    if platform.system() == 'Darwin':
        make_command = 'gmake'
    else:
        make_command = 'make'

    try:
        # Run the make (or gmake) command and capture the output
        result = subprocess.run([make_command, '-nps', target], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, cwd=makefile_dir)
    except subprocess.CalledProcessError as e:
        # Handle errors if the make command fails
        print(f'{make_command} failed with return code: {e.returncode}:\n{e.stderr}', file=sys.stderr)
        raise
    except Exception as e:
        # Handle any other exceptions
        print(f'Error occurred attempting to parse Makefile:\n{str(e)}', file=sys.stderr)
        raise

    return result.stdout


def extract_image_targets(makefile_dir: str = os.getcwd()) -> list[str]:
    makefile_all_target = 'all-images'

    output = parse_makefile(target=makefile_all_target, makefile_dir=makefile_dir)

    # Extract the 'all-images' entry and its values
    all_images = []
    match = re.search(rf'^{makefile_all_target}:\s+(.*)$', output, re.MULTILINE)
    if match:
        all_images = match.group(1).split()

    if len(all_images) < 1:
        raise Exception("No image dependencies found for 'all-images' Makefile target")

    return all_images


def main() -> None:
    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    argparser = argparse.ArgumentParser()
    argparser.add_argument("--from-ref", type=str, required=False,
                           help="Git ref of the base branch (to determine changed files)")
    argparser.add_argument("--to-ref", type=str, required=False,
                           help="Git ref of the PR branch (to determine changed files)")
    args = argparser.parse_args()


    targets = extract_image_targets()

    if args.from_ref:
        logging.info(f"Skipping targets not modified in the PR")
        changed_files = gha_pr_changed_files.list_changed_files(args.from_ref, args.to_ref)
        targets = gha_pr_changed_files.filter_out_unchanged(targets, changed_files)

    output = [
        f"matrix={json.dumps({"target": targets}, separators=(',', ':'))}",
        f"has_jobs={json.dumps(len(targets) > 0, separators=(',', ':'))}"
    ]

    print("targets", targets)
    print(*output, sep="\n")

    if "GITHUB_ACTIONS" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "at") as f:
            for entry in output:
                print(entry, file=f)
    else:
        logging.info(f"Not running on Github Actions, won't produce GITHUB_OUTPUT")


if __name__ == '__main__':
    main()


class SelfTests(unittest.TestCase):
    def test_select_changed_targets_dockerfile(self):
        targets = extract_image_targets(makefile_dir=project_dir)

        changed_files = ["jupyter/datascience/ubi9-python-3.11/Dockerfile.cpu"]

        targets = gha_pr_changed_files.filter_out_unchanged(targets, changed_files)
        assert set(targets) == {'jupyter-datascience-ubi9-python-3.11'}

    def test_select_changed_targets_shared_file(self):
        targets = extract_image_targets(makefile_dir=project_dir)

        changed_files = ["cuda/ubi9-python-3.11/NGC-DL-CONTAINER-LICENSE"]

        # With the removal of chained builds - which now potentially has multiple Dockerfiles defined in a given
        # directory, there is an inefficiency introduced to 'gha_pr_changed_files' as demonstrated by this unit test.
        # Even though this test only changes a (shared) CUDA file - you will notice the 'cpu' and 'rocm' targets
        # also being returned.  Odds of this inefficiency noticably "hurting us" is low - so of the opinion we can
        # simply treat this as technical debt.
        targets = gha_pr_changed_files.filter_out_unchanged(targets, changed_files)
        assert set(targets) == {'jupyter-minimal-ubi9-python-3.11',
                                'cuda-jupyter-minimal-ubi9-python-3.11',
                                'cuda-jupyter-pytorch-ubi9-python-3.11',
                                'runtime-cuda-pytorch-ubi9-python-3.11',
                                'cuda-jupyter-tensorflow-ubi9-python-3.11',
                                'rocm-jupyter-minimal-ubi9-python-3.11',
                                'runtime-cuda-tensorflow-ubi9-python-3.11'}
