# Package Update Procedure

This document describes the procedure for updating Python package versions across all notebook images in this repository. The process is driven by automated tests and lock file generation tools.

## Overview

The package update workflow consists of three main steps:

1. **Update `pyproject.toml` files** with new package versions
2. **Regenerate lock files** using `make refresh-lock-files`
3. **Verify alignment** using `make test`

## Key Concepts

### pyproject.toml

Each notebook image has a `pyproject.toml` file that declares its Python dependencies with version specifiers (e.g., `boto3~=1.42.29`). These files are located in directories like:

- `jupyter/datascience/ubi9-python-3.12/pyproject.toml`
- `runtimes/pytorch/ubi9-python-3.12/pyproject.toml`
- `codeserver/ubi9-python-3.12/pyproject.toml`

### pylock.toml

Lock files (`pylock.toml`) contain the exact resolved versions with SHA256 hashes for reproducible builds. These are generated from `pyproject.toml` files.

### Manifest Files

ImageStream manifests in `manifests/base/` contain version metadata displayed in the OpenShift/ODH Dashboard UI. These must be kept in sync with actual package versions.

## Step-by-Step Procedure

### 1. Update pyproject.toml Files

Edit the `pyproject.toml` files to update package versions. When updating a package that appears in multiple images, **you must update it consistently across all images** to maintain version alignment.

Common packages that must be aligned across images include:
- `boto3`, `kafka-python-ng`, `matplotlib`, `numpy`, `pandas`
- `plotly`, `scikit-learn`, `scipy`, `kfp`
- `psycopg`, `pyodbc`, `mysql-connector-python`, `pymongo`
- `onnxconverter-common`, `skl2onnx`, `feast`

### 2. Regenerate Lock Files

Use the `make refresh-lock-files` target to regenerate all lock files:

```bash
# Regenerate all lock files using auto-detected index mode
make refresh-lock-files

# Regenerate for a specific directory
make refresh-lock-files DIR=jupyter/datascience/ubi9-python-3.12

# Use public PyPI index explicitly
make refresh-lock-files INDEX_MODE=public-index

# Use internal Red Hat (AIPCC) index
make refresh-lock-files INDEX_MODE=rh-index
```

#### Index Modes

The `scripts/pylocks_generator.sh` script supports three modes:

| Mode | Description |
|------|-------------|
| `auto` (default) | Uses `rh-index` if `uv.lock.d/` exists, otherwise `public-index` |
| `public-index` | Uses public PyPI, generates/updates `pylock.toml` |
| `rh-index` | Uses internal AIPCC indexes, generates `uv.lock.d/pylock.<flavor>.toml` |

#### Force Upgrade

To upgrade all packages to their latest compatible versions:

```bash
FORCE_LOCKFILES_UPGRADE=1 make refresh-lock-files
```

### 3. Update Manifest Files

When package versions change, update the corresponding manifest files in `manifests/base/`:

```yaml
# Example: manifests/base/jupyter-datascience-notebook-imagestream.yaml
opendatahub.io/notebook-python-dependencies: |
  [
    {"name": "Boto3", "version": "1.42"},
    {"name": "Scikit-learn", "version": "1.8"},
    ...
  ]
```

Only the major.minor version is typically shown (e.g., `1.42` not `1.42.29`).

### 4. Run Tests to Verify

Run the test suite to verify all changes are consistent:

```bash
# On macOS
gmake test

# On Linux
make test
```

#### What the Tests Check

The `test_image_pyprojects_version_alignment` test verifies:

1. **Version Alignment**: All `pyproject.toml` files use the same version for shared packages
2. **Lock File Consistency**: Versions in `pylock.toml` match specifiers in `pyproject.toml`
3. **Manifest Consistency**: Versions in manifest YAML files match versions in `pylock.toml`
4. **Dependency Presence**: All declared dependencies exist in the lock file

Example test failures:

```
SUBFAILED: boto3 has multiple specifiers: [~=1.42.29, ~=1.40.52]
  → Fix: Update all pyproject.toml files to use the same boto3 version

SUBFAILED: Version of boto3~=1.42.29 in pyproject.toml does not match version='1.40.76' in pylock.toml
  → Fix: Regenerate lock files with `make refresh-lock-files`

SUBFAILED: Scikit-learn: manifest declares 1.7, but pylock.toml pins 1.8.0
  → Fix: Update the manifest YAML file
```

## Common Scenarios

### Adding a New Package

1. Add the package to the appropriate `pyproject.toml` file(s)
2. Run `make refresh-lock-files DIR=<directory>`
3. Update manifest files if the package should be displayed in the UI
4. Run `make test` to verify

### Upgrading a Package Across All Images

1. Search for all occurrences: `grep -r "package-name" --include="pyproject.toml"`
2. Update all `pyproject.toml` files with the new version
3. Run `make refresh-lock-files` to regenerate all lock files
4. Update manifest files with new version numbers
5. Run `make test` to verify alignment

### Handling GA Blockers

When a package is not available in the AIPCC index, you may need to:

1. Comment out the dependency in `pyproject.toml` with a TODO and Jira reference:
   ```toml
   # TODO(RHAIENG-XXXX): Re-enable package-name before RHOAI X.Y GA
   # "package-name~=1.0.0",
   ```

2. Move the manifest entry to a YAML comment:
   ```yaml
   # TODO(RHAIENG-XXXX): Re-enable Package-Name before RHOAI X.Y GA
   # {"name": "Package-Name", "version": "1.0"}
   ```

3. Create a Jira ticket to track re-enabling the package

### Using Override Dependencies

For dependency conflicts, use `override-dependencies` in `pyproject.toml`:

```toml
[tool.uv]
override-dependencies = [
    # AIPCC-8698: python-lsp-server[all] has conflicting requirements
    "python-lsp-server>=1.11.0",
]
```

## Troubleshooting

### Lock File Generation Fails

1. Check if the package version exists in the target index
2. Use `scripts/list_aipcc_packages.py` to query available versions:
   ```bash
   python3 scripts/list_aipcc_packages.py --package boto3 --versions
   ```
3. Try a different version or add override-dependencies

### Version Alignment Test Fails

1. Search for all occurrences of the package across pyproject.toml files
2. Ensure all files use the same version specifier
3. Regenerate lock files after making changes

### Manifest Mismatch

1. Check which manifest file is referenced in the error message
2. Update the version number in the manifest's JSON array
3. Only update the N version (current), not N-1 (previous release)

## Related Files

- `scripts/pylocks_generator.sh` - Lock file generation script
- `tests/test_main.py` - Version alignment tests
- `Makefile` - Build targets (`test`, `refresh-lock-files`)
- `manifests/base/*.yaml` - ImageStream manifest files

## See Also

- [Developer Guide](developer-guide.md) - General development information
- [AGENTS.md](../AGENTS.md) - Instructions for AI agents
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
