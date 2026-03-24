# Skill: Generate Triage Report

Produce a summary of triage results from the ledger.

## Inputs

None required. Reads from `.artifacts/triage/ledger.json`.

## Procedure

1. Read `.artifacts/triage/ledger.json`.
2. Count totals:
   - Total issues scanned
   - Assessed vs pending
   - ai-fixable vs ai-nonfixable
   - By category (Dockerfile, dependency, test, manifest, CVE, CI, runtime, UI)
   - By priority (Blocker, Critical, Major, Normal, Minor)
3. Generate a markdown report:

```markdown
# Triage Report - {date}

## Summary
- **Total scanned**: N
- **Assessed**: M / N
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
Priority-ordered list of ai-fixable bugs:
1. RHAIENG-XXXX (Blocker) — {summary} — files: {list}
2. ...

## Issues Needing Human Review
List of ai-nonfixable issues with brief reasons.
```

4. Write report to `.artifacts/triage/report.md`.
5. Print the summary section to the user.
