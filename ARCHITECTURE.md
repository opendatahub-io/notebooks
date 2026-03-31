# Architecture

This document describes the high-level architecture of the OpenDataHub Notebooks repository.
For AI agent-specific instructions, see [AGENTS.md](AGENTS.md).
For contributing guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

## What this repo produces

The repository builds **container images** for interactive data science workbenches:
Jupyter notebooks, RStudio, and Code-Server (VS Code in the browser).
These images run on OpenShift as part of OpenDataHub (ODH) and Red Hat OpenShift AI (RHOAI).

## Image hierarchy

Images form a conceptual hierarchy. Each image is built by a standalone multi-stage
Dockerfile that pulls its parent as a `FROM` base image (not as a build-time dependency
in this repo):

```text
Base image (external or base-images/)
  └── jupyter/minimal                    ← Python, JupyterLab, basic packages
        └── jupyter/datascience          ← NumPy, Pandas, SciPy, scikit-learn
              ├── jupyter/pytorch                ← PyTorch + CUDA/ROCm
              ├── jupyter/pytorch+llmcompressor  ← PyTorch + LLM Compressor
              ├── jupyter/tensorflow             ← TensorFlow + CUDA
              ├── jupyter/trustyai               ← TrustyAI explainability
              ├── jupyter/rocm/pytorch           ← PyTorch + ROCm
              └── jupyter/rocm/tensorflow        ← TensorFlow + ROCm
```

In ODH (OpenDataHub), base images are built from `base-images/` in this repo.
In RHOAI (Red Hat OpenShift AI), base images come from the AIPCC pipeline instead.

Each image directory (e.g. `jupyter/minimal/ubi9-python-3.12/`) contains:
- `Dockerfile.*` — one per variant (cpu, cuda, rocm, konflux.cpu, etc.)
- `pyproject.toml` — Python dependencies
- `uv.lock.d/pylock.*.toml` — locked dependency files per variant
- `build-args/` — build argument configuration per variant

The `runtimes/` directory mirrors the same flavor structure (minimal, datascience, pytorch, tensorflow, etc.) for Elyra pipeline execution images.

## Key directories

| Directory | Purpose |
|-----------|---------|
| `jupyter/` | Jupyter notebook image definitions, organized by flavor and accelerator |
| `runtimes/` | Pipeline runtime images used by Elyra to execute notebook pipeline nodes |
| `codeserver/` | Code-Server (VS Code in the browser) image definitions |
| `rstudio/` | RStudio Server image definitions |
| `ci/` | CI utility scripts — Makefile helpers, PR change detection, validation, cached build logic |
| `scripts/` | Maintenance scripts — lockfile generation, CVE tracking, image analysis |
| `ntb/` | Shared Python library — string utilities, assertions, constants used across CI and tests |
| `tests/` | Test suite — unit tests, container integration tests (testcontainers), browser tests (Playwright) |
| `manifests/` | Kubernetes ImageStream manifests for ODH (`manifests/odh/`) and RHOAI (`manifests/rhoai/`) |
| `base-images/` | CUDA and ROCm GPU-accelerated base image definitions |
| `dependencies/` | Shared dependency constraints (CVE pinning) and meta packages for common dependency groups |
| `examples/` | Example JupyterLab notebooks for validating workbench functionality |
| `docs/adr/` | Architecture Decision Records |

## Build system

The `Makefile` orchestrates image builds. Each image has a make target:

```bash
make jupyter-minimal-ubi9-python-3.12       # build one image
make all-images                              # build everything
make test                                    # run quick static tests (pytest + lint)
```

The build system supports two modes:
- **ODH mode** (default): `KONFLUX=no`, uses standard Dockerfiles
- **RHOAI/Konflux mode**: `KONFLUX=yes`, uses `Dockerfile.konflux.*` variants with prefetched dependencies

## Testing layers

| Layer | Location | What it tests | How to run |
|-------|----------|---------------|-----------|
| Unit tests | `tests/`, `ntb/` | CI scripts, utilities, doctests | `make test` |
| Container tests | `tests/containers/` | Image startup, package imports, CLI tools | `pytest tests/containers --image=<img>` |
| GPU tests | `tests/containers/workbenches/` | CUDA/ROCm library loading, GPU operations | Requires GPU hardware or fake GPU setup |
| Browser tests | `tests/browser/` | JupyterLab, Code-Server UI via Playwright | `cd tests/browser && pnpm playwright test` |
| OpenShift tests | `tests/containers/` (marked `@openshift`) | Full pod lifecycle on a real cluster | Requires OpenShift cluster |

### External test suites

The images built by this repo are also tested by other projects in the OpenDataHub ecosystem:

