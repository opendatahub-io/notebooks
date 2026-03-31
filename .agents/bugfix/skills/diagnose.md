# Skill: Diagnose Root Cause

Deep investigation of the bug's root cause with evidence.

## Inputs

Continues from `skills/start.md`. Expects the issue context is already loaded.

## Procedure

### 1. Targeted Search by Category

Based on the bug category from start phase:

**Dockerfile/build**: Read the relevant Dockerfile. Check base image, COPY paths, package install commands, layer ordering. Compare Dockerfile.cpu with Dockerfile.konflux.cpu for drift.

**Python dependency**: Read pyproject.toml and lock files. Check version constraints. Search for the package import that's failing. Check inheritance chain (minimal -> datascience -> specialized).

**Test infrastructure**: Read the failing test file. Trace the code path. Check fixtures, conftest.py, test markers.

**Manifest/version**: Read imagestream YAML. Check tag patterns. Compare with Makefile variables and params-latest.env.

**Security/CVE**: Identify the vulnerable package and current version. Check if it's a direct
or transitive dependency. Use manifest-box SBOMs (see `triage/reference/manifestbox.md`) to
confirm the package is actually in the shipped image, not just in source-scan material.
Distinguish ecosystem: Python deps use `cve-constraints.txt`; npm in code-server requires
an upstream version bump; Go and RPM are case-by-case. If the package is only in source-scan
paths (`/tests/...`, `jupyter/utils/addons/`), route to VEX closure instead of a code fix.
For upstream dependencies, inspect actual release artifacts — source tree metadata may show
a fix that the released artifact does not yet contain.

**CI/CD pipeline**: Read the pipeline config. Check for missing steps, wrong parameters, syntax errors.

### 2. History Investigation

```bash
git log --oneline -20 -- <affected-files>
git blame <file> -L <relevant-lines>
```

Look for: when was the problem introduced? Was there a recent change that caused it?

### 3. Research (via Subagent)

For complex issues, launch an **Explore subagent** to:
- Search GitHub PRs for similar fixes (`gh search prs --repo opendatahub-io/notebooks "<keywords>"`)
- Search Slack for prior discussions about this issue
- Check related repos if the issue might span boundaries
- Check if there's a customer support case referenced

The subagent returns a **summary** — do not bring raw search results into main context.

### 4. Write Root Cause Analysis

Save to `.artifacts/bugfix/{key}/root-cause.md`:

```markdown
# Root Cause: RHAIENG-XXXX

## Summary
{one-sentence root cause}

## Evidence
- {file:line — what's wrong}
- {git blame — when it was introduced}
- {related PR or discussion}

## Affected Files
- {file1} — {what needs to change}
- {file2} — {what needs to change}

## Recommended Fix
{specific changes}

## Confidence
{High/Medium/Low} — {why}
```

### 5. HITL Checkpoint

Present the root cause analysis to the user. Wait for confirmation before proceeding to `skills/fix.md`.

If confidence is below 80%, recommend stopping and applying `ai-could-not-fix` label:
```text
mcp__atlassian__editJiraIssue  issueKey=<key>  fields={"labels": [...existing, "ai-could-not-fix"]}
```
Add a comment explaining why confidence is low and what was investigated.
