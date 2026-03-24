# Skill: End-to-End Triage Run

Chains scan -> assess -> report without pausing between phases.

## Inputs

- `$ARGUMENTS`: optional JQL override (passed to scan).

## Procedure

1. **Scan**: execute `skills/scan.md` with `$ARGUMENTS`.
   - Exit criteria: `.artifacts/triage/ledger.json` exists with at least 1 issue.
   - If zero issues found, report "No matching issues" and stop.

2. **Assess**: execute `skills/assess.md` (processes all pending issues in the ledger).
   - HITL checkpoint on first issue (see assess.md).
   - Continue through all issues, labeling and commenting as you go.

3. **Report**: execute `skills/report.md`.
   - Generates `.artifacts/triage/report.md` and prints summary.

## On Completion

Print:
```
Triage complete.
- Scanned: N issues
- Fixable: X | Not fixable: Y
- Report: .artifacts/triage/report.md
- Ledger: .artifacts/triage/ledger.json

Next: run /fix-start RHAIENG-XXXX on the top fixable candidate.
```
