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

import allure
import packaging.requirements
import packaging.specifiers
import packaging.version
import pytest
import yaml

from tests import PROJECT_ROOT, manifests

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    import pytest_subtests

MAKE = shutil.which("gmake") or shutil.which("make")


def test_dockerfiles_unintended_subscription_manager_pattern():
    """Konflux will not `subscription-manager register --org --activationkey` if the pattern matches.
    Because it is easy to be matched by mistake (e.g. in a string/comment on the same line), add a check.

    See the buildah task definition in https://github.com/konflux-ci/build-definitions for more details."""

    # https://github.com/konflux-ci/build-definitions/blob/main/task/buildah/0.6/buildah.yaml#L795-L813
    pattern = re.compile(r"^[^#]*subscription-manager.[^#]*register")

    skip_dirs = (
        PROJECT_ROOT / "rstudio/rhel9-python-3.12",  # RStudio Dockerfiles
        PROJECT_ROOT / "scripts/lockfile-generators",  # RPM lockfile image optionally uses subscription-manager
    )
    for file in PROJECT_ROOT.glob("**/Dockerfile*"):
        if file.is_dir():
            continue
        if any(file.is_relative_to(d) for d in skip_dirs):
            continue
        with open(file, "r") as f:
            for line_no, line in enumerate(f, start=1):
                assert not pattern.match(line), (
                    f"Undesirable subscription-manager pattern that disables Konflux subscription found in {file}:{line_no}."
                    f" Modify the test if this is intended behaviour. But it is very reasonable to assume it is a mistake."
                )


@pytest.mark.parametrize("manifests_directory", [manifests.MANIFESTS_ODH_DIR, manifests.MANIFESTS_RHOAI_DIR])
def test_image_pyprojects(subtests: pytest_subtests.plugin.SubTests, manifests_directory: pathlib.Path):
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
                major, minor = (int(v) for v in python.split("."))
                requires_python_specifier = packaging.specifiers.SpecifierSet(pyproject["project"]["requires-python"])
                assert requires_python_specifier.contains(f"{major}.{minor}.0", prereleases=True), (
                    "pyproject.toml requires-python does not include the expected Python minor version"
                )
                if minor > 0:
                    assert not requires_python_specifier.contains(f"{major}.{minor - 1}.0", prereleases=True), (
                        "pyproject.toml requires-python must not include the previous Python minor version"
                    )
                assert not requires_python_specifier.contains(f"{major}.{minor + 1}.0", prereleases=True), (
                    "pyproject.toml requires-python must not include the next Python minor version"
                )

                assert "dependencies" in pyproject["project"], (
                    "pyproject.toml is missing a [project.dependencies] section"
                )

            if (f := file.parent / "uv.lock.d").is_dir():
                pylock_candidates = sorted(f.glob("pylock.*.toml"))
                assert pylock_candidates, (
                    f"uv.lock.d directory exists at {f} but contains no pylock.*.toml files. "
                    f"This likely means pylocks_generator.py failed. "
                    f"Delete the empty uv.lock.d directory or re-run the lockfile generator."
                )
                pylock = tomllib.loads(pylock_candidates[0].read_text())
            else:
                pylock = tomllib.loads(file.with_name("pylock.toml").read_text())
            pylock_packages: dict[str, dict[str, Any]] = {p["name"]: p for p in pylock["packages"]}
            with subtests.test(msg="checking pylock.toml consistency with pyproject.toml", pyproject=file):
                for d in pyproject["project"]["dependencies"]:
                    requirement = packaging.requirements.Requirement(d)

                    # Skip subproject meta-packages - they should NOT be in pylock.toml
                    # Their dependencies are expanded inline
                    if is_subproject_metapackage(requirement.name):
                        # Verify the subproject package is correctly excluded from pylock.toml
                        assert requirement.name not in pylock_packages, (
                            f"Subproject meta-package {requirement.name} found in pylock.toml. "
                            f"It should be excluded via --no-emit-package in scripts/pylocks_generator.sh"
                        )
                        continue

                    assert requirement.name in pylock_packages, f"Dependency {d} is not in pylock.toml"
                    assert "version" in pylock_packages[requirement.name], (
                        f"Version missing for {requirement.name} in pylock.toml"
                    )
                    version = pylock_packages[requirement.name]["version"]
                    if requirement.specifier:
                        assert requirement.specifier.contains(version), (
                            f"Version of {d} in pyproject.toml does not match {version=} in pylock.toml"
                        )

            with subtests.test(msg="checking imagestream manifest consistency with pylock.toml", pyproject=file):
                _skip_unimplemented_manifests(directory)

                manifest = load_manifests_file_for(directory, manifests_directory)

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
                            "ROCm-PyTorch": "torch",
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
                        # Runtime llmcompressor currently resolves via lm-eval constraints to 0.9.x
                        # while the workbench line can resolve to 0.10.x.
                        if (
                            manifest.metadata.scope == "pytorch+llmcompressor"
                            and manifest.metadata.type == manifests.NotebookType.RUNTIME
                            and name == "LLM-Compressor"
                        ):
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


