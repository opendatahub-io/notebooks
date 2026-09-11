#!/usr/bin/env python3
"""Generates per-architecture Konflux PipelineRuns under .tekton/konflux/.

Each notebook image gets one PipelineRun per architecture (image x arch matrix),
so images and architectures build in parallel instead of one multi-arch
PipelineRun per image (see the ADR in docs/architecture/decisions/).

Pipeline shape (single inline pipelineSpec — no cluster-side Pipeline CR needed):

    init -> clone-repository -> prefetch-dependencies -> build-images -> build-image-index
                                        (all skipped when skip-build=true)

    then, in parallel (two test legs, each its own pod):
      test-testcontainers   (rootless podman: testcontainers pytest)
      test-k8s              (rootless podman + kind: make deploy/papermill,
                             then openshift-marked pytest — one step because
                             the kind cluster only lives inside this pod)

GHA parity: this mirrors .github/workflows/build-notebooks-TEMPLATE.yaml
(build, then testcontainers pytest, then make deploy/test/undeploy, then
openshift pytest — which GHA runs serially in one job; here the two legs
run in parallel, and within the k8s leg the steps stay serial because they
share one in-pod kind cluster).

The tenant's SCCs forbid privileged containers (verified live), so the test
pods run rootless podman/kind (see rootless_step_script).

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
# K8s object names must be RFC 1123 (lowercase alphanumerics and '-'), so the
# 'x86_64' arch token cannot appear in PipelineRun names or filenames — use
# 'amd64' (the K8s node-label spelling) there. 'x86_64' stays in the Konflux
# platform id (linux/x86_64) and pip arch lists, which are plain string values.
K8S_ARCH_NAME = {"x86_64": "amd64"}


def k8s_arch(arch_key: str) -> str:
    return K8S_ARCH_NAME.get(arch_key, arch_key)


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
# Pinned so the test pods don't drift past pyproject.toml's [tool.uv]
# required-version (">=0.11.8,<0.13") when a newer uv releases. Must stay in
# that range; bump deliberately.
UV_VERSION = "0.12.13"
UV_INSTALL_URL = f"https://astral.sh/uv/{UV_VERSION}/install.sh"


def rootless_env_lines() -> list[str]:
    """Rootless podman/kind environment (the tenant SCCs forbid privileged pods,
    verified live: every usable SCC rejects .containers[0].privileged=true)."""
    return [
        'if [ -z "${XDG_RUNTIME_DIR:-}" ] || [ ! -w "/run/user/$(id -u)" ]; then',
        '  mkdir -p "/run/user/$(id -u)" 2>/dev/null || true',
        "fi",
        'export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"',
        'export DOCKER_HOST="unix://$XDG_RUNTIME_DIR/podman/podman.sock"',
        'export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE="$XDG_RUNTIME_DIR/podman/podman.sock"',
    ]


def podman_service_start_lines() -> list[str]:
    """docker-compatible API on the rootless podman socket (GHA podman.socket equivalent)."""
    return [
        "nohup podman system service --time=0 >/tmp/podman-service.log 2>&1 &",
        "for _ in $(seq 1 30); do podman info >/dev/null 2>&1 && break; sleep 1; done",
        "podman --version",
    ]


def rootless_step_script(*body_sections: list[str]) -> str:
    """Step script that re-execs its body as a non-root user when running as root.

    Tekton runs each step in its own container, and the tenant's SCCs forbid
    privileged containers, so containers-in-the-pod (podman, kind) must run
    rootless. Root phase (as root): install packages, create a user with a
    subuid range, then re-exec the body (everything below the marker) as that
    user. When the pod already runs non-root, the root phase is skipped.
    """
    body_lines: list[str] = []
    for section in body_sections:
        body_lines += section
    header = [
        "#!/bin/bash",
        "set -Eeuxo pipefail",
        "# --- root phase: packages + non-root user (rootless podman/kind below) ---",
        "dnf install -y podman podman-docker git python3 curl make sudo",
        # diagnostics: pod capabilities + no_new_privs (rootless feasibility)
        "grep -E 'CapEff|NoNewPrivs' /proc/self/status",
        'if [ "$(id -u)" = "0" ]; then',
        "  useradd -m tester 2>/dev/null || true",
        "  U=$(id -u tester)",
        '  grep -q "^tester:" /etc/subuid || usermod --add-subuids 100000-165535 tester',
        '  mkdir -p "/run/user/$U" && chown tester "/run/user/$U"',
        # the fedora image ships newuidmap/newgidmap without setuid/filecaps;
        # rootless user-namespace setup needs them (podman info: exit 125).
        # Filecaps need CAP_SETFCAP, which this pod may lack (setcap EPERM);
        # the setuid bit only needs file ownership, so prefer it.
        "  chmod u+s /usr/bin/newuidmap /usr/bin/newgidmap",
        "  ls -l /usr/bin/newuidmap",
        "  sed -n '/^# __BODY_BELOW__/,$p' \"$0\" | tail -n +2 > /tmp/step-body.sh",
        "  chmod +x /tmp/step-body.sh",
        '  exec su -s /bin/bash tester -c "export XDG_RUNTIME_DIR=/run/user/$U; bash /tmp/step-body.sh"',
        "fi",
        "# __BODY_BELOW__",
        "set -Eeuxo pipefail",
        'export PATH="$HOME/.local/bin:$HOME/bin:$PATH"',
        # su preserves the (root-owned) cwd — work from $HOME instead
        'cd "$HOME"',
        # diagnostics for the next rootless failure, if any
        "grep -E 'CapEff|NoNewPrivs' /proc/self/status",
    ]
    return "\n".join(header + body_lines) + "\n"


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
    """Clone the PR revision and set up the repo's uv venv (GHA: uv venv + uv sync --group dev).

    Runs as the non-root body user (home-dir uv install; PATH is set by
    rootless_step_script).
    """
    return [
        f"curl -LsSf {UV_INSTALL_URL} | sh",
        "uv python install 3.14",
        'git clone "$(params.GIT_URL)" src_code',
        "cd src_code",
        'git checkout "$(params.REVISION)"',
        "uv venv --python 3.14",
        "uv sync --group dev --locked",
    ]


def resolve_image_lines() -> list[str]:
    # Re-trigger note: the test pods fail at 0s (admission); next iteration
    # captures the exact rejection to pick between privileged-SCC and rootless.
    """BUILT_IMAGE is the deterministic on-pr tag the build pushes to (params.output-image).

    It is a param, not a task-result reference: a task that references a
    $(tasks.X.results.Y) of a when-skipped task is itself skipped (Tekton
    MissingResultsSkip), which would break the skip-build iteration mode.
    """
    return [
        'if [[ "${SKIP_BUILD}" == "true" && -z "${IMAGE_UNDER_TEST}" ]]; then',
        '  echo "ERROR: skip-build=true requires image-under-test" >&2; exit 1',
        "fi",
        'IMAGE="${IMAGE_UNDER_TEST:-${BUILT_IMAGE}}"',
        'echo "Testing image: ${IMAGE}"',
    ]


def test_script(*sections: list[str]) -> str:
    """Tekton StepSpec.script is a STRING — join the lines with newlines."""
    lines = ["#!/bin/bash", "set -Eeuxo pipefail"]
    for section in sections:
        lines += section
    return "\n".join(lines) + "\n"


def image_params() -> list[dict]:
    # BUILT_IMAGE is params.output-image (the deterministic on-pr tag), NOT
    # $(tasks.build-image-index.results.IMAGE_URL): referencing a
    # when-skipped task's result would skip this task too (MissingResultsSkip).
    return [
        {"name": "BUILT_IMAGE", "value": "$(params.output-image)"},
        {"name": "IMAGE_UNDER_TEST", "value": "$(params.image-under-test)"},
        {"name": "SKIP_BUILD", "value": "$(params.skip-build)"},
    ]


def image_param_declarations() -> list[dict]:
    return [
        {"name": "BUILT_IMAGE", "type": "string"},
        {"name": "IMAGE_UNDER_TEST", "type": "string"},
        {"name": "SKIP_BUILD", "type": "string"},
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


def image_env() -> list[dict]:
    """Expose the image params to the step script as shell variables."""
    return [
        {"name": "BUILT_IMAGE", "value": "$(params.BUILT_IMAGE)"},
        {"name": "IMAGE_UNDER_TEST", "value": "$(params.IMAGE_UNDER_TEST)"},
        {"name": "SKIP_BUILD", "value": "$(params.SKIP_BUILD)"},
    ]


def testcontainers_task(image: Image) -> dict:
    """GHA parity: 'Run Testcontainers container tests (in PyTest)' step.

    Rootless podman in the pod (the tenant SCCs forbid privileged containers).
    The podman service and its consumer share one step: Tekton steps are
    separate containers, and a service started in an earlier step dies with it.
    """
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
                    "env": [
                        *image_env(),
                        # GHA parity: pulling Ryuk from docker.io flakes CI
                        {"name": "TESTCONTAINERS_RYUK_DISABLED", "value": "true"},
                        {"name": "FORCE_COLOR", "value": "1"},
                    ],
                    "script": rootless_step_script(
                        # NOTE: never use '{{...}}' in a script line — PaC template-renders the
                        # whole file, so e.g. --format '{{.Version}}' is parsed as a template var
                        # and breaks the whole PipelineRun render.
                        rootless_env_lines(),
                        setup_uv_and_repo_lines(),
                        resolve_image_lines(),
                        podman_service_start_lines(),
                        [
                            (
                                'uv run pytest tests/containers -m "$(params.MARKERS)" '
                                '--image="${IMAGE}" --log-level=DEBUG -o junit_family=legacy'
                            )
                        ],
                    ),
                }
            ],
        },
    }


def k8s_test_task(image: Image) -> dict:
    """The whole k8s test leg in ONE task/pod: kind cluster, make deploy/
    test/undeploy (papermill), then the openshift-marked pytest.

    One pod (and one step) because the kind cluster is podman containers
    inside the pod — a dependent task's pod could never reach it, and each
    Tekton step is its own container, so even separate steps in one task
    would kill the cluster between steps. Everything kind/podman-related
    therefore lives in a single step, sequentially, like GHA.

    GHA parity: provision-k8s provisions a single-node kubeadm cluster — plain
    k8s, not OpenShift (the 'openshift' markers work on plain k8s via the
    fake-scc label trick). EPHC (CSO, TestPlatformCluster claims) is the
    documented upgrade path for real-OpenShift testing — see ci/konflux/README.md.
    """
    kind_tooling = [
        'mkdir -p "$HOME/bin"',
        f'curl -Lo "$HOME/bin/kind" https://kind.sigs.k8s.io/dl/{KIND_VERSION}/kind-linux-amd64',
        'chmod +x "$HOME/bin/kind"',
        f'curl -Lo "$HOME/bin/kubectl" https://dl.k8s.io/release/{KUBECTL_VERSION}/bin/linux/amd64/kubectl',
        'chmod +x "$HOME/bin/kubectl"',
        # kind drives podman directly (rootless); no long-running service needed
        "export KIND_EXPERIMENTAL_PROVIDER=podman",
    ]
    body = [
        *rootless_env_lines(),
        *kind_tooling,
        *setup_uv_and_repo_lines(),
        *resolve_image_lines(),
        # No TTL flag in kind v0.33; the cluster dies with the pod.
        "kind create cluster --name tekton --wait 10m",
        "kubectl cluster-info",
        'podman pull "${IMAGE}"',
        'kind load docker-image "${IMAGE}"',
        "export KUBECONFIG=$HOME/.kube/config",
        "kind get kubeconfig",
        "kubectl get nodes -o wide",
    ]
    if image.has_makefile_tests:
        # deploy9-<t> rewrites kustomization.yaml from IMAGE_REGISTRY + NOTEBOOK_TAG
        body += [
            'export IMAGE_REGISTRY="${IMAGE%%:*}"',
            'export NOTEBOOK_TAG="${IMAGE##*:}"',
            'export IMAGE_TAG="${IMAGE##*:}"',
            'uv run python3 ci/cached-builds/make_test.py --target "$(params.TARGET)"',
        ]
    body += [
        # the openshift-marked workbench tests also spin up local testcontainers
        # (mysql etc.) — same step, so the podman service survives
        *podman_service_start_lines(),
        (
            'uv run pytest tests/containers -m "$(params.MARKERS)" '
            '--image="${IMAGE}" --log-level=DEBUG -o junit_family=legacy'
        ),
        "kind delete cluster --name tekton || true",
    ]
    return {
        "name": "test-k8s",
        "runAfter": ["build-image-index"],
        "params": [
            *git_params(),
            *image_params(),
            {"name": "TARGET", "value": image.make_target},
            {"name": "MARKERS", "value": image.openshift_markers},
        ],
        "taskSpec": {
            "params": [
                *git_param_declarations(),
                *image_param_declarations(),
                {"name": "TARGET", "type": "string"},
                {"name": "MARKERS", "type": "string"},
            ],
            "steps": [
                {
                    "name": "test",
                    "image": TEST_IMAGE,
                    "env": [
                        *image_env(),
                        {"name": "TESTCONTAINERS_RYUK_DISABLED", "value": "true"},
                        {"name": "FORCE_COLOR", "value": "1"},
                        {"name": "PRODUCT", "value": "odh"},
                    ],
                    "script": rootless_step_script(body),
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
        # two parallel test legs (each its own pod): testcontainers, and the
        # whole k8s leg (kind + make deploy/papermill + openshift pytest)
        tasks.append(testcontainers_task(image))
        tasks.append(k8s_test_task(image))

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
                # TEMPORARY: "true" while iterating on the test/provision stages
                # (they fail at admission; the build stages are proven). Revert to
                # "false" once the test pods schedule.
                "default": "true",
                "description": (
                    '"true" skips clone/prefetch/build stages so the test/provision stages can be '
                    "developed against an existing image (image-under-test)."
                ),
            },
            {
                "name": "image-under-test",
                "type": "string",
                # TEMPORARY: the amd64 image built by the c528eab8b run (still
                # valid, 5d expiry) while iterating on the test stages. Revert
                # to "" when skip-build goes back to "false".
                "default": "quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:on-pr-c528eab8b3110650fed41910339281c8f2efb894-x86_64",
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


def compute_resources(has_tests: bool) -> list[dict]:
    """taskRunSpecs overrides (mirrors the existing per-image PR pipelines).

    Only emit entries for tasks that actually exist in the pipeline: referencing a
    non-existent pipelineTaskName makes the whole PipelineRun InvalidTaskRunSpecs.

    Test-pod memory mirrors GHA (the whole suite runs on a 7Gi runner); the
    k8s leg needs the most (kind control plane + notebook pod + pytest).
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
                "computeResources": cr("4", "4Gi", "40Gi"),
                "timeout": "60m",
            },
            # kind + papermill notebook + openshift pytest in one pod
            {
                "pipelineTaskName": "test-k8s",
                "computeResources": cr("4", "6Gi", "60Gi"),
                "timeout": "90m",
            },
        ]
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
    return (
        'event == "pull_request" && target_branch == "main" && body.repository.full_name == "opendatahub-io/notebooks"'
    )


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
            "name": f"{component}-{k8s_arch(arch_key)}-on-pull-request",
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
            "taskRunSpecs": compute_resources(has_tests=arch_key in image.test_arches),
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
        self.add_representer(str, _represent_str)  # pyright: ignore[reportArgumentType]

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
            path = out_dir / f"{image.component}-{k8s_arch(arch_key)}-pull-request.yaml"
            path.write_text(render(image, platform, refs))
            written.append(str(path.relative_to(ROOT_DIR)))
    print(f"Generated {len(written)} PipelineRun(s) in {out_dir.relative_to(ROOT_DIR)}/:")
    for p in written:
        print(f"  {p}")


