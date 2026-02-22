# Lockfile Generators

Scripts to generate lockfiles for **generic artifacts**, **RPMs**, **npm packages**,
and **pip packages**, download the referenced packages and support **offline**
hermetic image builds via Cachi2/Hermeto.

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
  - path: codeserver/ubi9-python-3.12/prefetch-input/odh   # use 'rhds' for downstream
    type: rpm                                              # rpms.lock.yaml
  - path: codeserver/ubi9-python-3.12/prefetch-input/odh
    type: generic                                          # artifacts.lock.yaml
  - path: codeserver/ubi9-python-3.12
    type: pip                                              # requirements.cpu.txt
    binary:
      arch: "x86_64,aarch64,ppc64le"                      # prefetch wheels for all build platforms
    requirements_files: ["requirements.cpu.txt"]
  - path: codeserver/ubi9-python-3.12/prefetch-input/code-server/lib/vscode/extensions
    type: npm                                              # package-lock.json (many)
  # ... more npm entries for code-server root, build/, test/, patched lockfiles, etc.
```

All scripts must be run from the **repository root**.

---

## Orchestrator — `prefetch-all.sh`

**For most local and CI use, this is the only script you need to run.**

`prefetch-all.sh` orchestrates all four lockfile generators in the correct
order, downloading dependencies into `cachi2/output/deps/`. After running it,
the Makefile auto-detects `cachi2/output/` and passes `--volume` +
`LOCAL_BUILD=true` to `podman build`.

```bash
# Upstream ODH (default variant, CentOS Stream base, no subscription):
scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12

# Downstream RHDS (with RHEL subscription for cdn.redhat.com RPMs):
scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --rhds \
    --activation-key my-key --org my-org

# Custom flavor:
scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --flavor cuda
```

Then build with make:

```bash
# On macOS use gmake
gmake codeserver-ubi9-python-3.12 BUILD_ARCH=linux/arm64 PUSH_IMAGES=no
```

### Options

| Option | Description |
|--------|-------------|
| `--component-dir DIR` | Component directory (required), e.g. `codeserver/ubi9-python-3.12` |
| `--rhds` | Use downstream (RHDS) lockfiles instead of upstream (ODH, the default) |
| `--flavor NAME` | Lock file flavor (default: `cpu`) |
| `--tekton-file FILE` | Tekton PipelineRun YAML for npm path discovery (auto-detected from `.tekton/` if omitted) |
| `--activation-key KEY` | Red Hat activation key for RHEL RPMs (optional) |
| `--org ORG` | Red Hat organization ID for RHEL RPMs (optional) |

### What it does

| Step | Condition | Script called |
|------|-----------|---------------|
| 1. Generic artifacts | `artifacts.in.yaml` exists | `create-artifact-lockfile.py` |
| 2. Pip wheels | `pyproject.toml` exists | `create-requirements-lockfile.sh --download` |
| 3. NPM packages | `package-lock.json` files found | `download-npm.sh` |
| 4. RPMs | `rpms.in.yaml` exists | `hermeto-fetch-rpm.sh` (if lockfile committed) or `create-rpm-lockfile.sh --download` |

Steps are skipped if their input files don't exist. For RPMs, if
`rpms.lock.yaml` is already committed, it downloads directly (skipping
lockfile regeneration) — this avoids cross-platform issues on arm64 CI runners.

### GitHub Actions integration

The GHA workflow template (`.github/workflows/build-notebooks-TEMPLATE.yaml`)
calls `prefetch-all.sh` automatically for codeserver targets before running
`make`. Non-codeserver targets skip the prefetch step entirely.

---

## Individual tools

The four scripts below can also be run individually for debugging or partial
updates. `prefetch-all.sh` calls them internally.

| # | Type | Main script | What it generates |
|---|------|-------------|-------------------|
| 1 | Generic | [create-artifact-lockfile.py](#1-generic-artifacts--create-artifact-lockfilepy) | `artifacts.lock.yaml` |
| 2 | RPM | [create-rpm-lockfile.sh](#2-rpm-packages--create-rpm-lockfilesh) | `rpms.lock.yaml` |
| 3 | npm | [download-npm.sh](#3-npm-packages--download-npmsh) | Downloaded tarballs in `cachi2/output/deps/npm/` |
| 4 | pip (RHOAI) | [create-requirements-lockfile.sh](#4-pip-packages-rhoai--create-requirements-lockfilesh) | `pylock.<flavor>.toml` + `requirements.<flavor>.txt` |

### Helper scripts (used internally by the main tools)

| Helper | Used by | Purpose |
|--------|---------|---------|
| `helpers/pylock-to-requirements.py` | pip | Convert `pylock.<flavor>.toml` (PEP 751) to pip-compatible `requirements.<flavor>.txt` with `--hash` lines. |
| `helpers/download-pip-packages.py` | pip | Download wheels/sdists from PyPI or RHOAI into `cachi2/output/deps/pip/`. |
| `helpers/download-rpms.sh` | RPM | Download RPMs from `rpms.lock.yaml` via `wget` into `cachi2/output/deps/rpm/` and create DNF repo metadata. Standalone alternative to `hermeto-fetch-rpm.sh`. |
| `helpers/hermeto-fetch-rpm.sh` | RPM | Download RPMs from `rpms.lock.yaml` using [Hermeto](https://github.com/hermetoproject/hermeto) in a container. Handles RHEL entitlement cert extraction for `cdn.redhat.com` auth. Called by `create-rpm-lockfile.sh --download`. |
| `helpers/hermeto-fetch-npm.sh` | npm | Alternative npm fetcher using [Hermeto](https://github.com/hermetoproject/hermeto) in a container. |
| `rewrite-npm-urls.sh` | npm (Dockerfile) | Rewrites `resolved` URLs in `package-lock.json` / `package.json` to `file:///cachi2/output/deps/npm/`. |
| `helpers/rpm-lockfile-generate.sh` | RPM | Runs `rpm-lockfile-prototype` inside the lockfile container. Not for direct host use. |
| `Dockerfile.rpm-lockfile` | RPM | Builds the container image for `create-rpm-lockfile.sh` (includes `rpm-lockfile-prototype` v0.20.0, `createrepo_c`, `modulemd-tools`). |
| `helpers/rhsm-pulp.repo` | RPM | DNF repo file for RHEL 9 E4S appstream (used inside the lockfile container to install `modulemd-tools`). |

