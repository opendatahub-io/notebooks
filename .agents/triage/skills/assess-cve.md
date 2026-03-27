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

### 1.5. Cross-Project Label Search

Search Jira for all issues with the CVE ID label across all accessible projects:

```jql
labels = "CVE-XXXX-XXXXX" ORDER BY project ASC, updated DESC
```

Group results by project key. Note:
- `OCPBUGS` issues for the same `pscomponent` (e.g., `ose-cli`) → downstream component owner is
  already tracking; check their status/resolution before deep notebooks investigation
- `RHOAIENG` children → expected, these are the blocked vulnerabilities
- Other project hits (`AAP`, `SRVCOM`, `SECURESIGN`) → shared exposure, may show handling patterns

If the search shows the component is tracked in another project with a clear handling path
(fixed, not-affected, or assigned to an engineering team), reference that in the assessment
instead of duplicating the investigation.

### 2. Check for a Sibling Tracker First

Before doing the full workflow, check whether the same CVE was already triaged for another
supported RHOAI version.

- If a sibling tracker already has a solid assessment, reuse its reasoning structure.
- Still verify the current tracker's branch/version-specific facts.
- Do NOT trust the sibling Jira comment by itself; use it as a pointer for what to verify next.

This is especially useful for pairs like `[rhoai-2.25]` and `[rhoai-3.3]`, where the
package family and blocked image families are often the same.

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
- **RPM / shipped CLI tool** cases where the same component may be intentionally installed across
  many image families

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

For broad Go/RPM trackers spanning many image families, do not classify the tracker before this
manifest-box step. The first question is whether the vulnerable component is really shipped.

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
- repo-only Go tooling paths such as `scripts/buildinputs/go.mod`, `scripts/buildinputs/go.sum`, `ci/dockerfile/go.sum`, or other non-image helper inputs → likely source-scan or build-tooling evidence, not a notebooks runtime dependency
- shipped CLI paths such as `/usr/bin/skopeo` → real shipped runtime/tooling component; not a VEX `Component not Present` case

### 6. Query OSV API for Fix Version

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

### 7. Check Package Version Across Supported Versions

**CVE trackers are version-specific**: a `[rhoai-3.3]` tracker → only check rhoai-3.3 and
newer (main). Don't check 2.25/2.16 — they have their own trackers if affected.

Currently supported RHOAI versions (see `guidelines.md` for full table):
- **2.16 EUS** — branches `release-2024a`/`release-2024b` in red-hat-data-services/notebooks (ends June 30, 2026)
- **2.25 EUS** — branch `rhoai-2.25` in red-hat-data-services/notebooks
- **3.3** — branch `rhoai-3.3` in red-hat-data-services/notebooks
- **main** — local checkout (upcoming RHOAI 3.4+)

For Python packages, prefer the exact lock artifact the image build consumes. If you use a
simplified path for speed, say so explicitly in the comment and do not let it override
shipped-image SBOM evidence.

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

### 8. Query Red Hat Security Data API

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

For RPM / shipped-tool cases, also check:
- whether the RHEL package itself (for example `skopeo`) is still `Affected`
- whether the canonical Product Security Bugzilla is still open
- whether there is a released RHEL / AppStream erratum for this exact CVE

### 9. Check for False Positives and Mixed Trackers

**Critical**: Konflux source SBOM scans the entire repo (RHAIENG-3006). The package may be in the SBOM but NOT in the specific image. Check:
- Use manifest-box image-specific SBOMs first (see `reference/manifestbox.md`)
- Is the package present in a shipped runtime path, or only in repo/test/source-scan paths?
- Is the package in `pyproject.toml` for the affected image, or only in a different image?
- If false positive: do not transition children here. Route them to `skills/close-vex.md` / `/triage-close-vex` and get user approval before setting "Not a Bug" with VEX "Component not Present".

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

### 10. For Python CVEs: Check cve-constraints.txt

