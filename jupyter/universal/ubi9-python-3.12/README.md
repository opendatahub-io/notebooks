# jupyter/universal/ubi9-python-3.12

Hermetic **Universal Jupyter** image: one digest for interactive JupyterLab
workbench mode and Elyra / AI Pipelines runtime mode. Python 3.12 on EL9 for
both ODH (CentOS Stream) and RHOAI (AIPCC) product variants.

Tracked by [RHAIENG-7730](https://redhat.atlassian.net/browse/RHAIENG-7730).

## Status

- Dual-mode entrypoint (`entrypoint-universal.sh`): workbench when
  `NOTEBOOK_ARGS` / default CMD; pipeline runtime when the command is overridden
  or the first arg is `runtime` (see [Operating modes](#operating-modes)).
- Lean package contract: JupyterLab + Elyra/Kale (+ PDF export). No datascience,
  AI framework, or accelerator stacks.
- RPMs and Python packages install from Cachi2 prefetch inputs.
- Python install uses `requirements.${PYLOCK_FLAVOR}.txt` with
  `--no-index --find-links /cachi2/output/deps/pip` (no public PyPI at build time).
- **Same RH-index lock** for ODH and RHOAI (`uv.lock.d/pylock.cpu.toml`); only the
  base image and RPM prefetch variant differ.
- **Multi-arch (Path B)**: Konflux builds all four Linux arches; JupyterLab /
  Elyra / Kale Python deps install on **x86_64 + aarch64 only**. See
  `pyproject.toml` allowlist markers. GHA/IBM workbench matrix tests only those
  arches (ppc64le/s390x have no `jupyter` binary — not in `PPC64LE_COMPATIBLE` /
  `S390X_COMPATIBLE`).

## Product variants

| Product | Build args | Base image | Make |
|---------|------------|------------|------|
| **ODH** | [`build-args/cpu.conf`](build-args/cpu.conf) | CentOS Stream `odh-base-image-cpu-py312-c9s` | `PRODUCT=odh` (default) |
| **RHOAI** | [`build-args/konflux.cpu.conf`](build-args/konflux.cpu.conf) | AIPCC `cpu-torch2.13-el9.8` | `PRODUCT=rhoai` |

Imagestreams: `manifests/odh/base/jupyter-universal-notebook-imagestream.yaml` and
`manifests/rhoai/base/jupyter-universal-notebook-imagestream.yaml`.

## Operating modes

Entrypoint: `/opt/app-root/bin/entrypoint-universal.sh`.

| Mode | How it is selected | What runs |
|------|--------------------|-----------|
| **Workbench** | No args, or arg is `start-notebook.sh` (controller sets `NOTEBOOK_ARGS`) | `/opt/app-root/bin/start-notebook.sh` → JupyterLab; sources `setup-elyra.sh` / `setup-kale.sh` |
| **Pipeline runtime** | First arg is `runtime`, **or** arbitrary command override (typical Elyra `bootstrapper.py`) | `python /opt/app-root/bin/utils/bootstrapper.py …` or `exec "$@"` |

Examples (override entrypoint only when inspecting the image):

```bash
# Workbench (default)
podman run --rm -e NOTEBOOK_ARGS='--ServerApp.port=8888' <image>

# Explicit runtime shortcut
podman run --rm --entrypoint="" <image> \
  /opt/app-root/bin/entrypoint-universal.sh runtime --help

# Command override (pipeline-style)
podman run --rm --entrypoint="" <image> \
  /opt/app-root/bin/entrypoint-universal.sh python -c 'print("ok")'
```

Unit coverage for mode selection:
`tests/unit/jupyter/universal/test_entrypoint_universal.py`.

## Local hermetic build

This image has **no** component-local `prefetch-input/`; the Dockerfile uses
**repo-root** `prefetch-input/` (ODH/RHDS RPM + mongocli) plus pip requirements
under this directory. Prefetch and build from the **repository root**.

### Prerequisites

| Tool | Purpose |
|------|---------|
| GNU Make 4.0+ (`gmake` on macOS) | Build pipeline |
| `podman` | Container build |
| Repo `.venv` (`uv sync`) | Prefetch scripts |
| `hermeto`, `wget`, `jq` | RPM / artifact prefetch |
| RHSM entitlements | RHOAI / `--rhds` only — see [subscribed-builds.md](../../../docs/subscribed-builds.md) |

Set `RELEASE_PYTHON_VERSION=3.12` and `BUILD_ARCH` to match the platform you
will build (same as GHA). See
[lockfile generators — Local development](../../../scripts/lockfile-generators/README.md#local-development)
and [hermetic-guide.md](../../../docs/hermetic-guide.md).

### ODH (`PRODUCT=odh`)

```bash
uv sync --locked
source .venv/bin/activate
git submodule update --init --recursive   # mongocli for gomod prefetch

RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/amd64 \
  ./scripts/lockfile-generators/prefetch-all.sh \
    --component-dir jupyter/universal/ubi9-python-3.12 \
    --flavor cpu

make jupyter-universal-ubi9-python-3.12 PRODUCT=odh PUSH_IMAGES=no
```

The Makefile mounts `cachi2/output` when present and the Dockerfile references
`prefetch-input/`. Python install is `--no-index` only.

### RHOAI hermetic (`PRODUCT=rhoai`, no public PyPI)

Requires host entitlements (or podman-machine sync) and RHDS RPM prefetch:

```bash
# Entitlements: docs/subscribed-builds.md (entitlement/*.pem or machine sync)

RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/amd64 \
  ./scripts/lockfile-generators/prefetch-all.sh \
    --component-dir jupyter/universal/ubi9-python-3.12 \
    --flavor cpu \
    --rhds

make jupyter-universal-ubi9-python-3.12 PRODUCT=rhoai PUSH_IMAGES=no
```

Confirm hermetic Python install: the Dockerfile uses
`UV_NO_CACHE=true … uv pip install --no-index … --find-links /cachi2/output/deps/pip`.
Do not point the build at public PyPI. TLS / CDN issues:
[subscribed-builds.md](../../../docs/subscribed-builds.md).

GHA subscribed builds also pass `--rhds` when the Dockerfile references
`prefetch-input/` (see `.github/workflows/build-notebooks-TEMPLATE.yaml`).

## Python lockfile flow

- `pyproject.toml` is the source of truth (RH-index for **both** products).
- `uv.lock.d/pylock.cpu.toml` and `requirements.cpu.txt` are generated via
  `make refresh-lock-files` / `create-requirements-lockfile.sh`.
- See [uv-guide.md](../../../docs/uv-guide.md) (§ RH-index for both products).

```bash
./scripts/lockfile-generators/create-requirements-lockfile.sh \
  --pyproject-toml jupyter/universal/ubi9-python-3.12/pyproject.toml \
  --flavor cpu
```

## Local validation (workbench mode)

Keep `PRODUCT` consistent between build and test. After you have an image ref
(local tag or Quay):

```bash
# Workbench smoke + JupyterLab suite + offline features (x86_64/aarch64)
make test-integration PRODUCT=odh PYTEST_ARGS="--image=<universal-image> -k 'workbench or jupyterlab or offline'"

# Optional browser offline suite
# See tests/browser/AGENTS.md — set OFFLINE_WORKBENCH_IMAGE=<universal-image>

# Cluster papermill (Elyra/Kale imports via test/test_notebook.ipynb)
make deploy9-jupyter-universal-ubi9-python-3.12   # or your deploy target
make test-jupyter-universal-ubi9-python-3.12 PRODUCT=odh
```

Fixtures treat `-universal-` as a lean JupyterLab workbench (skip datascience
library suites; skip JupyterLab tests on ppc64le/s390x). See
[`tests/containers/conftest.py`](../../../tests/containers/conftest.py) and
[docs/agents/testing.md](../../../docs/agents/testing.md).

Kustomize probes (startup / liveness / readiness) live under
[`kustomize/base/statefulset.yaml`](kustomize/base/statefulset.yaml).

## Elyra pipeline-as-runtime validation

Use the **stdlib-only** baseline Elyra pipeline with this image as the runtime
(same digest as the workbench). Do **not** use the iris/pandas sample.

→ [tests/manual/runtime_elyra/baseline/README.md](../../../tests/manual/runtime_elyra/baseline/README.md)
(section **Universal Jupyter as runtime**).

## Qualification pointers

| Check | Where |
|-------|--------|
| Image size budget | `ci/expected-image-metadata.yaml` → `odh-workbench-jupyter-universal-cpu-py312-ubi9-n` (`size_mb`) |
| FIPS policy | [docs/fips.md](../../../docs/fips.md) — workbenches are not “Designed for FIPS”; this image excludes `py-spy`; mongocli builds with `strictfipsruntime` |
| Hermetic / SBOM / Clair / provenance | ODH Konflux PipelineRuns (below); RHOAI via midstream→downstream Konflux |
| Startup / resources | WorkbenchContainer readiness timeouts; kustomize CPU/memory requests in `kustomize/base/statefulset.yaml` |

## CI and Konflux

| Path | Detail |
|------|--------|
| ODH PR / push | `.tekton/odh-workbench-jupyter-universal-cpu-py312-c9s-*-request.yaml` / `*-push.yaml` |
| Manual PR trigger | `/build-jupyter-universal` (also `/build-konflux` / `/kfbuild-all`) |
| Hermetic | `hermetic: true`; prefetch mongocli (gomod), `prefetch-input/odh` (rpm+generic), pip from `requirements.cpu.txt` |
| Platforms | `linux/x86_64`, `arm64`, `ppc64le`, `s390x` |
| GHA matrix | `jupyter-universal-ubi9-python-3.12` (ODH + RHOAI) in `ci/cached-builds/gen_gha_matrix_jobs.py` |
| Group test | `.tekton/notebooks-group-testing-pipeline.yaml` includes deploy/test/undeploy for universal |

RHOAI Konflux PipelineRuns are synced downstream from `konflux-central` into
`red-hat-data-services/notebooks` — do not add them here.
