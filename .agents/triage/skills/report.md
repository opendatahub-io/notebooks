# Skill: Generate Triage Report

Produce a summary of triage results from the ledger.

## Inputs

None required. Reads from `.artifacts/triage/ledger.json`.

## Procedure

1. Read `.artifacts/triage/ledger.json`.
2. Count totals:
   - Total issues scanned
   - Assessed vs pending vs error
   - `assessed` should include both `triageStatus = assessed` and `triageStatus = previously-assessed`
   - ai-fixable vs ai-nonfixable
   - By category (Dockerfile, dependency, test, manifest, CVE, CI, runtime, UI)
   - By priority (Blocker, Critical, Major, Normal, Minor)
   - Determine fixability from Jira labels first (`ai-fixable`, `ai-nonfixable`); only fall back to `assessment.fixable` if labels are unavailable in the ledger entry
   - When an issue has moved beyond initial triage (draft PR, execution label, strong retriage update), treat the newest state as authoritative and avoid preserving superseded narrative in summary sections
3. Generate a markdown report:

```markdown
# Triage Report - {date}

## Summary
- **Total scanned**: N
- **Assessed**: M / N
- **Pending**: P
- **Errors**: E
- **AI-fixable**: X ({percentage}%)
- **AI-nonfixable**: Y ({percentage}%)

## By Category
| Category | Fixable | Not Fixable | Total |
|----------|---------|-------------|-------|
| Dockerfile/build | ... | ... | ... |
| ...

## By Priority
| Priority | Fixable | Not Fixable | Total |
|----------|---------|-------------|-------|
| Blocker | ... | ... | ... |
| ...

## Top Candidates for Fixing
Priority-ordered list of ai-fixable bugs that are still ready for new work:
- exclude issues with terminal execution labels (`ai-fully-automated`, `ai-accelerated-fix`, `ai-could-not-fix`, `ai-verification-failed`)
- exclude issues whose latest assessment/comment says they are already fixed or superseded
1. RHAIENG-XXXX (Blocker) — {summary} — files: {list}
2. ...

## Issues Needing Human Review
List of ai-nonfixable issues with brief reasons.

## Final State Of Recently Touched Issues
Use this section when issues were retriaged or moved into bugfix work after the initial triage
assessment. Do not repeat stale earlier narratives here; summarize the latest known state instead.
```

4. Write report to `.artifacts/triage/report.md`.
   The report is a derived artifact; `ledger.json` is the authoritative local state.
   When an earlier section's narrative is superseded by retriage or bugfix work, rewrite or
   replace it instead of leaving contradictory older text in place.
5. Print the summary section to the user.
