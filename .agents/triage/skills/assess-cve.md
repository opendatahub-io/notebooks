# Skill: Assess CVE Tracker

Triage a CVE tracker issue (RHAIENG-XXXX that blocks RHOAIENG Vulnerability issues).

## Inputs

- `$ARGUMENTS`: RHAIENG tracker issue key (e.g., `RHAIENG-3755`). Required.

## Procedure

### 1. Read the Tracker

Fetch the tracker via `mcp__atlassian__getJiraIssue`. Extract:
- CVE ID and description from summary (e.g., `CVE-2026-32597 PyJWT...`)
- Affected RHOAI version from title suffix (e.g., `[rhoai-3.3]`)
- `duedate` — this is the remediation deadline
- Labels: `CVE`, `CVE-XXXX-XXXXX`, `security`
- Linked issues (outward "blocks" links → RHOAIENG Vulnerability children)

### 2. Read ONE Child Issue

Fetch one linked RHOAIENG child to get:
- **Fix version**: in the description (e.g., "fixed in 2.12.0")
- **`pscomponent:` label**: identifies the container image (e.g., `pscomponent:rhoai/odh-pipeline-runtime-pytorch-rocm-py312-rhel9`)
- Note the issuetype is `Vulnerability` (not Bug)

### 3. Identify Ecosystem

Based on the package name, determine the ecosystem:
- **Python** (~80%): check pylock.toml / pyproject.toml
- **Node.js (npm)**: likely in code-server (`/usr/lib/code-server/`) or Jupyter addons (`jupyter/utils/addons/`). Use `scripts/cve/sbom_analyze.py` + manifestbox to locate.
- **Go**: local utils or esbuild in RStudio
- **RPM**: base image concern (AIPCC)

### 4. Check Package Version Across Supported Versions

Currently supported RHOAI versions (check all four):
- **2.16 EUS** — branches `release-2024a`/`release-2024b` in red-hat-data-services/notebooks (ends June 30, 2026)
- **2.25 EUS** — branch `rhoai-2.25` in red-hat-data-services/notebooks
- **3.3** — branch `rhoai-3.3` in red-hat-data-services/notebooks
- **main** — local checkout (upcoming RHOAI 3.4+)

For Python packages, use `curl -sL` for large pylock.toml files:
```bash
curl -sL "https://raw.githubusercontent.com/red-hat-data-services/notebooks/<branch>/jupyter/datascience/ubi9-python-3.12/pylock.toml" | grep -A1 'name = "<package>"'
```

For main, check locally:
```bash
grep -A1 '^name = "<package>"' jupyter/datascience/ubi9-python-3.12/uv.lock
```

Build the 4-version table.

### 5. Locate Package in Image (manifestbox + sbom_analyze.py)

If you have a manifestbox SBOM JSON file for the affected image, use the repo's built-in tool:
```bash
./uv run scripts/cve/sbom_analyze.py <sbom.json> <package_name>
```

This shows the package type (npm/Python/RPM), install location, and source info — critical for determining the ecosystem and fix approach.

See also `reference/manifestbox.md` for how to fetch SBOM files from the manifest-box repo.

### 6. Check for False Positives (continued) (SBOM source scan issue)

**Critical**: Konflux source SBOM scans the entire repo (RHAIENG-3006). The package may be in the SBOM but NOT in the specific image. Check:
- Is the package in `pyproject.toml` for the affected image, or only in a different image?
- Use manifestbox image-specific SBOM to verify (see `reference/manifestbox.md`)
- If false positive: all children should be closed as "Not a Bug" with VEX "Component not Present" (use `skills/close-vex.md`)

### 6. For Python CVEs: Check cve-constraints.txt

```bash
grep "<package>" dependencies/cve-constraints.txt
```
If already constrained, the fix may already be in place.

### 7. Determine Fixability

- **Python, package in our pyproject.toml**: ai-fixable — bump version, add to cve-constraints.txt, refresh locks
- **Python, transitive dep only**: ai-fixable — add to cve-constraints.txt, refresh locks
- **npm in code-server**: nonfixable by us — needs code-server version bump
- **npm in jupyter addons**: fixable — update pnpm-lock.yaml in `jupyter/utils/addons/`
- **Go**: case-by-case
- **RPM**: nonfixable — AIPCC base image concern
- **False positive (not in image)**: close with VEX

### 8. Useful Scripts

- `scripts/cve/create_cve_trackers.py` — creates RHAIENG tracker issues from orphan RHOAIENG CVEs. Run `./uv run scripts/cve/create_cve_trackers.py --dry-run` to preview.
- `scripts/cve/cve_due_dates.py` — lists overdue trackers, syncs due dates from children. Run `./uv run scripts/cve/cve_due_dates.py --list-overdue`.
- `scripts/group_cves_by_id.py` — groups CVE issues by CVE ID for bulk analysis.

### 9. Label and Comment

Apply `ai-triaged` + `ai-fixable` or `ai-nonfixable`. Post comment with:
- Version table across 2.16/2.25/3.3/main
- Fix version from child issue description
- Ecosystem and location
- Fix approach
- Due date awareness
