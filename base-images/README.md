# Base Images

Foundation layer for **ODH** (Open Data Hub) workbenches and runtimes.
All images are **CentOS Stream 9** (c9s) with **Python 3.12**.

> **RHOAI** (Red Hat OpenShift AI) workbenches and runtimes use
> **RHEL 9.6 EUS** base images from [AIPCC](https://gitlab.com/redhat/rhel-ai/core/base-images/app),
> not these c9s images.

## Layout

| Directory | Purpose |
|---|---|
| `cpu/` | CPU-only base image |
| `cuda/` | NVIDIA CUDA (12.9, 13.0) |
| `rocm/` | AMD ROCm (6.4, 7.1) |
| `build-args/` | `.conf` files with `INDEX_URL` per variant |
| `utils/` | Shared scripts: `aipcc.sh`, `dnf-helper.sh`, `fix-permissions`, `pip.conf.in`, `uv.toml.in` |
| `copr/` | Tool to rebuild Fedora SRPMs for EL9 ([README](copr/README.md)) |

## How Base Images Are Consumed

Downstream Dockerfiles reference base images via build arg:

    ARG BASE_IMAGE
    FROM ${BASE_IMAGE}

Resolved at build time by Tekton / Konflux pipelines.

## Building Locally

Base images are **not in the Makefile** -- they are built by Tekton/Konflux
pipelines only. To build locally, invoke `podman build` directly.
Build context is the **repo root** (Dockerfiles use `COPY base-images/utils/...`):

    podman build \
      --build-arg-file=base-images/build-args/cpu.conf \
      -f base-images/cpu/c9s-python-3.12/Dockerfile.cpu .

## Python Versions and RHEL Lifecycle

Red Hat ships **2 out of every 3** CPython releases in AppStream, skipping the
version released ~6 months before the next RHEL major (*3.10* was skipped for
RHEL 9, *3.13* for RHEL 10).

| RHEL | Default (full-life) | AppStream | Skipped |
|---|---|---|---|
| **9** | 3.9 | 3.11 (9.2, retires May 2026), **3.12** (9.4, retires Apr 2027) | 3.10 |
| **10** | **3.12** | *3.14 arriving via z-stream* | 3.13 |

- **Python 3.13** is EPEL-only, not in RHEL AppStream
- **Python 3.14** is in CentOS Stream 9/10 and shipping to RHEL 9.8 / 10.2

> **This repo ships Python 3.12**, aligned with both RHEL 9 AppStream
> (supported until Apr 2027) and RHEL 10 full-life. The next version to
> consider is **3.14** (3.13 was skipped). The AIPCC wheel builder already
> has CI for 3.14 ([AIPCC-8168](https://redhat.atlassian.net/browse/AIPCC-8168)).

References:
- [RHEL Application Streams Life Cycle](https://access.redhat.com/support/policy/updates/rhel-app-streams-life-cycle)
- [RHEL 9 ABI Compatibility](https://access.redhat.com/articles/rhel9-abi-compatibility)
- [RHEL Life Cycle / Errata Policy](https://access.redhat.com/support/policy/updates/errata)

## Adding a New Accelerator Version

The CUDA and ROCm Dockerfiles are adapted from upstream vendor references:

- **CUDA**: [gitlab.com/nvidia/container-images/cuda](https://gitlab.com/nvidia/container-images/cuda) (see `dist/<version>/ubi9/` for base, runtime, and cudnn stages)
- **ROCm**: [github.com/ROCm/ROCm-docker](https://github.com/ROCm/ROCm-docker) and [ROCm install docs](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/post-install.html)

Steps:

1. Copy an existing version directory (e.g. `cuda/12.9/` -> `cuda/13.1/`)
2. Update the Dockerfile stages from the upstream vendor Dockerfiles for the new SDK version
3. Update `cuda-repos/` repo files if needed (GPG keys, baseurls)
4. Create `build-args/<variant>.conf` with the correct `INDEX_URL`
5. Add Tekton pipeline YAMLs in `.tekton/`