@pytest.mark.parametrize("manifests_directory", [manifests.MANIFESTS_ODH_DIR, manifests.MANIFESTS_RHOAI_DIR])
def test_image_manifests_version_alignment(
    subtests: pytest_subtests.plugin.SubTests, manifests_directory: pathlib.Path
):
    collected_manifests = []
    for file in PROJECT_ROOT.glob("**/pyproject.toml"):
        logging.info(file)
        directory = file.parent  # "ubi9-python-3.11"
        if not is_image_directory(directory):
            logging.debug(f"skipping {directory.name}/pyproject.toml as it is not an image directory")
            continue

        if _skip_unimplemented_manifests(directory, call_skip=False):
            continue

        manifest = load_manifests_file_for(directory, manifests_directory)
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
        ("Codeflare-SDK", ("0.34", "0.35")),
        ("Scikit-learn", ("1.7", "1.6")),
        ("Pandas", ("2.3", "1.5")),
        (
            "Numpy",
            (
                "2.0",  # for tensorflow rocm (numpy 2.0.2)
                "2.3",  # this used to be our latest
                "2.4",  # this is our latest where possible
            ),
        ),
        ("Tensorboard", ("2.18", "2.20")),
        ("PyTorch", ("2.7", "2.9")),
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

        if not is_image_directory(directory) and not is_dependencies_directory(file):
            logging.debug(f"skipping {directory.name}/pyproject.toml as it is not an image or dependencies directory")
            continue

        pyproject = tomllib.loads(file.read_text())
        for d in pyproject["project"]["dependencies"]:
            requirement = packaging.requirements.Requirement(d)
            requirements[requirement.name].append(requirement.specifier)

    # Packages allowed to use multiple dependency specifiers across pyproject.toml files.
    # Keep only package names here to avoid coupling tests to specific version values.
    ignored_exceptions: set[str] = {
        "setuptools",
        "wheel",
        "tensorboard",
        "torchvision",
        "triton",
        "numpy",
        "jupyterlab-lsp",
        "transformers",
        "datasets",
        "accelerate",
        "requests",
    }

    for name, data in requirements.items():
        actual_specs = {str(spec) for spec in data}
        # Unpinned specs are intentionally version-agnostic and should not
        # trigger alignment failures on their own.
        non_empty_specs = {spec for spec in actual_specs if spec}

        if len(non_empty_specs) <= 1:
            continue

        with subtests.test(msg=f"checking versions of {name} across all pyproject.tomls"):
            if name in ignored_exceptions:
                continue
            # all hope is lost, the check has failed
            pytest.fail(
                f"{name} has multiple non-empty specifiers across pyproject.toml files: "
                f"{non_empty_specs}. Full breakdown: {pprint.pformat(data)}"
            )


