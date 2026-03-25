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

### 3. Read Representative Child Issues

Do NOT generalize from one child when the tracker spans multiple image families.

Read one linked RHOAIENG child per distinct `pscomponent:` family when possible:
- one `codeserver` child if present
- one representative `jupyter-*` child
- one representative `runtime-*` child if runtimes are also blocked

For each representative child, extract:
- **Fix version**: in the description if present
- **`pscomponent:` label**: identifies the container image (e.g., `pscomponent:rhoai/odh-pipeline-runtime-pytorch-rocm-py312-rhel9`)
- Note the issuetype is `Vulnerability` (not Bug)

If all children clearly belong to the same family, one child is enough.

### 4. Fetch Image-Specific SBOMs From Manifest-box Early

When built-image presence is uncertain, manifest-box is the primary evidence source.
Use it before deep repo inference for:
- **Node.js/npm** CVEs
- **mixed trackers** spanning multiple image families
- **Python** CVEs where source files may not match shipped image contents
- **Go** CVEs where the vulnerable code may be in embedded tooling, a bundled binary, or another repo

Fetch one SBOM per representative child family for tracker-level triage.
For closing individual children, fetch the exact SBOM for each child's `pscomponent:` image (see below).

To derive the `--component` argument from a child's `pscomponent:` label:
1. Read the label (e.g., `pscomponent:rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9`)
2. Strip the `rhoai/` prefix
3. Use the remainder as the `--component` substring

If you already have an SBOM JSON file locally, use the repo tool:
```bash
./uv run scripts/cve/sbom_analyze.py <sbom.json> <package_name>
```

If you need to fetch one from manifest-box, follow `reference/manifestbox.md`.
Use the lightweight GitLab API + Git LFS workflow there instead of downloading the large SQLite DB when you only need a small number of files.

**SBOM version must match tracker version.** If tracker says `[rhoai-3.3]`, use v3-3 SBOMs,
not v2-25. Different versions have different packages.
**Always verify `build_component` after download** — confirm it contains the expected version
suffix (e.g., `v3-3`). Use `--expect-version v3-3` with the helper script to fail loudly on mismatch.
"First/second matching digest" is never evidence by itself.

Treat manifest-box `sourceInfo` as primary evidence for whether a component is really in the shipped image.
Repo lockfiles and source grep are secondary evidence.

**Triage vs closure evidence thresholds:**
- **Tracker-level triage**: representative-family sampling (one SBOM per family) is acceptable
- **Closing individual child issues**: requires exact per-child SBOM proof (see `skills/close-vex.md`)

### 5. Identify Ecosystem and Location

Based on the package name and manifest-box `sourceInfo` / location:
- **Python**: real runtime paths look like `/usr/lib/python*/site-packages/` or `/opt/app-root/lib/python*/site-packages/`
- **Node.js (npm)**: likely in code-server (`/usr/lib/code-server/`). Paths under `/jupyter/utils/addons/` are currently source-scan artifacts in our images, not shipped runtime content.
- **Go**: often appears via bundled binaries, embedded tooling, or other repos; use SBOM location first
- **RPM**: base image concern (AIPCC)

Location patterns matter:
- `/usr/lib/code-server/.../node_modules/...` → real shipped code-server npm component
- `/tests/browser/pnpm-lock.yaml` or other `/tests/...` paths → likely source-scan / test-only false positive
- `/jupyter/utils/addons/pnpm-lock.yaml` → currently source-scan artifact from repository content; likely VEX `Component not Present` candidate unless image-specific SBOM evidence shows otherwise

### 6. Check Package Version Across Supported Versions

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

For Python and npm, use branch files to compare versions only after confirming package presence in the image.
Do not let repo inspection override manifest-box evidence about whether the package is actually shipped.

### 7. Query Red Hat Security Data API

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

### 8. Check for False Positives and Mixed Trackers

**Critical**: Konflux source SBOM scans the entire repo (RHAIENG-3006). The package may be in the SBOM but NOT in the specific image. Check:
- Use manifest-box image-specific SBOMs first (see `reference/manifestbox.md`)
- Is the package present in a shipped runtime path, or only in repo/test/source-scan paths?
- Is the package in `pyproject.toml` for the affected image, or only in a different image?
- If false positive: all children should be closed as "Not a Bug" with VEX "Component not Present" (use `skills/close-vex.md`)

