# Skill: Fix a Python CVE

Implement a fix for an ai-fixable Python CVE on the main branch.

## Inputs

- `$ARGUMENTS`: RHAIENG tracker issue key (e.g., `RHAIENG-3755`). Required.

## Prerequisites

- The tracker must be assessed (`ai-fixable` label) with a known fix version
- Python ecosystem CVE (not npm/Go/RPM)

## Procedure

### 1. Load Context

Read the tracker's triage comment to get:
- Package name and fix version
- Which images are affected (from `pscomponent:` labels)
- Whether it's a direct or transitive dependency

### 2. Check cve-constraints.txt

Read `dependencies/cve-constraints.txt`. If the package is already constrained:
- Update the version constraint if the new fix version is higher
If not present:
- Add a new entry with the CVE reference

Format:
```
# CVE-XXXX-XXXXX: Description
# Reference: https://access.redhat.com/security/cve/CVE-XXXX-XXXXX
package-name>=X.Y.Z
```

### 3. Check if Direct Dependency

Search for the package in pyproject.toml files:
```bash
grep -r "<package>" */*/pyproject.toml
```

If it's a **direct dependency**: bump the version constraint in the affected pyproject.toml files.
If it's **transitive only**: the cve-constraints.txt entry is sufficient — it will be applied during lock refresh.

### 4. Refresh Lock Files

```bash
# Targeted refresh (faster)
./uv run scripts/pylocks_generator.py auto jupyter/datascience/ubi9-python-3.12

# Or full refresh
gmake refresh-lock-files
```

### 5. Verify

```bash
# Check the package version in the refreshed lock
grep -A1 'name = "<package>"' jupyter/datascience/ubi9-python-3.12/uv.lock

# Run consistency tests
make test
```

### 6. Create Branch and PR

Branch: `fix/{tracker-key}-cve-{package}`

PR body should reference:
- The RHAIENG tracker
- The CVE ID
- Which images are affected
- The version bump (old → new)

### 7. Update Tracker

Add `ai-fully-automated` label. Comment with PR link.

## Notes

- See `reference/cve-python.md` (→ `docs/cves/python.md`) for the full Python CVE resolution guide
- For transitive deps: `cve-constraints.txt` is the mechanism, not editing pyproject.toml
- After the fix lands on main, it flows to RHOAI via the normal upstream → downstream process
- For z-stream fixes on release branches: go directly to `rhoai-X.Y` in `red-hat-data-services/notebooks`