def test_files_that_should_be_same_are_same(subtests: pytest_subtests.plugin.SubTests):
    file_groups = {
        "ROCm de-vendor script": [
            PROJECT_ROOT / "jupyter/rocm/pytorch/ubi9-python-3.12/de-vendor-torch.py",
            PROJECT_ROOT / "runtimes/rocm-pytorch/ubi9-python-3.12/de-vendor-torch.py",
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


@allure.issue("RHOAIENG-42632")
def test_rhds_pipelines_use_rhds_args(subtests: pytest_subtests.plugin.SubTests):
    r"""Pipelines under .tekton/ that build `^Dockerfile\.konflux.*` dockerfiles have to use
    `^konflux\..*` args files. For example, this would be a violation of the rule:

    - name: dockerfile
      value: jupyter/rocm/tensorflow/ubi9-python-3.12/Dockerfile.konflux.rocm
    - name: build-args-file
      value: jupyter/rocm/tensorflow/ubi9-python-3.12/build-args/rocm.conf
    """
    for file in PROJECT_ROOT.glob(".tekton/*.yaml"):
        with subtests.test(msg="checking tekton pipeline", pipeline=file):
            pipeline = yaml.safe_load(file.read_text())

            if pipeline["kind"] == "Pipeline":
                continue
            assert pipeline["kind"] == "PipelineRun", f"Expected PipelineRun, got {pipeline['kind']}"

            dockerfile_param = None
            build_args_file_param = None

            for param in pipeline["spec"]["params"]:
                if param["name"] == "dockerfile":
                    dockerfile_param = pathlib.Path(param["value"])
                if param["name"] == "build-args-file":
                    build_args_file_param = pathlib.Path(param["value"])

            assert dockerfile_param is not None, (
                f"Pipeline {file.relative_to(PROJECT_ROOT)} is missing the required 'dockerfile' parameter"
            )

            if not dockerfile_param.name.startswith("Dockerfile.konflux"):
                continue

            assert build_args_file_param is not None, (
                f"Pipeline {file.relative_to(PROJECT_ROOT)} builds a konflux Dockerfile ({dockerfile_param.name}) "
                f"but is missing the required 'build-args-file' parameter"
            )

            assert build_args_file_param.name.startswith("konflux."), (
                f"Pipeline {file.relative_to(PROJECT_ROOT)} builds a konflux Dockerfile but does not use konflux build-args"
            )


CANONICAL_TAG_ORDER = ["3.4", "2025.2", "2025.1", "2024.2", "2024.1", "2023.2", "2023.1", "1.2"]

_PLACEHOLDER_RE = re.compile(
    r"""
    ^
    ( .+? )                 # Group 1: base key (non-greedy)
    (                       # Group 2: version suffix
        -n                  #   latest tag
      | -n-\d+              #   old positional style (e.g. -n-1) -- a bug when found on rhds
      | -\d+-\d+            #   year-minor style (e.g. -2025-2)
    )
    _PLACEHOLDER
    $
    """,
    re.VERBOSE,
)


def _parse_env_keys(env_path: pathlib.Path) -> set[str]:
    keys: set[str] = set()
    if not env_path.exists():
        return keys
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, _ = line.partition("=")
        keys.add(key.strip())
    return keys


@pytest.mark.parametrize(
    "base_dir", [PROJECT_ROOT / "manifests" / "odh" / "base", PROJECT_ROOT / "manifests" / "rhoai" / "base"]
)
def test_imagestream_kustomization_consistency(subtests: pytest_subtests.plugin.SubTests, base_dir):
    """Validate that imagestream YAML files, kustomization.yaml replacements, and .env files are consistent."""
    kustomization = yaml.safe_load((base_dir / "kustomization.yaml").read_text())
    replacements = kustomization.get("replacements", [])

    # Build lookup: (imagestream_name, fieldPath_suffix) -> fieldPath_key
    # e.g. ("s2i-minimal-notebook", "spec.tags.0.from.name") -> "odh-workbench-...-n"
    params_replacements: dict[tuple[str, str], str] = {}
    commit_replacements: dict[tuple[str, str], str] = {}
    for r in replacements:
        field_path_key = r["source"]["fieldPath"].removeprefix("data.")
        configmap = r["source"]["name"]
        for target in r["targets"]:
            select = target.get("select", {})
            if "name" not in select:
                continue
            target_name = select["name"]
            for fp in target["fieldPaths"]:
                key = (target_name, fp)
                if configmap == "notebook-image-params":
                    assert key not in params_replacements, (
                        f"Duplicate params replacement for {key}: {params_replacements[key]!r} vs {field_path_key!r}"
                    )
                    params_replacements[key] = field_path_key
                elif configmap == "notebook-image-commithash":
                    assert key not in commit_replacements, (
                        f"Duplicate commit replacement for {key}: {commit_replacements[key]!r} vs {field_path_key!r}"
                    )
                    commit_replacements[key] = field_path_key

    param_env_keys = _parse_env_keys(base_dir / "params.env") | _parse_env_keys(base_dir / "params-latest.env")
    commit_env_keys = _parse_env_keys(base_dir / "commit.env") | _parse_env_keys(base_dir / "commit-latest.env")

    for is_file in sorted(base_dir.glob("*-imagestream.yaml")):
        is_data = yaml.safe_load(is_file.read_text())
        is_name = is_data["metadata"]["name"]
        tags = is_data["spec"]["tags"]
        tag_names = [t["name"] for t in tags]
        is_runtime = is_data["metadata"].get("labels", {}).get("opendatahub.io/runtime-image") == "true"
        has_kustomize_replacements = any(
            target.get("select", {}).get("name") == is_name for r in replacements for target in r["targets"]
        )

        with subtests.test(msg=f"imagestream {is_file.name}", imagestream=is_file.name):
            if is_runtime:
                # Runtime imagestreams have a single non-version tag; skip ordering/placeholder checks
                continue

            # --- Check 1: Tag ordering ---
            with subtests.test(msg=f"tag ordering in {is_file.name}"):
                # Find where this imagestream's tags fit in the canonical order
                canonical_positions = []
                for tn in tag_names:
                    if tn in CANONICAL_TAG_ORDER:
                        canonical_positions.append(CANONICAL_TAG_ORDER.index(tn))
                    else:
                        pytest.fail(
                            f"{is_file.name}: tag name {tn!r} is not in CANONICAL_TAG_ORDER. "
                            f"Update CANONICAL_TAG_ORDER if a new version was added."
                        )
                assert canonical_positions == sorted(canonical_positions), (
                    f"{is_file.name}: tags are not in newest-to-oldest order. "
                    f"Got {tag_names}, expected order per CANONICAL_TAG_ORDER."
                )

            with subtests.test(msg=f"no duplicate tag names in {is_file.name}"):
                assert len(tag_names) == len(set(tag_names)), f"{is_file.name}: duplicate tag names found: {tag_names}"

            # --- Check 2 & 3: Placeholder consistency per tag ---
            for idx, tag in enumerate(tags):
                from_placeholder = tag["from"]["name"]
                commit_placeholder = tag["annotations"].get("opendatahub.io/notebook-build-commit")
                tag_name = tag["name"]

                with subtests.test(msg=f"placeholder consistency for tag {tag_name} in {is_file.name}"):
                    m = _PLACEHOLDER_RE.match(from_placeholder)
                    assert m, (
                        f"{is_file.name} tag {tag_name}: from.name placeholder {from_placeholder!r} "
                        f"does not match expected pattern '<base>-<suffix>_PLACEHOLDER'"
                    )
                    suffix = m.group(2)

                    if idx == 0:
                        assert suffix == "-n", (
                            f"{is_file.name} tag {tag_name} (index 0): expected suffix '-n' for latest tag, "
                            f"got {suffix!r} in {from_placeholder!r}"
                        )
                    else:
                        expected_suffix = "-" + tag_name.replace(".", "-")
                        assert suffix == expected_suffix, (
                            f"{is_file.name} tag {tag_name} (index {idx}): expected suffix {expected_suffix!r} "
                            f"matching tag name, got {suffix!r} in {from_placeholder!r}"
                        )

                # Check 3: commit placeholder matches from.name placeholder
                with subtests.test(msg=f"commit placeholder for tag {tag_name} in {is_file.name}"):
                    if commit_placeholder is None:
                        continue
                    m_from = _PLACEHOLDER_RE.match(from_placeholder)
                    if m_from is None:
                        # from.name already failed Check 2; skip derived check
                        continue
                    m_commit = _PLACEHOLDER_RE.match(commit_placeholder)
                    assert m_commit, (
                        f"{is_file.name} tag {tag_name}: commit placeholder {commit_placeholder!r} "
                        f"does not match expected pattern"
                    )
                    expected_commit = f"{m_from.group(1)}-commit{m_from.group(2)}_PLACEHOLDER"
                    assert commit_placeholder == expected_commit, (
                        f"{is_file.name} tag {tag_name}: commit placeholder mismatch. "
                        f"Expected {expected_commit!r} (derived from from.name), got {commit_placeholder!r}"
                    )

            if not has_kustomize_replacements:
                continue

            # --- Check 4: Kustomization replacement presence ---
            for idx, tag in enumerate(tags):
                tag_name = tag["name"]
                from_placeholder = tag["from"]["name"]
                m = _PLACEHOLDER_RE.match(from_placeholder)
                if not m:
                    continue
                param_key = f"{m.group(1)}{m.group(2)}"

                with subtests.test(msg=f"kustomize params replacement for tag {tag_name} in {is_file.name}"):
                    expected_target = f"spec.tags.{idx}.from.name"
                    actual_key = params_replacements.get((is_name, expected_target))
                    assert actual_key is not None, (
                        f"{is_file.name} tag {tag_name}: no kustomization replacement found for "
                        f"({is_name!r}, {expected_target!r})"
                    )
                    assert actual_key == param_key, (
                        f"{is_file.name} tag {tag_name}: kustomization replacement key mismatch. "
                        f"Expected {param_key!r}, got {actual_key!r}"
                    )

                commit_placeholder = tag["annotations"].get("opendatahub.io/notebook-build-commit")
                if commit_placeholder:
                    m_c = _PLACEHOLDER_RE.match(commit_placeholder)
                    if m_c:
                        commit_key = f"{m_c.group(1)}{m_c.group(2)}"
                        with subtests.test(msg=f"kustomize commit replacement for tag {tag_name} in {is_file.name}"):
                            expected_target = f"spec.tags.{idx}.annotations.[opendatahub.io/notebook-build-commit]"
                            actual_key = commit_replacements.get((is_name, expected_target))
                            assert actual_key is not None, (
                                f"{is_file.name} tag {tag_name}: no kustomization commit replacement found for "
                                f"({is_name!r}, {expected_target!r})"
                            )
                            assert actual_key == commit_key, (
                                f"{is_file.name} tag {tag_name}: kustomization commit replacement key mismatch. "
                                f"Expected {commit_key!r}, got {actual_key!r}"
                            )

            # --- Check 5: Env file key existence ---
            for _idx, tag in enumerate(tags):
                tag_name = tag["name"]
                from_placeholder = tag["from"]["name"]
                m = _PLACEHOLDER_RE.match(from_placeholder)
                if not m:
                    continue
                param_key = f"{m.group(1)}{m.group(2)}"

                with subtests.test(msg=f"env key for tag {tag_name} in {is_file.name}"):
                    assert param_key in param_env_keys, (
                        f"{is_file.name} tag {tag_name}: param key {param_key!r} not found in "
                        f"params.env or params-latest.env"
                    )

                commit_placeholder = tag["annotations"].get("opendatahub.io/notebook-build-commit")
                if commit_placeholder:
                    m_c = _PLACEHOLDER_RE.match(commit_placeholder)
                    if m_c:
                        commit_key = f"{m_c.group(1)}{m_c.group(2)}"
                        with subtests.test(msg=f"commit env key for tag {tag_name} in {is_file.name}"):
                            assert commit_key in commit_env_keys, (
                                f"{is_file.name} tag {tag_name}: commit key {commit_key!r} not found in "
                                f"commit.env or commit-latest.env"
                            )


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


def is_subproject_metapackage(package_name: str) -> bool:
    """Check if a package name is a subproject meta-package that should be excluded from pylock.toml.

    Subproject meta-packages are dependency-only packages (package = false) that group common dependencies.
    They are excluded from lock files via --no-emit-package in scripts/pylocks_generator.sh.
    """
    return package_name.startswith("odh-notebooks-meta-") and package_name.endswith("-deps")


def _skip_unimplemented_manifests(directory: pathlib.Path, call_skip=True) -> bool:
    unimplemented_dirs = ()
    for d in unimplemented_dirs:
        if is_suffix(directory.parts, pathlib.Path(d).parts):
            if call_skip:
                pytest.skip(f"Manifest not implemented {directory.parts}")
            else:
                return True
    return False


def is_image_directory(directory: pathlib.Path) -> bool:
    """image directory e.g. "ubi9-python-3.11"""
    try:
        _ubi, _lang, _python = directory.name.split("-")
        return True
    except ValueError:
        return False


def is_dependencies_directory(file: pathlib.Path) -> bool:
    return "dependencies" in file.relative_to(PROJECT_ROOT).parts


@dataclasses.dataclass
class Manifest:
    filename: pathlib.Path
    imagestream: dict[str, Any]
    metadata: manifests.NotebookMetadata
    sw: list[dict[str, Any]]
    dep: list[dict[str, Any]]


def load_manifests_file_for(directory: pathlib.Path, manifests_directory: pathlib.Path) -> Manifest:
    metadata = manifests.extract_metadata_from_path(directory)
    manifest_file = manifests.get_source_of_truth_filepath(
        manifests_directory=manifests_directory,
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
