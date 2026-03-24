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

### 2. Query OSV API for Fix Version

**Always check OSV before posting any version comparison.** Free, no auth, no rate limits.

```bash
curl -sX POST -d '{"package": {"name": "<package>", "ecosystem": "PyPI"}, "version": "<current_version>"}' \
  https://api.osv.dev/v1/query | python3 -c "
import sys,json
for v in json.load(sys.stdin).get('vulns',[]):
    for a in v.get('affected',[]):
        for r in a.get('ranges',[]):
            for e in r.get('events',[]):
                if 'fixed' in e: print(f'{v.get(\"aliases\",[\"\"])[0]}: fixed in {e[\"fixed\"]}')
"
```

Ecosystems: `PyPI` for Python, `npm` for Node.js. This gives exact fix versions — verify
the current version in each branch is actually >= the fix version before claiming "fixed."

### 3. Read ONE Child Issue

Fetch one linked RHOAIENG child to get:
- **Fix version**: in the description (e.g., "fixed in 2.12.0")
- **`pscomponent:` label**: identifies the container image (e.g., `pscomponent:rhoai/odh-pipeline-runtime-pytorch-rocm-py312-rhel9`)
- Note the issuetype is `Vulnerability` (not Bug)

### 4. Identify Ecosystem

Based on the package name, determine the ecosystem:
- **Python** (~80%): check pylock.toml / pyproject.toml
- **Node.js (npm)**: likely in code-server (`/usr/lib/code-server/`) or Jupyter addons (`jupyter/utils/addons/`). Use `scripts/cve/sbom_analyze.py` + manifestbox to locate.
- **Go**: local utils or esbuild in RStudio
- **RPM**: base image concern (AIPCC)

### 5. Check Package Version Across Supported Versions

**CVE trackers are version-specific**: a `[rhoai-3.3]` tracker → only check rhoai-3.3 and
newer (main). Don't check 2.25/2.16 — they have their own trackers if affected.

Currently supported RHOAI versions (see `guidelines.md` for full table):
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

Build the version table (from tracker version up to main).

**Fixes on main do NOT flow to release branches.** Each version needs its own fix
(separate PR on separate branch). Never claim "one fix covers all versions."

### 6. Query Red Hat Security Data API

Covers ALL Red Hat products including RHOAI. No auth needed.

```bash
curl -s "https://access.redhat.com/hydra/rest/securitydata/cve/CVE-XXXX-XXXXX.json" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for ps in d.get('package_state',[]):
    if 'rhoai' in ps.get('package_name','').lower() or 'notebook' in ps.get('package_name','').lower():
        print(f'{ps[\"fix_state\"]:15s} {ps[\"package_name\"]}')
"
```

Returns per-image fix state (Affected/Not affected/Fixed) for every RHOAI container.
Web UI: `https://access.redhat.com/security/cve/CVE-XXXX-XXXXX`

### 7. Locate Package in Image (manifestbox + sbom_analyze.py)

If you have a manifestbox SBOM JSON file for the affected image, use the repo's built-in tool:
```bash
./uv run scripts/cve/sbom_analyze.py <sbom.json> <package_name>
```

This shows the package type (npm/Python/RPM), install location, and source info — critical for determining the ecosystem and fix approach.

**SBOM version must match tracker version.** If tracker says `[rhoai-3.3]`, use v3-3 SBOM,
not v2-25. Different versions have different packages.

See also `reference/manifestbox.md` for how to fetch SBOM files from the manifest-box repo.

### 8. Check for False Positives

**Critical**: Konflux source SBOM scans the entire repo (RHAIENG-3006). The package may be in the SBOM but NOT in the specific image. Check:
- Is the package in `pyproject.toml` for the affected image, or only in a different image?
- Use manifestbox image-specific SBOM to verify (see `reference/manifestbox.md`)
- If false positive: all children should be closed as "Not a Bug" with VEX "Component not Present" (use `skills/close-vex.md`)

**False positive pattern: dev deps in source scan.** A package may exist in the top-level
`pyproject.toml` (dev dependency) or `uv.lock` (transitive of MCP SDK, etc.) but not in any
workbench image's pyproject.toml or lock files. The manifestbox SBOM for hermetic builds
correctly excludes them, but non-hermetic image SBOMs include the repo source scan →
false positive CVE tickets. VEX justification: "Component not Present" (in the shipped container).

**"Commit fix but no release" pattern.** Upstream may have a commit fix but no release
containing it. In this case:
- Mark as `ai-nonfixable` (can't bump to a version that doesn't exist yet)
- Note the commit hash in the assessment for tracking
- Monitor upstream for a release
- Don't try to pin to a git commit — pyproject.toml/cve-constraints.txt work with released versions

### 9. For Python CVEs: Check cve-constraints.txt

```bash
grep "<package>" dependencies/cve-constraints.txt
```
If already constrained, the fix may already be in place.

### 10. Determine Fixability

- **Python, package in our pyproject.toml**: ai-fixable — bump version, add to cve-constraints.txt, refresh locks
- **Python, transitive dep only**: ai-fixable — add to cve-constraints.txt, refresh locks
- **npm in code-server**: nonfixable by us — needs code-server version bump
- **npm in jupyter addons**: fixable — update pnpm-lock.yaml in `jupyter/utils/addons/`
- **Go**: case-by-case
- **RPM**: nonfixable — AIPCC base image concern
- **False positive (not in image)**: close with VEX
- **Commit fix but no release**: nonfixable — monitor upstream

### 11. Useful Scripts

- `scripts/cve/create_cve_trackers.py` — creates RHAIENG tracker issues from orphan RHOAIENG CVEs. Run `./uv run scripts/cve/create_cve_trackers.py --dry-run` to preview.
- `scripts/cve/cve_due_dates.py` — lists overdue trackers, syncs due dates from children. Run `./uv run scripts/cve/cve_due_dates.py --list-overdue`.
- `scripts/group_cves_by_id.py` — groups CVE issues by CVE ID for bulk analysis.

### 12. Label and Comment

Apply `ai-triaged` + `ai-fixable` or `ai-nonfixable`. Post comment with:
- Version table across affected versions (from tracker version up to main)
- Fix version from OSV API and/or child issue description
- Ecosystem and location
- Fix approach
- Due date awareness

**Sibling tracker pattern**: for same CVE on a different RHOAI version (e.g., `[rhoai-2.25]`
after already triaging `[rhoai-3.3]`), reference the prior assessment and just check the
version-specific branch. No need to repeat the full investigation.
