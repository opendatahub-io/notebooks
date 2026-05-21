# Skill: Create PR and Update Jira

Push the fix, create a PR, and update Jira labels/comments.

## Inputs

Continues from `skills/test.md`.

Supported entry states:
- **All tests pass** on the feature branch
- **Baseline failures** were documented and the user approved a draft-PR handoff path

## HITL Checkpoint

Show the user what will be done before proceeding:
- Branch name and diff summary
- Exact files that will be committed
- PR title and body draft
- Jira label changes (`ai-fully-automated`, `ai-accelerated-fix`, or `ai-verification-failed` from `.artifacts/bugfix/{key}/test-handoff.md`; see `triage/reference/label-taxonomy.md`)
- Wait for user confirmation

## Procedure

### 0. Verify Commit Scope

Before committing:
- run `git diff --name-only --cached` (or the equivalent)
- confirm that only the intended fix files are staged
- if unexpected files are staged, unstage them before continuing

### 1. Commit

```bash
git add <specific-files>
git commit -m "$(cat <<'COMMITEOF'
RHAIENG-XXXX: {short description of the fix}

{Brief explanation of what was wrong and how it was fixed.}

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

### 2. Push

```bash
git push -u origin fix/{key}-{desc}
```

### 3. Create PR

```bash
gh pr create --title "RHAIENG-XXXX: {short description}" --body "$(cat <<'PREOF'
## Summary

{1-3 bullet points describing the fix}

## Root Cause

{Brief root cause from .artifacts/bugfix/{key}/root-cause.md}

## Changes

{List of files changed and why}

## Test Results

{Summary of test results — either all passed, or baseline failures outside the fix scope}

## Jira

https://redhat.atlassian.net/browse/RHAIENG-XXXX

Generated with [Claude Code](https://claude.com/claude-code)
PREOF
)"
```

### 4. Update Jira Labels

Read `.artifacts/bugfix/{key}/test-handoff.md` and parse:
- `test_failure_cycles` (default `0` if missing)
- `verification_result` (`all_pass` or `baseline_failures`)

| `test_failure_cycles` | Append this label |
|------------------------|-------------------|
| `0` | `ai-fully-automated` |
| `>= 1` | `ai-accelerated-fix` |

If `verification_result = baseline_failures`, append `ai-verification-failed` instead of a success label and keep the PR in **draft** state.

Fetch current labels. Remove any stale execution labels (`ai-fully-automated`,
`ai-accelerated-fix`, `ai-could-not-fix`, `ai-verification-failed`) first, then append
exactly one of the above (never both):

```json
{
  "fields": {
    "labels": ["...existing...", "ai-fully-automated"]
  }
}
```

(use `ai-accelerated-fix` instead when `test_failure_cycles >= 1`)

### 5. Add Jira Comment

Post a comment linking to the PR:
```text
AI Fix Applied - {date}
PR: {pr-url}
Summary: {what was fixed}
Tests: {All passing | Baseline failures documented}
Status: {Awaiting human review | Draft PR opened because baseline verification is incomplete}
```

### 6. Clean Up

```bash
git checkout -
```

Return to the branch you were on before starting.

### 7. Report

```text
Fix complete for RHAIENG-XXXX
PR: {url}
Jira: labeled {ai-fully-automated|ai-accelerated-fix|ai-verification-failed}, comment added
Branch: fix/{key}-{desc}
```
