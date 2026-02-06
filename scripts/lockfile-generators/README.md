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
| 4 | pip | [create-pip-requirements-lockfile.sh](#4-pip-packages--create-pip-requirements-lockfilesh) | `requirements.txt` + `requirements-rhoai.txt` |

### Helper scripts (used internally by the main tools)

| Helper | Used by | Purpose |
|--------|---------|---------|
| `generate-rhoai-requirements.py` | pip | Discover RHOAI wheels, write `requirements-rhoai.txt`, merge hashes into `requirements.txt`. |
| `download-pip-packages.py` | pip | Download wheels/sdists from PyPI or RHOAI into `cachi2/output/deps/pip/`. |
| `download-rpms.sh` | RPM | Download RPMs from `rpms.lock.yaml` into `cachi2/output/deps/rpm/` and create DNF repo metadata. |
| `hermeto-fetch-npm.sh` | npm | Alternative npm fetcher using [Hermeto](https://github.com/hermetoproject/hermeto) in a container. |
| `rewrite-cachi2-path.sh` | npm (Dockerfile) | Sourceable function that rewrites `resolved` URLs in lockfiles to `file:///cachi2/output/deps/npm/`. |
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

# 4. pip packages (numpy, scipy, pandas, pyarrow, etc.) — with RHOAI wheels + download
./scripts/lockfile-generators/create-pip-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --rhoai --download
```

After running these, the generated files are:

```
codeserver/ubi9-python-3.12/
├── requirements.txt                          # pinned pip packages (PyPI + RHOAI hashes merged)
├── requirements-rhoai.txt                    # RHOAI-only packages (--index-url to RHOAI mirror)
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

### Helper: `rewrite-cachi2-path.sh`

**Sourced** by other scripts or Dockerfile `RUN` steps (do NOT execute standalone).
Defines a single function `rewrite_cachi2_path <file>` that performs three `perl`
in-place substitutions on `package-lock.json` or `npm-shrinkwrap.json`:

1. **Registry URLs** — `https://registry.npmjs.org/[@scope/]pkg/-/file.tgz`
   → `file:///cachi2/output/deps/npm/[scope-]file.tgz`
2. **Relative `file:` paths** — `file:../../../cachi2/output/deps/npm/...`
   → `file:///cachi2/output/deps/npm/...`
3. **Un-prefixed `file:` paths** — `file:cachi2/output/deps/npm/...`
   → `file:///cachi2/output/deps/npm/...`

Used by `setup-offline-binaries.sh` during the Dockerfile `npm ci` stage.

**Requirements:** `perl`.

---

## 4. pip packages — `create-pip-requirements-lockfile.sh`

Generates a fully pinned `requirements.txt` with sha256 hashes using `uv`.
Supports two modes:

- **export** (default): resolves from `pyproject.toml` using `uv export`
  with `--python 3.12` and `--no-annotate`.
- **compile**: resolves from a plain requirements file using `uv pip compile`
  with `--generate-hashes`.

With `--rhoai`, also discovers RHOAI pre-built wheels, generates
`requirements-rhoai.txt`, and merges RHOAI hashes into `requirements.txt`.
RHOAI generation is **not** supported in compile mode.

### Why `--rhoai`?

Public PyPI does not publish pre-built manylinux wheels for **ppc64le** and
**s390x** for many data-science packages (numpy, scipy, pandas, pyarrow,
pillow, pyzmq, scikit-learn, debugpy, etc.).  Without pre-built wheels the
Dockerfile must compile them from source, which:

- Is **slow** — building numpy + scipy + pyarrow from source can take 30+ minutes.
- Is **fragile** — requires a full C/C++/Fortran build toolchain (gcc, gfortran,
  cmake, meson, OpenBLAS-devel, etc.) installed inside the image.
- **Bloats the image** — the -devel RPMs and build tools are only needed at build
  time but are hard to cleanly remove afterward.

Red Hat OpenShift AI (RHOAI) maintains an internal PyPI index that publishes
pre-built wheels for these packages on ppc64le and s390x.  Using `--rhoai`
eliminates most source compilations from the build.

### Why merge hashes?

The Dockerfile installs packages with:

```bash
uv pip install --find-links /cachi2/output/deps/pip \
    --verify-hashes -r requirements.txt
```

The `--verify-hashes` flag requires that **every wheel** `uv` encounters has a
matching hash in `requirements.txt`.  However, `uv export` (Step 1) only
generates hashes from **public PyPI** — it has no knowledge of RHOAI wheels.
When `uv` tries to install an RHOAI wheel (e.g. `numpy` for ppc64le), it finds
no matching hash and **rejects the install**.

The `--rhoai` flag solves this by calling `generate-rhoai-requirements.py` with
`--merge-hashes`, which appends the RHOAI wheel sha256 hashes into the
corresponding package blocks in `requirements.txt`.  After merging, each package
entry contains hashes from **both** PyPI and RHOAI, so `--verify-hashes` accepts
whichever wheel matches the target platform.

### Why two requirements files?

Konflux/cachi2 does **not** support `--extra-index-url` inside a single
`requirements.txt`.  To prefetch from both PyPI and the RHOAI mirror, we
maintain two files:

| File | Index | Purpose |
|------|-------|---------|
| `requirements.txt` | PyPI (default) | All packages with pinned versions.  Contains hashes from **both** PyPI and RHOAI (after merge) so `--verify-hashes` works at install time. |
| `requirements-rhoai.txt` | RHOAI (`--index-url`) | Same packages that overlap with RHOAI, but with the RHOAI index URL.  cachi2 prefetches these as a second pip source into `/cachi2/output/deps/pip/`. |

At install time, `/cachi2/output/deps/pip/` contains wheels from **both**
sources.  `uv pip install --find-links` picks whichever wheel matches the
platform (x86_64 from PyPI, ppc64le/s390x from RHOAI).

### Requirements

`uv` (Python package manager/resolver).

### Usage

```bash
./scripts/lockfile-generators/create-pip-requirements-lockfile.sh \
    --pyproject-toml path/to/pyproject.toml [--output FILE] [--compile FILE] \
    [--rhoai | --rhoai-index URL] [--download]
```

### Options

| Option | Description |
|--------|-------------|
| `--pyproject-toml FILE` | Path to `pyproject.toml` (required). Output files are written to the same directory. |
| `--output FILE` | Output file path (default: `<project-dir>/requirements.txt` for export, `<project-dir>/prefetch-input/requirements-wheel-build.txt` for compile). |
| `--compile FILE` | Switch to compile mode with the given input file. |
| `--rhoai` | After export, generate `requirements-rhoai.txt` and merge RHOAI hashes (uses the default RHOAI index). |
| `--rhoai-index URL` | Same as `--rhoai` but with a custom RHOAI index URL. |
| `--download` | Fetch all wheels/sdists into `cachi2/output/deps/pip/` via `download-pip-packages.py`. |

### Example (codeserver)

```bash
# Full pipeline: export from pyproject.toml + RHOAI discovery + download all wheels
./scripts/lockfile-generators/create-pip-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml --rhoai --download
```

This single command:
1. Runs `uv export` against `codeserver/ubi9-python-3.12/pyproject.toml`
   → `codeserver/ubi9-python-3.12/requirements.txt` (PyPI hashes).
2. Runs `generate-rhoai-requirements.py`
   → `codeserver/ubi9-python-3.12/requirements-rhoai.txt` (RHOAI wheels)
   and merges RHOAI hashes into `requirements.txt`.
3. Runs `download-pip-packages.py` twice — once for `requirements.txt` (PyPI),
   once for `requirements-rhoai.txt` (RHOAI) — downloading into
   `cachi2/output/deps/pip/`.

```bash
# Export only (no RHOAI, no download)
./scripts/lockfile-generators/create-pip-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml

# Custom RHOAI index URL
./scripts/lockfile-generators/create-pip-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml \
    --rhoai-index https://console.redhat.com/api/pypi/public-rhai/rhoai/3.4/cpu-ubi9/simple/

# Compile mode (pin a plain requirements file, e.g. for wheel-build deps)
./scripts/lockfile-generators/create-pip-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml \
    --compile some-requirements.in --output some-requirements.txt
```

### Helper: `generate-rhoai-requirements.py`

Discovers which packages from `requirements.txt` are available on the RHOAI PyPI
index.  For each match, collects wheel hashes that match the pinned version and
the requested Python tag (default: `cp312`), then:

1. Writes `requirements-rhoai.txt` with `--index-url` header — consumed by cachi2
   as a second pip prefetch source.
2. With `--merge-hashes`, appends RHOAI hashes into the matching package blocks
   in `requirements.txt` so `uv pip install --verify-hashes` accepts both PyPI
   and RHOAI wheels.

```bash
# Can also be run standalone
python3 scripts/lockfile-generators/generate-rhoai-requirements.py \
    --requirements codeserver/ubi9-python-3.12/requirements.txt \
    --output codeserver/ubi9-python-3.12/requirements-rhoai.txt \
    --merge-hashes
```

| Option | Description |
|--------|-------------|
| `--requirements PATH` | Path to `requirements.txt` (input and merge target). Required. |
| `--output PATH` | Output path for `requirements-rhoai.txt`. Required. |
| `--rhoai-index URL` | RHOAI simple-index URL (default: `https://console.redhat.com/api/pypi/public-rhai/rhoai/3.3/cpu-ubi9/simple/`). |
| `--merge-hashes` | Also merge RHOAI wheel hashes into `requirements.txt`. |
| `--python-tag TAG` | Python version tag to filter wheels (default: `cp312`). |

**Requirements:** Python 3, network access to the RHOAI index.

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

python3 scripts/lockfile-generators/download-pip-packages.py \
    codeserver/ubi9-python-3.12/requirements-rhoai.txt
```

**Requirements:** Python 3, `wget`.
