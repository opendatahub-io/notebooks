# ruff: noqa: COM819
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
import packaging.specifiers
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
                    for s in manifest.sw:
                        if s.get("name") == "Python":
                            assert s.get("version") == f"v{python}", (
                                "Python version in imagestream does not match Pipfile"
                            )
                        elif s.get("name") in ("R", "code-server"):
                            # TODO(jdanek): check not implemented yet
                            continue
                        elif s.get("name") in ("CUDA", "ROCm"):
                            # TODO(jdanek): check not implemented yet
                            continue
                        else:
                            e = next((dep for dep in manifest.dep if dep.get("name") == s.get("name")), None)
                            if e:
                                assert s.get("version") == e.get("version")
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
                            "Feast",
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
                            "TensorFlow-ROCm",
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
                        ), (
                            f"{name}: manifest {manifest.filename} declares {manifest_version}, but pylock.toml pins {locked_version}"
                        )


def test_image_manifests_version_alignment(subtests: pytest_subtests.plugin.SubTests):
    collected_manifests = []
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
        collected_manifests.append(manifest)

    @dataclasses.dataclass
    class VersionData:
        manifest: Manifest
        version: str

    packages: dict[str, list[VersionData]] = defaultdict(list)
    for manifest in collected_manifests:
        for dep in manifest.dep:
            name = dep["name"]
            version = dep["version"]
            packages[name].append(VersionData(manifest=manifest, version=version))

    # TODO(jdanek): review these, if any are unwarranted
    ignored_exceptions: tuple[tuple[str, tuple[str, ...]], ...] = (
        # ("package name", ("allowed version 1", "allowed version 2", ...))
        ("Codeflare-SDK", ("0.30", "0.29")),
        ("Scikit-learn", ("1.7", "1.6")),
        ("Pandas", ("2.3", "1.5")),
        (
            "Numpy",
            (
                "1.26",  # trustyai 0.6.2 depends on numpy~=1.26.4
                "2.0",  # for tensorflow rocm
                "2.1",  # for tensorflow cuda
                "2.2",  # for python 3.11 n-1 images
                "2.3",  # this is our latest where possible
            ),
        ),
        ("Tensorboard", ("2.20", "2.18")),
        ("PyTorch", ("2.6", "2.7")),
    )

    for name, data in packages.items():
        versions = [d.version for d in data]

        # if there is only a single version, all is good
        if len(set(versions)) == 1:
            continue

        mapping = {str(d.manifest.filename.relative_to(PROJECT_ROOT)): d.version for d in data}
        with subtests.test(msg=f"checking versions for {name} across the latest tags in all imagestreams"):
            exception = next((it for it in ignored_exceptions if it[0] == name), None)
            if exception:
                # exception may save us from failing
                assert set(versions) == set(exception[1]), (
                    f"{name} is allowed to have {set(exception[1])} but actually has {set(versions)}. "
                    f"Manifest breakdown: {pprint.pformat(mapping)}"
                )
                continue
            # all hope is lost, the check has failed
            pytest.fail(f"{name} has multiple versions: {pprint.pformat(mapping)}")


