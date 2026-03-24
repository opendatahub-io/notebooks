# Triage Workflow

Route commands to the appropriate skill.

## Commands

| Command | Skill | Description |
|---------|-------|-------------|
| `/triage-run` | `skills/run.md` | End-to-end: scan -> assess -> report |
| `/triage-scan` | `skills/scan.md` | Fetch issues from Jira via JQL |
| `/triage-assess` | `skills/assess.md` | Assess fixability (single issue or all pending) |
| `/triage-label` | `skills/label.md` | Relabel/retriage a single issue |
| `/triage-report` | `skills/report.md` | Generate summary report from ledger |
| `/triage-assess-cve` | `skills/assess-cve.md` | Assess a CVE tracker (RHAIENG → RHOAIENG children) |
| `/triage-close-vex` | `skills/close-vex.md` | Bulk-close CVE children with VEX justification |
| `/triage-scan-image` | `skills/scan-image.md` | Scan container image for vulnerabilities |

## Before Starting

1. Read `guidelines.md` for safety rules and allowed tools.
2. Ensure Jira MCP is configured (run `/setup-preflight` if unsure).
3. Read the root `AGENTS.md` (repo root) for project context.

## Default JQL

```jql
project = RHAIENG AND status = Backlog
AND issuetype in (Bug) AND component = Notebooks
ORDER BY priority DESC, updated DESC
```

All commands accept `$ARGUMENTS` to override the JQL or specify an issue key.

## Artifacts

All output goes to `.artifacts/triage/`:
- `ledger.json` — central state file (scan results + assessment status)
- `report.md` — summary report
