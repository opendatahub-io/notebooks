# Skill: Relabel / Retriage a Single Issue

Standalone skill for re-assessing and relabeling a single issue that was previously triaged.

## When to Use

- Initial verdict was wrong (e.g., marked fixable but actually needs cluster access)
- New information is available (e.g., more details added to the issue)
- Issue has the `ai-retriage` label

## Inputs

- `$ARGUMENTS`: issue key (e.g., `RHAIENG-3611`). Required.

## Procedure

1. Fetch the issue via `mcp__atlassian__getJiraIssue`.
2. Note existing labels and any previous AI triage comments.
3. Re-run the assessment logic from `skills/assess.md` (steps 2-4).
4. Update labels:
   - Keep `ai-triaged`
   - Replace `ai-fixable` with `ai-nonfixable` (or vice versa)
   - Add `ai-retriage` if not already present
   - If changing from fixable to nonfixable, add `ai-initiallymarkedfixable`
5. Post a new comment noting this is a retriage:
```text
   AI Retriage Analysis - {date}
   Previous verdict: {ai-fixable/ai-nonfixable}
   Updated verdict: {ai-fixable/ai-nonfixable}
   Reason for change: {explanation}
   ...rest of analysis...
   ```
6. Update ledger if entry exists.