---

## Quick start — codeserver example

The fastest way to prefetch everything and build:

```bash
# Prefetch all dependencies (one command)
scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12

# Build (Makefile auto-detects cachi2/output/ and mounts it)
gmake codeserver-ubi9-python-3.12 BUILD_ARCH=linux/arm64 PUSH_IMAGES=no
```

### Alternative: run each generator individually

If you need to regenerate only one dependency type, or for debugging:

```bash
# 1. Generic artifacts (GPG keys, node headers, nfpm, oc client, VS Code extensions, etc.)
python3 scripts/lockfile-generators/create-artifact-lockfile.py \
    --artifact-input codeserver/ubi9-python-3.12/prefetch-input/odh/artifacts.in.yaml

# 2. RPM packages (gcc, nodejs, nginx, openblas, etc.) — lockfile + download for local testing
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/odh/rpms.in.yaml --download

# 3. npm packages (code-server + VSCode extensions) — download for local testing
./scripts/lockfile-generators/download-npm.sh \
    --tekton-file .tekton/odh-workbench-codeserver-datascience-cpu-py312-ubi9-pull-request.yaml

# 4. pip packages (numpy, scipy, pandas, pyarrow, etc.) — via RHOAI index + download for local testing
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --download
```

> **Note:** The `--download` flag (and `download-npm.sh`) fetches packages into
> `cachi2/output/deps/` for **local development and testing with podman**.
> In Konflux CI, cachi2 handles all prefetching automatically from the lockfiles —
> you never need `--download` there.

After running these, the generated files are:

