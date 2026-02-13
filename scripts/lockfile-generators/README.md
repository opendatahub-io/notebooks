# Lockfile Generators

Scripts to generate lockfiles for **generic artifacts**, **RPMs**, **npm packages**,
and **pip packages** — download the referenced packages and support **offline**
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
  - path: codeserver/ubi9-python-3.12/prefetch-input
    type: generic                                          # artifacts.lock.yaml
  - path: codeserver/ubi9-python-3.12/prefetch-input
    type: rpm                                              # rpms.lock.yaml
  - path: codeserver/ubi9-python-3.12/prefetch-input/code-server
    type: npm                                              # package-lock.json (many)
  - path: codeserver/ubi9-python-3.12
    type: pip                                              # requirements.txt + requirements-rhoai.txt
    requirements_files: ["requirements.txt", "requirements-rhoai.txt"]
```

All scripts must be run from the **repository root**.

---

## Main tools

| # | Type | Main script | What it generates |
|---|------|-------------|-------------------|
| 1 | Generic | [create-artifact-lockfile.py](#1-generic-artifacts--create-artifact-lockfilepy) | `artifacts.lock.yaml` |
| 2 | RPM | [create-rpm-lockfile.sh](#2-rpm-packages--create-rpm-lockfilesh) | `rpms.lock.yaml` |
| 3 | npm | [download-npm.sh](#3-npm-packages--download-npmsh) | Downloaded tarballs in `cachi2/output/deps/npm/` |
| 4 | pip (RHOAI) | [create-requirements-lockfile.sh](#4-pip-packages-rhoai--create-requirements-lockfilesh) | `pylock.<flavor>.toml` + `requirements.txt` |

### Helper scripts (used internally by the main tools)

| Helper | Used by | Purpose |
|--------|---------|---------|
| `download-pip-packages.py` | pip | Download wheels/sdists from PyPI or RHOAI into `cachi2/output/deps/pip/`. |
| `download-rpms.sh` | RPM | Download RPMs from `rpms.lock.yaml` into `cachi2/output/deps/rpm/` and create DNF repo metadata. |
| `hermeto-fetch-npm.sh` | npm | Alternative npm fetcher using [Hermeto](https://github.com/hermetoproject/hermeto) in a container. |
| `rewrite-npm-urls.sh` | npm (Dockerfile) | Rewrites `resolved` URLs in `package-lock.json` / `package.json` to `file:///cachi2/output/deps/npm/`. |
| `utils.sh` | RPM | Runs `rpm-lockfile-prototype` inside the lockfile container. Not for direct host use. |
| `Dockerfile.rpm-lockfile` | RPM | Builds the container image for `create-rpm-lockfile.sh` (includes `rpm-lockfile-prototype` v0.20.0, `createrepo_c`, `modulemd-tools`). |
| `rhsm-pulp.repo` | RPM | DNF repo file for RHEL 9 E4S appstream (used inside the lockfile container to install `modulemd-tools`). |

---

## Quick start — codeserver example

Generate all four lockfile types for `codeserver/ubi9-python-3.12` in one go:

```bash
# 1. Generic artifacts (GPG keys, node headers, nfpm, oc client, VS Code extensions, etc.)
python3 scripts/lockfile-generators/create-artifact-lockfile.py \
    --artifact-input codeserver/ubi9-python-3.12/prefetch-input/artifacts.in.yaml

# 2. RPM packages (gcc, nodejs, nginx, openblas, etc.) — lockfile + download
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/rpms.in.yaml --download

# 3. npm packages (code-server + VSCode extensions) — from Tekton file
./scripts/lockfile-generators/download-npm.sh \
    --tekton-file .tekton/odh-workbench-codeserver-datascience-cpu-py312-ubi9-pull-request.yaml

# 4. pip packages (numpy, scipy, pandas, pyarrow, etc.) — via RHOAI index + download
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --download
```

After running these, the generated files are:

```
codeserver/ubi9-python-3.12/
├── requirements.txt                          # pinned pip packages (generated from pylock.toml)
├── uv.lock.d/
│   └── pylock.cpu.toml                       # PEP 665 lock file (from uv pip compile via RHOAI)
└── prefetch-input/
    ├── artifacts.in.yaml                     # input: URLs to prefetch
    ├── artifacts.lock.yaml                   # output: URLs + sha256 checksums
    ├── rpms.in.yaml                          # input: package names + repo files
    ├── rpms.lock.yaml                        # output: exact RPM URLs + checksums per arch

cachi2/output/deps/
├── generic/    # downloaded artifacts (GPG keys, tarballs, etc.)
├── rpm/        # downloaded RPMs + repodata/
├── npm/        # downloaded npm tarballs
└── pip/        # downloaded Python wheels/sdists
```

---

## 1. Generic artifacts — `create-artifact-lockfile.py`

