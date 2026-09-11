"""Papermill notebook execution test — the GHA papermill leg without a cluster.

GHA runs this leg by deploying the image to a kind cluster (make deploy9-*) and
then running scripts/test_jupyter_with_papermill.sh: pip-install papermill in the
notebook pod, build expected_versions.json from the imagestream manifest (source
of truth) plus the build directory's requirements file, copy the build directory's
test_notebook.ipynb in, execute it via papermill, and fail on 'FAILED' in the
papermill stderr file.

This pytest port runs the same assertions through the shared container transport
(testcontainers locally, the sidecar agent in-pod — see container_transport.py),
so no cluster is required: the image under test runs as a plain container and the
notebook executes against its installed stack. The kind leg only ever existed to
host the image; the papermill execution itself never needed kubernetes.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import TYPE_CHECKING

import allure
import pytest
import yaml

from tests import manifests
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer

if TYPE_CHECKING:
    from tests.containers import conftest

ROOT_DIR = pathlib.Path(__file__).resolve().parents[3]

# ODH workbench images run as uid 1001 (USER 1001 in the Dockerfiles); the
# sidecar agent's exec default is the same (SUT_IMAGE_USER), and the GHA shell
# script ran papermill as the image's default user.
WORKBENCH_USER = 1001

# ODH workbench WORKDIR (also the sidecar agent's SUT_WORKDIR)
WORKDIR = "/opt/app-root/src"


def _build_dir_and_flavor(image_name: str) -> tuple[pathlib.Path, str] | None:
    """Locate the repo build directory for an image by its name label.

    build-args/<flavor>.conf's LABEL_COMPONENT is the single source of truth
    for the component name (the Konflux generator reads it the same way), so
    matching against it keeps this mapping in sync with the build.
    """
    component = image_name.rsplit("/", 1)[-1]
    for conf in sorted(ROOT_DIR.glob("jupyter/*/ubi9-python-*/build-args/*.conf")):
        match = re.search(r"^LABEL_COMPONENT=(\S+)", conf.read_text(), re.MULTILINE)
        if match and match.group(1) == component:
            return conf.parent.parent, conf.name.rsplit(".", 1)[0]
    return None


def _requirements_version(requirements_file: pathlib.Path, package: str) -> str:
    """major.minor of the `package==X.Y...` pin (shell _get_package_version_from_requirements)."""
    if not requirements_file.is_file():
        return ""
    for line in requirements_file.read_text().splitlines():
        match = re.match(rf"^{package}==([0-9]+\.[0-9]+)", line)
        if match:
            return match.group(1)
    return ""


def _requirements_file(build_dir: pathlib.Path, flavor: str) -> pathlib.Path:
    """GHA parity: cpu images use requirements.cpu.txt; cuda/rocm images use
    requirements.{cuda,rocm}.txt when present (no .cpu.txt fallback miss)."""
    flavor_file = build_dir / f"requirements.{flavor}.txt"
    if flavor in ("cuda", "rocm") and flavor_file.is_file():
        return flavor_file
    return build_dir / "requirements.cpu.txt"


def _expected_versions(manifest_path: pathlib.Path, build_dir: pathlib.Path, flavor: str) -> dict[str, str]:
    """expected_versions.json contents — GHA parity with
    scripts/test_jupyter_with_papermill.sh::_create_test_versions_source_of_truth:
    imagestream software + python-dependency annotations, plus nbdime/nbgitpuller
    major.minor from the requirements file (the imagestream does not pin them).
    """
    manifest = yaml.safe_load(manifest_path.read_text())
    annotations = manifest["spec"]["tags"][0]["annotations"]
    entries = json.loads(annotations["opendatahub.io/notebook-software"])
    entries += json.loads(annotations["opendatahub.io/notebook-python-dependencies"])
    expected = {entry["name"]: entry["version"] for entry in entries}

    requirements_file = _requirements_file(build_dir, flavor)
    # shell parity: stale-default fallbacks when the pin is absent
    expected["nbdime"] = _requirements_version(requirements_file, "nbdime") or "4.0"
    expected["nbgitpuller"] = _requirements_version(requirements_file, "nbgitpuller") or "1.3"

    # llmcompressor-only packages are not listed in imagestream annotations;
    # read their pins from the requirements file (shell parity, empty = omitted)
    if "llmcompressor" in build_dir.name:
        for package in ("compressed-tensors", "lm-eval", "speculators"):
            version = _requirements_version(requirements_file, package)
            if version:
                expected[package] = version
    return expected


@allure.description(
    "Execute the image's test_notebook.ipynb via papermill against the image's "
    "installed stack (GHA parity: the make deploy/test papermill leg, cluster-free)."
)
@pytest.mark.papermill
class TestPapermillNotebook:
    def test_test_notebook_executes(
        self,
        jupyterlab_image: conftest.Image,
        subtests: pytest.Subtests,
        tmp_path: pathlib.Path,
    ) -> None:
        matched = _build_dir_and_flavor(jupyterlab_image.labels["name"])
        if matched is None:
            pytest.skip(f"no jupyter build directory declares LABEL_COMPONENT {jupyterlab_image.labels['name']}")
        build_dir, flavor = matched

        notebook = build_dir / "test" / "test_notebook.ipynb"
        if not notebook.is_file():
            pytest.skip(f"{build_dir} has no test/test_notebook.ipynb (no papermill test for this image)")

        metadata = manifests.extract_metadata_from_path(build_dir)
        manifest_path = manifests.get_source_of_truth_filepath(manifests.MANIFESTS_ODH_DIR, metadata)
        if not manifest_path.is_file():
            pytest.skip(f"imagestream manifest not found at {manifest_path}")

        expected_versions = _expected_versions(manifest_path, build_dir, flavor)
        versions_file = tmp_path / "expected_versions.json"
        versions_file.write_text(json.dumps(expected_versions, indent=2) + "\n")

        output_prefix = f"{metadata.scope}_{metadata.os_flavor}"
        with WorkbenchContainer(image=jupyterlab_image.name, user=WORKBENCH_USER, group_add=[0]) as container:
            container.start()
            with allure.step("pip install papermill (GHA parity: the shell script installs it in the pod)"):
                ecode, output = container.exec(["python3", "-m", "pip", "install", "papermill"])
                assert ecode == 0, f"pip install papermill failed: {output.decode()}"
            with allure.step("Copy the test notebook and expected versions into the image"):
                container.cp(notebook, WORKDIR, user=WORKBENCH_USER, group=0)
                container.cp(versions_file, WORKDIR, user=WORKBENCH_USER, group=0)
            with allure.step("Execute the notebook via papermill"):
                # the notebook unittests raise on version mismatch, so a clean
                # exit already implies the assertions held; the stderr-file check
                # below is the shell script's second safety net
                ecode, output = container.exec(
                    [
                        "/bin/sh",
                        "-c",
                        (
                            "export IPY_KERNEL_LOG_LEVEL=DEBUG; "
                            f"python3 -m papermill test_notebook.ipynb {output_prefix}_output.ipynb "
                            f"--kernel python3 --log-level DEBUG --stderr-file {output_prefix}_error.txt"
                        ),
                    ]
                )
                assert ecode == 0, f"papermill failed:\n{output.decode()}"
            with allure.step("No FAILED entries in the papermill stderr file"):
                ecode, error_output = container.exec(["cat", f"{output_prefix}_error.txt"])
                if ecode == 0 and "FAILED" in error_output.decode():
                    pytest.fail(f"papermill stderr file contains FAILED:\n{error_output.decode()}")
