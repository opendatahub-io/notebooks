# Architecture

This document describes the high-level architecture of the OpenDataHub Notebooks repository.
For AI agent-specific instructions, see [AGENTS.md](AGENTS.md).
For contributing guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

## What this repo produces

The repository builds **container images** for interactive data science workbenches:
Jupyter notebooks, RStudio, and Code-Server (VS Code in the browser).
These images run on OpenShift as part of OpenDataHub (ODH) and Red Hat OpenShift AI (RHOAI).

## Image inheritance model

Images form a layered hierarchy where each level adds capabilities:

```text
Base images (cuda/, rocm/)
  └── jupyter/minimal     ← Python, JupyterLab, basic packages
        └── jupyter/datascience   ← NumPy, Pandas, SciPy, scikit-learn
              ├── jupyter/pytorch         ← PyTorch + CUDA/ROCm
              ├── jupyter/tensorflow      ← TensorFlow + CUDA
              └── jupyter/trustyai        ← TrustyAI explainability
```

Each image directory (e.g. `jupyter/minimal/ubi9-python-3.12/`) contains:
- `Dockerfile.*` — one per variant (cpu, cuda, rocm, konflux.cpu, etc.)
- `Pipfile` or `pyproject.toml` — Python dependencies
- `uv.lock.d/pylock.*.toml` — locked dependency files per variant
- `build-args/` — build argument configuration per variant

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
| `cuda/`, `rocm/` | GPU-specific configuration files, repo files, and licenses |
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
| Browser tests | `tests/browser/` | JupyterLab, Code-Server UI via Playwright | `cd tests/browser && pnpm test` |
| OpenShift tests | `tests/containers/` (marked `@openshift`) | Full pod lifecycle on a real cluster | Requires OpenShift cluster |

## Languages

- **Python** — CI scripts, tests, image dependency management
- **Go** — `scripts/buildinputs/` tool that parses Dockerfiles to extract COPY/ADD dependencies
- **TypeScript** — Browser tests (Playwright), Code-Server test models
- **Bash** — Build scripts, CI checks
- **Makefile** — Build orchestration
