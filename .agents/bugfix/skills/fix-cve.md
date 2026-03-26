# Skill: Fix a Python or Node.js CVE

Implement a fix for an ai-fixable Python or Node.js CVE on the main branch.

## Inputs

- `$ARGUMENTS`: RHAIENG tracker issue key (e.g., `RHAIENG-3755`). Required.

## Prerequisites

- The tracker must be assessed (`ai-fixable` label) with a known fix version
- **Python or Node.js ecosystem CVE only** (not Go/RPM)
- If the CVE is Go or RPM: **stop** — this skill does not apply.
- If no released upstream version contains the fix: **stop** — document "awaiting upstream
  release" and do not attempt speculative version bumps

## Procedure

### 1. Load Context

Read the tracker's triage comment to get:
- Package name and fix version
- Which images are affected (from `pscomponent:` labels)
- Whether it's a direct or transitive dependency
- **Ecosystem**: Python (PyPI) or Node.js (npm)

Branch to the appropriate procedure below. Step 1 applies to both ecosystems;
per-ecosystem steps restart at 2.

---

## Python CVE Procedure

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

---

## Node.js CVE Procedure

### 2. Determine the source of the vulnerability

Use `reference/cve-nodejs.md` (→ `docs/cves/nodejs.md`) to identify the source. Check the
manifest-box SBOM `sourceInfo` to determine where the vulnerable package comes from:

- `tests/containers` or `tests/browser` → **false positive** (test-only, Component Not Present)
- `jupyter/utils/addons` → **false positive** (source-scan artifact, Component Not Present)
- `/usr/lib/code-server/...` → **true finding** (code-server runtime)
- `rstudio/utils` → **true finding** (RStudio components)

For false positives: route to VEX closure (`skills/close-vex.md`), not a code fix.

### 3. Update the vulnerable package

For **code-server**, **RStudio**, or **JupyterLab** npm dependencies (packages under
`/usr/lib/code-server/`, IDE runtime paths):
- We never patch individual node packages inside these IDEs.
- The only fix is finding a newer release of the IDE (code-server, RStudio, JupyterLab) that
  is not affected, and upgrading to that release.
- Searching for such a release and proposing the upgrade is valuable triage/fix work.
- If the vulnerable package is a deep transitive of the IDE and no unaffected release exists:
  mark as `ai-nonfixable` and document "awaiting upstream release."

For **rstudio/utils** or **jupyter/utils/addons** (our own lockfiles, maintenance fix):
- In the directory containing `package.json`, run:
  ```bash
  pnpm update --latest
  ```
- Commit the updated `pnpm-lock.yaml`

### 4. Verify

```bash
# Check the lockfile for the updated version
grep "<package>" <path>/pnpm-lock.yaml

# Run tests
make test
```

---

## Common Steps (both ecosystems)

### 6. Create Branch and PR

Branch: `fix/{tracker-key}-cve-{package}`

PR body should reference:
- The RHAIENG tracker
- The CVE ID
- Which images are affected
- The version bump (old → new)

### 7. Update Tracker

Add **one** success label (same rules as `skills/pr.md` / `label-taxonomy.md`):

- `ai-fully-automated` — verification (`make test`, lock checks) passed on the first try with no test-failure cycle in this CVE workflow.
- `ai-accelerated-fix` — you had to re-run verification or adjust the fix after at least one failed test or check before opening the PR.

Comment with PR link.

## Notes

- See `reference/cve-python.md` (→ `docs/cves/python.md`) for the full Python CVE resolution guide
- See `reference/cve-nodejs.md` (→ `docs/cves/nodejs.md`) for the Node.js CVE resolution guide
- For Python transitive deps: `cve-constraints.txt` is the mechanism, not editing pyproject.toml
- After the fix lands on main, it flows to RHOAI via the normal upstream → downstream process
- For z-stream fixes on release branches: go directly to `rhoai-X.Y` in `red-hat-data-services/notebooks`
