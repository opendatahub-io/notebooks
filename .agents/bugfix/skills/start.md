# Skill: Start Bugfix

Load a Jira issue, understand the context, and present a fix plan for user approval.

## Inputs

- `$ARGUMENTS`: Jira issue key (e.g., `RHAIENG-3611`). Required.
  Must match pattern `[A-Z]+-[0-9]+`. Reject other formats immediately.

## Procedure

### 1. Fetch Issue

Call `mcp__atlassian__getJiraIssue` with the issue key. If the call fails (network error,
404, auth failure), report the error and stop — do not proceed with a partial or missing issue.

Extract:
- Summary, description, priority, status, labels, assignee
- Any existing AI triage comments

### 2. Verify Readiness

- Check for `ai-fixable` label. If absent, warn the user: "This issue is not labeled ai-fixable. Proceed anyway?"
- Check if it already has a terminal execution label (`ai-fully-automated`, `ai-accelerated-fix`, `ai-could-not-fix`, `ai-verification-failed`). If so, warn: "This issue was already attempted." (`regressions-found` is post-merge and does not by itself mean the fix workflow is incomplete.)
- If not already known from preflight: ask the user if they have a **remote machine with podman**
  available via SSH for image pulls, container tests, and large artifact downloads (manifest-box
  SBOMs, upstream release tarballs). Record the answer — it determines whether verification
  steps run locally or remotely. See `triage/reference/remote-artifact-investigation.md` for
  SSH patterns.

### 2.2. Determine Execution Target

Use the Jira title, triage assessment, and `triage/guidelines.md` supported-version table to
decide where the fix belongs:

- **ODH / mainline path**: ODH checkout on `main`
- **RHOAI z-stream path**: `red-hat-data-services/notebooks` on `rhoai-X.Y`

For release-branch work:
- fetch the latest target branch before diagnose
- record the exact target ref in the start summary
- do not proceed from a stale `rhds/rhoai-X.Y` remote-tracking branch

### 2.5. Early Short-Circuit Checks

Stop before diagnose if any of these apply:

- **Not Python/Node.js + using `/fix-cve`**: `fix-cve.md` covers Python and Node.js CVEs. For
  Go or RPM CVEs, stop and explain the correct remediation path instead.
- **Mixed tracker**: if the tracker spans multiple image families and only a subset are real
  remediation targets, the correct action is triage + VEX closure (see `triage/skills/close-vex.md`),
  not a code fix.
- **No released upstream fix**: if the vulnerable component comes from an upstream project
  (e.g., code-server, VS Code) and no released artifact from that project contains the fix,
  stop with "awaiting upstream release" rather than attempting a speculative version bump.
- **Source-vs-release divergence**: if upstream source `main` shows the fix but the latest
  released artifact still ships the vulnerable version, document the divergence and stop.

### 3. Load Triage Assessment

If `.artifacts/triage/ledger.json` exists and has an entry for this key, read the assessment (category, files to modify, steps to resolve). This saves re-analysis.

If the ledger entry is `previously-assessed` or `assessment` is null, fall back to the latest AI
triage Jira comment and build a minimal local summary from that plus repo evidence. Do not assume
the ledger always contains enough structured fix detail.

If no assessment exists, do a quick classification using the logic from `triage/skills/assess.md`
steps 2-4.

### 4. Identify Affected Files

Based on the assessment category and error description:
- Use **Grep** to find files matching error messages, package names, or component names
- Use **Glob** to list candidate files (e.g., `*/Dockerfile.*`, `*/pyproject.toml`)
- For dependency CVEs on release branches, explicitly probe the branch-local fix mechanism:
  - shared `dependencies/cve-constraints.txt`
  - shared dependency subprojects under `dependencies/`
  - direct image-local `pyproject.toml` / lock updates
  - branch-local `uv` / `uv.toml` or other lock-refresh toolchain expectations
- Summarize which files likely need changes

### 5. Create Artifacts Directory

```bash
mkdir -p ".artifacts/bugfix/${ISSUE_KEY}"
```

(Replace `${ISSUE_KEY}` with the actual key, e.g., `mkdir -p .artifacts/bugfix/RHAIENG-3611`)

### 6. Present Plan

Show the user:
```text
Issue: RHAIENG-XXXX — {summary}
Priority: {priority} | Category: {category}
Execution target: {odh-main | rhds/rhoai-X.Y} @ {ref}

Root cause hypothesis: {brief explanation}

Files to modify:
- path/to/file1 — {what needs to change}
- path/to/file2 — {what needs to change}

Proposed approach:
1. {step 1}
2. {step 2}
3. ...

Test plan:
- make test
- {additional tests}

Proceed to /fix-diagnose? [waiting for user confirmation]
```

## Next Step

Wait for user confirmation, then proceed to `skills/diagnose.md`.

If the user declines:
- Do not proceed to diagnose or fix
- Do not apply any labels or comments to Jira
- Report "Fix declined by user" and stop cleanly
