# Skill: Create PR and Update Jira

Push the fix, create a PR, and update Jira labels/comments.

## Inputs

Continues from `skills/test.md`. All tests pass on the feature branch.

## HITL Checkpoint

Show the user what will be done before proceeding:
- Branch name and diff summary
- PR title and body draft
- Jira label changes
- Wait for user confirmation

## Procedure

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

{Summary of test results — which tests ran, all passed}

## Jira

https://redhat.atlassian.net/browse/RHAIENG-XXXX

Generated with [Claude Code](https://claude.com/claude-code)
PREOF
)"
```

### 4. Update Jira Labels

Fetch current labels, append `ai-fully-automated`:
```json
{
  "fields": {
    "labels": ["...existing...", "ai-fully-automated"]
  }
}
```

### 5. Add Jira Comment

Post a comment linking to the PR:
```
AI Fix Applied - {date}
PR: {pr-url}
Summary: {what was fixed}
Tests: All passing (make test, ruff, pyright)
Status: Awaiting human review
```

### 6. Clean Up

```bash
git checkout -
```

Return to the branch you were on before starting.

### 7. Report

```
Fix complete for RHAIENG-XXXX
PR: {url}
Jira: labeled ai-fully-automated, comment added
Branch: fix/{key}-{desc}
```