```
codeserver/ubi9-python-3.12/
├── requirements.cpu.txt                      # pinned pip packages (generated from pylock.cpu.toml)
├── uv.lock.d/
│   └── pylock.cpu.toml                       # PEP 751 lock file (from pylocks_generator.sh via RHOAI)
└── prefetch-input/
    ├── repos/                                # shared DNF repo definitions (ubi, centos, epel, rhsm-pulp)
    ├── odh/                                  # upstream (ODH) lockfiles
    │   ├── artifacts.in.yaml                 # input: URLs to prefetch
    │   ├── artifacts.lock.yaml               # output: URLs + sha256 checksums
    │   ├── rpms.in.yaml                      # input: references ../repos/*.repo
    │   └── rpms.lock.yaml                    # output: exact RPM URLs + checksums per arch
    ├── rhds/                                 # downstream (RHDS) lockfiles
    │   ├── artifacts.in.yaml
    │   ├── rpms.in.yaml                      # references ../repos/*.repo + redhat.repo
    │   └── rpms.lock.yaml                    # (generated)
    ├── code-server/                          # git submodule (shared)
    └── patches/                              # patch files (shared)

cachi2/output/deps/
├── generic/    # downloaded artifacts (GPG keys, tarballs, etc.)
├── rpm/        # downloaded RPMs + repodata/
├── npm/        # downloaded npm tarballs
└── pip/        # downloaded Python wheels/sdists
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

    # OpenShift oc client (one per arch, filename distinguishes them)
    - url: https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-client-linux.tar.gz
      filename: openshift-client-linux-x86_64.tar.gz

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
Node.js/Electron headers, nfpm RPMs, OpenShift `oc` client binaries, Playwright
Chromium, ripgrep binaries, VS Code marketplace extensions (.vsix).

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

| Field | Required | Description |
|-------|----------|-------------|
| `url` | yes | The URL to download. |
| `filename` | no | Override the filename (default: extracted from URL). |
| `checksum` | no | Expected SHA-256 checksum (validated if present; accepts `sha256:` prefix). |

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

| Option | Description |
|--------|-------------|
| `--rpm-input FILE` | Path to `rpms.in.yaml` (required). |
| `--activation-key VALUE` | Red Hat activation key for subscription-manager (optional). |
| `--org VALUE` | Red Hat organization ID for subscription-manager (optional). |
| `--download` | After generating the lockfile, fetch RPMs and create DNF repo metadata (for local testing with podman; not needed in Konflux CI). |

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
`create-rpm-lockfile.sh --download`.  When `--activation-key` and `--org` are
provided, it extracts RHEL entitlement certs from the `notebook-rpm-lockfile`
container and passes them to Hermeto for `cdn.redhat.com` authentication.

```bash
# Called automatically by create-rpm-lockfile.sh --download, but can also run standalone:
./scripts/lockfile-generators/helpers/hermeto-fetch-rpm.sh \
    --prefetch-dir codeserver/ubi9-python-3.12/prefetch-input

# With RHEL entitlement certs (requires notebook-rpm-lockfile image built with subscription):
./scripts/lockfile-generators/helpers/hermeto-fetch-rpm.sh \
    --prefetch-dir codeserver/ubi9-python-3.12/prefetch-input \
    --activation-key my-key --org my-org
```

**Requirements:** `podman`, network access.

### Helper: `helpers/download-rpms.sh`

Standalone alternative to `hermeto-fetch-rpm.sh` that downloads RPMs directly
via `wget`.  Downloads RPMs from a lockfile into `cachi2/output/deps/rpm/`,
verifies checksums (when `yq` is available), and creates DNF repo metadata using
the first available method: `createrepo_c` → `createrepo` → container fallback
(runs `createrepo_c` + `repo2module` + `modifyrepo_c` inside the
`notebook-rpm-lockfile` image via podman).

Does not handle RHEL entitlement — use `hermeto-fetch-rpm.sh` when downloading
from `cdn.redhat.com` repos that require subscription certs.

```bash
./scripts/lockfile-generators/helpers/download-rpms.sh \
    --lock-file codeserver/ubi9-python-3.12/prefetch-input/odh/rpms.lock.yaml
