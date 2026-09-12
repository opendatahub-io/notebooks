#!/usr/bin/env python3
"""Generates per-architecture Konflux PipelineRuns under .tekton/konflux/.

Each notebook image gets one PipelineRun per architecture (image x arch matrix),
so images and architectures build in parallel instead of one multi-arch
PipelineRun per image (see the ADR in docs/architecture/decisions/).

Pipeline shape (single inline pipelineSpec — no cluster-side Pipeline CR needed):

    init -> clone-repository -> prefetch-dependencies -> build-images -> build-image-index
                                        (all skipped when skip-build=true)

    then, in parallel (two test legs, each its own pod):
      test-testcontainers   (testcontainers pytest, markers per Image)
      test-papermill        (the GHA papermill leg as a pytest port, marker
                             "papermill" — test_notebook.ipynb executed via
                             papermill against the image's installed stack)

GHA parity: this mirrors .github/workflows/build-notebooks-TEMPLATE.yaml
(build, then testcontainers pytest, then make deploy/test/undeploy (papermill),
then openshift pytest — which GHA runs serially in one job). Here the two
test legs run in parallel, and both run the image under test as a pod
SIDECAR (below) — no in-pod cluster. The TEMPLATE's kind-based k8s leg
(make deploy + openshift-marked pytest) is intentionally NOT replicated:
the papermill test no longer needs a cluster at all, and the openshift-marked
tests require a real cluster (deferred to an EPHC/CSO-managed test cluster).

In-pod container runtimes are impossible in this tenant: the SCCs reject
privileged containers (verified live), rootless is voided by NoNewPrivs: 1,
and a per-step CAP_SYS_ADMIN request was rejected too (see the ADR
Investigation section). The test legs therefore run the image under test as
a pod SIDECAR and drive it through a sidecar exec agent over a localhost
control plane (no runtime at all; the k8s exec API was probed and rejected
by RBAC — the pipeline SA cannot even `get pods`).

Usage:

    PYTHONPATH=. uv run ci/konflux/generate_pipelineruns.py

The generated files are read by Pipelines-as-Code, which only scans .tekton/
(the directory is hardcoded in the PaC source), so they live in .tekton/konflux/
even though this package is named after the Konflux experiment.
"""

from __future__ import annotations

import base64
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

