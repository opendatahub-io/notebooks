from __future__ import annotations

import json
import logging
import os
import pathlib
import shutil
import subprocess
import tomllib
from typing import TYPE_CHECKING

import packaging.requirements
import packaging.utils
import pytest
import ruamel.yaml

from tests import PROJECT_ROOT, manifests

if TYPE_CHECKING:
    from collections.abc import Sequence
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

            with subtests.test(msg="checking imagestream manifest consistency with pylock.toml", pyproject=file):
                # TODO(jdanek): missing manifests
                if is_suffix(directory.parts, pathlib.Path("runtimes/rocm-tensorflow/ubi9-python-3.12").parts):
                    pytest.skip(f"Manifest not implemented {directory.parts}")
                if is_suffix(directory.parts, pathlib.Path("jupyter/rocm/tensorflow/ubi9-python-3.12").parts):
                    pytest.skip(f"Manifest not implemented {directory.parts}")

                metadata = manifests.extract_metadata_from_path(directory)
                manifest_file = manifests.get_source_of_truth_filepath(
                    root_repo_directory=PROJECT_ROOT,
                    metadata=metadata,
                )
                if not manifest_file.is_file():
                    raise FileNotFoundError(
                        f"Unable to determine imagestream manifest for '{directory}'. "
                        f"Computed filepath '{manifest_file}' does not exist."
                    )

                imagestream = ruamel.yaml.YAML().load(manifest_file.read_text())
                recommended_tags = [
                    tag
                    for tag in imagestream["spec"]["tags"]
                    if tag["annotations"].get("opendatahub.io/workbench-image-recommended", None) == "true"
                ]
                assert len(recommended_tags) <= 1, "at most one tag may be recommended at a time"
                assert recommended_tags or len(imagestream["spec"]["tags"]) == 1, (
                    "Either there has to be recommended image, or there can be only one tag"
                )
                current_tag = recommended_tags[0] if recommended_tags else imagestream["spec"]["tags"][0]

                sw = json.loads(current_tag["annotations"]["opendatahub.io/notebook-software"])
                dep = json.loads(current_tag["annotations"]["opendatahub.io/notebook-python-dependencies"])

                with subtests.test(msg="checking the `notebook-software` array", pyproject=file):
                    # TODO(jdanek)
                    pytest.skip("checking the `notebook-software` array not yet implemented")
                    for s in sw:
                        if s.get("name") == "Python":
                            assert s.get("version") == f"v{python}", (
                                "Python version in imagestream does not match Pipfile"
                            )
                        else:
                            pytest.fail(f"unexpected {s=}")

                with subtests.test(msg="checking the `notebook-python-dependencies` array", pyproject=file):
                    for d in dep:
                        workbench_only_packages = [
                            "Kfp",
                            "JupyterLab",
                            "Odh-Elyra",
                            "Kubeflow-Training",
                            "Codeflare-SDK",
                        ]

                        # complex translation from names used in imagestream manifest to python package name
                        manifest_to_pylock_translation = {
                            # TODO(jdanek): is this one intentional?
                            "LLM-Compressor": "llmcompressor",
                            "PyTorch": "torch",
                            "Sklearn-onnx": "skl2onnx",
                            "Nvidia-CUDA-CU12-Bundle": "nvidia-cuda-runtime-cu12",
                            "MySQL Connector/Python": "mysql-connector-python",
                        }

                        # when .lower() is all it takes to do the translation
                        manifest_to_pylock_capitalization: set[str] = {
                            "Accelerate",
                            "Boto3",
                            "Codeflare-SDK",
                            "Datasets",
                            "JupyterLab",
                            "Kafka-Python-ng",
                            "Kfp",
                            "Kubeflow-Training",
                            "Matplotlib",
                            "Numpy",
                            "Odh-Elyra",
                            "Pandas",
                            "Psycopg",
                            "PyMongo",
                            "Pyodbc",
                            "Scikit-learn",
                            "Scipy",
                            "TensorFlow",
                            "Tensorboard",
                            # TODO(jdanek): inconsistent with PyTorch elsewhere
                            "Torch",
                            "Transformers",
                            "TrustyAI",
                        }

                        name = d["name"]
                        if name in workbench_only_packages and metadata.type == manifests.NotebookType.RUNTIME:
                            continue

                        # TODO(jdanek): intentional?
                        if metadata.scope == "pytorch+llmcompressor" and name == "Codeflare-SDK":
                            continue

                        if name == "ROCm-PyTorch":
                            # TODO(jdanek): figure out what to do here
                            continue

                        if name == "rstudio-server":
                            # TODO(jdanek): figure out how to check rstudio version statically
                            continue

                        if name in manifest_to_pylock_translation:
                            normalized_name = manifest_to_pylock_translation[name]
                        elif name in manifest_to_pylock_capitalization:
                            normalized_name = name.lower()
                        else:
                            normalized_name = name

                        resolved = pylock_packages.get(normalized_name, None)
                        if resolved is None:
                            with subtests.test(name):
                                pytest.fail(f"Dependency {name} ({normalized_name=}) is not in pylock.toml ({file=})")


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


def is_suffix[T](main_sequence: Sequence[T], suffix_sequence: Sequence[T]):
    """Checks if a sequence (list or tuple) is a suffix of another sequence."""
    suffix_len = len(suffix_sequence)
    if suffix_len > len(main_sequence):
        return False
    return main_sequence[-suffix_len:] == suffix_sequence
