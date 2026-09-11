#!/usr/bin/env python3
"""Generates per-architecture Konflux PipelineRuns under .tekton/konflux/.

Each notebook image gets one PipelineRun per architecture (image x arch matrix),
so images and architectures build in parallel instead of one multi-arch
PipelineRun per image (see the ADR in docs/architecture/decisions/).

Pipeline shape (single inline pipelineSpec — no cluster-side Pipeline CR needed):

    init -> clone-repository -> prefetch-dependencies -> build-images -> build-image-index
                                        (all skipped when skip-build=true)

    then, in parallel (each test is its own task/pod):
      test-testcontainers                     (podman in a privileged pod)
      provision-kind -> test-makefile-deploy  (kind cluster in a privileged pod)
                       -> test-openshift-pytest

GHA parity: this mirrors .github/workflows/build-notebooks-TEMPLATE.yaml
(build, then testcontainers pytest, then make deploy/test/undeploy, then
openshift pytest — which GHA runs serially in one job; here in parallel).

Usage:

    PYTHONPATH=. uv run ci/konflux/generate_pipelineruns.py

The generated files are read by Pipelines-as-Code, which only scans .tekton/
(the directory is hardcoded in the PaC source), so they live in .tekton/konflux/
even though this package is named after the Konflux experiment.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import yaml

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent
GENERATED_DIR = ROOT_DIR / ".tekton" / "konflux"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GIT_URL = "https://github.com/opendatahub-io/notebooks"
NAMESPACE = "open-data-hub-tenant"
APPLICATION = "opendatahub-release"
OUTPUT_REGISTRY = "quay.io/opendatahub"

# Base pipeline whose task bundle digests we reuse (single source of truth for
# bundle pins: regen after updating .tekton/multiarch-odh-main-combined-pipeline.yaml).
COMBINED_PIPELINE_FILE = ROOT_DIR / ".tekton" / "multiarch-odh-main-combined-pipeline.yaml"
BUILD_TASKS = ("init", "clone-repository", "prefetch-dependencies", "build-images", "build-image-index")

# Konflux multi-platform-controller platform IDs on stone-prd-rh01.
# amd64 builds in-cluster (ADR 0016); arm64 uses the d160-m4xlarge VM pool;
# ppc64le/s390x run on their respective remote VM pools.
FLAVOR_PLATFORMS: dict[str, list[str]] = {
    "cpu": ["linux/x86_64", "linux-d160-m4xlarge/arm64", "linux/ppc64le", "linux/s390x"],
    "cuda": ["linux/x86_64", "linux-d160-m4xlarge/arm64"],
    "rocm": ["linux/x86_64"],
}
PLATFORM_ARCH_KEY = {
    "linux/x86_64": "x86_64",
    "linux-d160-m4xlarge/arm64": "arm64",
    "linux/ppc64le": "ppc64le",
    "linux/s390x": "s390x",
}
# pip binary wheel arches per flavor (prefetch-input binary.arch)
FLAVOR_PIP_ARCHES = {
    "cpu": "x86_64, aarch64, ppc64le, s390x",
    "cuda": "x86_64, aarch64",
    "rocm": "x86_64",
}

# v1: tests only run on amd64. Non-amd64 images would need qemu binfmt in the
# test pod (too slow/flaky for ppc64le/s390x). Extend per image as needed.
DEFAULT_TEST_ARCHES = {"x86_64"}

# Test pod tooling (pinned for reproducibility)
TEST_IMAGE = "quay.io/fedora/fedora:43"
KIND_VERSION = "v0.33.0"
KUBECTL_VERSION = "v1.34.1"
UV_INSTALL_URL = "https://astral.sh/uv/install.sh"
PODMAN_SERVICE_START = [
    # docker-compatible API on the podman socket (GHA's podman.socket equivalent)
    "nohup podman system service --time=0 unix:///run/podman/podman.sock >/tmp/podman-service.log 2>&1 &",
    "for i in $(seq 1 30); do podman info >/dev/null 2>&1 && break; sleep 1; done",
]

# ---------------------------------------------------------------------------
# Image inventory
# ---------------------------------------------------------------------------


@dataclass
class Image:
    """One notebook image (Makefile target) to generate per-arch PipelineRuns for."""

    # Makefile target, e.g. "jupyter-minimal-ubi9-python-3.12"
    make_target: str
    # cpu | cuda | rocm — selects Dockerfile.konflux.<flavor> and build-args/<flavor>.conf
    flavor: str
    # Directory containing the Dockerfile and build-args/
    build_directory: str
    # Which arches run the test stages (default: amd64 only)
    test_arches: set[str] = field(default_factory=lambda: set(DEFAULT_TEST_ARCHES))
    # pytest marker for the testcontainers stage (GHA parity: build-notebooks-TEMPLATE.yaml)
    testcontainers_markers: str = "not openshift and not cuda and not rocm and not manifest_validation"
    # pytest marker for the OpenShift stage (GHA parity)
    openshift_markers: str = "openshift and not cuda and not rocm"

    @property
    def dockerfile(self) -> str:
        return f"{self.build_directory}/Dockerfile.konflux.{self.flavor}"

    @property
    def build_args_file(self) -> str:
        return f"{self.build_directory}/build-args/{self.flavor}.conf"

    @property
    def platforms(self) -> list[str]:
        return FLAVOR_PLATFORMS[self.flavor]

    @property
    def component(self) -> str:
        """Konflux component name, single source of truth: LABEL_COMPONENT in the build-args conf."""
        conf = (ROOT_DIR / self.build_args_file).read_text()
        match = re.search(r"^LABEL_COMPONENT=(\S+)", conf, re.MULTILINE)
        if not match:
            raise ValueError(f"LABEL_COMPONENT not found in {self.build_args_file}")
        return match.group(1)

    @property
    def has_makefile_tests(self) -> bool:
        """GHA parity: ci/cached-builds/has_tests.py — deploy tests exist iff kustomize/base exists."""
        return (ROOT_DIR / self.build_directory / "kustomize" / "base" / "kustomization.yaml").is_file()

    @property
    def hermetic(self) -> bool:
        """GHA parity: hermetic when the image dir ships prefetch-input/ or the Dockerfile consumes it."""
        if (ROOT_DIR / self.build_directory / "prefetch-input").is_dir():
            return True
        return "prefetch-input/" in (ROOT_DIR / self.dockerfile).read_text()

    @property
    def prefetch_input(self) -> list[dict]:
        """Hermetic prefetch inputs (same shape as the existing .tekton PR pipelines)."""
        return [
            {"path": "prefetch-input/odh", "type": "rpm"},
            {"path": "prefetch-input/odh", "type": "generic"},
            {
                "path": self.build_directory,
                "type": "pip",
                "binary": {"arch": FLAVOR_PIP_ARCHES[self.flavor]},
                "requirements_files": [f"requirements.{self.flavor}.txt"],
            },
        ]


# v1 scope: minimal jupyter image only (keep the Konflux infrastructure load low
# while the per-arch + test pipeline shape is being proven out). Add more
# images here to include them.
IMAGES: list[Image] = [
    Image(
        make_target="jupyter-minimal-ubi9-python-3.12",
        flavor="cpu",
        build_directory="jupyter/minimal/ubi9-python-3.12",
    ),
]

# ---------------------------------------------------------------------------
# Task bundle refs (parsed from the combined pipeline so digests stay in sync)
# ---------------------------------------------------------------------------


def bundle_task_refs() -> dict[str, dict]:
    with open(COMBINED_PIPELINE_FILE) as f:
        pipeline = yaml.safe_load(f)
    refs: dict[str, dict] = {}
    for task in pipeline["spec"]["tasks"]:
        if task["name"] in BUILD_TASKS:
            refs[task["name"]] = task["taskRef"]
    missing = set(BUILD_TASKS) - set(refs)
    if missing:
        raise ValueError(f"tasks not found in {COMBINED_PIPELINE_FILE.name}: {missing}")
    return refs


# ---------------------------------------------------------------------------
# Test task specs (GHA parity, parallelized: one task/pod per test group)
# ---------------------------------------------------------------------------


def setup_uv_and_repo_lines() -> list[str]:
    """Clone the PR revision and set up the repo's uv venv (GHA: uv venv + uv sync --group dev)."""
    return [
        "export UV_INSTALL_DIR=/usr/local",
        f"curl -LsSf {UV_INSTALL_URL} | sh",
        "uv python install 3.14",
        "git clone $(params.GIT_URL) src_code",
        "cd src_code",
        "git checkout $(params.REVISION)",
        "uv venv --python 3.14",
        "uv sync --group dev --locked",
    ]


