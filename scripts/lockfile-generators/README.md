# Lockfile Generators

Scripts to generate lockfiles for **generic artifacts**, **RPMs**, **npm packages**,
**pip packages**, and **Go modules (gomod)**, download the referenced packages and
support **offline** hermetic image builds via Cachi2/Hermeto.

## Why lockfiles?

Konflux requires lockfiles that pin exact package URLs and checksums so that:

- Builds are **reproducible** and **offline-capable** (no live access to upstream mirrors).
- Cachi2 (or Hermeto) prefetches everything once; the image build uses only
the cached output.

In the Tekton PipelineRun, `prefetch-input` entries tell cachi2 which lockfiles
to process and where to find them:

```yaml
# .tekton/odh-workbench-codeserver-...-pull-request.yaml (abbreviated)
- name: prefetch-input
  value:
  - path: codeserver/ubi9-python-3.12/prefetch-input/rhds  # rhoai-2.25 / downstream
    type: rpm                                              # rpms.lock.yaml
  - path: codeserver/ubi9-python-3.12/prefetch-input/rhds
    type: generic                                          # artifacts.lock.yaml
  - path: codeserver/ubi9-python-3.12
    type: pip                                              # requirements.cpu.txt
    binary:
      arch: "x86_64,aarch64,ppc64le"                      # prefetch wheels for all build platforms
    requirements_files: ["requirements.cpu.txt"]
  - path: codeserver/ubi9-python-3.12/prefetch-input/code-server/lib/vscode/extensions
    type: npm                                              # package-lock.json (many)
  - path: prefetch-input/mongocli
    type: gomod                                            # go.mod + go.sum (Go modules)
  # ... more npm entries for code-server root, build/, test/, patched lockfiles, etc.
```

All scripts must be run from the **repository root**.

---

## Python lockfiles on `rhoai-2.25`

This branch uses **two lockfile paths**. Only codeserver needs both; jupyter,
runtime, and other images use track 1 only.

| Track | Images | Command | Committed output |
| ----- | ------ | ------- | ---------------- |
| **1 — CI / online build** | All (`jupyter/`, `runtimes/`, `codeserver/`, …) | `bash ci/generate_code.sh` | `pylock.toml` in each image dir |
| **2 — Hermetic prefetch** | **codeserver only** | `prefetch-all.sh --rhds …` (or individual scripts below) | `requirements.cpu.txt`, `uv.lock.d/pylock.cpu.toml`, `prefetch-input/rhds/*.lock.yaml`, npm/RPM locks |

### Regenerating lockfiles (quick reference)

**After editing any image `pyproject.toml` (jupyter, runtime, codeserver, …):**

```bash
bash ci/generate_code.sh          # → scripts/sync-python-lockfiles.sh
git add '**/pylock.toml'
```

CI job `check-generated-code` re-runs the same command and fails on drift.

**After editing codeserver deps or prefetch inputs** (`pyproject.toml`, `rpms.in.yaml`,
`artifacts.in.yaml`, npm lockfiles under `prefetch-input/patches/`, …):

```bash
# 1. Python lock for CI (same as other images)
bash ci/generate_code.sh

# 2. Hermetic locks + optional local wheel download
uv sync && source .venv/bin/activate
git submodule update --init --recursive codeserver/ubi9-python-3.12/prefetch-input/code-server

RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/amd64 \
  ./scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --rhds
```

On Apple Silicon for local builds, use `BUILD_ARCH=linux/arm64` (must match
`gmake … BUILD_ARCH=…`).

**Commit** (do not commit `cachi2/output/`):

- `codeserver/ubi9-python-3.12/pylock.toml`
- `codeserver/ubi9-python-3.12/uv.lock.d/pylock.cpu.toml`
- `codeserver/ubi9-python-3.12/requirements.cpu.txt`
- `codeserver/ubi9-python-3.12/prefetch-input/rhds/rpms.lock.yaml` (when RPM inputs changed)
- `codeserver/ubi9-python-3.12/prefetch-input/rhds/artifacts.lock.yaml` (when artifact inputs changed)

**Regenerate one dependency type only** (debugging):

```bash
./scripts/lockfile-generators/create-requirements-lockfile.sh \
  --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml

./scripts/lockfile-generators/create-rpm-lockfile.sh \
  --rpm-input codeserver/ubi9-python-3.12/prefetch-input/rhds/rpms.in.yaml

python3 scripts/lockfile-generators/create-artifact-lockfile.py \
  --artifact-input codeserver/ubi9-python-3.12/prefetch-input/rhds/artifacts.in.yaml

./scripts/lockfile-generators/download-npm.sh \
  --tekton-file .tekton/odh-workbench-codeserver-datascience-cpu-py312-pull-request.yaml
```

Add `--download` to pip/RPM scripts when you need wheels/RPMs under `cachi2/output/`
for a local `gmake codeserver-…` build. Konflux CI prefetches from committed
lockfiles and does not need `--download`.

### rhoai-2.25 codeserver pip strategy

On **downstream/main (3.5)**, codeserver locks against the Red Hat PyPI index via
`pylocks_generator.py rh-index` and `build-args/konflux.cpu.conf`.

On **rhoai-2.25**, codeserver is listed in `PUBLIC_INDEX_PROJECTS` inside
`create-requirements-lockfile.sh`:

1. **`pylock.toml`** — locked against **public PyPI** (same as `sync-python-lockfiles.sh`;
   keeps `check-generated-code` green).
2. **`uv.lock.d/pylock.cpu.toml`** — copy of `pylock.toml`, then patched with RH wheels
   from `uv.lock.d/rh-wheel-only.ref.toml` (ppc64le/s390x native deps, `uv`/`ripgrep`
   on all arches).
3. **`requirements.cpu.txt`** — pip/cachi2 format with `--hash` lines for Hermeto prefetch.

RPM locks on rhoai-2.25 use **`prefetch-input/rhds/`** with **public UBI + CentOS Stream**
repos (no RHEL subscription). Pass `--rhds` to `prefetch-all.sh`; subscription
(`--activation-key` / `--org`) is only needed if you switch `rpms.in.yaml` back to
`/etc/yum.repos.d/redhat.repo`.