Reads `artifacts.in.yaml`, downloads each artifact (or uses the existing cache
under `cachi2/output/deps/generic/`), computes SHA-256, and writes
`artifacts.lock.yaml` in the same directory.  Duplicate filenames are skipped.

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
    --artifact-input codeserver/ubi9-python-3.12/prefetch-input/artifacts.in.yaml
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

With `--download`, it also calls `download-rpms.sh` to fetch all RPMs into
`cachi2/output/deps/rpm/` and generate DNF repo metadata.

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
| `--download` | After generating the lockfile, fetch RPMs and create DNF repo metadata. |

### Example (codeserver)

```bash
# Generate lockfile only (no Red Hat subscription)
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/rpms.in.yaml

# Generate lockfile + download RPMs + create repo metadata
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/rpms.in.yaml --download

# With Red Hat subscription (for RHEL-only repos)
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --activation-key my-key --org my-org \
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/rpms.in.yaml --download
```

### Helper: `download-rpms.sh`

Downloads RPMs from a lockfile into `cachi2/output/deps/rpm/`, verifies checksums
(when `yq` is available), and creates DNF repo metadata using the first available
method: `createrepo_c` → `createrepo` → container fallback (runs `createrepo_c` +
`repo2module` + `modifyrepo_c` inside the `notebook-rpm-lockfile` image via podman).

```bash
# Can also be run standalone
./scripts/lockfile-generators/download-rpms.sh \
    --lock-file codeserver/ubi9-python-3.12/prefetch-input/rpms.lock.yaml
```

**Requirements:** `wget`.  `yq` recommended for checksum verification.

### Helper: `utils.sh`

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
downloads each tarball into `cachi2/output/deps/npm/`.  Scoped packages
(e.g. `@types/node`) are saved as `scope-filename` to avoid collisions.
Files that already exist are skipped.

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

### Helper: `hermeto-fetch-npm.sh`

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

Resolves Python dependencies via the **RHOAI PyPI index** using `uv pip compile`,
producing a PEP 665 `pylock.<flavor>.toml` with sha256 hashes, then converts it
to `requirements.txt` for use in hermetic builds.

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

1. **`uv pip compile`** — resolves `pyproject.toml` against the RHOAI index,
   producing `uv.lock.d/pylock.<flavor>.toml` (PEP 665 format) with exact
   versions, wheel URLs, and sha256 hashes for all target architectures.
2. **Convert** — parses the pylock.toml and generates `requirements.txt`
   (with `--index-url` and `--hash=sha256:…` lines) for compatibility with
   pip/uv install and cachi2 prefetching.
3. **Download** (optional, `--download`) — downloads every wheel referenced
   in the pylock.toml into `cachi2/output/deps/pip/`, verifying checksums.

### Requirements

`uv` (Python package manager/resolver).

### Usage

```bash
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml path/to/pyproject.toml \
    [--flavor NAME] [--rhoai-index URL] [--download]
```

### Options

| Option | Description |
|--------|-------------|
| `--pyproject-toml FILE` | Path to `pyproject.toml` (required). Output files are written to the same directory. |
| `--flavor NAME` | Lock file flavor (default: `cpu`). Determines output filename (`pylock.<flavor>.toml`) and RHOAI index URL (`<flavor>-ubi9`). |
| `--rhoai-index URL` | Custom RHOAI simple-index URL. If not given, derived from `--flavor`. |
| `--download` | After generating the lock, download all wheels into `cachi2/output/deps/pip/`. |

### Example (codeserver)

```bash
# Full pipeline: resolve via RHOAI + generate requirements.txt + download all wheels
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --download
```

This single command:
1. Runs `uv pip compile` against `codeserver/ubi9-python-3.12/pyproject.toml`
   with the RHOAI index → `codeserver/ubi9-python-3.12/uv.lock.d/pylock.cpu.toml`.
2. Converts `pylock.cpu.toml` → `codeserver/ubi9-python-3.12/requirements.txt`
   (with `--index-url` header and `--hash` lines).
3. Downloads all wheels from the pylock.toml URLs into `cachi2/output/deps/pip/`,
   verifying sha256 checksums.

```bash
# Resolve + generate requirements.txt only (no download)
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml

# Custom flavor (e.g. cuda) and RHOAI index
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml \
    --flavor cuda --rhoai-index https://console.redhat.com/api/pypi/public-rhai/rhoai/3.4-EA1/cuda-ubi9/simple/
```

### Helper: `download-pip-packages.py`

Downloads wheels/sdists from a `requirements.txt` that contains `--hash=sha256:…`
lines.  Resolves download URLs from PyPI (JSON API) or a PEP 503 simple index
(auto-detected from `--index-url` in the file, e.g. RHOAI).  Skips files that
already exist; always verifies sha256 checksums.  Windows, macOS, and iOS wheels
are automatically excluded when downloading from PyPI.

```bash
# Can also be run standalone
python3 scripts/lockfile-generators/download-pip-packages.py \
    codeserver/ubi9-python-3.12/requirements.txt
```

**Requirements:** Python 3, `wget`.
