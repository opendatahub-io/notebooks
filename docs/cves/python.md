# Python CVE Resolution Guide

This guide documents the workflow for resolving CVEs in Python packages within the OpenDataHub Notebooks images.

> **Acknowledgment**: This workflow was contributed by Adriana Theodorakopoulou.

## Overview

Python CVEs in notebook images can come from:
- **Direct dependencies**: Packages explicitly listed in `pyproject.toml`
- **Transitive dependencies**: Packages pulled in by direct dependencies

The resolution strategy differs based on which type is affected.

## Centralized CVE Constraints

To prevent CVEs from returning through transitive dependencies, we maintain a centralized constraints file:

```
dependencies/cve-constraints.txt
```

This file is automatically applied during lock file generation via `uv pip compile --constraints`. It ensures that even packages not explicitly in `pyproject.toml` (transitive dependencies) never go below the fixed version for CVEs we've resolved.

### How It Works

1. **Constraints file format** (requirements.txt style):
   ```
   # CVE-ID: Description
   # Reference: https://...
   package>=fixed_version
   ```

2. **Automatic application**: The `pylocks_generator.sh` script applies these constraints to all lock file generations.

3. **Override for conflicts**: Some packages (like odh-elyra's appengine-python-standard) have conflicting version requirements. For these, use `override-dependencies` in the specific image's `pyproject.toml`.

### Adding a New CVE Constraint

1. Add the constraint to `dependencies/cve-constraints.txt`:
   ```
   # RHAIENG-XXXX: CVE-YYYY-ZZZZZ package_name vulnerability description
   # Upstream: https://github.com/...
   package_name>=fixed_version
   ```

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

1. Add to `dependencies/cve-constraints.txt`:
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
1. Add to `dependencies/cve-constraints.txt` for general protection:
   ```
   # RHAIENG-2458: CVE-2025-66418 urllib3 decompression vulnerability
   urllib3>=2.6.0
   ```

2. Add override to jupyter images with odh-elyra (due to conflict):
   ```toml
   override-dependencies = [
       # RHAIENG-2458: CVE-2025-66418 urllib3 - override needed because odh-elyra pulls in
       # appengine-python-standard which has an obnoxious urllib3<2 constraint
       "urllib3>=2.6.0",
   ]
   ```

## Best Practices

1. **Always add to centralized constraints first** - This prevents CVEs from returning through any dependency path.

2. **Use override-dependencies sparingly** - Only when there's a genuine conflict that constraints can't resolve.

3. **Document the CVE** - Include RHAIENG ticket, CVE ID, and explanation in comments.

4. **Validate in both Trivy and Clair** - Trivy may catch issues Clair misses.

5. **Consider upstream fixes** - If a direct dependency has a newer version that fixes the transitive CVE, prefer upgrading the direct dependency.

## Component-Team-Owned Packages

> [!WARNING]
> Some Python packages in our images are developed by other Red Hat teams (feast, codeflare-sdk, kubeflow-training, llmcompressor). CVEs in these packages or their transitive dependencies require coordination with the owning team -- do **not** bump versions unilaterally. See the procedure below.

These packages have two distribution paths:
- **Upstream** (`pylock.toml`): installed from PyPI (`files.pythonhosted.org`)
- **Downstream/RHOAI** (`uv.lock.d/pylock.*.toml`): installed from AIPCC rh-index (`packages.redhat.com/api/pulp-content/public-rhai/rhoai/...`)

A CVE fix therefore requires both an upstream PyPI release **and** an AIPCC rebuild of the fixed version for downstream images.

### Contact Table

| Package | Owning Team | Slack Channel | Team Handle | Key Contacts |
|---------|-------------|---------------|-------------|--------------|
| feast | Feature Store | `TODO` | `TODO` | `TODO` |
| codeflare-sdk | Distributed Workloads | `TODO` | `TODO` | `TODO` |
| kubeflow-training | Training Kubeflow | `TODO` | `TODO` | `TODO` |
| llmcompressor | Model Optimization | `TODO` | `TODO` | `TODO` |

### Procedure

#### Step 1: Alert the Component Team Immediately

Post in the current release channel (e.g. `#wg-3_4-openshift-ai-release`) and tag the relevant team handle from the contact table above. Include:
- CVE ID and severity
- Affected package and vulnerable version
- Which notebook images are affected
- Whether the CVE is in the SDK itself or in a transitive dependency

Use the team-specific `#forum-...` channel from the table for follow-up discussion.

#### Step 2: Communicate AIPCC Build Need

These packages are served from the AIPCC rh-index in downstream (RHOAI) images. After the component team releases a fixed version to PyPI, an AIPCC build is needed so the fixed wheel appears in the rh-index. Tell the component team whether the AIPCC build is needed for the current release.

See [trigger_aipcc_self_serve_pipeline.md](trigger_aipcc_self_serve_pipeline.md) and [intro-to-aipcc.md](intro-to-aipcc.md) for how to verify availability and trigger test builds.

#### Step 3: Update the Package Per Team Instructions

After the component team develops and releases a fix (and the AIPCC build is available for downstream), bump the version in the relevant `pyproject.toml` files and regenerate both upstream and downstream locks.

Where each package is declared:
- **feast**: direct dep in `jupyter/datascience/ubi9-python-3.12/pyproject.toml` and other images that list it
- **codeflare-sdk**: direct dep in `jupyter/datascience/ubi9-python-3.12/pyproject.toml` and other images that list it
- **kubeflow-training**: pinned in `dependencies/odh-notebooks-meta-workbench-datascience-deps/pyproject.toml` (consumed by all datascience-derived images)
- **llmcompressor** (and related pins like compressed-tensors, transformers, etc.): pinned in `dependencies/odh-notebooks-meta-llmcompressor-deps/pyproject.toml`

### Fixing Transitive Dependency CVEs

When the CVE is not in the SDK itself but in one of its transitive dependencies (found via `uv tree --invert <package>`), there are two options -- both carry risk:

- **Option A: Update the SDK to a newer version** that pulls in the fixed transitive dep. Risk: a much newer SDK version may have version skew with the corresponding server component shipped in that RHOAI release, and the combination is untested.
- **Option B: Pin the transitive dep directly** via `dependencies/cve-constraints.txt` or `override-dependencies`. Risk: the SDK was not tested with that version of its dependency; subtle breakage is possible.

In either case, **discuss with the component team first** -- they know which approach is safe for their package. Do not make the decision unilaterally.

### Key Differences from Regular Python CVEs

- We don't control the release cadence -- the component team decides when to release
- Version bumps may require coordinated changes (API changes, new transitive deps)
- The component team may provide a patched version different from upstream
- Bumping to a much newer SDK version risks version skew with the server component in that RHOAI release
- Downstream images require an AIPCC rebuild of the fixed wheel before we can regenerate rh-index lock files
- Both upstream (`pylock.toml`) and downstream (`uv.lock.d/`) locks must be updated

## Related Files

- `dependencies/cve-constraints.txt` - Centralized CVE constraints
- `scripts/pylocks_generator.sh` - Lock file generator (applies constraints)
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