```bash
grep "<package>" dependencies/cve-constraints.txt
```
If already constrained, the fix may already be in place.

### 11. Determine Fixability

- **Python, package present in the image and in our pyproject.toml**: ai-fixable — bump version, add to cve-constraints.txt, refresh locks
- **Python, transitive dep present in the image**: ai-fixable — add to cve-constraints.txt, refresh locks
- **npm in code-server runtime path**: ai-nonfixable in this repo — likely needs a code-server version bump or upstream remediation path
- **npm only in `jupyter/utils/addons/` source-scan paths**: currently treat as likely false positive — review for VEX instead of planning a dependency update
- **npm only in `/tests/...` or other source-scan-only paths**: false positive — do not transition here; route to `skills/close-vex.md` / `/triage-close-vex` for VEX review with user approval
- **Go present in shipped tooling/binary paths**: case-by-case, often nonfixable in this repo if remediation is upstream or in another bundled component
- **Go only in repo-tooling/source paths** (for example `scripts/buildinputs/go.mod`, `ci/dockerfile/go.sum`, or other helper inputs): treat as likely source-scan/external-component evidence until manifest-box proves shipped runtime presence
- **RPM-installed shipped tool / binary** (for example `/usr/bin/skopeo`): usually `ai-nonfixable` unless a fixed Red Hat package is already available for the branch's RHEL/AppStream source. This is a real shipped exposure, not a VEX false positive; next step is checking Red Hat security data, Bugzilla, and errata.
- **False positive (not in image)**: do not transition here; route to `skills/close-vex.md` / `/triage-close-vex` for VEX review with user approval
- **Mixed tracker**: usually parent `ai-nonfixable` until child issues are split into real vs VEX candidates
- **Commit fix but no release**: nonfixable — monitor upstream
- **Real shipped exposure, but waiting on Red Hat package fix / erratum**: keep `ai-nonfixable`, explain that the component is shipped and needed, and document that remediation is blocked on package availability rather than notebooks-side source changes

### 12. Useful Scripts

- `scripts/cve/create_cve_trackers.py` — creates RHAIENG tracker issues from orphan RHOAIENG CVEs. Run `./uv run scripts/cve/create_cve_trackers.py --dry-run` to preview.
- `scripts/cve/cve_due_dates.py` — lists overdue trackers, syncs due dates from children. Run `./uv run scripts/cve/cve_due_dates.py --list-overdue`.
- `scripts/group_cves_by_id.py` — groups CVE issues by CVE ID for bulk analysis.
- `scripts/cve/sbom_analyze.py` — inspects SBOM files and shows package type, location, and `sourceInfo`
- `scripts/cve/fetch_manifestbox_sbom.py` — resolves and downloads one manifest-box SBOM JSON via GitLab API + Git LFS

**Sandbox note**: `./uv run` may fail in sandboxed environments because `uv` writes
temp files outside the workspace (e.g., `~/.local/share/uv/tools/`). If that happens,
either request `all` permissions or invoke the script directly with `python3` when the
script does not require venv-specific dependencies.

### 13. Label and Comment

Apply `ai-triaged` + `ai-fixable` or `ai-nonfixable`. Post comment with:
- Version table across affected versions (from tracker version up to main)
- Fix version from OSV API and/or child issue description
- Ecosystem and location
- Fix approach
- Due date awareness
- If the tracker is mixed, separate real remediation targets from VEX `Component not Present` candidates

**Sync labels locally immediately**: after the Jira `editJiraIssue` call succeeds,
update the ledger entry's `labels` array to match what was just written to Jira.
Do not defer this to the report phase. The report skill reads labels from the ledger
to determine fixability counts; stale labels produce wrong reports.

**Sibling tracker pattern**: for same CVE on a different RHOAI version (e.g., `[rhoai-2.25]`
after already triaging `[rhoai-3.3]`), reference the prior assessment and just check the
version-specific branch and shipped-image evidence. No need to repeat the full investigation.