if __name__ == "__main__":
    main()
else:
    # test dependencies

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
            # K8s object name: 'x86_64' (underscore) is not RFC 1123, so it maps to 'amd64'
            assert run["metadata"]["name"] == "odh-workbench-jupyter-minimal-cpu-py312-ubi9-amd64-on-pull-request"
            assert re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", run["metadata"]["name"]), "name must be RFC 1123"
            output_image = next(p["value"] for p in run["spec"]["params"] if p["name"] == "output-image")
            assert (
                output_image
                == "quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:on-pr-{{revision}}-x86_64"
            )
            assert next(p["value"] for p in run["spec"]["params"] if p["name"] == "image-expires-after") == "5d"
            task_names = [t["name"] for t in run["spec"]["pipelineSpec"]["tasks"]]
            assert task_names[:5] == [
                "init",
                "clone-repository",
                "prefetch-dependencies",
                "build-images",
                "build-image-index",
            ]
            # two parallel test legs (no more provision-kind / makefile / openshift tasks)
            assert "test-testcontainers" in task_names
            assert "test-k8s" in task_names
            assert not any(n in task_names for n in ("provision-kind", "test-makefile-deploy", "test-openshift-pytest"))
            # test legs run in parallel after the build (not serially like GHA)
            for name in ("test-testcontainers", "test-k8s"):
                task = next(t for t in run["spec"]["pipelineSpec"]["tasks"] if t["name"] == name)
                assert task["runAfter"] == ["build-image-index"]
            # taskRunSpecs must only reference tasks that exist (else InvalidTaskRunSpecs)
            task_names = {t["name"] for t in run["spec"]["pipelineSpec"]["tasks"]}
            assert {t["pipelineTaskName"] for t in run["spec"]["taskRunSpecs"]} <= task_names
            # the tenant SCCs forbid privileged containers — no test step may request one
            for task in run["spec"]["pipelineSpec"]["tasks"]:
                for step in task.get("taskSpec", {}).get("steps", []):
                    assert isinstance(step.get("script"), str), f"{task['name']}: script must be a string"
                    assert step["script"].startswith("#!/bin/bash")
                    assert step.get("securityContext", {}).get("privileged") is not True, (
                        f"{task['name']}: privileged forbidden"
                    )

        def test_script_vars_resolved(self):
            """Every shell variable referenced in a generated step script must be
            either provided by the step's env or assigned in the script.

            Catches the '$SKIP_BUILD: unbound variable' class of bug: the step
            env is invisible to the authoring flow, so an env var that is
            referenced but never declared only surfaces as a live-run failure
            (under set -u) many minutes into iteration.
            """
            env_provided = {
                # set by the container runtime / su, not by the step env list
                "HOME",
                "PATH",
                "PWD",
                "SHLVL",
                "USER",
                "LOGNAME",
                "HOSTNAME",
                "SHELL",
                "TERM",
                "OPTIND",
            }

            def shell_refs(script: str) -> set[str]:
                """$VAR / ${VAR} references outside single quotes."""
                refs: set[str] = set()
                in_squote = False
                i, n = 0, len(script)
                while i < n:
                    c = script[i]
                    if in_squote:
                        if c == "'":
                            in_squote = False
                    elif c == "'":
                        in_squote = True
                    elif c == "\\" and i + 1 < n:
                        i += 1
                    elif c == "$":
                        m = re.match(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", script[i:])
                        if m:
                            refs.add(m.group(1))
                    i += 1
                return refs

            image = Image(
                make_target="jupyter-minimal-ubi9-python-3.12",
                flavor="cpu",
                build_directory="jupyter/minimal/ubi9-python-3.12",
            )
            run = pipelinerun(image, "linux/x86_64", bundle_task_refs())
            for task in run["spec"]["pipelineSpec"]["tasks"]:
                for step in task.get("taskSpec", {}).get("steps", []):
                    script = step.get("script")
                    if not isinstance(script, str):
                        continue
                    env_names = {e["name"] for e in step.get("env", [])}
                    assigned = set(re.findall(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=", script, re.M))
                    missing = shell_refs(script) - env_names - assigned - env_provided
                    assert not missing, (
                        f"{task['name']}/step-{step['name']}: referenced but never env'd or assigned: {sorted(missing)}"
                    )

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
            assert task_names == [
                "init",
                "clone-repository",
                "prefetch-dependencies",
                "build-images",
                "build-image-index",
            ]

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