def test_image_pyprojects_version_alignment(subtests: pytest_subtests.plugin.SubTests):
    requirements = defaultdict(list)
    for file in PROJECT_ROOT.glob("**/pyproject.toml"):
        logging.info(file)
        directory = file.parent  # "ubi9-python-3.11"
        try:
            _ubi, _lang, _python = directory.name.split("-")
        except ValueError:
            logging.debug(f"skipping {directory.name}/pyproject.toml as it is not an image directory")
            continue

        pyproject = tomllib.loads(file.read_text())
        for d in pyproject["project"]["dependencies"]:
            requirement = packaging.requirements.Requirement(d)
            requirements[requirement.name].append(requirement.specifier)

    # TODO(jdanek): review these, if any are unwarranted
    ignored_exceptions: tuple[tuple[str, tuple[str, ...]], ...] = (
        # ("package name", ("allowed specifier 1", "allowed specifier 2", ...))
        ("setuptools", ("~=80.9.0", "==80.9.0")),
        ("wheel", ("==0.45.1", "~=0.45.1")),
        ("tensorboard", ("~=2.18.0", "~=2.20.0")),
        ("torch", ("==2.7.1", "==2.7.1+cu128", "==2.7.1+rocm6.2.4")),
        ("torchvision", ("==0.22.1", "~=0.22.1", "==0.22.1+cu128", "==0.22.1+rocm6.2.4")),
        (
            "matplotlib",
            ("~=3.10.6",),
        ),
        (
            "numpy",
            (
                "~=1.26.4",  # trustyai 0.6.2 depends on numpy~=1.26.4
                "~=2.0.2",  # for tensorflow rocm
                "~=2.1.3",
                "~=2.2.6",
                "~=2.3.4",  # for tensorflow cuda and latest possible
            ),
        ),
        ("pandas", ("~=2.3.3", "~=1.5.3")),
        ("scikit-learn", ("~=1.7.2",)),
        ("codeflare-sdk", ("~=0.31.0", "~=0.31.1")),
        ("ipython-genutils", (">=0.2.0", "~=0.2.0")),
        ("jinja2", (">=3.1.6", "~=3.1.6")),
        ("jupyter-client", ("~=8.6.3", ">=8.6.3")),
        ("requests", ("~=2.32.3", ">=2.0.0")),
        ("urllib3", ("~=2.5.0", "~=2.3.0")),
        ("transformers", ("<5.0,>4.0", "~=4.55.0")),
        ("datasets", ("", "~=3.4.1")),
        ("accelerate", ("!=1.1.0,>=0.20.3", "~=1.5.2")),
        ("kubeflow-training", ("==1.9.0", "==1.9.2", "==1.9.3")),
        (
            "jupyter-bokeh",
            (
                "~=3.0.5",  # trustyai 0.6.2 depends on jupyter-bokeh~=3.0.7
                "~=4.0.5",
            ),
        ),
        ("jupyterlab-lsp", ("~=5.1.0", "~=5.1.1")),
        ("jupyterlab-widgets", ("~=3.0.13", "~=3.0.15")),
    )

    for name, data in requirements.items():
        if len(set(data)) == 1:
            continue

        with subtests.test(msg=f"checking versions of {name} across all pyproject.tomls"):
            exception = next((it for it in ignored_exceptions if it[0] == name), None)
            if exception:
                # exception may save us from failing
                actual_specs = {str(spec) for spec in data}
                expected_specs = set(exception[1])
                assert actual_specs == expected_specs, (
                    f"{name} is allowed to have {expected_specs} but actually has {actual_specs}"
                )
                continue
            # all hope is lost, the check has failed
            pytest.fail(f"{name} has multiple specifiers: {pprint.pformat(data)}")


def test_files_that_should_be_same_are_same(subtests: pytest_subtests.plugin.SubTests):
    file_groups = {
        "ROCm de-vendor script": [
            PROJECT_ROOT / "jupyter/rocm/pytorch/ubi9-python-3.12/de-vendor-torch.sh",
            PROJECT_ROOT / "runtimes/rocm-pytorch/ubi9-python-3.12/de-vendor-torch.sh",
        ],
        "nginx/common.sh": [
            PROJECT_ROOT / "codeserver/ubi9-python-3.12/nginx/root/usr/share/container-scripts/nginx/common.sh",
            PROJECT_ROOT / "rstudio/c9s-python-3.12/nginx/root/usr/share/container-scripts/nginx/common.sh",
            PROJECT_ROOT / "rstudio/rhel9-python-3.12/nginx/root/usr/share/container-scripts/nginx/common.sh",
        ],
    }
    for group_name, (first_file, *rest) in file_groups.items():
        with subtests.test(msg=f"Checking {group_name}"):
            for file in rest:
                # file.write_text(first_file.read_text())  # update rest according to first
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
    unimplemented_dirs = ()
    for d in unimplemented_dirs:
        if is_suffix(directory.parts, pathlib.Path(d).parts):
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
    sw: list[dict[str, Any]]
    dep: list[dict[str, Any]]


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

    # BEWARE: rhds rstudio has imagestream bundled in the buildconfig yaml
    if "buildconfig" in manifest_file.name:
        # imagestream is the first document in the file
        imagestream = next(yaml.safe_load_all(manifest_file.read_text()))
    else:
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

    try:
        sw = json.loads(current_tag["annotations"]["opendatahub.io/notebook-software"])
        dep = json.loads(current_tag["annotations"]["opendatahub.io/notebook-python-dependencies"])
    except Exception as e:
        raise ValueError(f"invalid json syntax in {manifest_file}") from e

    return Manifest(
        filename=manifest_file,
        imagestream=imagestream,
        metadata=metadata,
        sw=sw,
        dep=dep,
    )
