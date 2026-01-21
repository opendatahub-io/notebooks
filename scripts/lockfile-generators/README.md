```markdown
# RPM & Artifact Lockfile Helpers

This directory contains a small collection of scripts that help you generate
lockfiles for RPMs and generic artifacts, download the referenced packages,
and build a container image that runs the lockfile generator.

> **Important** – All scripts must be executed from the repository root
> Eg. `./scripts/lockfile-generators/create-rpm-lockfile --...etc`

---

## Table of Contents

| Script | Purpose |
|--------|---------|
| `create-rpm-lockfile` | Builds a container image and runs `rpm-lockfile-prototype` to generate an RPM lockfile from `rpms.in.yaml`. |
| `create-artifact-lockfile.py` | Generates `artifacts.lock.yaml` from `artifacts.in.yaml`. |
| `download-rpms` | Downloads all RPMs referenced in an RPM lockfile. |

---

## 1. `create-rpm-lockfile`

### Usage

```bash
./scripts/lockfile-generators/create-rpm-lockfile \
  [--activation-key=KEY] \
  [--org=ORG] \
  --image-dir=DIR
```

### What it does

1. **Builds a container image** (`notebook-rpm-lockfile`) from
   `Dockerfile.rpm-lockfile`.  
   The first build may take several minutes; subsequent runs are fast.

2. **Runs the lockfile generator** inside the container, mounting the
   repository into `/workspace` and executing `utils.sh` with the
   `prefetch-input` directory of the supplied image directory.

### Arguments

| Option | Description |
|--------|-------------|
| `--activation-key=VALUE` | Red Hat activation key for `subscription-manager` (optional). |
| `--org=VALUE` | Red Hat organization ID for `subscription-manager` (optional). |
| `--image-dir=VALUE` | Path to a directory containing `rpms.*.yaml` files (required). |
| `--help` | Show help and exit. |

### Example

```bash
# Run without subscription
./scripts/lockfile-generators/create-rpm-lockfile --image-dir=codeserver/ubi9-python-3.12

# Run with subscription and a prefetch directory
./scripts/lockfile-generators/create-rpm-lockfile \
  --activation-key=my-key \
  --org=my-org \
  --image-dir=codeserver/ubi9-python-3.12
```

---

## 2. `create-artifact-lockfile.py`

### Purpose

Generates `artifacts.lock.yaml` from `artifacts.in.yaml`.  
The script downloads each artifact (if a checksum is not supplied), computes
its SHA‑256 hash, and writes a lockfile that contains:

- `download_url`
- `checksum` (prefixed with `sha256:`)
- `filename` (including any directory prefix)

### Usage

```bash
python create-artifact-lockfile.py --artifact-input=path/to/artifacts.in.yaml
```

### Key Features

- Handles both short‑form (`url:`) and long‑form (`url:`, `filename:`,
  `checksum:`) entries.
- Caches downloaded files under `cachi2/output/deps/generic`.
- Skips duplicate filenames.
- Prints progress and a summary of the generated lockfile.

---

## 3. `download-rpms`

### Purpose

Downloads all RPMs referenced in an RPM lockfile (`rpms.lock.yaml`).

### Usage

```bash
./scripts/lockfile-generators/download-rpms --lock-file <path-to-lockfile>
```

### How it works

1. **Validates** that the script is run from the project root.
2. **Parses** the lockfile (using `yq` if available, otherwise falls back to
   `grep`/`sed`).
3. **Downloads** each RPM into `cachi2/output/deps/rpm`.
4. **Verifies** checksums (if `yq` is available).

### Example

```bash
# Download RPMs for the codeserver image
./scripts/lockfile-generators/download-rpms \
  --lock-file=codeserver/ubi9-python-3.12/prefetch-input/rpms.lock.yaml
```