| Suite | Framework | What it tests |
|-------|-----------|---------------|
| [odh-dashboard](https://github.com/opendatahub-io/odh-dashboard/tree/main/packages/cypress/cypress/tests/e2e/dataScienceProjects/workbenches) | Cypress (TypeScript) | Workbench creation/deletion, image selection, status transitions, storage, and RBAC via the ODH dashboard UI |
| [ods-ci](https://github.com/red-hat-data-services/ods-ci/tree/master/ods_ci/tests/Tests/0500__ide) | Robot Framework | Image spawning, GPU/CUDA validation, JupyterLab plugin consistency, Elyra pipelines, long-running stability, and specialized toolkit integration (OpenVINO, Intel AIKIT) |
| [opendatahub-tests](https://github.com/opendatahub-io/opendatahub-tests/tree/main/tests/workbenches) | Pytest (Python) | Kubernetes ImageStream health, Notebook CR spawning, Python package availability inside images, and container resource constraints |

## Integration with ODH/RHOAI platform

The workbench images are not standalone — they integrate tightly with several ODH platform components.

### Operator deployment chain

The [ODH Operator](https://github.com/opendatahub-io/opendatahub-operator/tree/main/internal/controller/components/workbenches)
deploys workbench ImageStreams to the cluster using a kustomize pipeline:

```text
manifests/*/base/params-latest.env     (image digests, nudge-updated)
manifests/*/base/params.env            (released version refs)
        ↓
kustomize configMapGenerator           → ConfigMap "notebook-image-params"
        ↓
kustomize replacements (80+ entries)   → *_PLACEHOLDER values in ImageStreams
        ↓
operator deploys to cluster            → OpenShift imports images from registry
```

The operator maps `RELATED_IMAGE_*` environment variables to params.env keys
(see [issue #2982](https://github.com/opendatahub-io/notebooks/issues/2982) for simplification plans).
Each ImageStream carries two tags: the current version (N) and the previous release (N-1).

### ODH Dashboard

The [ODH Dashboard](https://github.com/opendatahub-io/odh-dashboard) discovers workbench images via
ImageStream annotations in `manifests/*/base/`. Key annotations include `opendatahub.io/notebook-image-name`,
`opendatahub.io/notebook-image-order`, `opendatahub.io/recommended-accelerators`, and
`opendatahub.io/notebook-python-dependencies`. When launching a workbench, the dashboard injects
the `NOTEBOOK_ARGS` environment variable with OAuth proxy and configuration settings.

### Notebook controller (kubeflow)

The [ODH Notebook Controller](https://github.com/opendatahub-io/kubeflow/tree/main/components/odh-notebook-controller)
runs a mutating webhook that transforms Notebook CR pods at creation time:

1. Resolves container image from ImageStream annotations
2. Mounts CA certificate bundles at `/etc/pki/tls/custom-certs/ca-bundle.crt`
3. Mounts pipeline runtime images ConfigMap at `/opt/app-root/pipeline-runtimes/` (for Elyra)
4. Mounts DSPA connection secret at `/opt/app-root/runtimes/` (for Elyra pipeline execution)
5. Injects kube-rbac-proxy sidecar for OAuth

### Idle culling

The notebook controller's culler expects a Jupyter-compatible API at `/api/kernels/` that reports
`last_activity` timestamps and `execution_state` (busy/idle). JupyterLab provides this natively.

Code-Server and RStudio **do not** have a Jupyter-compatible API, so this repo fakes it using
a three-process stack per workbench container:

- **nginx** (port 80) — reverse proxy with custom JSON access logging for activity tracking
- **httpd** (port 8080) — Apache acting as a CGI gateway
- **bash CGI scripts** — `access.cgi` implements the `/api/kernels/` endpoint by either polling
  the IDE's heartbeat (Code-Server) or parsing nginx access logs (RStudio)

Key files:
- `codeserver/*/nginx/api/kernels/access.cgi` — polls `localhost:8888/codeserver/healthz`,
  converts heartbeat to Jupyter kernel format
- `rstudio/*/nginx/api/kernels/access.cgi` — parses nginx access logs, marks idle after
  10 minutes of inactivity
- `codeserver/*/nginx/httpconf/http.conf` — custom nginx log format producing JSON with
  `last_activity` in ISO 8601 format

This architecture is fragile and is planned for replacement with a single Go reverse proxy
that handles both traffic forwarding and activity tracking in one process.

### Elyra pipeline integration

[Elyra](https://github.com/opendatahub-io/elyra) (ODH fork) enables visual pipeline editing
in JupyterLab. The integration chain:

1. **This repo** builds runtime images (`runtimes/`) and publishes ImageStreams with
   `opendatahub.io/runtime-image: "true"` label and `opendatahub.io/runtime-image-metadata`
   annotation containing Elyra runtime configuration
2. **Notebook controller** discovers runtime ImageStreams and creates a ConfigMap,
   mounted at `/opt/app-root/pipeline-runtimes/` inside workbench pods
   ([notebook_runtime.go](https://github.com/opendatahub-io/kubeflow/blob/main/components/odh-notebook-controller/controllers/notebook_runtime.go))
3. **Notebook controller** also creates a DSPA connection secret mounted at `/opt/app-root/runtimes/`
   ([notebook_dspa_secret.go](https://github.com/opendatahub-io/kubeflow/blob/main/components/odh-notebook-controller/controllers/notebook_dspa_secret.go))
4. **`setup-elyra.sh`** (sourced at workbench startup) copies the mounted JSON configs into
   Elyra's metadata directories so pipelines can discover available runtime images and the
   Data Science Pipelines endpoint

### Security configuration sync

Several security scanning config files are synced automatically from the central
[opendatahub-io/security-config](https://github.com/opendatahub-io/security-config) repository
by the `security-config-sync[bot]`:

| File | Purpose |
|------|---------|
| `.coderabbit.yaml` | CodeRabbit review configuration (inherits org-wide settings) |
| `semgrep.yaml` | Semgrep static analysis rules (secrets detection, language-specific checks) |
| `.gitleaks.toml` | Gitleaks secret scanning configuration |
| `.gitleaksignore` | Gitleaks false-positive suppressions |

These files are **protected by an org-level push ruleset** — they cannot be modified directly
in this repo. Changes must go upstream to `security-config`. The yamllint config
(`ci/yamllint-config.yaml`) suppresses the `document-start` rule for these files since their
format is controlled externally.

## Languages

- **Python** — CI scripts, tests, image dependency management
- **Go** — `scripts/buildinputs/` tool that parses Dockerfiles to extract COPY/ADD dependencies
- **TypeScript** — Browser tests (Playwright), Code-Server test models
- **Bash** — Build scripts, CI checks
- **Makefile** — Build orchestration
