# Skill: Fix a Python or Node.js CVE

Implement a fix for an ai-fixable Python or Node.js CVE on the correct target branch.

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
- Which supported RHOAI version the tracker targets (`rhoai-X.Y`) if this is a z-stream fix

Determine the execution target before editing:
- **Future / mainline-only work**: ODH checkout on `main`
- **Supported release / z-stream work**: `red-hat-data-services/notebooks` on the matching `rhoai-X.Y` branch

For release-branch work, fetch the latest target branch first and record the exact ref you are
using for the fix.

### 1.5. Probe the Branch-Local Fix Mechanism

Before editing anything, inspect how this branch expects dependency fixes to be applied:
- Does it have `dependencies/cve-constraints.txt` already?
- Does it use shared dependency subprojects under `dependencies/`?
- Are the affected images wired to those dependency subprojects in `pyproject.toml`?
- What lock refresh path does the branch use (`./uv`, explicit `uv tool run`, bare `uv`, `gmake`)?

Pick the narrowest branch-native mechanism:
1. shared CVE constraints file
2. shared dependency subproject pin
3. direct image-local dependency update

Do not assume the same mechanism exists on every release branch.

Branch to the appropriate procedure below. Step 1 applies to both ecosystems;
per-ecosystem steps restart at 2.

---

## Python CVE Procedure

### 2. Choose the Python Pin Location

Apply the fix using the branch-local mechanism discovered above:

- **Shared CVE constraints file**:
  - Read `dependencies/cve-constraints.txt`
  - If the package is already constrained, update the constraint if the new fix version is higher
  - If not present, add a new entry with the CVE reference

  Format:
  ```
  # CVE-XXXX-XXXXX: Description
  # Reference: https://access.redhat.com/security/cve/CVE-XXXX-XXXXX
  package-name>=X.Y.Z
  ```

- **Shared dependency subproject**:
  - Update the shared dependency project's `pyproject.toml`
  - Prefer this when multiple affected images already consume the same dependency subproject

- **Direct image-local dependency update**:
  - Use only when the branch does not provide a shared mechanism and the package is directly owned there

### 3. Check if Direct Dependency

Search for the package in relevant `pyproject.toml` files:
```bash
grep -r "<package>" */*/pyproject.toml
```

If it's a **direct dependency**: bump the version constraint in the affected `pyproject.toml` files.
If it's **transitive only**:
- the shared constraints file is sufficient when that mechanism exists on the branch
- otherwise prefer the smallest shared dependency project that actually owns the transitive path

### 4. Refresh Lock Files

```bash
# Targeted refresh (faster)
./uv run scripts/pylocks_generator.py auto <affected-dir>

# Or full refresh
gmake refresh-lock-files
```

For release-branch work, record the exact lock refresh toolchain used (`./uv`, explicit
`uv tool run uv@X.Y.Z`, or branch-local equivalent). Different branches may need different `uv`
versions or wrapper paths.

### 5. Verify

```bash
# Check the package version in the refreshed lock
grep -A1 'name = "<package>"' <affected-lockfile>

# Run consistency tests
gmake test
```

Use `make test` when `make` is GNU Make; use `gmake` on macOS when needed.

If a verification command fails:
- decide whether it is a **baseline branch failure** or a **regression introduced by this fix**
- only treat true regressions as fix-test loop failures
- if the target branch already fails broadly on unrelated checks, document that and route to the
  draft-PR / `ai-verification-failed` path instead of repeatedly fixing unrelated branch issues

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
- For Python transitive deps, prefer the branch-native shared mechanism (`cve-constraints.txt` or a shared dependency subproject) rather than duplicating pins across multiple image-local files
- After the fix lands on main, it flows to RHOAI via the normal upstream → downstream process
- For z-stream fixes on release branches: go directly to `rhoai-X.Y` in `red-hat-data-services/notebooks`
