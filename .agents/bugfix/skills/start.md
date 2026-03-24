# Skill: Start Bugfix

Load a Jira issue, understand the context, and present a fix plan for user approval.

## Inputs

- `$ARGUMENTS`: Jira issue key (e.g., `RHAIENG-3611`). Required.

## Procedure

### 1. Fetch Issue

Call `mcp__atlassian__getJiraIssue` with the issue key. Extract:
- Summary, description, priority, status, labels, assignee
- Any existing AI triage comments

### 2. Verify Readiness

- Check for `ai-fixable` label. If absent, warn the user: "This issue is not labeled ai-fixable. Proceed anyway?"
- Check if it already has an execution label (`ai-fully-automated`, `ai-could-not-fix`, `ai-verification-failed`). If so, warn: "This issue was already attempted."

### 3. Load Triage Assessment

If `.artifacts/triage/ledger.json` exists and has an entry for this key, read the assessment (category, files to modify, steps to resolve). This saves re-analysis.

If no assessment exists, do a quick classification using the logic from `triage/skills/assess.md` steps 2-4.

### 4. Identify Affected Files

Based on the assessment category and error description:
- Use **Grep** to find files matching error messages, package names, or component names
- Use **Glob** to list candidate files (e.g., `*/Dockerfile.*`, `*/pyproject.toml`)
- Summarize which files likely need changes

### 5. Create Artifacts Directory

```bash
mkdir -p .artifacts/bugfix/RHAIENG-XXXX
```

### 6. Present Plan

Show the user:
```
Issue: RHAIENG-XXXX — {summary}
Priority: {priority} | Category: {category}

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