def resolve_image_lines() -> list[str]:
    """BUILT_IMAGE is empty when skip-build=true; fall back to image-under-test then."""
    return [
        'IMAGE="${BUILT_IMAGE:-${IMAGE_UNDER_TEST}}"',
        'if [[ -z "${IMAGE}" ]]; then echo "ERROR: set skip-build=false or image-under-test" >&2; exit 1; fi',
        'echo "Testing image: ${IMAGE}"',
    ]


def test_script(*sections: list[str]) -> str:
    """Tekton StepSpec.script is a STRING — join the lines with newlines."""
    lines = ["#!/bin/bash", "set -Eeuxo pipefail"]
    for section in sections:
        lines += section
    return "\n".join(lines) + "\n"


def image_params() -> list[dict]:
    return [
        {"name": "BUILT_IMAGE", "value": "$(tasks.build-image-index.results.IMAGE_URL)"},
        {"name": "IMAGE_UNDER_TEST", "value": "$(params.image-under-test)"},
    ]


def image_param_declarations() -> list[dict]:
    return [
        {"name": "BUILT_IMAGE", "type": "string"},
        {"name": "IMAGE_UNDER_TEST", "type": "string"},
    ]


def git_params() -> list[dict]:
    return [
        {"name": "GIT_URL", "value": "$(params.git-url)"},
        {"name": "REVISION", "value": "$(params.revision)"},
    ]