See also [codeserver/ubi9-python-3.12/README.md](../../codeserver/ubi9-python-3.12/README.md).

---

## Orchestrator `prefetch-all.sh`

**For most local and CI use, this is the main script you need to run.**

`prefetch-all.sh` orchestrates all five lockfile generators in the correct
order, downloading dependencies into `cachi2/output/deps/`. After running it,
the Makefile auto-detects `cachi2/output/` and passes `--volume` to
`podman build`.

```bash
# Upstream ODH (default variant, CentOS Stream base, no subscription):
RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/arm64 \
  scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12

# rhoai-2.25 / downstream RHDS (public UBI + CentOS repos; no subscription):
RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/arm64 \
  scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --rhds

# RHOAI 3.5+ with RHEL subscription RPMs (optional; only if rpms.in.yaml uses redhat.repo):
RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/arm64 \
  scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --rhds \
    --activation-key my-key --org my-org

# Custom flavor:
RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/arm64 \
  scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --flavor cuda
```

Then build with make:

```bash
# On macOS use gmake
gmake codeserver-ubi9-python-3.12 BUILD_ARCH=linux/arm64 PUSH_IMAGES=no
```

See [Local development](#local-development) for prerequisites, verification steps,
and a full walkthrough (including jupyter datascience).

### Options


| Option                 | Description                                                            |
| ---------------------- | ---------------------------------------------------------------------- |
| `--component-dir DIR`  | Component directory (required), e.g. `codeserver/ubi9-python-3.12`     |
| `--rhds`               | Use downstream (RHDS) lockfiles instead of upstream (ODH, the default) |
| `--flavor NAME`        | Lock file flavor (default: `cpu`)                                      |
| `--activation-key KEY` | Red Hat activation key for RHEL RPMs (optional)                        |
| `--org ORG`            | Red Hat organization ID for RHEL RPMs (optional)                       |


### What it does


| Step                 | Condition                                                   | Script called                                                                         |
| -------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| 1. Generic artifacts | `prefetch-input/<variant>/artifacts.in.yaml` exists         | `create-artifact-lockfile.py`                                                         |
| 2. Pip wheels        | `pyproject.toml` exists in component dir                    | `create-requirements-lockfile.sh --download`                                          |
| 3. NPM packages      | Tekton PipelineRun found for component (see below)          | `download-npm.sh --tekton-file`                                                       |
| 4. RPMs              | `prefetch-input/<variant>/rpms.in.yaml` exists              | `hermeto-fetch-rpm.sh` (if lockfile committed) or `create-rpm-lockfile.sh --download` |
| 5. Go modules        | Tekton file has `prefetch-input` entries with `type: gomod` | `create-go-lockfile.sh --tekton-file`                                                 |


**Variant directory:** Lockfiles live under `prefetch-input/odh/` (upstream) or
`prefetch-input/rhds/` (downstream). If that directory is missing, steps 1 and 4
are skipped; steps 2 (pip), 3 (npm), and 5 (gomod) still run when their inputs exist
(`pyproject.toml`, a Tekton file for the component, or gomod-type prefetch-input).

**Step 3 (NPM):** The script finds the Tekton file automatically via
`find_tekton_yaml`: it looks for a `.tekton/*pull-request*.yaml` whose
`dockerfile` param matches this component (`COMPONENT_DIR/Dockerfile.konflux.*`)
for both ODH and RHDS variants.
If no Tekton file is found, npm is skipped. If the Tekton file has no
`npm`-type `prefetch-input` entries, `download-npm.sh` exits successfully
(nothing to download).

**Step 5 (Go modules):** Uses the same Tekton file as step 3. If the file has
one or more `prefetch-input` entries with `type: gomod` and a `path` to a
directory containing `go.mod` and `go.sum`, `create-go-lockfile.sh` runs Hermeto
to fetch Go modules into `cachi2/output/deps/gomod/`. If there are no gomod
entries, the step is skipped.

Steps are skipped if their input files don't exist. For RPMs, if
`rpms.lock.yaml` is already committed, it downloads directly (skipping
lockfile regeneration) — this avoids cross-platform issues on arm64 CI runners.

### GitHub Actions integration

The GHA workflow template (`.github/workflows/build-notebooks-TEMPLATE.yaml`)
derives the component directory from the **Makefile** (dry-run of the build
target, parsing `#*# Image build directory: <...>`), so it works for all image
targets (codeserver, jupyter-*, runtime-*, base-images-*). Prefetch
runs when `COMPONENT_DIR/prefetch-input` exists; otherwise the step is skipped.
After the build, container tests run (e.g. `tests/containers` with pytest);
image metadata is read from both Docker `Config` and `ContainerConfig` so
labels work when the daemon is Podman (see
[tests/containers/docs/github-vs-local-image-metadata.md](../../tests/containers/docs/github-vs-local-image-metadata.md)).

**uv version:** Image locks use the exact version in `dependencies/uv-image-lock-version`
via the repo root `./uv` wrapper (e.g. `0.11.18`). `make refresh-lock-files` and
`create-requirements-lockfile.sh` invoke `./uv` automatically.

---

## Local development

GitHub Actions sets `RELEASE_PYTHON_VERSION` and `BUILD_ARCH` on the job **before**
`prefetch-all.sh` runs (see `.github/workflows/build-notebooks-TEMPLATE.yaml`).
You must set the same variables locally or pip prefetch can silently skip wheels
that the image still requires at build time.


| Variable                 | Purpose                                                                                     | Example                           |
| ------------------------ | ------------------------------------------------------------------------------------------- | --------------------------------- |
| `RELEASE_PYTHON_VERSION` | Python version for **pip marker filtering** during prefetch (image Python, not host Python) | `3.12` for `*-python-3.12` images |
| `BUILD_ARCH`             | OCI platform for pip wheels and RPM repos                                                   | `linux/arm64`, `linux/amd64`      |


The repo root `.venv` (from `uv sync`) is **Python 3.14** — used to run prefetch
scripts (`pyyaml`, `packaging`, `uv`, etc.). Image wheels are still resolved for
**3.12** via `RELEASE_PYTHON_VERSION`.

### Prerequisites

Run from the **repository root**.

- **podman** (or docker) and **gmake** on macOS
- **uv**, **wget**, **jq**, **hermeto** (RPM download), **yq** (optional; npm step)
- **Git submodules** required by the component (e.g. `prefetch-input/mongocli` for
jupyter datascience):
  ```bash
  git submodule update --init --recursive prefetch-input/mongocli
  ```

### Setup and prefetch

```bash
# 1. Dev venv (runs prefetch scripts — 3.14 is fine here)
uv sync
source .venv/bin/activate

# 2. Optional: clear pip cache when switching arch or fixing a bad prefetch
rm -rf cachi2/output/deps/pip

# 3. Prefetch — BUILD_ARCH must match the platform you will build
RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/arm64 \
  ./scripts/lockfile-generators/prefetch-all.sh \
    --component-dir jupyter/datascience/ubi9-python-3.12
```

Use `BUILD_ARCH=linux/amd64` when building for x86_64. Prefetch arch and build
arch must match (Makefile mounts `cachi2/output/deps/rpm/<arch>/repos.d/`).

### Build

```bash
gmake jupyter-datascience-ubi9-python-3.12 \
  BUILD_ARCH=linux/arm64 \
  PUSH_IMAGES=no
```

The Makefile auto-mounts `cachi2/output/` when prefetch exists. See
[Appendix: Local podman build](#appendix-local-podman-build) for manual
`podman build` details.

---

## Individual tools

The six options below can be used for hermetic builds. Scripts 1–5 can also be
run individually for debugging or partial updates; `prefetch-all.sh` calls them
internally. Option 6 (Git submodule) is a manual setup.


| #   | Type               | Main script                                                                              | What it generates                                     |
| --- | ------------------ | ---------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| 1   | Generic            | [create-artifact-lockfile.py](#1-generic-artifacts--create-artifact-lockfilepy)          | `artifacts.lock.yaml`                                 |
| 2   | RPM                | [create-rpm-lockfile.sh](#2-rpm-packages--create-rpm-lockfilesh)                         | `rpms.lock.yaml`                                      |
| 3   | npm                | [download-npm.sh](#3-npm-packages--download-npmsh)                                       | Downloaded tarballs in `cachi2/output/deps/npm/`      |
| 4   | pip (RHOAI)        | [create-requirements-lockfile.sh](#4-pip-packages-rhoai--create-requirements-lockfilesh) | `pylock.<flavor>.toml` + `requirements.<flavor>.txt`  |
| 5   | Go modules (gomod) | [create-go-lockfile.sh](#5-go-modules--create-go-lockfilesh)                             | Go module cache in `cachi2/output/deps/gomod/`        |
| 6   | Git submodule      | (manual setup)                                                                           | [Pinned repo under prefetch-input/](#6-git-submodule) |


### Helper scripts (used internally by the main tools)


| Helper                                          | Used by          | Purpose                                                                                                                                                                                                                                  |
| ----------------------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `helpers/pylock-to-requirements.py`             | pip              | Convert `pylock.<flavor>.toml` (PEP 751) to pip-compatible `requirements.<flavor>.txt` with `--hash` lines.                                                                                                                              |
| `helpers/download-pip-packages.py`              | pip              | Standalone pip downloader: downloads wheels/sdists from a `requirements.txt` (with `--hash` lines) into `cachi2/output/deps/pip/`. Not called by `create-requirements-lockfile.sh` (which has its own inline download from pylock.toml). |
| `helpers/hermeto-fetch-rpm.sh`                  | RPM              | Download RPMs from `rpms.lock.yaml` using [Hermeto](https://github.com/hermetoproject/hermeto) in a container. Handles RHEL entitlement cert extraction for `cdn.redhat.com` auth. Called by `create-rpm-lockfile.sh --download`.        |
| `helpers/hermeto-fetch-npm.sh`                  | npm              | Alternative npm fetcher using [Hermeto](https://github.com/hermetoproject/hermeto) in a container.                                                                                                                                       |
| `helpers/hermeto-fetch-gomod.sh`                | Go modules       | Fetches Go dependencies from a directory with `go.mod`/`go.sum` using [Hermeto](https://github.com/hermetoproject/hermeto) in a container. Output: `cachi2/output/deps/gomod/`. Called by `create-go-lockfile.sh`.                       |
| `rewrite-npm-urls.sh`                           | npm (Dockerfile) | Rewrites `resolved` URLs in `package-lock.json` / `package.json` to `file:///cachi2/output/deps/npm/`.                                                                                                                                   |
| `helpers/rpm-lockfile-generate.sh`              | RPM              | Runs `rpm-lockfile-prototype` inside the lockfile container. Not for direct host use.                                                                                                                                                    |
| `Dockerfile.rpm-lockfile`                       | RPM              | Builds the container image for `create-rpm-lockfile.sh` (includes `rpm-lockfile-prototype` v0.20.0). Applies patches from `patches/` at build time. Does not install internal-only corp repos. |
| `patches/apply-patches.sh`                      | RPM (build)      | Applies local patches to pip-installed packages inside the `notebook-rpm-lockfile` container during `docker build`.                                                                                                                      |
| `patches/rpm-lockfile-prototype-dnf-conf.patch` | RPM (build)      | Adds `RPM_LOCKFILE_MODULE_PLATFORM_ID` and `RPM_LOCKFILE_SKIP_UNAVAILABLE` env var support to `rpm-lockfile-prototype`'s DNF config.                                                                                                     |


---

## Quick start — codeserver example

The fastest way to prefetch everything and build:

```bash
uv sync && source .venv/bin/activate
git submodule update --init --recursive codeserver/ubi9-python-3.12/prefetch-input/code-server

RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/arm64 \
  scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --rhds

gmake codeserver-ubi9-python-3.12 BUILD_ARCH=linux/arm64 PUSH_IMAGES=no
```

See [Local development](#local-development) for prerequisites and troubleshooting.

### Alternative: run each generator individually

If you need to regenerate only one dependency type, or for debugging:

```bash
# 1. Generic artifacts (GPG keys, VS Code .vsix, etc.)
python3 scripts/lockfile-generators/create-artifact-lockfile.py \
    --artifact-input codeserver/ubi9-python-3.12/prefetch-input/rhds/artifacts.in.yaml

# 2. RPM packages — lockfile + download for local testing
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/rhds/rpms.in.yaml --download

# 3. npm packages (code-server + VSCode extensions)
./scripts/lockfile-generators/download-npm.sh \
    --tekton-file .tekton/odh-workbench-codeserver-datascience-cpu-py312-pull-request.yaml

# 4. pip packages — public PyPI lock + RH wheel patch + requirements.cpu.txt
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --download

# 5. Go modules (e.g. mongocli) — from Tekton file or single directory
./scripts/lockfile-generators/create-go-lockfile.sh \
    --tekton-file .tekton/odh-workbench-jupyter-pytorch-llmcompressor-cuda-py312-ubi9-odh-main-pull-request.yaml
# Or a single directory with go.mod + go.sum:
./scripts/lockfile-generators/create-go-lockfile.sh \
    --prefetch-dir prefetch-input/mongocli
```

> **Note:** The `--download` flag (and `download-npm.sh`) fetches packages into
> `cachi2/output/deps/` for **local development and testing with podman**.
> In Konflux CI, cachi2 handles all prefetching automatically from the lockfiles —
> you never need `--download` there.

After running these, the generated files are:

```
codeserver/ubi9-python-3.12/
├── pylock.toml                               # CI / check-generated-code (public PyPI)
├── requirements.cpu.txt                      # pinned pip packages for cachi2 prefetch
├── uv.lock.d/
│   ├── pylock.cpu.toml                       # hermetic install (RH-wheel patched copy)
│   └── rh-wheel-only.ref.toml                # RH wheel URLs for ppc64le/s390x overlay
└── prefetch-input/
    ├── repos/                                # shared DNF repo definitions (ubi, centos, epel)
    ├── odh/                                  # upstream (ODH) lockfiles — reference for midstream
    ├── rhds/                                 # rhoai-2.25 / downstream lockfiles (use --rhds)
    │   ├── artifacts.in.yaml
    │   ├── artifacts.lock.yaml
    │   ├── rpms.in.yaml
    │   └── rpms.lock.yaml
    ├── code-server/                          # git submodule (shared)
    └── patches/                              # patch files (shared)

cachi2/output/deps/
├── generic/    # GPG keys, .vsix, etc.
├── rpm/        # downloaded RPMs + repodata/
├── npm/        # downloaded npm tarballs
├── pip/        # downloaded Python wheels/sdists
└── gomod/      # Go module cache (from go.mod/go.sum via Hermeto)
```

---

## File format templates

This section shows abbreviated examples of each input and output file format.
Real files are much larger — these samples show just enough entries to illustrate
the structure and field names.

### Generic artifacts

**Input — `artifacts.in.yaml`**

```yaml
---
# artifacts.in.yaml - Generic (non-RPM, non-pip) artifacts to prefetch
#
# URLs are downloaded to /cachi2/output/deps/generic/<filename>.
# The lock file (artifacts.lock.yaml) is auto-generated with sha256 checksums.

input:
    # GPG keys for verifying prefetched RPM packages
    - url: https://dl.fedoraproject.org/pub/epel/RPM-GPG-KEY-EPEL-9

    # OpenShift oc client (one per arch) — optional; codeserver uses openshift-clients RPM in rpms.in.yaml instead
    # - url: https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-client-linux.tar.gz
    #   filename: openshift-client-linux-x86_64.tar.gz

    # VSCode marketplace extensions
    - url: https://github.com/microsoft/vscode-js-debug/releases/download/v1.105.0/ms-vscode.js-debug.1.105.0.vsix
      filename: ms-vscode.js-debug.1.105.0.vsix
```

**Output — `artifacts.lock.yaml`** (auto-generated, do not edit)

```yaml
---
metadata:
  version: '1.0'
artifacts:
  - download_url: https://dl.fedoraproject.org/pub/epel/RPM-GPG-KEY-EPEL-9
    checksum: sha256:fcf0eab4f05a1c0de6363ac4b707600a27a9d774e9b491059e59e6921b255a84
    filename: RPM-GPG-KEY-EPEL-9
  - download_url: https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-client-linux.tar.gz
    checksum: sha256:735b43f9ae4ffe8f1777b13e23d691540f51dcbe18ac73ab058754d42abfb4b2
    filename: openshift-client-linux-x86_64.tar.gz
  # ... one entry per input URL, in the same order ...
```

### RPM packages

**Input — `rpms.in.yaml`**

```yaml
---
# rpms.in.yaml - RPM packages to prefetch for hermetic build
#
# Lists package names (not versions). The lock file generator resolves exact
# versions and URLs for each architecture from the configured repos.

contentOrigin:
  repofiles:
    # Pick one set of repos (can't mix subscription-manager and community repos):
    # Option 1: registered with subscription-manager
    # - /etc/yum.repos.d/redhat.repo
    # Option 2: no subscription-manager
    - ubi.repo
context:
  bare: true

arches:
  - x86_64
  - aarch64
  - ppc64le

# Enable module streams needed for specific packages
moduleEnable: [nodejs:22]

packages:
  # Build tools
  - gcc-toolset-14
  - gcc-toolset-14-gcc
  - gcc-toolset-14-gcc-c++
  - gcc-toolset-14-gcc-gfortran
  - libtool

  # Node.js (from module stream)
  - nodejs-devel
  - npm
```

**Output — `rpms.lock.yaml`** (auto-generated, do not edit)

```yaml
---
lockfileVersion: 1
lockfileVendor: redhat
arches:
- arch: aarch64
  packages:
  - url: http://mirror.its.umich.edu/epel/9/Everything/aarch64/Packages/l/libsodium-1.0.18-9.el9.aarch64.rpm
    repoid: epel
    size: 121734
    checksum: sha256:737d0a7d1667aab7a703344d550994b94c154c4b69c4affbbd624d5fc9c57075
    name: libsodium
    evr: 1.0.18-9.el9
    sourcerpm: libsodium-1.0.18-9.el9.src.rpm
  # ... hundreds more per arch ...

- arch: ppc64le
  packages:
  - url: http://mirror.its.umich.edu/epel/9/Everything/ppc64le/Packages/l/libsodium-1.0.18-9.el9.ppc64le.rpm
    repoid: epel
    size: 134608
    checksum: sha256:abc123...
    name: libsodium
    evr: 1.0.18-9.el9
    sourcerpm: libsodium-1.0.18-9.el9.src.rpm
  # ...

- arch: x86_64
  packages:
  # ...
```

### npm packages

The input is a standard `package-lock.json` (generated by `npm install`). No custom
format is needed — the script extracts `resolved` URLs directly from it. See the
[npm documentation](https://docs.npmjs.com/cli/v10/configuring-npm/package-lock-json)
for the `package-lock.json` format.

### pip packages (RHOAI)

The input is a standard `pyproject.toml` following
[PEP 621](https://peps.python.org/pep-0621/). List your dependencies under
`[project] dependencies` as you normally would — no custom format is required.
The script uses `pylocks_generator.sh` (which calls `uv pip compile`) to resolve
versions and generate the lock files (`pylock.<flavor>.toml` and
`requirements.<flavor>.txt`).

---

## 1. Generic artifacts — `create-artifact-lockfile.py`

Reads `artifacts.in.yaml`, downloads each artifact (or uses the existing cache
under `cachi2/output/deps/generic/`), computes SHA-256, and writes
`artifacts.lock.yaml` in the same directory.  Duplicate filenames are skipped.
The downloaded files are used for **local testing with podman**; in Konflux CI,
cachi2 prefetches them automatically from `artifacts.lock.yaml`.

**Typical artifacts:** GPG keys, X.org source tarballs (libxkbfile, util-macros),
Node.js/Electron headers, nfpm RPMs, Playwright Chromium, VS Code marketplace
extensions (.vsix). For codeserver, ripgrep is supplied via the RHOAI Python
wheel (deps/pip) and the `oc` client via the openshift-clients RPM (deps/rpm);
they are not in generic artifacts.

### Requirements

Python 3, PyYAML, `wget`.

### Usage

```bash
python3 scripts/lockfile-generators/create-artifact-lockfile.py \
    --artifact-input path/to/artifacts.in.yaml
```

### Example (codeserver)

```bash
python3 scripts/lockfile-generators/create-artifact-lockfile.py \
    --artifact-input codeserver/ubi9-python-3.12/prefetch-input/odh/artifacts.in.yaml
```

### Input format (`artifacts.in.yaml`)

Each entry under the `input:` key can have:


| Field      | Required | Description                                                                 |
| ---------- | -------- | --------------------------------------------------------------------------- |
| `url`      | yes      | The URL to download.                                                        |
| `filename` | no       | Override the filename (default: extracted from URL).                        |
| `checksum` | no       | Expected SHA-256 checksum (validated if present; accepts `sha256:` prefix). |


---

## 2. RPM packages — `create-rpm-lockfile.sh`

Builds the `notebook-rpm-lockfile` container image (from `Dockerfile.rpm-lockfile`),
runs it with the repository mounted, and executes `rpm-lockfile-prototype` against
`rpms.in.yaml` to produce `rpms.lock.yaml` — exact RPM URLs and checksums for
each architecture listed in `rpms.in.yaml` (e.g. x86_64, aarch64, ppc64le).

With `--download`, it also calls `helpers/hermeto-fetch-rpm.sh` to fetch all RPMs
into `cachi2/output/deps/rpm/` and generate DNF repo metadata.  This is for **local
testing with podman** — in Konflux CI, cachi2 prefetches RPMs automatically.
When a RHEL subscription is active (`--activation-key` / `--org`), entitlement
certs are extracted from the lockfile container and passed to Hermeto for
`cdn.redhat.com` authentication.

**Base image selection:** With `--activation-key` and `--org`, the container uses
Red Hat UBI9 with subscription-manager registration and release pinning.
Otherwise it falls back to the ODH base image (CentOS Stream).

### Requirements

`podman`.

### Usage

```bash
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --rpm-input path/to/rpms.in.yaml \
    [--activation-key VALUE] [--org VALUE] [--download]
```

### Options


| Option                   | Description                                                                                                                       |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `--rpm-input FILE`       | Path to `rpms.in.yaml` (required).                                                                                                |
| `--activation-key VALUE` | Red Hat activation key for subscription-manager (optional).                                                                       |
| `--org VALUE`            | Red Hat organization ID for subscription-manager (optional).                                                                      |
| `--download`             | After generating the lockfile, fetch RPMs and create DNF repo metadata (for local testing with podman; not needed in Konflux CI). |


### Example (codeserver)

```bash
# Generate lockfile only — upstream (ODH, no Red Hat subscription)
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/odh/rpms.in.yaml

# Generate lockfile + download RPMs + create repo metadata
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/odh/rpms.in.yaml --download

# Downstream (RHDS) with Red Hat subscription
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --activation-key my-key --org my-org \
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/rhds/rpms.in.yaml --download
```

### Helper: `helpers/hermeto-fetch-rpm.sh`

Downloads RPMs from `rpms.lock.yaml` using
[Hermeto](https://github.com/hermetoproject/hermeto) in a container and generates
repo metadata.  This is the default downloader called by
`create-rpm-lockfile.sh --download`.  When entitlement certs are needed for `cdn.redhat.com`, the helper resolves
them in order: (1) `entitlement/` directory if present (GHA subscription step),
(2) explicit `--cert-dir` with pre-extracted PEM files, (3) `--activation-key`
and `--org` to register a temporary UBI container and extract fresh certs.

```bash
# Called automatically by create-rpm-lockfile.sh --download, but can also run standalone:
./scripts/lockfile-generators/helpers/hermeto-fetch-rpm.sh \
    --prefetch-dir codeserver/ubi9-python-3.12/prefetch-input

# With RHEL entitlement certs:
./scripts/lockfile-generators/helpers/hermeto-fetch-rpm.sh \
    --prefetch-dir codeserver/ubi9-python-3.12/prefetch-input \
    --activation-key my-key --org my-org
```

**Requirements:** `podman`, network access.

### Helper: `helpers/rpm-lockfile-generate.sh`

Invoked **inside** the `notebook-rpm-lockfile` container by `create-rpm-lockfile.sh`.
Not for direct host use.  Steps:

1. Parse the `prefetch-input` directory path from arguments.
2. Detect OS and `subscription-manager` registration status.
3. If RHEL is registered, enable `/etc/yum.repos.d/redhat.repo` in `rpms.in.yaml`.
4. Run `rpm-lockfile-prototype rpms.in.yaml` to generate `rpms.lock.yaml`.

---

## 3. npm packages — `download-npm.sh`

> **Applicability:** Only use this for images that download/install Node.js/npm
> packages during their build (for example code-server images). Many `jupyter/`*
> images do not install npm dependencies, so this cmd may not apply.

Extracts `resolved` http(s) URLs from `package-lock.json` files with `jq`, then
downloads each tarball into `cachi2/output/deps/npm/`.  This is for **local
testing with podman** — in Konflux CI, cachi2 prefetches npm packages
automatically from the `package-lock.json` files.

Scoped packages (e.g. `@types/node`) are saved as `scope-filename` to avoid
collisions.  Files that already exist are skipped.

**Two modes:**

- `--lock-file <path>` — process a single `package-lock.json`.
- `--tekton-file <path>` — parse a Tekton PipelineRun YAML to discover all
`npm`-type `prefetch-input` paths, then process every `package-lock.json`
found under them. If the file has **no** `npm`-type entries, the script
exits 0 (nothing to download) instead of erroring.

Both flags can be combined.  URLs that are already local (`file:///cachi2/...`)
are automatically skipped.

### Requirements

`jq`, `wget`.  `yq` required for `--tekton-file` mode.

### Usage

```bash
./scripts/lockfile-generators/download-npm.sh --lock-file path/to/package-lock.json
./scripts/lockfile-generators/download-npm.sh --tekton-file path/to/pipeline-run.yaml
```

### Example (codeserver)

```bash
# Download all npm packages referenced by the codeserver Tekton PipelineRun
# (code-server root, lib/vscode, all VSCode extensions, patched lockfiles, etc.)
./scripts/lockfile-generators/download-npm.sh \
    --tekton-file .tekton/odh-workbench-codeserver-datascience-cpu-py312-ubi9-pull-request.yaml

# Or download from a single lockfile
./scripts/lockfile-generators/download-npm.sh \
    --lock-file codeserver/ubi9-python-3.12/prefetch-input/code-server/package-lock.json
```

### Helper: `helpers/hermeto-fetch-npm.sh`

Alternative to `download-npm.sh` that uses the
[Hermeto Project](https://github.com/hermetoproject/hermeto) tool in a container.
Hermeto fetches dependencies **per source directory**, then the script merges all
results into one output directory using `rsync`.  Edit the `sources` array in the
script to choose which directories to fetch.

**Requirements:** `podman`, network access.

### Helper: `rewrite-npm-urls.sh`

Rewrites all `resolved` URLs in `package-lock.json` and `package.json` files
to point to the local cachi2 offline cache (`file:///cachi2/output/deps/npm/`).

Handles four URL types (in order):

1. **HTTPS registry URLs** — `https://registry.npmjs.org/[@scope/]pkg/-/file.tgz`
  → `file:///cachi2/output/deps/npm/[scope-]file.tgz`
2. **git+ssh:// URLs** — `git+ssh://git@github.com/owner/repo.git#hash`
  → `file:///cachi2/output/deps/npm/owner-repo-hash.tgz`
3. **git+https:// URLs** — same as above but with https protocol.
4. **GitHub shortname refs** — `owner/repo#ref` in dependency values
  → `file:///cachi2/output/deps/npm/owner-repo-ref.tgz`

Also strips integrity hashes for git-resolved dependencies (tarballs from
GitHub archives differ from npm-packed tarballs, so the original integrity
hash won't match).

Called during the Dockerfile build to make `npm ci` install from the
local cachi2 cache instead of the network.

```bash
# Process a specific directory
./scripts/lockfile-generators/rewrite-npm-urls.sh prefetch-input/code-server
```

**Requirements:** `perl`.

---

## 4. pip packages — `create-requirements-lockfile.sh`

Generates hermetic pip lock artifacts from `pyproject.toml`, then converts them
to a pip-compatible `requirements.<flavor>.txt` for Cachi2/Hermeto prefetch.

### Index modes

The script picks a mode from `PUBLIC_INDEX_PROJECTS` in the script itself
(currently `codeserver/ubi9-python-3.12` on rhoai-2.25):

| Mode | When | Lock output | CI check |
| ---- | ---- | ----------- | -------- |
| **`public-index`** | Project dir listed in `PUBLIC_INDEX_PROJECTS` | `pylock.toml` + copy to `uv.lock.d/pylock.<flavor>.toml` | Matches `bash ci/generate_code.sh` / `sync-python-lockfiles.sh` |
| **`rh-index`** | All other hermetic components (downstream 3.5+) | `uv.lock.d/pylock.<flavor>.toml` only | Uses `scripts/pylocks_generator.py` + RH index from `build-args/konflux.<flavor>.conf` |

### Why RH wheels on rhoai-2.25 codeserver?

Public PyPI does not publish pre-built manylinux wheels for **ppc64le** and
**s390x** for many data-science packages (numpy, scipy, pandas, pyarrow, …).
Red Hat publishes architecture-specific wheels on the RH index.

On rhoai-2.25, codeserver locks against **public PyPI first** (for CI parity),
then **`patch-rh-wheel-only-packages.py`** merges/replaces selected packages in
`uv.lock.d/pylock.cpu.toml` using `uv.lock.d/rh-wheel-only.ref.toml`. That
patched file drives `requirements.cpu.txt` and Hermeto prefetch — without
changing the committed root `pylock.toml` that `check-generated-code` validates.

On downstream/main (3.5), the same script uses **`rh-index`** end-to-end instead
of the public-index + patch overlay.

### How it works

The script performs these steps:

1. **Generate pylock** — `public-index`: same `uv pip compile` as
   `sync-python-lockfiles.sh` → `pylock.toml`, then copy to
   `uv.lock.d/pylock.<flavor>.toml`. `rh-index`: `scripts/pylocks_generator.py`
   against the RH index from `build-args/konflux.<flavor>.conf`.
2. **Patch RH wheels** (when `uv.lock.d/rh-wheel-only.ref.toml` exists) —
   replace `uv`/`ripgrep`; merge BE RH wheels for ppc64le/s390x-only packages.
3. **Convert** (`helpers/pylock-to-requirements.py`) — `requirements.<flavor>.txt`
   with `--index-url` and `--hash=sha256:…` lines for cachi2 prefetch.
4. **Download** (optional, `--download`) — wheels into `cachi2/output/deps/pip/`
   for local podman builds. Not used in Konflux CI.

### Requirements

`uv` (Python package manager/resolver).

### Usage

```bash
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml path/to/pyproject.toml \
    [--flavor NAME] [--download]
```

### Options


| Option                  | Description                                                                                                                                                                                                          |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--pyproject-toml FILE` | Path to `pyproject.toml` (required). Output files are written to the same directory.                                                                                                                                 |
| `--flavor NAME`         | Lock file flavor (default: `cpu`). Must match a `Dockerfile.<flavor>` and `build-args/<flavor>.conf` in the project directory. Determines output filenames (`pylock.<flavor>.toml` and `requirements.<flavor>.txt`). |
| `--download`            | After generating the lock, download all wheels into `cachi2/output/deps/pip/` (for local testing with podman; not needed in Konflux CI).                                                                             |


### Example (codeserver on rhoai-2.25)

```bash
# Regenerate committed lockfiles (no local wheel download)
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml

# Same + download wheels for local podman build
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --download
```

This command:

1. Regenerates `pylock.toml` from public PyPI (same as `ci/generate_code.sh`).
2. Copies to `uv.lock.d/pylock.cpu.toml` and applies `rh-wheel-only.ref.toml` patches.
3. Writes `requirements.cpu.txt` (with `--hash` lines).
4. With `--download`, fetches wheels into `cachi2/output/deps/pip/`.

```bash
# Generate pylock + requirements.cpu.txt only (no download)
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml

# Custom flavor (e.g. cuda — requires Dockerfile.cuda and build-args/cuda.conf)
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml \
    --flavor cuda
```

### Helper: `helpers/download-pip-packages.py`

Standalone pip downloader — downloads wheels/sdists from a
`requirements.<flavor>.txt` that contains `--hash=sha256:…` lines.  Resolves
download URLs from PyPI (JSON API) or a PEP 503 simple index (auto-detected
from `--index-url` in the file, e.g. RHOAI).  Skips files that already exist;
always verifies sha256 checksums.  Windows, macOS, and iOS wheels are
automatically excluded when downloading from PyPI.

This is the **local-development equivalent** of what cachi2 does for pip
dependencies in Konflux CI.  The downloaded wheels populate
`cachi2/output/deps/pip/` so that podman builds can install packages with
`--no-index --find-links`.

Note: `create-requirements-lockfile.sh --download` has its own inline download
step that works directly from `pylock.toml` URLs.  This script is a standalone
alternative that works from `requirements.txt` instead.

```bash
python3 scripts/lockfile-generators/helpers/download-pip-packages.py \
    codeserver/ubi9-python-3.12/requirements.cpu.txt

# Custom output directory:
python3 scripts/lockfile-generators/helpers/download-pip-packages.py \
    -o /tmp/my-wheels codeserver/ubi9-python-3.12/requirements.cpu.txt
```

**Requirements:** Python 3, `wget`.

---

## 5. Go modules — `create-go-lockfile.sh`

Prefetches Go dependencies for hermetic builds. Go modules are pinned in
`go.sum` (no separate lockfile). The script discovers `gomod`-type
`prefetch-input` paths from a Tekton PipelineRun YAML or a single
`--prefetch-dir`, then runs [Hermeto](https://github.com/hermetoproject/hermeto)
`fetch-deps` for each directory that contains `go.mod` and `go.sum`. Output is
written to `cachi2/output/deps/gomod/` so Dockerfiles can build Go code offline
(e.g. `GOPROXY=file:///cachi2/output/deps/gomod`).

**Typical use:** Images that build Go binaries (e.g. mongocli) during the
Docker build. The Tekton file lists the path to the Go module under
`prefetch-input` with `type: gomod`; the source is usually a git submodule under
`prefetch-input/` (e.g. `jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli`).

### Requirements

`podman`, `jq`. `yq` required when using `--tekton-file`.

### Usage

```bash
# From Tekton: discover all gomod prefetch-input paths and fetch each
./scripts/lockfile-generators/create-go-lockfile.sh --tekton-file .tekton/<pipeline>-pull-request.yaml

# Single directory (must contain go.mod and go.sum)
./scripts/lockfile-generators/create-go-lockfile.sh --prefetch-dir path/to/gomod/source
```

### Options


| Option                | Description                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------ |
| `--tekton-file PATH`  | Tekton PipelineRun YAML; extract `prefetch-input` entries with `type: gomod`.              |
| `--prefetch-dir PATH` | Single directory containing `go.mod` and `go.sum` (required if not using `--tekton-file`). |


### Example (jupyter pytorch+llmcompressor with mongocli)

```bash
# From Tekton file (recommended when the pipeline already defines prefetch-input)
./scripts/lockfile-generators/create-go-lockfile.sh \
    --tekton-file .tekton/odh-workbench-jupyter-pytorch-llmcompressor-cuda-py312-ubi9-odh-main-pull-request.yaml

# Single directory
./scripts/lockfile-generators/create-go-lockfile.sh \
    --prefetch-dir jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli
```

### Helper: `helpers/hermeto-fetch-gomod.sh`

Fetches Go modules for one directory using Hermeto in a container. Called by
`create-go-lockfile.sh` for each gomod path. Can be run standalone for a single
module:

```bash
./scripts/lockfile-generators/helpers/hermeto-fetch-gomod.sh \
    --prefetch-dir jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli
```

**Requirements:** `podman`, `jq`. Must be run from the repository root (Hermeto
expects a git repo for SBOM).

---

## 6. Git submodule

The notebooks repository uses external code (e.g. code-server) that is normally
cloned during the Docker build. For hermetic builds, Konflux can prefetch these
dependencies via **git submodules**: the external repo is added as a submodule
under `prefetch-input/` and pinned to a specific commit or tag. The build then
uses the checked-out tree instead of running `git clone` at build time.

### Setup

Run from the **repository root**. Replace the submodule URL and
`<component>/prefetch-input/<name>` with your target path (e.g.
`codeserver/ubi9-python-3.12/prefetch-input/code-server`). For Go modules, the
same submodule path is listed in the Tekton `prefetch-input` with `type: gomod`.

```bash
# Add the external repo as a submodule under prefetch-input
git submodule add https://github.com/coder/code-server.git \
    codeserver/ubi9-python-3.12/prefetch-input/code-server

# Pin to a specific tag (or commit)
cd codeserver/ubi9-python-3.12/prefetch-input/code-server
git fetch --tags
git checkout tags/v4.104.0
git submodule update --init --recursive   # pull nested submodules if any

# Commit the submodule and .gitmodules (from repo root so .gitmodules is staged)
cd ../../../..
git add .gitmodules codeserver/ubi9-python-3.12/prefetch-input/code-server
git commit -m "Added submodule code-server"
```

Use the same tag or commit that your Dockerfile or build scripts expect, so the
hermetic build uses an identical source tree.

---

## Appendix: Local podman build

After running `prefetch-all.sh` with `RELEASE_PYTHON_VERSION` and `BUILD_ARCH`
set (see [Local development](#local-development)), the **recommended** way to
build is via make:

```bash
# Makefile auto-detects cachi2/output/ and injects --volume
gmake codeserver-ubi9-python-3.12 BUILD_ARCH=linux/arm64 PUSH_IMAGES=no
```

The Makefile adds the cachi2 volume only when both `prefetch-input/` and
`cachi2/output/` exist (after prefetch). Non-hermetic targets are unaffected.

### Alternative: manual podman build

Running `podman build` directly differs from `gmake` in these ways:


| Aspect            | `gmake codeserver-ubi9-python-3.12 BUILD_ARCH=... PUSH_IMAGES=no`                  | Manual `podman build ...`                                                                            |
| ----------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Build context** | Minimal (via `scripts/sandbox.py`: only files needed by the Dockerfile)            | Full repo (`.`).                                                                                     |
| **Volume**        | `--volume $(ROOT_DIR)cachi2/output:/cachi2/output:Z` (mounts only `cachi2/output`) | Often `-v ./cachi2:/cachi2` (mounts whole dir); equivalent is `-v ./cachi2/output:/cachi2/output:z`. |
| **Build args**    | From `build-args/cpu.conf` (`PRODUCT=odh`) or `build-args/konflux.cpu.conf` (`PRODUCT=rhoai`) | You must pass these explicitly (see below).                                                          |
| **Tag**           | `$(IMAGE_REGISTRY):codeserver-ubi9-python-3.12-$(RELEASE)_$(DATE)`                 | Whatever you pass with `-t`.                                                                         |
| **Label**         | `--label release=$(RELEASE)`                                                       | Omitted unless you add it.                                                                           |
| **Cache**         | Default `CONTAINER_BUILD_CACHE_ARGS ?= --no-cache`                                 | Podman uses its default cache unless you pass `--no-cache`.                                          |


To approximate the make build when running podman manually, use the same volume
path as make and pass build-args from the conf file your `PRODUCT` selects
(`build-args/cpu.conf` for ODH, `build-args/konflux.cpu.conf` for RHOAI). The
example below uses `konflux.cpu.conf` values (including a derived `INDEX_URL`)
to match the RH-index lockfile path and `Dockerfile.konflux.cpu`:

- `-v $(realpath ./cachi2/output):/cachi2/output:z` — prefetched deps (pip, npm, generic, RPMs).
- `-v $(realpath ./cachi2/output/deps/rpm/<arch>/repos.d):/etc/yum.repos.d/:z` — hermeto-generated
RPM repo files (replace `<arch>` with `x86_64`, `aarch64`, etc.).
- Pass the same `BASE_IMAGE`, `PYLOCK_FLAVOR`, and
`INDEX_URL` as in `codeserver/ubi9-python-3.12/build-args/konflux.cpu.conf`
(`INDEX_URL` is derived from `BASE_IMAGE`; resolve with
`uv run python scripts/index_url_resolver.py index-url` on that file).

```bash
# Same volume path as Makefile; build-args from build-args/konflux.cpu.conf
podman build \
    -f codeserver/ubi9-python-3.12/Dockerfile.konflux.cpu \
    --platform linux/arm64 \
    -t code-server-test \
    --build-arg BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-1782270118 \
    --build-arg PYLOCK_FLAVOR=cpu \
    --build-arg INDEX_URL=https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5/cpu-ubi9/simple/ \
    -v "$(realpath ./cachi2/output):/cachi2/output:z" \
    -v "$(realpath ./cachi2/output/deps/rpm/aarch64/repos.d):/etc/yum.repos.d/:z" \
    .
```

To build for a different architecture, change `--platform` (e.g. `linux/amd64`,
`linux/arm64`, `linux/ppc64le`). The manual command uses the **full repo** as
context; make uses a **sandboxed** context for reproducibility.