# Test step image: the image under test itself ($(params.BUILT_IMAGE) at
# render time). These workbench images already ship bash, git, curl, tar,
# python3 and uv, so the step needs no package-manager installs (no dnf), and
# the pod's image pull is shared with the sidecar. If a future test image lacks
# a required binary, the step fails fast on the first use (set -Ee) and the
# fix is either in the image or a dedicated tooling image here.
# Pinned fallback uv, only installed when the image ships none: it keeps the
# test pods inside pyproject.toml's [tool.uv] required-version
# (">=0.11.8,<0.13") when a newer uv releases. Must stay in that range; bump
# deliberately. (Images built from this repo's Dockerfiles ship an in-range uv.)
UV_VERSION = "0.12.13"
UV_INSTALL_URL = f"https://astral.sh/uv/{UV_VERSION}/install.sh"


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
    # pytest marker for the testcontainers stage (GHA parity: build-notebooks-TEMPLATE.yaml).
    # "not papermill" keeps the GHA papermill leg out of this task — it runs as
    # its own sidecar task (test-papermill) with marker "papermill".
    testcontainers_markers: str = (
        "not openshift and not cuda and not rocm and not manifest_validation and not papermill"
    )

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

    Runs as root (home-dir uv install; PATH is set by sidecar_step_script).
    """
    return [
        # the workbench images ship uv in pyproject's required-version range;
        # the pinned installer is the fallback for images that do not
        f"command -v uv >/dev/null || curl -LsSf {UV_INSTALL_URL} | sh",
        "uv python install 3.14",
        'git clone "$(params.GIT_URL)" src_code',
        "cd src_code",
        'git checkout "$(params.REVISION)"',
        "uv venv --python 3.14",
        "uv sync --group dev --locked",
    ]


def resolve_image_lines() -> list[str]:
    """IMAGE is BUILT_IMAGE — params.output-image, the single source of truth
    for the image under test: the deterministic on-pr tag the build pushes
    (normal mode) or an existing image to test (skip-build mode, where the
    caller overrides output-image).

    It is a param, not a task-result reference: a task that references a
    $(tasks.X.results.Y) of a when-skipped task is itself skipped (Tekton
    MissingResultsSkip), which would break the skip-build mode.
    """
    return [
        'if [[ -z "${BUILT_IMAGE}" ]]; then',
        '  echo "ERROR: output-image must be set (the built tag, or the image under test when skip-build=true)" >&2; exit 1',
        "fi",
        'IMAGE="${BUILT_IMAGE}"',
        'echo "Testing image: ${IMAGE}"',
    ]


def image_params() -> list[dict]:
    # BUILT_IMAGE is params.output-image (the deterministic on-pr tag), NOT
    # $(tasks.build-image-index.results.IMAGE_URL): referencing a
    # when-skipped task's result would skip this task too (MissingResultsSkip).
    return [
        {"name": "BUILT_IMAGE", "value": "$(params.output-image)"},
        {"name": "SKIP_BUILD", "value": "$(params.skip-build)"},
    ]


def image_param_declarations() -> list[dict]:
    return [
        {"name": "BUILT_IMAGE", "type": "string"},
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
        {"name": "SKIP_BUILD", "value": "$(params.SKIP_BUILD)"},
    ]


def sidecar_step_script(body_lines: list[str]) -> str:
    """Test step script for the sidecar stage.

    No container runtime is installed — that is the point: the image under
    test runs as a pod sidecar and is driven through the sidecar agent's
    localhost control plane.
    """
    # No package-manager installs: the step runs in the image under test,
    # which ships bash/git/curl/tar/python3/uv (verified per image build).
    header = [
        "#!/bin/bash",
        "set -Eeuxo pipefail",
        # the workbench image's app bin (uv, python3) may not be on PATH
        'export PATH="$HOME/.local/bin:$HOME/bin:/opt/app-root/bin:$PATH"',
        "mkdir -p /workspace",
        "cd /workspace",
    ]
    return "\n".join(header + body_lines) + "\n"


def gh_report_lines(label: str) -> list[str]:
    """Post a run summary as a PR comment — the persistent sink.

    This tenant GCs pod logs within ~2 min of failure, so the PR comment is
    the only durable record of what the run did. The whole block is
    best-effort and never fails the task: a report-delivery glitch must not
    mask the test result (a missing report.json once failed a green run via
    curl's CURLE_READ_ERROR under `set -Eeuxo pipefail`).
    """
    return [
        'GH_TOKEN=$(cat "$(workspaces.basic-auth.path)/git-provider-token" 2>/dev/null || true)',
        'if [ -n "$GH_TOKEN" ]; then',
        "  tail -25 /tmp/pytest.log > /tmp/report-tail.txt",
        # the \n sequences must stay literal (printf format + python escapes)
        "# shellcheck disable=SC2016",
        (
            "printf '%s\\n' 'import json' 'fence = chr(96) * 3' "
            "'tail = open(\"/tmp/report-tail.txt\").read()' "
            f'\'body = "{label} (auto-posted; pod logs are GCed in this tenant):\\n" + fence + "\\n" + tail + "\\n" + fence\' '
            '\'open("/tmp/report.json", "w").write(json.dumps({"body": body}))\' > /tmp/post_report.py'
        ),
        # the report must exist before the curl, and delivery failure must
        # not mask the test result (|| true)
        "  python3 /tmp/post_report.py",
        (
            '  GH_STATUS=$(curl -s -o /tmp/gh-response.json -w "%{http_code}" '
            '-X POST "https://api.github.com/repos/opendatahub-io/notebooks/issues/4566/comments" '
            '-H "Authorization: token $GH_TOKEN" -H "Accept: application/vnd.github+json" '
            "--data-binary @/tmp/report.json || true)"
        ),
        '  echo "github summary comment: HTTP $GH_STATUS"',
        "else",
        '  echo "github summary comment: SKIPPED (no git-provider-token key in git-auth)"',
        "fi",
    ]


def sidecar_test_task(
    image: Image,
    arch_key: str,
    *,
    task_name: str,
    markers: str,
    report_label: str,
    pytest_extra: str = "",
) -> dict:
    """One sidecar-based test leg (task/pod per leg; legs run in parallel).

    Sidecar design (the runtime-free path): the image under test runs as a
    Tekton SIDECAR of the test pod — a plain pod container, so no container
    runtime, no SCC involvement, no capabilities (in-pod podman/kind is
    impossible in this tenant; see the ADR Investigation section). The
    sidecar's main process is the sidecar exec agent (tests/containers/
    sidecar_agent.py, embedded here at generation time and handed to the
    sidecar over a shared emptyDir); the test step drives the image through
    its localhost HTTP control plane — start the entrypoint, exec commands,
    copy files, restart the server. The k8s-exec-API alternative was probed
    and rejected by RBAC (the pipeline SA cannot even `get pods`), so the
    agent is the only in-pod transport. The test step runs in the image under
    test itself (git/curl/python3/uv preinstalled — no dnf; runAsUser 0
    because the workbench images' default user is 1001). A pytest summary is
    posted as a PR comment (via the PaC git-auth secret, key
    git-provider-token) because this tenant GCs pod logs within ~2 min of
    failure — the comment is the persistent sink. pytest_extra carries
    per-leg pytest flags (the papermill leg uses --capture=no so the
    papermill run output streams to the task log on success, GHA parity).
    """
    # uname-style arch for the container_arch fixture (the PLR is per-arch);
    # keys are the canonical PLATFORM_ARCH_KEY values (x86_64, arm64, ...)
    uname_arch = {"x86_64": "x86_64", "arm64": "aarch64", "ppc64le": "ppc64le", "s390x": "s390x"}[arch_key]
    agent_path = pathlib.Path(__file__).resolve().parents[2] / "tests" / "containers" / "sidecar_agent.py"
    agent_b64 = base64.b64encode(agent_path.read_bytes()).decode()
    agent_wait = (
        "for i in $(seq 1 120); do "
        "python3 -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8899/status', timeout=1)\" >/dev/null 2>&1 && break; "
        "sleep 1; done"
    )
    script_lines = [
        *setup_uv_and_repo_lines(),
        *resolve_image_lines(),
        # the sidecar waits for this file, then execs the agent as its main process
        f"echo {agent_b64} | base64 -d > /shared/agent.py",
        agent_wait,
        "python3 -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8899/status', timeout=2).read().decode())\"",
        "PYTEST_EXIT=0",
        (
            f'uv run pytest tests/containers -m "$(params.MARKERS)" --image="${{IMAGE}}" -vvv --color=yes {pytest_extra}'
            " > /tmp/pytest.log 2>&1 || PYTEST_EXIT=$?"
        ),
        "tail -60 /tmp/pytest.log || true",
        *gh_report_lines(report_label),
        'exit "${PYTEST_EXIT}"',
    ]
    return {
        "name": task_name,
        "runAfter": ["build-image-index"],
        "params": [
            *git_params(),
            *image_params(),
            {"name": "MARKERS", "value": markers},
            {"name": "ARCH", "value": uname_arch},
        ],
        "workspaces": [{"name": "basic-auth", "workspace": "git-auth"}],
        "taskSpec": {
            "params": [
                *git_param_declarations(),
                *image_param_declarations(),
                {"name": "MARKERS", "type": "string"},
                {"name": "ARCH", "type": "string"},
            ],
            # optional: the pipeline workspace git-auth is optional, so the
            # task-side declaration must be too (PaC always provides the
            # secret); the script guards against the absent/empty case
            "workspaces": [{"name": "basic-auth", "optional": True}],
            "volumes": [{"name": "shared", "emptyDir": {}}],
            "sidecars": [
                {
                    "name": "sut",
                    # the image under test; its main process is the sidecar
                    # exec agent (the image's own entrypoint is replaced —
                    # the agent relaunches it as a child on /start). BUILT_IMAGE
                    # is params.output-image: the built tag in normal mode, or
                    # the existing image under test when skip-build=true (the
                    # caller overrides output-image) — one reference, valid in
                    # both modes (an empty ref would fail pod admission).
                    "image": "$(params.BUILT_IMAGE)",
                    "command": [
                        "/bin/sh",
                        "-c",
                        "while [ ! -s /shared/agent.py ]; do sleep 1; done; exec python3 /shared/agent.py",
                    ],
                    "env": [
                        {"name": "SUT_ENTRYPOINT", "value": "start-notebook.sh"},
                        {"name": "SUT_WORKDIR", "value": "/opt/app-root/src"},
                        {"name": "SUT_SERVER_LOG", "value": "/shared/server.log"},
                        {"name": "SUT_IMAGE_USER", "value": "1001"},
                    ],
                    "volumeMounts": [{"name": "shared", "mountPath": "/shared"}],
                    "securityContext": {"runAsUser": 0},
                    "resources": {
                        "requests": {"cpu": "500m", "memory": "256Mi"},
                        "limits": {"cpu": "2", "memory": "2Gi"},
                    },
                }
            ],
            "steps": [
                {
                    "name": "test",
                    # the image under test itself: git/curl/python3/uv are
                    # preinstalled (no dnf), and the pod's image pull is
                    # shared with the sidecar container.
                    "image": "$(params.BUILT_IMAGE)",
                    "securityContext": {"runAsUser": 0},
                    "env": [
                        *image_env(),
                        {"name": "FORCE_COLOR", "value": "1"},
                        # sidecar mode for the test suite (see sidecar_transport.py)
                        {"name": "SUT_AGENT_URL", "value": "http://127.0.0.1:8899"},
                        {"name": "SUT_IMAGE_USER", "value": "1001"},
                        {"name": "SUT_ARCH", "value": uname_arch},
                    ],
                    "volumeMounts": [{"name": "shared", "mountPath": "/shared"}],
                    "resources": {
                        "requests": {"cpu": "500m", "memory": "1Gi"},
                        "limits": {"cpu": "2", "memory": "4Gi"},
                    },
                    "script": sidecar_step_script(script_lines),
                }
            ],
        },
    }


def testcontainers_task(image: Image, arch_key: str) -> dict:
    """GHA parity: 'Run Testcontainers container tests (in PyTest)' step."""
    return sidecar_test_task(
        image,
        arch_key,
        task_name="test-testcontainers",
        markers=image.testcontainers_markers,
        report_label="sidecar test run",
    )


def papermill_task(image: Image, arch_key: str) -> dict:
    """GHA papermill leg (make deploy/test/undeploy) as a pytest port.

    Runs the image's test_notebook.ipynb via papermill against the image's
    installed stack — cluster-free (tests/containers/workbenches/
    papermill_test.py). Images without a test_notebook.ipynb skip at runtime.
    --capture=no: this leg selects exactly one test, and that test prints the
    papermill run output (stdout) on success so it reaches the task log, the
    way GHA's papermill step streamed it.
    """
    return sidecar_test_task(
        image,
        arch_key,
        task_name="test-papermill",
        markers="papermill",
        report_label="papermill test run",
        pytest_extra="--capture=no",
    )


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
        # two parallel sidecar test legs (each its own pod): the testcontainers
        # pytest and the papermill leg (GHA's make deploy/test, cluster-free)
        tasks.append(testcontainers_task(image, arch_key))
        tasks.append(papermill_task(image, arch_key))

    return tasks


def pipeline_spec(image: Image, platform: str, refs: dict[str, dict], test_arches: set[str]) -> dict:
    return {
        "params": [
            {"name": "event-type", "type": "string", "default": "pull_request"},
            {"name": "git-url", "type": "string"},
            {"name": "revision", "type": "string", "default": ""},
            {
                "name": "output-image",
                "type": "string",
                "description": (
                    "The image under test, in both modes: the tag the build pushes "
                    "on-pr-<revision>-<arch> in normal mode, or an existing image to "
                    "test when skip-build=true. (Must be non-empty — the test "
                    "sidecars pull it directly.)"
                ),
            },
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
                    '"true" skips clone/prefetch/build stages so the test stages can run '
                    "against an existing image — set output-image to that image "
                    "(e.g. a stable-branch build)."
                ),
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
    testcontainers leg needs the most (it runs the largest pytest subset).
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
            # papermill notebook + pip install papermill in the sidecar
            {
                "pipelineTaskName": "test-papermill",
                "computeResources": cr("4", "4Gi", "40Gi"),
                "timeout": "30m",
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
            # two parallel sidecar test legs (no k8s/kind leg, no provision-kind /
            # makefile / openshift tasks)
            assert "test-testcontainers" in task_names
            assert "test-papermill" in task_names
            assert not any(
                n in task_names for n in ("test-k8s", "provision-kind", "test-makefile-deploy", "test-openshift-pytest")
            )
            # test legs run in parallel after the build (not serially like GHA)
            for name in ("test-testcontainers", "test-papermill"):
                task = next(t for t in run["spec"]["pipelineSpec"]["tasks"] if t["name"] == name)
                assert task["runAfter"] == ["build-image-index"]
            # taskRunSpecs must only reference tasks that exist (else InvalidTaskRunSpecs)
            task_names = {t["name"] for t in run["spec"]["pipelineSpec"]["tasks"]}
            assert {t["pipelineTaskName"] for t in run["spec"]["taskRunSpecs"]} <= task_names
            # the tenant SCCs reject privileged:true (and per-step CAP_SYS_ADMIN)
            # — no step may request either (sidecar design: the test steps need
            # no capabilities at all)
            for task in run["spec"]["pipelineSpec"]["tasks"]:
                for step in task.get("taskSpec", {}).get("steps", []):
                    assert isinstance(step.get("script"), str), f"{task['name']}: script must be a string"
                    assert step["script"].startswith("#!/bin/bash")
                    assert step.get("securityContext", {}).get("privileged") is not True, (
                        f"{task['name']}: privileged forbidden"
                    )
                    assert step.get("securityContext", {}).get("capabilities", {}).get("add") is None, (
                        f"{task['name']}: capability adds forbidden"
                    )
            task = next(t for t in run["spec"]["pipelineSpec"]["tasks"] if t["name"] == "test-testcontainers")
            sidecars = task["taskSpec"]["sidecars"]
            assert sidecars[0]["name"] == "sut"
            # BUILT_IMAGE is the single source of truth (params.output-image);
            # an empty/other ref would fail pod admission in one of the modes
            assert sidecars[0]["image"] == "$(params.BUILT_IMAGE)"
            assert sidecars[0]["securityContext"]["runAsUser"] == 0
            # the sidecar's main process is the exec agent (waits for the file
            # the test step writes into the shared emptyDir)
            assert "/shared/agent.py" in sidecars[0]["command"][-1]
            sidecar_env = {e["name"]: e["value"] for e in sidecars[0]["env"]}
            assert sidecar_env["SUT_ENTRYPOINT"] == "start-notebook.sh"
            assert sidecar_env["SUT_SERVER_LOG"] == "/shared/server.log"
            step = task["taskSpec"]["steps"][0]
            # the step runs in the image under test (no dnf: git/curl/python3/
            # uv are preinstalled); runAsUser 0 because the workbench images'
            # default user is 1001
            assert step["image"] == "$(params.BUILT_IMAGE)"
            assert step["securityContext"] == {"runAsUser": 0}
            step_env = {e["name"]: e["value"] for e in step["env"]}
            assert step_env["SUT_AGENT_URL"] == "http://127.0.0.1:8899"
            assert step_env["SUT_ARCH"] == "x86_64"
            # shared emptyDir: agent handoff (sidecar) + server log (both)
            assert task["taskSpec"]["volumes"] == [{"name": "shared", "emptyDir": {}}]
            assert step["volumeMounts"] == [{"name": "shared", "mountPath": "/shared"}]
            assert sidecars[0]["volumeMounts"] == [{"name": "shared", "mountPath": "/shared"}]
            # the step posts a pytest summary to the PR via the PaC git-auth secret
            assert task["workspaces"] == [{"name": "basic-auth", "workspace": "git-auth"}]
            assert task["taskSpec"]["workspaces"] == [{"name": "basic-auth", "optional": True}]
            script = step["script"]
            assert "base64 -d > /shared/agent.py" in script
            assert "pytest tests/containers" in script
            assert "git-provider-token" in script
            # no package-manager installs: the image under test ships the
            # tooling (regression: the dnf line came back once)
            assert "dnf" not in script
            # testcontainers leg: no capture override (default capture)
            assert "--capture=no" not in script
            # the report step must generate report.json before curling it, and
            # the curl must be non-fatal (a missing file once failed a green
            # run via CURLE_READ_ERROR under set -e)
            assert "python3 /tmp/post_report.py" in script
            assert "--data-binary @/tmp/report.json || true" in script
            # the papermill leg: same sidecar shape, its own marker
            task = next(t for t in run["spec"]["pipelineSpec"]["tasks"] if t["name"] == "test-papermill")
            params = {p["name"]: p["value"] for p in task["params"]}
            assert params["MARKERS"] == "papermill"
            assert task["taskSpec"]["sidecars"][0]["image"] == "$(params.BUILT_IMAGE)"
            pm_script = task["taskSpec"]["steps"][0]["script"]
            assert "python3 /tmp/post_report.py" in pm_script
            # GHA parity: the papermill run output streams to the task log on
            # success (the single selected test prints it)
            assert "--capture=no" in pm_script
            assert "dnf" not in pm_script

        def test_script_vars_resolved(self):
            """Every shell variable referenced in a generated step script must be
            either provided by the step's env or assigned in the script.

            Catches the '$SKIP_BUILD: unbound variable' class of bug: the step
            env is invisible to the authoring flow, so an env var that is
            referenced but never declared only surfaces as a live-run failure
            (under set -u) many minutes into iteration.
            """
            env_provided = {
                # set by the container runtime / k8s, not by the step env list
                "HOME",
                "PATH",
                "PWD",
                "SHLVL",
                "USER",
                "HOSTNAME",  # k8s sets hostname = pod name
                "LOGNAME",
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
