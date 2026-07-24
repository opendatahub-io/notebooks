# Python CVE Resolution Guide

This guide documents the workflow for resolving CVEs in Python packages within the OpenDataHub Notebooks images.

> **Acknowledgment**: This workflow was contributed by Adriana Theodorakopoulou.

## Overview

Python CVEs in notebook images can come from:
- **Direct dependencies**: Packages explicitly listed in `pyproject.toml`
- **Transitive dependencies**: Packages pulled in by direct dependencies

The resolution strategy differs based on which type is affected.

## Centralized dependency rules

Global lock inputs live under `dependencies/` and are always passed to
`uv pip compile` during `make refresh-lock-files`:

| File | uv flag | Purpose |
|------|---------|---------|
| `dependencies/constraints.txt` | `--constraints` | Global version **floors** (`package>=X`) |
| `dependencies/overrides.txt` | `--override` | Global **forced pins/ranges** when a floor is insufficient |
| `pyproject.toml` `[tool.uv.override-dependencies]` | (from pyproject) | **Image-specific** overrides |

See [`dependencies/README.md`](../../dependencies/README.md) for format rules and branch policy.

**Prefer `constraints.txt` over `overrides.txt`.** Put shared rules in the `.txt`
files; put subset-specific rules in individual `pyproject.toml` files.

### `constraints.txt` structure

Two sections:

```text
# --- CVE-motivated floors ---
# RHAIENG-XXXX: CVE-YYYY-ZZZZ short description
package>=fixed_version

# --- General floors ---
# Non-CVE policy/resolver floors
other-package>=version
```

Keep **one line and one comment per package** (most restrictive floor only).
Do not maintain a historical ledger of superseded CVE fixes.

### Branch policy

| Repo / branch | When to update `constraints.txt` |
|---------------|----------------------------------|
| `opendatahub-io/notebooks` `main` | Lock-renewal auto-syncs with the latest AIPCC index. Once a fixed version is on AIPCC, lock renewal picks it up — do not add constraints solely to track a fix the index already ships. |
| `red-hat-data-services/notebooks` `rhoai-x.y` | Audit proof of what the release enforces. **Keep updating** when backporting CVE fixes. |

### How it works

1. **Constraints file format** (requirements.txt style):
   ```
   # RHAIENG-XXXX: CVE-YYYY-ZZZZ description
   package>=fixed_version
   ```

2. **Automatic application**: `scripts/pylocks_generator.py` always passes
   `--constraints` and `--override` for the global files to all lock generations.

3. **Override for conflicts**: When a floor is insufficient or loses resolver
   conflicts, use `dependencies/overrides.txt` (global) or `override-dependencies`
   in a specific image's `pyproject.toml` (image-specific).

### Adding a new CVE constraint

1. Add the constraint to `dependencies/constraints.txt` in the CVE section:
   ```
   # RHAIENG-XXXX: CVE-YYYY-ZZZZZ package_name vulnerability description
   # Upstream: https://github.com/...
   package_name>=fixed_version
   ```
   On `main`, only add if the resolver/index sync alone cannot guarantee the floor.
   On `rhoai-x.y` release branches, add to document and enforce the fix.

2. Regenerate all lock files:
   ```bash
   make refresh-lock-files
   # or
   bash scripts/pylocks_generator.sh public-index
   ```

3. If resolution fails due to conflicts, add `override-dependencies` to the affected image's `pyproject.toml`.

## CVE Resolution Workflow

### Step 1: Identify the Package and Affected Images

Example: RHAIENG-2448 - Tornado quadratic DoS repeated header

1. Open the Jira ticket and identify the package name (e.g., "tornado")
2. Check which images are affected (often all images from minimal to trustyai, tensorflow, pytorch, etc.)
3. Open one of the linked Jiras from ProdSec to see the summary

### Step 2: Determine the Fixed Version

From the CVE summary, identify:
- **Affected versions**: e.g., "version 6.5.2 and below"
- **Fixed version**: e.g., "fixed in version 6.5.3"

### Step 3: Search for the Package in the Repository

```bash
# Search in pyproject.toml files
grep -r "tornado" --include="pyproject.toml" .

# Search in pylock.toml files
grep -r "tornado" --include="pylock.toml" .
```

Determine if it's a:
- **Direct dependency**: Found in `pyproject.toml`
- **Transitive dependency**: Only found in `pylock.toml`

### Step 4: Identify the Source of Transitive Dependencies

For transitive dependencies, find which direct dependency pulls it in:

```bash
# Using uv (preferred)
uv tree | grep -A5 -B5 tornado

# Or check the package's dependents
uv tree --invert tornado
```

Example: Tornado is typically pulled in by `jupyter-server`.

### Step 4.5: Verify Package Availability on the RH Index

Before attempting to fix the CVE, check that the fixed version is actually available
on the RH index. A version may exist on PyPI but not on the RH index — this is a
common blocker for downstream (RHOAI) images.

```bash
# Check which versions are on the production RH index
curl -sL "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.4/cpu-ubi9/simple/<package>/?format=json" \
  | python3 -c "
import json,sys
data = json.load(sys.stdin)
versions = sorted({f['filename'].split('-')[1] for f in data.get('files',[])})
print('\n'.join(versions))
"
```

There are **three layers** that can block a CVE fix from resolving:

1. **RH index**: The fixed version may not have been built by AIPCC yet.
   If missing, request it via the [AIPCC dashboard](https://dashboard.aipcc.redhat.com/package-request).

2. **Builder constraints**: The `wheels/builder` project may pin an older version
   in `collections/torch-*/constraints.txt`. For example, `onnx==1.20.0` was pinned
   with `# AIPCC-7623 - Constraining onnx while we carry patches`, preventing
   1.21.0 from appearing on the index even after the onboarding pipeline ran.
   Check with: `glab api --hostname gitlab.com "projects/58339326/search?scope=blobs&search=<package>%3D%3D"`

3. **Upstream SDK exact pins**: Packages like `codeflare-sdk` may exact-pin the
   vulnerable version (e.g., `cryptography==46.0.6`, `ray[data]==2.53.0`). These
   conflicts surface during `make refresh-lock-files` as "unsatisfiable" errors.
   Coordinate with the owning team per the
   [component-team-owned packages](https://gitlab.cee.redhat.com/data-hub/guide/-/blob/main/docs/notebooks/cves/python.md)
   procedure.

If the fixed version is not on the RH index, **do not proceed to Step 5** — the
lock refresh will fail. Instead, request the build and revisit once it is available.

### Step 5: Resolve the CVE

#### Option A: Upgrade the Direct Dependency

1. Check the latest version on [pypi.org](https://pypi.org)
2. Check the upstream package's `pyproject.toml` to see their version constraints
3. Update the version in your `pyproject.toml`:
   ```toml
   "jupyter-server~=2.17.0",  # Updated for tornado CVE fix
   ```

#### Option B: Use Centralized CVE Constraints

If the direct dependency can't be upgraded but the transitive package version is flexible:

1. Add to `dependencies/constraints.txt` (CVE section):
   ```
   # RHAIENG-2448: CVE-XXXX-YYYY tornado quadratic DoS
   tornado>=6.5.3
   ```

2. Regenerate lock files - the constraint will be applied automatically.

#### Option C: Use Override Dependencies (Last Resort)

If there are version conflicts that prevent constraint-based resolution:

```toml
[tool.uv]
override-dependencies = [
    # RHAIENG-2448: CVE-XXXX-YYYY tornado - override needed due to version conflict
    "tornado>=6.5.3",
]
```

**Note**: Override dependencies force the specified version, potentially breaking packages that genuinely can't work with it. Use sparingly.

### Step 6: Regenerate Lock Files and Build

```bash
# Regenerate lock files
make refresh-lock-files

# Build the affected image(s)
make jupyter-datascience-ubi9-python-3.12
```

### Step 7: Validate the Fix

#### Downstream (Konflux) - Clair Scan

1. Go to Konflux and find the Tekton build pipeline for your image
2. Open the **clair-scan** task logs
3. Search for the CVE number (e.g., `CVE-2024-XXXXX`)
4. If the CVE is **not found** in the logs, the fix is validated

#### Upstream (GitHub Actions) - Trivy

1. Go to the "push build notebooks" GitHub Action
2. Check the "Vulnerability Report by Trivy" section
3. Search for the CVE number
4. If the CVE is **not present** after the fix, validation is successful

**Note**: Trivy is more sensitive than Konflux's Clair scan. A CVE may appear in Trivy but not in Clair. Always validate against the downstream Konflux scans for production images.

## Example: Complete CVE Resolution

### Scenario: CVE-2025-66418 in urllib3

1. **Identify**: urllib3 decompression vulnerability, affects all images
2. **Fixed version**: urllib3 >= 2.6.0
3. **Type**: Transitive dependency (pulled in by many packages)
4. **Conflict**: odh-elyra depends on appengine-python-standard which requires urllib3<2

**Solution**:
1. Add to `dependencies/constraints.txt` for general protection:
   ```
   # RHAIENG-2458: CVE-2025-66418 urllib3 decompression vulnerability
   urllib3>=2.7.0
   ```

2. Add override to jupyter images with odh-elyra (due to conflict):
   ```toml
   override-dependencies = [
       # RHAIENG-2458: CVE-2026-44431 urllib3 - override (also CVE-2025-66418) needed because odh-elyra pulls in
       # appengine-python-standard which has an obnoxious urllib3<2 constraint
       "urllib3>=2.7.0",
   ]
   ```

## Best Practices

1. **Always add to centralized constraints first** - This prevents CVEs from returning through any dependency path.

2. **Use override-dependencies sparingly** - Only when there's a genuine conflict that constraints can't resolve.

3. **Document the CVE** - Include RHAIENG ticket, CVE ID, and explanation in comments.

4. **Validate in both Trivy and Clair** - Trivy may catch issues Clair misses.

5. **Consider upstream fixes** - If a direct dependency has a newer version that fixes the transitive CVE, prefer upgrading the direct dependency.

## Related Files

- `dependencies/constraints.txt` - Global version floors (CVE and general sections)
- `dependencies/overrides.txt` - Global forced pins/ranges
- `dependencies/README.md` - Format rules and branch policy
- `scripts/pylocks_generator.py` - Lock file generator (applies global inputs)
- `pyproject.toml` - Direct dependencies and override-dependencies
- `pylock.toml` / `uv.lock.d/` - Generated lock files

## Useful Commands

```bash
# Regenerate all lock files
make refresh-lock-files

# Regenerate lock files for specific directory
bash scripts/pylocks_generator.sh public-index jupyter/datascience/ubi9-python-3.12

# Check dependency tree
uv tree

# Find what depends on a package
uv tree --invert package-name

# Search for package in repository
grep -r "package-name" --include="*.toml" .
```
