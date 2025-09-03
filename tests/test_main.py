from __future__ import annotations

import dataclasses
import json
import logging
import os
import pathlib
import pprint
import re
import shutil
import subprocess
import tomllib
from collections import defaultdict
from typing import TYPE_CHECKING

import packaging.requirements
import packaging.utils
import packaging.version
import pytest
import yaml

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
                _skip_unimplemented_manifests(directory)

                manifest = load_manifests_file_for(directory)

                with subtests.test(msg="checking the `notebook-software` array", pyproject=file):
                    # TODO(jdanek)
                    pytest.skip("checking the `notebook-software` array not yet implemented")
                    for s in manifest.sw:
                        if s.get("name") == "Python":
                            assert s.get("version") == f"v{python}", (
                                "Python version in imagestream does not match Pipfile"
                            )
                        else:
                            pytest.fail(f"unexpected {s=}")

                with subtests.test(msg="checking the `notebook-python-dependencies` array", pyproject=file):
                    for d in manifest.dep:
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
                        if name in workbench_only_packages and manifest.metadata.type == manifests.NotebookType.RUNTIME:
                            continue

                        # TODO(jdanek): intentional?
                        if manifest.metadata.scope == "pytorch+llmcompressor" and name == "Codeflare-SDK":
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

                        # assert on name

                        resolved = pylock_packages.get(normalized_name, None)
                        if resolved is None:
                            with subtests.test(name):
                                pytest.fail(f"Dependency {name} ({normalized_name=}) is not in pylock.toml ({file=})")

                        # assert on version

                        manifest_version = d.get("version")
                        locked_version = resolved.get("version")

                        split_manifest_version = re.fullmatch(r"^v?(\d+)\.(\d+)", manifest_version)
                        assert split_manifest_version is not None, f"{name}: malformed {manifest_version=}"
                        parsed_locked_version = packaging.version.Version(locked_version)
                        assert (parsed_locked_version.major, parsed_locked_version.minor) == tuple(
                            int(v) for v in split_manifest_version.groups()
                        ), f"{name}: manifest declares {manifest_version}, but pylock.toml pins {locked_version}"


def test_image_manifests_version_alignment(subtests: pytest_subtests.plugin.SubTests):
    manifests = []
    for file in PROJECT_ROOT.glob("**/pyproject.toml"):
        logging.info(file)
        directory = file.parent  # "ubi9-python-3.11"
        try:
            _ubi, _lang, _python = directory.name.split("-")
        except ValueError:
            logging.debug(f"skipping {directory.name}/pyproject.toml as it is not an image directory")
            continue

        if _skip_unimplemented_manifests(directory, call_skip=False):
            continue

        manifest = load_manifests_file_for(directory)
        manifests.append(manifest)

    @dataclasses.dataclass
    class VersionData:
        manifest: Manifest
        version: str

    packages: dict[str, list[VersionData]] = defaultdict(list)
    for manifest in manifests:
        for dep in manifest.dep:
            name = dep["name"]
            version = dep["version"]
            packages[name].append(VersionData(manifest=manifest, version=version))

    # TODO(jdanek): review these, if any are unwarranted
    ignored_exceptions = (
        ("Codeflare-SDK", ("0.30", "0.29")),
        ("Scikit-learn", ("1.7", "1.6")),
        ("Pandas", ("2.2", "1.5")),
        ("Numpy", ("2.2", "1.26")),
        ("Tensorboard", ("2.19", "2.18")),
    )

    for name, data in packages.items():
        versions = [
            d.version
            for d in data
            if (d.manifest.filename.relative_to(PROJECT_ROOT), d.version) not in ignored_exceptions
        ]

        # if there is only a single version, all is good
        if len(set(versions)) == 1:
            continue

        mapping = {str(d.manifest.filename.relative_to(PROJECT_ROOT)): d.version for d in data}

        exception = next((it for it in ignored_exceptions if it[0] == name), None)
        if exception:
            if set(versions) == set(exception[1]):
                continue
            else:
                pytest.fail(
                    f"{name} is allowed to have {exception} but actually has more versions: {pprint.pformat(mapping)}"
                )

        with subtests.test(msg=f"checking versions for {name} across the latest tags in all imagestreams"):
            pytest.fail(f"{name} has multiple versions: {pprint.pformat(mapping)}")


# TODO(jdanek): ^^^ should also check pyproject.tomls, in fact checking there is more useful than in manifests


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


def _skip_unimplemented_manifests(directory: pathlib.Path, call_skip=True) -> bool:
    # TODO(jdanek): missing manifests
    dirs = (
        "runtimes/rocm-tensorflow/ubi9-python-3.12",
        "jupyter/rocm/tensorflow/ubi9-python-3.12",
    )
    for dir in dirs:
        if is_suffix(directory.parts, pathlib.Path(dir).parts):
            if call_skip:
                pytest.skip(f"Manifest not implemented {directory.parts}")
            else:
                return True
    return False


@dataclasses.dataclass
class Manifest:
    filename: pathlib.Path
    imagestream: dict[str, Any]
    metadata: manifests.NotebookMetadata
    sw: dict
    dep: dict


def load_manifests_file_for(directory: pathlib.Path) -> Manifest:
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

    imagestream = yaml.safe_load(manifest_file.read_text())
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

    return Manifest(
        filename=manifest_file,
        imagestream=imagestream,
        metadata=metadata,
        sw=sw,
        dep=dep,
    )