**False positive pattern: dev deps in source scan.** A package may exist in the top-level
`pyproject.toml` (dev dependency) or `uv.lock` (transitive of MCP SDK, etc.) but not in any
workbench image's pyproject.toml or lock files. The manifestbox SBOM for hermetic builds
correctly excludes them, but non-hermetic image SBOMs include the repo source scan →
false positive CVE tickets. VEX justification: "Component not Present" (in the shipped container).

**False positive pattern: test-only npm paths.** If manifest-box shows the package only under
`/tests/...` (for example `/tests/browser/pnpm-lock.yaml`), treat it as a likely source-scan
false positive and route toward VEX review rather than remediation.

**Mixed tracker pattern.** Some children may be real while others are false positives.
Example: code-server images may carry a real runtime npm dependency under `/usr/lib/code-server/...`,
while Jupyter or runtime images only pick it up from `/tests/...`.
In this case:
- keep the parent tracker `ai-nonfixable`
- identify which image families are real remediation targets
- identify which image families are likely VEX `Component not Present` candidates
- do NOT let one real child justify all blocked children

**"Commit fix but no release" pattern.** Upstream may have a commit fix but no release
containing it. In this case:
- Mark as `ai-nonfixable` (can't bump to a version that doesn't exist yet)
- Note the commit hash in the assessment for tracking
- Monitor upstream for a release
- Don't try to pin to a git commit — pyproject.toml/cve-constraints.txt work with released versions

**Source-vs-release divergence pattern.** Upstream repo `main` or a git tag may show the
fix (e.g., `package.json` declares `undici ^7.24.0`), but the published release artifact
still ships the vulnerable version (e.g., `undici 7.19.0` in the tarball). For customer-impact
decisions, the released artifact wins. Inspect actual release tarballs or manifest-box SBOMs,
not source tree metadata.

**Anti-patterns to avoid:**
- Do not infer child-level closure eligibility from one representative image family
- Do not assume the second matching SBOM file is the right product version
- Do not proceed from "likely" or "representative" language into actual Jira transitions
- Stop and verify the exact image if there is any version or digest ambiguity

### 9. For Python CVEs: Check cve-constraints.txt

```bash
grep "<package>" dependencies/cve-constraints.txt
```
If already constrained, the fix may already be in place.

### 10. Determine Fixability

- **Python, package present in the image and in our pyproject.toml**: ai-fixable — bump version, add to cve-constraints.txt, refresh locks
- **Python, transitive dep present in the image**: ai-fixable — add to cve-constraints.txt, refresh locks
- **npm in code-server runtime path**: nonfixable by us — needs code-server version bump or upstream remediation path
- **npm only in `jupyter/utils/addons/` source-scan paths**: currently treat as likely false positive — review for VEX instead of planning a dependency update
- **npm only in `/tests/...` or other source-scan-only paths**: false positive — close with VEX
- **Go present in shipped tooling/binary paths**: case-by-case, often nonfixable in this repo if remediation is upstream or in another bundled component
- **RPM**: nonfixable — AIPCC base image concern
- **False positive (not in image)**: close with VEX
- **Mixed tracker**: usually parent `ai-nonfixable` until child issues are split into real vs VEX candidates
- **Commit fix but no release**: nonfixable — monitor upstream

### 11. Useful Scripts

- `scripts/cve/create_cve_trackers.py` — creates RHAIENG tracker issues from orphan RHOAIENG CVEs. Run `./uv run scripts/cve/create_cve_trackers.py --dry-run` to preview.
- `scripts/cve/cve_due_dates.py` — lists overdue trackers, syncs due dates from children. Run `./uv run scripts/cve/cve_due_dates.py --list-overdue`.
- `scripts/group_cves_by_id.py` — groups CVE issues by CVE ID for bulk analysis.
- `scripts/cve/sbom_analyze.py` — inspects SBOM files and shows package type, location, and `sourceInfo`
- `scripts/cve/fetch_manifestbox_sbom.py` — resolves and downloads one manifest-box SBOM JSON via GitLab API + Git LFS

### 12. Label and Comment

Apply `ai-triaged` + `ai-fixable` or `ai-nonfixable`. Post comment with:
- Version table across affected versions (from tracker version up to main)
- Fix version from OSV API and/or child issue description
- Ecosystem and location
- Fix approach
- Due date awareness
- If the tracker is mixed, separate real remediation targets from VEX `Component not Present` candidates

**Sibling tracker pattern**: for same CVE on a different RHOAI version (e.g., `[rhoai-2.25]`
after already triaging `[rhoai-3.3]`), reference the prior assessment and just check the
version-specific branch. No need to repeat the full investigation.
