# Testing Guide

This document is the test catalog for the notebooks repository. It describes what
tests exist, where they live, how to run them, and how they map to CI.

For operational gotchas (worktree naming, pyfakefs, PRODUCT matching, CI `-n` metadata),
see [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Setup

```bash
uv venv --python "$(which python3.14)"
uv sync --locked
```

On macOS, install Homebrew GNU Make so `make` resolves to GNU Make 4.x:

```bash
brew install make
PATH="/opt/homebrew/opt/make/libexec/gnubin:$PATH"
```

## Test targets

| Target | What it runs | Requires |
|--------|-------------|----------|
| `make test` | Static checks, Python unit tests and doctests | Locked Python environment |
| `make test-unit` | Python tests + doctests, explicit agentic-reviewer tests, and Go tests | Locked Python environment (Go auto-downloads) |
| `make test-integration PYTEST_ARGS="--image=<img>"` | Container integration tests | Podman/Docker |
| `make test-<notebook>` | Notebook smoke test via papermill | kubectl + deployed workbench |

### Deploying for notebook smoke tests

`make test-<notebook>` requires a deployed workbench on Kubernetes; OpenShift is
one supported environment. CI provisions Kubernetes for these smoke tests. For the full
deploy/test/undeploy cycle, see [README.md § Notebooks](../../README.md#notebooks)
and [README.md § Runtimes](../../README.md#runtimes).

## Test types and locations

| Type | Location | Naming | Organization |
|------|----------|--------|--------------|
| Static / manifest | `tests/test_*.py` | Module-level functions | Group with `subtests` |
| Unit | `tests/unit/` | `test_*.py` mirroring source layout | Module-level functions |
| Container integration | `tests/containers/` | `*_test.py` (class-based) | `Test*` classes with fixtures |
| Browser E2E | `tests/browser/tests/` | `*.spec.ts` | Playwright + pnpm |
| Go | `scripts/buildinputs/` | Standard Go test files | `make test-unit` runs these |
| K8s notebook smoke | `scripts/` | Shell scripts | `make test-<notebook>` |

### Collection behavior

- `tests/containers/` is **excluded from default collection** via `collect_ignore` in
  `tests/conftest.py`. Run container tests explicitly with `pytest tests/containers --image=<img>`.
- Default `make test` collects from `tests/`, `ntb/`, and `ci/` (doctests).
- `ci/agentic-reviewer/` is excluded from recursive collection; `make test-unit`
  explicitly includes its tests and also runs the Go tests.
- `--strict-markers` is on — unregistered markers fail the run.

### Offline JupyterLab feature tests

The JupyterLab offline feature suite runs explicitly against a preloaded image.
The workbench is attached only to an internal container network, without a
default route or published host ports. Host HTTP and WebSocket clients reach it
through a Caddy sidecar attached to both the internal network and a regular
network, with a published proxy port. This topology is also called a **bastion**:
a pod, container, or virtual machine that provides controlled access between an
air-gapped part of the system and the outside world. Here, Caddy forwards requests
to Jupyter; it does not provide the workbench with general outbound connectivity.

```bash
podman pull quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:odh-stable
podman pull quay.io/hummingbird/caddy:latest
uv sync --locked
TESTCONTAINERS_RYUK_DISABLED=true uv run --offline --no-sync pytest \
  tests/containers/workbenches/jupyterlab/offline_features_test.py \
  --image=quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:odh-stable
```

Pulling both images and preparing the locked `uv` environment are separate from
the offline test run. Caddy may be pulled during setup if it is not cached.
`uv --offline` controls dependency resolution; the internal network isolates the
workbench. This invocation's `--offline` and Ryuk setting do not change the network
or cleanup behavior of other integration suites. The helper manages the workbench,
bastion and networks on Linux and macOS.

Protocol clients (`jupyter-client` and `websocket-client`, included in the locked
development dependencies) run on the host. Git commands run inside the workbench
against temporary repositories there, so the test exercises the image's Git.

Kernel readiness and execution each have a 30-second budget, increased to 120
seconds for `arm64`/`aarch64`, `s390x` and `ppc64le`. Architecture comes from
`BUILD_ARCH`, or image metadata when it is unset. During readiness, the probe
reconnects unresponsive WebSocket channels with fresh session IDs to recover from
[ipykernel #1554](https://github.com/ipython/ipykernel/issues/1554). It sends user
code once after readiness and never replays execution to recover a timeout.

It covers prefixed Lab startup and local assets, Contents API CRUD, server-managed
kernel execution, offline wheel installation, local Git clone/commit/push/pull,
environment and secret propagation across replacement, and persistent versus
ephemeral storage. Dashboard/RBAC/Kueue/ImageStream and hardware behavior require
OpenShift tests; S3 and certificate behavior require service-backed tests; other
IDEs, R, GPU, and browser-specific behavior are outside this backend suite.

Coverage of the [workbench feature inventory](../features.md):

| Feature group | Local offline coverage | Requires a different environment |
|---|---|---|
| Create and manage workbenches | Normal Jupyter entrypoint, Python package installation and kernel import, container replacement | Dashboard lifecycle, image selection, other IDEs |
| Customize images and resources | Arbitrary UID with group 0 | ImageStreams, Notebook CRs, hardware profiles and accelerators |
| Secrets, connections and storage | Dummy environment values reach kernels; replacement loads changed values; mounted notebooks survive replacement and container-layer files do not | Kubernetes Secret/ConfigMap injection, connection management, S3/TLS, PVC provisioning and access-mode enforcement |
| Develop and collaborate | Notebook Contents API, execution through server-managed kernels, local Git clone/commit/push/pull | External Git authentication, R workflows |
| Schedule and govern access | None | Kueue, RBAC, administrator controls, idle shutdown and scheduling |

Browser interactions have a [separate Playwright suite](../../tests/browser/README.md#running-the-offline-jupyterlab-suite).
The dedicated `run-offline-browser.sh` launcher places the browser runner and
workbench on an internal network. Ordinary Playwright runs use a Testcontainers
fixture on a regular network with a published Jupyter port; the `@offline` tag
means the tests need no internet access to pass, making them suitable for
air-gapped (disconnected) clusters. Neither local Jupyter suite requires a cluster
or external services during execution. Image pulls and test dependency
installation are preparation steps and require connectivity unless already cached.

## Markers

All markers must be registered in `pytest.ini`:

| Marker | Meaning | Excluded from default run |
|--------|---------|--------------------------|
| `openshift` | Needs live OpenShift cluster | Yes |
| `cuda` | Needs NVIDIA GPU | Yes |
| `rocm` | Needs AMD GPU | Yes |
| `manifest_validation` | Slow registry/skopeo checks | Yes |
| `buildonlytest` | Runs inside docker build only | Yes (different filter) |
| `codeserver` | Code-Server workbench specific | No |

## CI parity

The `pytest-tests` job in `.github/workflows/code-quality.yaml` runs `make test`.
`make test-unit` overlaps that coverage, explicitly adds agentic-reviewer tests,
and runs the Go tests that CI runs separately with `gotestsum`. Other CI checks
whose exact workflow commands are **not yet**
exposed as `make` targets:

- yamllint (inline in workflow)
- hadolint (inline in workflow)
- gotestsum (inline in workflow)
- prek (inline in workflow)

Closing this gap (moving inline CI logic into Makefile targets) is tracked in
[#3174](https://github.com/opendatahub-io/notebooks/issues/3174).

Jupyter workbench builds in `build-notebooks-TEMPLATE.yaml` run the local
`playwright-test` action with `--grep @jupyter`; runtime images are excluded.
`test-playwright-action.yaml` also tests that action with separate Code-Server and
JupyterLab matrix legs. These callers enable report and JUnit uploads for all
supported events, including scheduled and manually dispatched runs. The HTML
report and raw results (screenshots, videos and traces) share one artifact; JUnit
is uploaded separately.

The browser action passes the image architecture as `TEST_TARGET_ARCH`. The
Jupyter fixture allows 120 seconds for startup when that architecture differs
from the runner's normalized `process.arch`, and 30 seconds otherwise.

### `check-generated-code` (lock scoping)

The `check-generated-code` job runs `ci/generate_code.sh`, then verifies a clean working tree with `git status --porcelain`.

- **Pull requests:** lock regen is scoped to image directories whose lock chain the PR
  touched (`pyproject.toml`, `pylock.toml`, `requirements.*.txt`, or `uv.lock.d/*`). If the PR only changes
  unrelated files, `pylocks_generator` is skipped so external AIPCC index churn does not
  fail the job. Shared inputs (`dependencies/constraints.txt`, `dependencies/overrides.txt`, lock generator scripts)
  still trigger full lock regen. CI fetches base and PR head refs (same pattern as
  `build-notebooks-pr.yaml`), then runs `pylocks_generator --pr-base origin/<base-branch>
  --pr-to-ref <pr-branch>` with `gha_pr_changed_files.list_changed_files()` (`git diff`
  three-dot). Locally: `bash ci/generate_code.sh --pr-base origin/main` (default head: `HEAD`).
  See [RHAIENG-6397](https://redhat.atlassian.net/browse/RHAIENG-6397).
- **Push** (`main`, `stable`, `rhoai-*`): full lock regen for all image dirs (unchanged).

## Frameworks and tools

| Tool | Purpose |
|------|---------|
| pytest | Test runner for all Python tests |
| pytest's built-in `subtests` fixture (pytest 9+) | Granular sub-assertions within a single test |
| pytest-cov | Coverage (XML + terminal) |
| allure-pytest | Issue tracking + step decoration |
| hypothesis | Property-based tests for pure helpers (`tests/unit/test_property_helpers.py`) |
| crosshair | Optional SMT backend for those Hypothesis tests (`make test-crosshair`) |
| testcontainers | Container lifecycle for integration tests |
| pyfakefs | Filesystem mocking for unit tests |
| Playwright | Browser tests (TypeScript) |
| papermill | Notebook execution verification |

Hypothesis tests run in the normal `make test` / `make test-unit` pytest jobs
(same `pytest-tests` CI job). There is no separate Hypothesis workflow: default
`max_examples` is enough for PR CI. Raise examples locally when exploring
(`settings(max_examples=...)` or a Hypothesis profile).

### Optional CrossHair (SMT) backend

CrossHair is **not** in the default `dev` install (pulls z3 ~37MB). Use it when you
want a solver to hunt hard-to-reach branches in existing `@given` tests:

```bash
make test-crosshair
# equivalent:
uv sync --locked --group crosshair
uv run pytest tests/unit/test_property_helpers.py --hypothesis-profile=crosshair
```

Do **not** enable `backend="crosshair"` on the default CI path: it is slower and the
standard Hypothesis backend already covers PR gating. Standalone `crosshair check`
needs explicit contracts (`pre:`/`post:`) and is not wired up yet.

## Troubleshooting

- **Container tests hang:** Ensure the container runtime (podman/docker) is running.
  On Linux: `systemctl --user start podman.service`.
- **Dependency conflicts after lock regen:** Run `make refresh-lock-files` and check
  for "unsatisfiable" errors. See [docs/cves/python.md](../cves/python.md) for
  constraint resolution.
- **`make test` fails on stray files:** Extra top-level directories (`.cursor-tmp-*`)
  break repo-wide assertions. Clean clone or `git clean -fdx` the offending paths.
- **Security scanning:** Weekly Quay vulnerability reports are generated by
  `ci/security-scan/quay_security_analysis.py` (triggered via `.github/workflows/sec-scan.yml`).

## External test suites

The images built by this repo are also tested by other projects:

| Suite | Framework | What it tests |
|-------|-----------|---------------|
| [odh-dashboard](https://github.com/opendatahub-io/odh-dashboard/tree/main/packages/cypress/cypress/tests/e2e/dataScienceProjects/workbenches) | Cypress | Workbench CRUD, image selection, RBAC via ODH dashboard |
| [ods-ci](https://github.com/red-hat-data-services/ods-ci/tree/master/ods_ci/tests/Tests/0500__ide) | Robot Framework | GPU/CUDA validation, Elyra pipelines, plugin consistency |
| [opendatahub-tests](https://github.com/opendatahub-io/opendatahub-tests/tree/main/tests/workbenches) | Pytest | ImageStream health, Notebook CR spawning, package availability |

## Package upgrade checklist

When upgrading a Python package (PyTorch, TensorFlow, numpy, etc.) or adding a new
dependency, follow these steps in order. Each layer catches a different class of
problem — skipping a layer means that class of bug ships silently.

### 1. Update the dependency and regenerate locks

Edit the relevant `pyproject.toml` file(s), then regenerate lock files:

```bash
make refresh-lock-files
```

If the resolver fails with "unsatisfiable" errors, see
[docs/cves/python.md](../cves/python.md) for constraint resolution.

### 2. Run static tests

```bash
make test
```

**What this catches:** version mismatches between `pyproject.toml` files (e.g., you
bumped numpy in one image but not another), broken lock files, Dockerfile alignment
issues, manifest drift.

Key tests in this layer:
- `test_image_pyprojects_version_alignment` — ensures the same package uses
  consistent version specifiers across all images
- Dockerfile structure checks — validates multi-stage build consistency
- Manifest validation — checks ImageStream definitions match expected metadata

### 3. Run unit tests

```bash
make test-unit
```

**What this catches:** regressions in helper scripts (index URL resolution, lock file
generation, CI tooling). These tests are fast and don't require containers.

### 4. Build the affected image(s)

```bash
# Non-GPU images (minimal, datascience, trustyai):
make jupyter-datascience-ubi9-python-3.12 PRODUCT=odh \
  IMAGE_REGISTRY=localhost/workbench-images IMAGE_TAG=latest PUSH_IMAGES=no

# CUDA GPU images (pytorch, tensorflow):
make cuda-jupyter-pytorch-ubi9-python-3.12 PRODUCT=odh \
  IMAGE_REGISTRY=localhost/workbench-images IMAGE_TAG=latest PUSH_IMAGES=no
```

GPU images require a `cuda-` or `rocm-` prefix on the target name.
Set `PUSH_IMAGES=no` for local-only builds.

**What this catches:** dependency conflicts at install time, missing system
libraries, broken pip constraints. If the build fails, the package combination is
not viable.

Keep `PRODUCT=odh` or `PRODUCT=rhoai` consistent between build and test steps (see
[CONTRIBUTING.md § ODH vs RHOAI local builds](../../CONTRIBUTING.md#odh-vs-rhoai-local-builds)).

### 5. Run container integration tests

```bash
make test-integration PRODUCT=odh PYTEST_ARGS="--image=<image>"
```

where `<image>` is the full image reference from the build step (e.g.,
`localhost/workbench-images:cuda-jupyter-pytorch-ubi9-python-3.12-latest`).

**What this catches:**
- Entrypoint fails to start (JupyterLab/Code-Server doesn't come up)
- Library import failures at runtime (numpy, pandas, sklearn, matplotlib, torch,
  torchvision, feast, mlflow — see `tests/containers/workbenches/jupyterlab/libraries_testunits.py`)
- GPU library loading issues for CUDA/ROCm images
- Missing runtime dependencies that pip installed but the OS layer doesn't support

### 6. Run manual test notebooks (GPU images)

For GPU-accelerated images (PyTorch, TensorFlow), run the manual test notebooks
inside a deployed workbench or locally with GPU passthrough:

| Notebook | What it validates |
|----------|-------------------|
| `tests/manual/pytorch-test-notebook.ipynb` | PyTorch quickstart (data loading, model training, save/load), tensor operations on GPU |
| `tests/manual/tensorflow-test.ipynb` | TensorFlow quickstart (MNIST training), GPU detection, nvidia-smi/hipcc, TensorBoard |
| `tests/manual/gpu-test-notebook.ipynb` | General GPU availability and basic operations |

These notebooks exercise real ML workflows end-to-end and catch problems that
unit-level import checks miss (e.g., CUDA version incompatibilities, broken
model serialization, silent CPU fallback).

### 7. Run browser tests (if UI-affecting)

If the upgrade could affect JupyterLab or Code-Server UI (e.g., upgrading
`jupyterlab`, a JupyterLab extension, or `code-server`):

```bash
cd tests/browser
pnpm install --frozen-lockfile
# Each IDE uses its own default image when TEST_TARGET is unset:
pnpm exec playwright test --grep @jupyter
pnpm exec playwright test --grep @codeserver
# To test a specific image, select the matching IDE suite:
TEST_TARGET='<jupyter-image>' pnpm exec playwright test --grep @jupyter
```

With `TEST_TARGET` set, the caller must filter on the matching `@jupyter` or
`@codeserver` tag. An unfiltered run also includes `@openshift` tests that require
a configured cluster. Jupyter tests use the shared `playwright.config.ts`.

See [tests/browser/AGENTS.md](../../tests/browser/AGENTS.md) for setup details.

**What this catches:** extension breakage, UI rendering regressions, IDE
feature failures.

### Quick reference

| Change type | Minimum test layers |
|-------------|-------------------|
| Python library version bump | Steps 1–5 |
| New Python dependency | Steps 1–5 |
| GPU library upgrade (PyTorch, TF, CUDA) | Steps 1–6 |
| JupyterLab / Code-Server / extension upgrade | Steps 1–5, 7 |
| Dockerfile structural change | Steps 1–5 |
| `pyproject.toml` constraint change only | Steps 1–3 |

## Running images locally

Build with a predictable tag and push disabled, then run:

```bash
# JupyterLab (port 8888)
make jupyter-minimal-ubi9-python-3.12 PRODUCT=odh \
  IMAGE_REGISTRY=localhost/workbench-images IMAGE_TAG=latest PUSH_IMAGES=no
podman run -it -p 8888:8888 localhost/workbench-images:jupyter-minimal-ubi9-python-3.12-latest

# Code-Server (port 8787)
make codeserver-ubi9-python-3.12 PRODUCT=odh \
  IMAGE_REGISTRY=localhost/workbench-images IMAGE_TAG=latest PUSH_IMAGES=no
podman run -it -p 8787:8787 localhost/workbench-images:codeserver-ubi9-python-3.12-latest
```

For published image references, see the [README.md Image Inventory](../../README.md#image-inventory-list).
Override the entrypoint to inspect an image without starting the workbench
(see [AGENTS.md](../../AGENTS.md) operational notes).