def git_param_declarations() -> list[dict]:
    return [
        {"name": "GIT_URL", "type": "string"},
        {"name": "REVISION", "type": "string"},
    ]


def kubeconfig_param() -> tuple[list[dict], list[dict]]:
    """param value (task level) + declaration (taskSpec level), from provision-kind."""
    return (
        [{"name": "KUBECONFIG", "value": "$(tasks.provision-kind.results.kubeconfig)"}],
        [{"name": "KUBECONFIG", "type": "string"}],
    )


def kubeconfig_setup_lines() -> list[str]:
    return [
        "mkdir -p /root/.kube",
        'echo "$(params.KUBECONFIG)" > /root/.kube/config',
        "export KUBECONFIG=/root/.kube/config",
        "kubectl get nodes",
    ]


def testcontainers_task(image: Image) -> dict:
    """GHA parity: 'Run Testcontainers container tests (in PyTest)' step."""
    return {
        "name": "test-testcontainers",
        "runAfter": ["build-image-index"],
        "params": [*git_params(), *image_params(), {"name": "MARKERS", "value": image.testcontainers_markers}],
        "taskSpec": {
            "params": [*git_param_declarations(), *image_param_declarations(), {"name": "MARKERS", "type": "string"}],
            "steps": [
                {
                    "name": "test",
                    "image": TEST_IMAGE,
                    "securityContext": {"privileged": True},
                    "env": [
                        {"name": "DOCKER_HOST", "value": "unix:///run/podman/podman.sock"},
                        {"name": "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "value": "/run/podman/podman.sock"},
                        # GHA parity: pulling Ryuk from docker.io flakes CI
                        {"name": "TESTCONTAINERS_RYUK_DISABLED", "value": "true"},
                        {"name": "FORCE_COLOR", "value": "1"},
                    ],
                    "script": test_script(
                        # NOTE: never use '{{...}}' in a script line — PaC template-renders the
                        # whole file, so e.g. --format '{{.Version}}' is parsed as a template var
                        # and breaks the whole PipelineRun render.
                        ["dnf install -y podman podman-docker git python3 curl", *PODMAN_SERVICE_START, "podman --version"],
                        setup_uv_and_repo_lines(),
                        resolve_image_lines(),
                        [
                            'uv run pytest tests/containers -m "$(params.MARKERS)" '
                            '--image="${IMAGE}" --log-level=DEBUG -o junit_family=legacy'
                        ],
                    ),
                }
            ],
        },
    }


def provision_kind_task() -> dict:
    """Provision a single-node kind cluster in a privileged pod.

    GHA parity: provision-k8s provisions a single-node kubeadm cluster — plain
    k8s, not OpenShift (the 'openshift' markers work on plain k8s via the
    fake-scc label trick). EPHC (CSO, TestPlatformCluster claims) is the
    documented upgrade path for real-OpenShift testing — see ci/konflux/README.md.
    """
    return {
        "name": "provision-kind",
        "runAfter": ["build-image-index"],
        "params": image_params(),
        "taskSpec": {
            "params": image_param_declarations(),
            "results": [
                {
                    "name": "kubeconfig",
                    "description": "kubeconfig for the kind cluster (kept under the 4KB result limit)",
                }
            ],
            "steps": [
                {
                    "name": "provision",
                    "image": TEST_IMAGE,
                    "securityContext": {"privileged": True},
                    "script": test_script(
                        [
                            "dnf install -y podman podman-docker git python3 curl",
                            # kind drives the docker CLI; route it to podman's docker-compatible API
                            *PODMAN_SERVICE_START,
                            "docker version",
                            f"curl -Lo /usr/local/bin/kind https://kind.sigs.k8s.io/dl/{KIND_VERSION}/kind-linux-amd64",
                            "chmod +x /usr/local/bin/kind",
                            f"curl -Lo /usr/local/bin/kubectl https://dl.k8s.io/release/{KUBECTL_VERSION}/bin/linux/amd64/kubectl",
                            "chmod +x /usr/local/bin/kubectl",
                            "kind create cluster --name tekton --wait 10m --retention 1h",
                            "kubectl cluster-info",
                            "kubectl get nodes -o wide",
                        ],
                        resolve_image_lines(),
                        [
                            "podman pull ${IMAGE}",
                            "kind load docker-image ${IMAGE}",
                            "kind get kubeconfig > /tmp/kubeconfig",
                            "wc -c /tmp/kubeconfig",
                            'cp /tmp/kubeconfig "$(results.kubeconfig.path)"',
                        ],
                    ),
                }
            ],
        },
    }


def makefile_deploy_task(image: Image) -> dict:
    """GHA parity: 'Run image tests' step (ci/cached-builds/make_test.py):
    make deploy9-<t> && make test-<t> (papermill) && make undeploy9-<t>."""
    kubeconfig_values, kubeconfig_declarations = kubeconfig_param()
    return {
        "name": "test-makefile-deploy",
        "runAfter": ["provision-kind"],
        "params": [*git_params(), *image_params(), *kubeconfig_values, {"name": "TARGET", "value": image.make_target}],
        "taskSpec": {
            "params": [*git_param_declarations(), *image_param_declarations(), *kubeconfig_declarations, {"name": "TARGET", "type": "string"}],
            "steps": [
                {
                    "name": "test",
                    "image": TEST_IMAGE,
                    "env": [
                        {"name": "FORCE_COLOR", "value": "1"},
                        {"name": "PRODUCT", "value": "odh"},
                    ],
                    "script": test_script(
                        ["dnf install -y make git python3 curl", *kubeconfig_setup_lines()],
                        setup_uv_and_repo_lines(),
                        resolve_image_lines(),
                        [
                            # deploy9-<t> rewrites kustomization.yaml from IMAGE_REGISTRY + NOTEBOOK_TAG
                            'export IMAGE_REGISTRY="${IMAGE%%:*}"',
                            'export NOTEBOOK_TAG="${IMAGE##*:}"',
                            'export IMAGE_TAG="${IMAGE##*:}"',
                            "uv run python3 ci/cached-builds/make_test.py --target $(params.TARGET)",
                        ],
                    ),
                }
            ],
        },
    }


def openshift_pytest_task(image: Image) -> dict:
    """GHA parity: 'Run OpenShift container tests (in PyTest)' step."""
    kubeconfig_values, kubeconfig_declarations = kubeconfig_param()
    return {
        "name": "test-openshift-pytest",
        "runAfter": ["provision-kind"],
        "params": [*git_params(), *image_params(), *kubeconfig_values, {"name": "MARKERS", "value": image.openshift_markers}],
        "taskSpec": {
            "params": [*git_param_declarations(), *image_param_declarations(), *kubeconfig_declarations, {"name": "MARKERS", "type": "string"}],
            "steps": [
                {
                    "name": "test",
                    "image": TEST_IMAGE,
                    "securityContext": {"privileged": True},
                    "env": [
                        # the openshift-marked workbench tests also spin up local
                        # testcontainers (mysql etc.), so the podman socket is needed here too
                        {"name": "DOCKER_HOST", "value": "unix:///run/podman/podman.sock"},
                        {"name": "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "value": "/run/podman/podman.sock"},
                        {"name": "TESTCONTAINERS_RYUK_DISABLED", "value": "true"},
                        {"name": "FORCE_COLOR", "value": "1"},
                    ],
                    "script": test_script(
                        [
                            "dnf install -y podman podman-docker git python3 curl",
                            *PODMAN_SERVICE_START,
                            *kubeconfig_setup_lines(),
                        ],
                        setup_uv_and_repo_lines(),
                        resolve_image_lines(),
                        [
                            'uv run pytest tests/containers -m "$(params.MARKERS)" '
                            '--image="${IMAGE}" --log-level=DEBUG -o junit_family=legacy'
                        ],
                    ),
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# Pipeline / PipelineRun assembly
# ---------------------------------------------------------------------------


def build_tasks_section(image: Image, arch_key: str, refs: dict[str, dict], test_arches: set[str]) -> list[dict]:
    """The inline pipeline spec's task graph for one (image, arch) PipelineRun."""
    not_skipped = [{"input": "$(params.skip-build)", "operator": "in", "values": ["false"]}]
    tasks: list[dict] = [
        {
            "name": "init",
            "params": [{"name": "enable-cache-proxy", "value": "$(params.enable-cache-proxy)"}],
            "taskRef": refs["init"],
        },
        {
            "name": "clone-repository",
            "params": [
                {"name": "url", "value": "$(params.git-url)"},
                {"name": "revision", "value": "$(params.revision)"},
                {"name": "ociStorage", "value": "$(params.output-image).git"},
                {"name": "ociArtifactExpiresAfter", "value": "$(params.image-expires-after)"},
            ],
            "runAfter": ["init"],
            "taskRef": refs["clone-repository"],
            "workspaces": [{"name": "basic-auth", "workspace": "git-auth"}],
        },
        {
            "name": "prefetch-dependencies",
            "timeout": "3h",
            "params": [
                {"name": "input", "value": "$(params.prefetch-input)"},
                {"name": "SOURCE_ARTIFACT", "value": "$(tasks.clone-repository.results.SOURCE_ARTIFACT)"},
                {"name": "ociStorage", "value": "$(params.output-image).prefetch"},
                {"name": "ociArtifactExpiresAfter", "value": "$(params.image-expires-after)"},
                # Hermeto timeouts for large pip wheels (copied from the combined pipeline)
                {
                    "name": "config-file-content",
                    "value": "http:\n  read_timeout: 900\nruntime:\n  concurrency_limit: 8\n  subprocess_timeout: 3600\n",
                },
                {"name": "ACTIVATION_KEY", "value": "$(params.rhel-subscription-activation-key)"},
            ],
            "runAfter": ["clone-repository"],
            "taskRef": refs["prefetch-dependencies"],
            "when": not_skipped,
            "workspaces": [
                {"name": "git-basic-auth", "workspace": "git-auth"},
                {"name": "netrc", "workspace": "netrc"},
            ],
        },
        {
            "name": "build-images",
            "matrix": {"params": [{"name": "PLATFORM", "value": ["$(params.build-platforms)"]}]},
            "timeout": "4h",
            "params": [
                {"name": "IMAGE", "value": "$(params.output-image)"},
                {"name": "DOCKERFILE", "value": "$(params.dockerfile)"},
                {"name": "CONTEXT", "value": "$(params.path-context)"},
                {"name": "HERMETIC", "value": "$(params.hermetic)"},
                {"name": "PREFETCH_INPUT", "value": "$(params.prefetch-input)"},
                {"name": "IMAGE_EXPIRES_AFTER", "value": "$(params.image-expires-after)"},
                {"name": "COMMIT_SHA", "value": "$(tasks.clone-repository.results.commit)"},
                {"name": "BUILD_ARGS", "value": ["$(params.build-args[*])"]},
                {"name": "BUILD_ARGS_FILE", "value": "$(params.build-args-file)"},
                {"name": "PRIVILEGED_NESTED", "value": "$(params.privileged-nested)"},
                {"name": "ACTIVATION_KEY", "value": "$(params.rhel-subscription-activation-key)"},
                {"name": "SOURCE_URL", "value": "$(tasks.clone-repository.results.url)"},
                {"name": "HTTP_PROXY", "value": "$(tasks.init.results.http-proxy)"},
                {"name": "NO_PROXY", "value": "$(tasks.init.results.no-proxy)"},
                {"name": "SOURCE_ARTIFACT", "value": "$(tasks.prefetch-dependencies.results.SOURCE_ARTIFACT)"},
                {"name": "CACHI2_ARTIFACT", "value": "$(tasks.prefetch-dependencies.results.CACHI2_ARTIFACT)"},
                {"name": "IMAGE_APPEND_PLATFORM", "value": "true"},
                {"name": "SOURCE_DATE_EPOCH", "value": "$(params.source-date-epoch)"},
                {"name": "REWRITE_TIMESTAMP", "value": "$(params.rewrite-timestamp)"},
                {"name": "OMIT_HISTORY", "value": "$(params.omit-history)"},
            ],
            "runAfter": ["prefetch-dependencies"],
            "taskRef": refs["build-images"],
            "when": not_skipped,
        },
        {
            "name": "build-image-index",
            "params": [
                {"name": "IMAGE", "value": "$(params.output-image)"},
                {"name": "ALWAYS_BUILD_INDEX", "value": "$(params.build-image-index)"},
                {"name": "IMAGES", "value": ["$(tasks.build-images.results.IMAGE_REF[*])"]},
            ],
            "runAfter": ["build-images"],
            "taskRef": refs["build-image-index"],
            "when": not_skipped,
        },
    ]

    if arch_key in test_arches:
        tasks.append(testcontainers_task(image))
        tasks.append(provision_kind_task())
        if image.has_makefile_tests:
            tasks.append(makefile_deploy_task(image))
        tasks.append(openshift_pytest_task(image))

    return tasks


def pipeline_spec(image: Image, platform: str, refs: dict[str, dict], test_arches: set[str]) -> dict:
    return {
        "params": [
            {"name": "event-type", "type": "string", "default": "pull_request"},
            {"name": "git-url", "type": "string"},
            {"name": "revision", "type": "string", "default": ""},
            {"name": "output-image", "type": "string"},
            {"name": "path-context", "type": "string", "default": "."},
            {"name": "dockerfile", "type": "string"},
            {"name": "hermetic", "type": "string", "default": "false"},
            {"name": "prefetch-input", "type": "string", "default": ""},
            {"name": "image-expires-after", "type": "string", "default": "5d"},
            {"name": "build-image-index", "type": "string", "default": "true"},
            {"name": "enable-cache-proxy", "type": "string", "default": "false"},
            {"name": "privileged-nested", "type": "string", "default": "false"},
            {"name": "build-args", "type": "array", "default": []},
            {"name": "build-args-file", "type": "string", "default": ""},
            {
                "name": "build-platforms",
                "type": "array",
                "default": [platform],
                "description": "Single platform: one PipelineRun per (image, arch).",
            },
            {
                "name": "rhel-subscription-activation-key",
                "type": "string",
                "default": "custom-activation-key",
            },
            {"name": "source-date-epoch", "type": "string", "default": ""},
            {"name": "rewrite-timestamp", "type": "string", "default": "false"},
            {"name": "omit-history", "type": "string", "default": "false"},
            {
                "name": "skip-build",
                "type": "string",
                "default": "false",
                "description": (
                    '"true" skips clone/prefetch/build stages so the test/provision stages can be '
                    "developed against an existing image (image-under-test)."
                ),
            },
            {
                "name": "image-under-test",
                "type": "string",
                "default": "",
                "description": "Image to test when skip-build=true (e.g. a stable-branch build).",
            },
        ],
        "results": [
            {"name": "IMAGE_URL", "value": "$(tasks.build-image-index.results.IMAGE_URL)"},
            {"name": "IMAGE_DIGEST", "value": "$(tasks.build-image-index.results.IMAGE_DIGEST)"},
        ],
        "tasks": build_tasks_section(image, PLATFORM_ARCH_KEY[platform], refs, test_arches),
        "workspaces": [
            {"name": "git-auth", "optional": True},
            {"name": "netrc", "optional": True},
        ],
    }


def compute_resources(has_tests: bool, has_makefile_tests: bool) -> list[dict]:
    """taskRunSpecs overrides (mirrors the existing per-image PR pipelines).

    Only emit entries for tasks that actually exist in the pipeline: referencing a
    non-existent pipelineTaskName makes the whole PipelineRun InvalidTaskRunSpecs.
    """

    def cr(cpu: str, memory: str, ephemeral: str | None = None) -> dict:
        base = {"cpu": cpu, "memory": memory}
        if ephemeral:
            base["ephemeral-storage"] = ephemeral
        return {"requests": dict(base), "limits": dict(base)}

    result = [
        {
            "pipelineTaskName": "prefetch-dependencies",
            "computeResources": cr("4", "8Gi"),
        },
        {
            "pipelineTaskName": "build-images",
            "stepSpecs": [
                {"name": "build", "computeResources": cr("4", "8Gi", "64Gi")},
            ],
        },
    ]
    if has_tests:
        result += [
            {
                "pipelineTaskName": "test-testcontainers",
                "computeResources": cr("4", "8Gi", "60Gi"),
            },
            {
                "pipelineTaskName": "provision-kind",
                "computeResources": cr("4", "8Gi", "60Gi"),
            },
        ]
        if has_makefile_tests:
            result.append(
                {
                    "pipelineTaskName": "test-makefile-deploy",
                    "computeResources": cr("4", "8Gi", "40Gi"),
                }
            )
        result.append(
            {
                "pipelineTaskName": "test-openshift-pytest",
                "computeResources": cr("4", "8Gi", "40Gi"),
            }
        )
    return result


def on_comment(image: Image, arch_key: str) -> str:
    """Per-arch manual trigger, e.g. /build-jupyter-minimal-cpu-x86_64 (PaC on-comment skips CEL)."""
    short = image.make_target.split("-ubi9-python-")[0]
    return f"^/build-{short}-{image.flavor}-{arch_key}"


def cel_expression() -> str:
    """Iteration-mode trigger: runs on every PR push to main.

    Deliberately NO pathChanged() guard — the point of this experiment is to
    iterate by pushing to the PR branch. Before this pattern graduates, add a
    pathChanged() guard (or move to on-comment-only) so unrelated PRs don't
    trigger these runs. See the ADR.
    """
    return 'event == "pull_request" && target_branch == "main" && body.repository.full_name == "opendatahub-io/notebooks"'


def pipelinerun(image: Image, platform: str, refs: dict[str, dict]) -> dict:
    arch_key = PLATFORM_ARCH_KEY[platform]
    component = image.component
    return {
        "apiVersion": "tekton.dev/v1",
        "kind": "PipelineRun",
        "metadata": {
            "annotations": {
                "build.appstudio.openshift.io/repo": GIT_URL + "?rev={{revision}}",
                "build.appstudio.redhat.com/commit_sha": "{{revision}}",
                "build.appstudio.redhat.com/pull_request_number": "{{pull_request_number}}",
                "build.appstudio.redhat.com/target_branch": "{{target_branch}}",
                "pipelinesascode.tekton.dev/cancel-in-progress": "true",
                "pipelinesascode.tekton.dev/max-keep-runs": "3",
                "pipelinesascode.tekton.dev/on-comment": on_comment(image, arch_key),
                "pipelinesascode.tekton.dev/on-cel-expression": cel_expression(),
            },
            "labels": {
                "appstudio.openshift.io/application": APPLICATION,
                "appstudio.openshift.io/component": component,
                "pipelines.appstudio.openshift.io/type": "build",
            },
            "name": f"{component}-{arch_key}-on-pull-request",
            "namespace": NAMESPACE,
        },
        "spec": {
            "timeouts": {"pipeline": "6h"},
            "params": [
                {"name": "event-type", "value": "{{event_type}}"},
                {"name": "git-url", "value": "{{source_url}}"},
                {"name": "revision", "value": "{{revision}}"},
                {
                    "name": "output-image",
                    "value": f"{OUTPUT_REGISTRY}/{component}:on-pr-{{{{revision}}}}-{arch_key}",
                },
                {"name": "image-expires-after", "value": "5d"},
                {"name": "build-platforms", "value": [platform]},
                {"name": "dockerfile", "value": image.dockerfile},
                {"name": "path-context", "value": "."},
                {"name": "build-args-file", "value": image.build_args_file},
                {"name": "hermetic", "value": "true" if image.hermetic else "false"},
                *([{"name": "prefetch-input", "value": image.prefetch_input}] if image.hermetic else []),
            ],
            "pipelineSpec": pipeline_spec(image, platform, refs, image.test_arches),
            "taskRunSpecs": compute_resources(has_tests=arch_key in image.test_arches, has_makefile_tests=image.has_makefile_tests),
            "taskRunTemplate": {
                # Per-component Konflux build SA (auto-created by build-service):
                # quay pull/push for the component image + secret attachment for git-auth.
                "serviceAccountName": f"build-pipeline-{component}",
            },
            "workspaces": [{"name": "git-auth", "secret": {"secretName": "{{ git_auth_secret }}"}}],
        },
    }


# ---------------------------------------------------------------------------
# YAML output
# ---------------------------------------------------------------------------


def _represent_str(dumper: yaml.Dumper, data: str) -> yaml.Node:
    style = None
    if "\n" in data:
        style = "|"
    elif "{" in data or "}" in data:
        style = "'"
    elif data in ("true", "false", ""):
        style = '"'
    elif " " in data and len(data) > 80:
        style = "|"
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


class _Dumper(yaml.SafeDumper):
    """No anchors/aliases (PaC reads these files as templates), block style for
    multi-line strings (shell scripts) and template-bearing strings so nothing
    depends on plain-scalar line folding.

    NOTE: representers are looked up in the class-level yaml_representers dict,
    so the str representer must be registered explicitly — overriding the
    represent_str method alone is dead code.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_representer(str, _represent_str)

    def ignore_aliases(self, data: object) -> bool:
        return True


def render(image: Image, platform: str, refs: dict[str, dict]) -> str:
    return (
        "# yamllint disable-file\n"
        "# This file is autogenerated by ci/konflux/generate_pipelineruns.py — do not edit by hand.\n"
        + yaml.dump(pipelinerun(image, platform, refs), Dumper=_Dumper, width=10_000, sort_keys=False)
    )


def main() -> None:
    out_dir = GENERATED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    refs = bundle_task_refs()
    written: list[str] = []
    for image in IMAGES:
        for platform in image.platforms:
            arch_key = PLATFORM_ARCH_KEY[platform]
            path = out_dir / f"{image.component}-{arch_key}-pull-request.yaml"
            path.write_text(render(image, platform, refs))
            written.append(str(path.relative_to(ROOT_DIR)))
    print(f"Generated {len(written)} PipelineRun(s) in {out_dir.relative_to(ROOT_DIR)}/:")
    for p in written:
        print(f"  {p}")


if __name__ == "__main__":
    main()
else:
    # test dependencies
    if TYPE_CHECKING:
        import pyfakefs.fake_filesystem

    class Tests:
        def test_flavor_platforms(self):
            assert FLAVOR_PLATFORMS["cpu"] == [
                "linux/x86_64",
                "linux-d160-m4xlarge/arm64",
                "linux/ppc64le",
                "linux/s390x",
            ]
            assert FLAVOR_PLATFORMS["cuda"] == ["linux/x86_64", "linux-d160-m4xlarge/arm64"]
            assert FLAVOR_PLATFORMS["rocm"] == ["linux/x86_64"]

        def test_image_derived_paths(self):
            image = Image(
                make_target="jupyter-minimal-ubi9-python-3.12",
                flavor="cpu",
                build_directory="jupyter/minimal/ubi9-python-3.12",
            )
            assert image.dockerfile == "jupyter/minimal/ubi9-python-3.12/Dockerfile.konflux.cpu"
            assert image.build_args_file == "jupyter/minimal/ubi9-python-3.12/build-args/cpu.conf"
            assert len(image.platforms) == 4
            assert image.component == "odh-workbench-jupyter-minimal-cpu-py312-ubi9"
            assert image.has_makefile_tests is True

        def test_pipelinerun_shape(self):
            image = Image(
                make_target="jupyter-minimal-ubi9-python-3.12",
                flavor="cpu",
                build_directory="jupyter/minimal/ubi9-python-3.12",
            )
            refs = bundle_task_refs()
            run = pipelinerun(image, "linux/x86_64", refs)
            assert run["metadata"]["name"] == "odh-workbench-jupyter-minimal-cpu-py312-ubi9-x86_64-on-pull-request"
            output_image = next(p["value"] for p in run["spec"]["params"] if p["name"] == "output-image")
            assert output_image == "quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:on-pr-{{revision}}-x86_64"
            assert next(p["value"] for p in run["spec"]["params"] if p["name"] == "image-expires-after") == "5d"
            task_names = [t["name"] for t in run["spec"]["pipelineSpec"]["tasks"]]
            assert task_names[:5] == ["init", "clone-repository", "prefetch-dependencies", "build-images", "build-image-index"]
            assert "test-testcontainers" in task_names
            assert "provision-kind" in task_names
            assert "test-makefile-deploy" in task_names
            assert "test-openshift-pytest" in task_names
            # test stages run in parallel after the build (not serially like GHA)
            for name in ("test-testcontainers", "provision-kind"):
                task = next(t for t in run["spec"]["pipelineSpec"]["tasks"] if t["name"] == name)
                assert task["runAfter"] == ["build-image-index"]
            # taskRunSpecs must only reference tasks that exist (else InvalidTaskRunSpecs)
            task_names = {t["name"] for t in run["spec"]["pipelineSpec"]["tasks"]}
            assert {t["pipelineTaskName"] for t in run["spec"]["taskRunSpecs"]} <= task_names
            # StepSpec.script is a string in Tekton (an array fails PipelineRun validation)
            for task in run["spec"]["pipelineSpec"]["tasks"]:
                for step in task.get("taskSpec", {}).get("steps", []):
                    assert isinstance(step.get("script"), str), f"{task['name']}: script must be a string"
                    assert step["script"].startswith("#!/bin/bash")

        def test_no_tests_on_non_test_arches(self):
            image = Image(
                make_target="jupyter-minimal-ubi9-python-3.12",
                flavor="cpu",
                build_directory="jupyter/minimal/ubi9-python-3.12",
                test_arches=set(),
            )
            refs = bundle_task_refs()
            run = pipelinerun(image, "linux/ppc64le", refs)
            task_names = [t["name"] for t in run["spec"]["pipelineSpec"]["tasks"]]
            assert task_names == ["init", "clone-repository", "prefetch-dependencies", "build-images", "build-image-index"]

        def test_no_stray_pac_templates(self):
            """PaC template-renders the whole file: any '{{...}}' is a template var.

            Guards against shell constructs like --format '{{.Version}}' silently
            breaking the PipelineRun render (the run just never gets created).
            """
            image = Image(
                make_target="jupyter-minimal-ubi9-python-3.12",
                flavor="cpu",
                build_directory="jupyter/minimal/ubi9-python-3.12",
            )
            allowed = {
                "{{revision}}",
                "{{pull_request_number}}",
                "{{target_branch}}",
                "{{source_url}}",
                "{{event_type}}",
                "{{ git_auth_secret }}",
            }
            for platform in image.platforms:
                text = render(image, platform, bundle_task_refs())
                stray = set(re.findall(r"\{\{[^{}]*\}\}", text))
                assert stray <= allowed, f"{platform}: unexpected template sequences: {stray - allowed}"

        def test_render_roundtrip(self):
            image = Image(
                make_target="jupyter-minimal-ubi9-python-3.12",
                flavor="cpu",
                build_directory="jupyter/minimal/ubi9-python-3.12",
            )
            refs = bundle_task_refs()
            text = render(image, "linux/x86_64", refs)
            doc = yaml.safe_load(text)
            assert doc["kind"] == "PipelineRun"
            assert doc["spec"]["pipelineSpec"]["tasks"][0]["name"] == "init"