```

**Requirements:** `wget`.  `yq` recommended for checksum verification.

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
> packages during their build (for example code-server images). Many `jupyter/*`
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
  found under them.

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

Used by `setup-offline-binaries.sh` during the Dockerfile `npm ci` stage.

```bash
# Process a specific directory
./scripts/lockfile-generators/rewrite-npm-urls.sh prefetch-input/code-server
```

**Requirements:** `perl`.

---

## 4. pip packages (RHOAI) — `create-requirements-lockfile.sh`

Generates `pylock.<flavor>.toml` via `pylocks_generator.sh` (the same script
CI uses), then converts it to a pip-compatible `requirements.<flavor>.txt`
for use in hermetic builds.

### Why RHOAI?

Public PyPI does not publish pre-built manylinux wheels for **ppc64le** and
**s390x** for many data-science packages (numpy, scipy, pandas, pyarrow,
pillow, pyzmq, scikit-learn, debugpy, etc.).  Without pre-built wheels the
Dockerfile must compile them from source, which:

- Is **slow** — building numpy + scipy + pyarrow from source can take 30+ minutes.
- Is **fragile** — requires a full C/C++/Fortran build toolchain (gcc, gfortran,
  cmake, meson, OpenBLAS-devel, etc.) installed inside the image.
- **Bloats the image** — the -devel RPMs and build tools are only needed at build
  time but are hard to cleanly remove afterward.

Red Hat OpenShift AI (RHOAI) maintains a PyPI index that publishes pre-built
wheels for all target architectures (x86_64, aarch64, ppc64le, s390x).  Using
`create-requirements-lockfile.sh` resolves everything through RHOAI, eliminating
source builds entirely.

### How it works

The script performs three steps:

1. **`pylocks_generator.sh`** — delegates to `scripts/pylocks_generator.sh`
   (the same script used by CI's `check-generated-code`) to run `uv pip compile`
   against `pyproject.toml` with the RHOAI index from `build-args/<flavor>.conf`,
   producing `uv.lock.d/pylock.<flavor>.toml` (PEP 751 format) with exact
   versions, wheel URLs, and sha256 hashes for all target architectures.
   This ensures the generated pylock is always identical to what CI expects.
2. **Convert** (`helpers/pylock-to-requirements.py`) — parses the pylock.toml
   and generates `requirements.<flavor>.txt` (with `--index-url` and
   `--hash=sha256:…` lines) for compatibility with pip/uv install and cachi2
   prefetching.
3. **Download** (optional, `--download`) — for local testing with podman,
   downloads every wheel referenced in the pylock.toml into
   `cachi2/output/deps/pip/`, verifying sha256 checksums.  Files already
   present are skipped.  Not needed in Konflux CI (cachi2 prefetches
   automatically from `requirements.<flavor>.txt`).

### Requirements

`uv` (Python package manager/resolver).

### Usage

```bash
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml path/to/pyproject.toml \
    [--flavor NAME] [--download]
```

### Options

| Option | Description |
|--------|-------------|
| `--pyproject-toml FILE` | Path to `pyproject.toml` (required). Output files are written to the same directory. |
| `--flavor NAME` | Lock file flavor (default: `cpu`). Must match a `Dockerfile.<flavor>` and `build-args/<flavor>.conf` in the project directory. Determines output filenames (`pylock.<flavor>.toml` and `requirements.<flavor>.txt`). |
| `--download` | After generating the lock, download all wheels into `cachi2/output/deps/pip/` (for local testing with podman; not needed in Konflux CI). |

### Example (codeserver)

```bash
# Full pipeline: generate pylock + requirements.cpu.txt + download all wheels
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --download
```

This single command:
1. Delegates to `pylocks_generator.sh` to resolve `codeserver/ubi9-python-3.12/pyproject.toml`
   via the RHOAI index (from `build-args/cpu.conf`) → `uv.lock.d/pylock.cpu.toml`.
2. Converts `pylock.cpu.toml` → `codeserver/ubi9-python-3.12/requirements.cpu.txt`
   (with `--index-url` header and `--hash` lines).
3. Downloads all wheels from the pylock URLs into `cachi2/output/deps/pip/`,
   verifying sha256 checksums.

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

Downloads wheels/sdists from a `requirements.<flavor>.txt` that contains
`--hash=sha256:…` lines.  Resolves download URLs from PyPI (JSON API) or a
PEP 503 simple index (auto-detected from `--index-url` in the file, e.g. RHOAI).
Skips files that already exist; always verifies sha256 checksums.  Windows,
macOS, and iOS wheels are automatically excluded when downloading from PyPI.

This is the **local-development equivalent** of what cachi2 does for pip
dependencies in Konflux CI.  The downloaded wheels populate
`cachi2/output/deps/pip/` so that podman builds can install packages with
`--no-index --find-links`.

```bash
# Can also be run standalone (for local testing)
python3 scripts/lockfile-generators/helpers/download-pip-packages.py \
    codeserver/ubi9-python-3.12/requirements.cpu.txt
```

**Requirements:** Python 3, `wget`.

---

## Appendix: Local podman build

After running `prefetch-all.sh`, the **recommended** way to build is via make:

```bash
# Makefile auto-detects cachi2/output/ and injects --volume + LOCAL_BUILD=true
gmake codeserver-ubi9-python-3.12 BUILD_ARCH=linux/arm64 PUSH_IMAGES=no
```

The Makefile evaluates each target independently: `CACHI2_VOLUME` is only set
when both `cachi2/output/` exists AND the target directory has a
`prefetch-input/` subdirectory. Non-hermetic targets are completely unaffected.

### Alternative: manual podman build

For developers who want to run `podman build` directly, the key flags are:

- `-v $(realpath ./cachi2):/cachi2:z` bind-mount the prefetched dependencies
  so the Dockerfile can install from them offline.
- `--build-arg LOCAL_BUILD=true` signals the Dockerfile that this is a local
  build (configures dnf to use the local cachi2 RPM repo).

```bash
podman build \
    -f codeserver/ubi9-python-3.12/Dockerfile.cpu \
    --platform linux/amd64 \
    -t code-server-test \
    --build-arg ARCH=amd64 \
    --build-arg LOCAL_BUILD=true \
    --build-arg BASE_IMAGE=quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest \
    --build-arg PYLOCK_FLAVOR=cpu \
    -v "$(realpath ./cachi2):/cachi2:z" \
    .
```

To build for a different architecture, change `--platform` and `ARCH`
accordingly (e.g. `linux/arm64` / `aarch64`, `linux/ppc64le` / `ppc64le`).
