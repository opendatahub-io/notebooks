# Lockfile Generators

Scripts and helpers to generate lockfiles for RPMs and other artifacts, download the referenced packages, and support **offline** and **Cachi2-based** image builds.

## Why lockfiles?

Required by Konflux, lockfiles pin exact package URLs and checksums so that:

- Builds are **reproducible** and **offline-capable** (no live access to upstream mirrors).
- Cachi2 (or similar) can prefetch everything once; the image build uses only the cached output.

All scripts in this directory must be run from the **repository root**, e.g.:

```bash
./scripts/lockfile-generators/create-rpm-lockfile.sh --image-dir=codeserver/ubi9-python-3.12
```

---

## Scripts in this directory

| Script | Purpose |
|--------|---------|
| [create-rpm-lockfile.sh](#1-create-rpm-lockfilesh) | Generate `rpms.lock.yaml` from `rpms.in.yaml` using `rpm-lockfile-prototype` (via Dockerfile.rpm-lockfile). |
| [create-artifact-lockfile.py](#2-create-artifact-lockfilepy) | Generate `artifacts.lock.yaml` from `artifacts.in.yaml` (download artifacts, compute SHA-256). |
| [download-rpms.sh](#3-download-rpmssh) | Download RPMs from `rpms.lock.yaml` into `cachi2/output/deps/rpm` and create DNF repo metadata. |
| [download-npm.sh](#4-download-npmsh) | Download npm packages from a single `package-lock.json` into `cachi2/output/deps/npm` (jq + wget). |
| [hermeto-fetch-npm.sh](#5-hermeto-fetch-npmsh) | Fetch npm packages using [Hermeto](https://github.com/hermetoproject/hermeto) in a container; per source dir, then merge into one output dir. |
| [download-pip-packages.py](#6-download-pip-packagespy) | Prefetch pip dependencies from a `requirements.txt` (with hashes) into `cachi2/output/deps/pip` (PyPI + wget; skip if file exists, verify checksum). |
| [rewrite-cachi2-path.sh](#7-rewrite-cachi2-pathsh) | Sourceable; rewrites npm `resolved` URLs in lockfiles to `file:///cachi2/output/deps/npm/`. |
| [utils.sh](#8-utilssh) | Used inside the RPM lockfile container by `create-rpm-lockfile.sh`; runs `rpm-lockfile-prototype`. Not for direct host use. |

---

## Typical workflows

**RPM lockfile and offline RPMs**

1. Run `create-rpm-lockfile.sh --image-dir=<image-dir>` (optionally with `--activation-key` / `--org` for RHEL).
2. Optionally run `create-rpm-lockfile.sh --image-dir=<image-dir> --download` to also fetch RPMs and create repo metadata, or run `download-rpms.sh --lock-file=<image-dir>/prefetch-input/rpms.lock.yaml` separately.

**Artifact lockfile**

1. Run `create-artifact-lockfile.py --artifact-input=<path>/artifacts.in.yaml`.
2. Output is `<path>/artifacts.lock.yaml`; artifacts are cached under `cachi2/output/deps/generic/`.

**npm packages (choose one)**

- **download-npm.sh:** Single `package-lock.json` → jq extracts URLs → wget downloads into `cachi2/output/deps/npm`.
- **hermeto-fetch-npm.sh:** Multiple source dirs (edit the `sources` array) → Hermeto fetches each → rsync merges into one output dir.

**pip packages**

- **download-pip-packages.py:** Single (or per-call) `requirements.txt` with hashes → parses packages, resolves PyPI URLs, wget into `cachi2/output/deps/pip`; skips if file exists, always verifies checksum. Generate hashes e.g. with `uv pip compile pyproject.toml -o requirements.txt --generate-hashes`.

---

## 1. create-rpm-lockfile.sh

Builds the `notebook-rpm-lockfile` image (from `Dockerfile.rpm-lockfile`), runs it with the repo mounted, and executes `rpm-lockfile-prototype` against the given image’s `prefetch-input` directory to produce `rpms.lock.yaml` with exact RPM URLs and checksums per arch.

### Usage

```bash
./scripts/lockfile-generators/create-rpm-lockfile.sh \
  [--activation-key VALUE] \
  [--org VALUE] \
  --image-dir VALUE \
  [--download]
```

### Options

| Option | Description |
|--------|-------------|
| `--activation-key VALUE` | Red Hat activation key for subscription-manager (optional). |
| `--org VALUE` | Red Hat organization ID for subscription-manager (optional). |
| `--image-dir VALUE` | Path to image directory that contains `prefetch-input/rpms.in.yaml` (required). |
| `--download` | After generating the lockfile, run `download-rpms.sh` to fetch RPMs and create DNF repo metadata. |
| `--help` | Show help and exit. |

### Examples

```bash
# Lockfile only (uses ODH base image when no subscription)
./scripts/lockfile-generators/create-rpm-lockfile.sh --image-dir=codeserver/ubi9-python-3.12

# With Red Hat subscription and RPM download
./scripts/lockfile-generators/create-rpm-lockfile.sh \
  --activation-key=my-key \
  --org=my-org \
  --image-dir=codeserver/ubi9-python-3.12 \
  --download
```

---

## 2. create-artifact-lockfile.py

Reads `artifacts.in.yaml`, downloads each artifact (or uses existing cache under `cachi2/output/deps/generic/`), computes SHA-256, and writes `artifacts.lock.yaml` in the same directory with `download_url`, `checksum`, and `filename`. Duplicate filenames are skipped.

**Requirements:** Python 3, PyYAML, `wget`.

### Usage

```bash
python scripts/lockfile-generators/create-artifact-lockfile.py \
  --artifact-input=path/to/artifacts.in.yaml
```

**Input format:** Each entry can have `url` (required), optional `filename`, optional `checksum` (validated if present). Short form: `- url: https://...` (filename from URL).

---

## 3. download-rpms.sh

Reads an RPM lockfile (`rpms.lock.yaml`), downloads each RPM into `cachi2/output/deps/rpm`, verifies checksums when `yq` is available, and runs `createrepo_c` (or `createrepo`, or a container fallback) so the directory can be used as a DNF repo (e.g. with `local.repo`).

**Requirements:** `wget`; `yq` recommended for parsing and checksum verification. On macOS, createrepo runs inside the `notebook-rpm-lockfile` image via podman.

### Usage

```bash
./scripts/lockfile-generators/download-rpms.sh --lock-file path/to/rpms.lock.yaml
```

**Example**

```bash
./scripts/lockfile-generators/download-rpms.sh \
  --lock-file=codeserver/ubi9-python-3.12/prefetch-input/rpms.lock.yaml
```

---

## 4. download-npm.sh

Extracts `resolved` URLs from a single `package-lock.json` with `jq`, then downloads each package into `cachi2/output/deps/npm`. Scoped packages are saved as `scope-filename`. Must be run from the repository root.

**Requirements:** `jq`, `wget`.

### Usage

```bash
./scripts/lockfile-generators/download-npm.sh --lock-file path/to/package-lock.json
```

---

## 5. hermeto-fetch-npm.sh

Same goal as **download-npm.sh** (fetch npm packages for offline/Cachi2 use), but uses the [Hermeto Project](https://github.com/hermetoproject/hermeto) in a container: it fetches dependencies **per source directory** (each with its own `package.json`/package-lock.json), then the script merges all results into one output directory using rsync. Edit the `sources` array in the script to choose which directories to fetch. Output directory is configurable (default e.g. `cachi2/output/deps/npm-test`).

**Requirements:** Podman, network access. Some repos may need an `origin` remote.

---

## 6. download-pip-packages.py

Prefetches pip (Python) dependencies from a `requirements.txt` that contains hashes (e.g. from `uv pip compile ... --generate-hashes`). Parses the file, resolves download URLs from PyPI, and downloads each wheel/sdist into `cachi2/output/deps/pip` (or `-o` path). Skips download if a file with matching SHA-256 already exists; always verifies checksum after download or when skipping.

**Requirements:** Python 3, `wget`.

### Usage

```bash
python scripts/lockfile-generators/download-pip-packages.py [ -o OUTPUT_DIR ] requirements.txt
```

**Example**

```bash
python scripts/lockfile-generators/download-pip-packages.py \
  -o ./cachi2/output/deps/pip \
  codeserver/ubi9-python-3.12/requirements.txt
```

**Input:** `requirements.txt` with `--hash=sha256:...` lines (e.g. generated by `uv pip compile pyproject.toml -o requirements.txt --generate-hashes --emit-index-url --python-version=3.12`). `uv` can be included in `pyproject.toml` so it appears in the compiled requirements.

---

## 7. rewrite-cachi2-path.sh

**Sourced** by other scripts or Dockerfile `RUN` steps (do not run as a standalone script). Defines `rewrite_cachi2_path <file>`: rewrites npm registry URLs and relative `file:` paths to `file:///cachi2/output/deps/npm/` in `package-lock.json` or `npm-shrinkwrap.json`.

**Requirements:** `perl`.

---

## 8. utils.sh

Invoked **inside** the RPM lockfile generator container by `create-rpm-lockfile.sh`. Parses `prefetch-input=...` (or a positional path), detects OS and subscription-manager, then runs `rpm-lockfile-prototype rpms.in.yaml` in the mounted prefetch directory. Not meant to be run directly from the host.

---

## Supporting files

| File | Purpose |
|------|---------|
| `Dockerfile.rpm-lockfile` | Builds the image used by `create-rpm-lockfile.sh` (includes `rpm-lockfile-prototype`). |
| `rhsm-pulp.repo` | Example repo file for Red Hat subscription / Pulp. |
