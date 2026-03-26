# Triage Workflow

Analyze Jira bugs, classify fixability, apply labels, and post structured analysis comments.

## Phases

1. **Scan**: Fetch bugs from Jira via JQL -> save to `.artifacts/triage/ledger.json`
2. **Assess**: For each issue, analyze fixability -> immediately label and comment in Jira
3. **Report**: Generate a summary of triage results

End-to-end: `/triage-run` chains scan -> assess -> report.
Single issue: `/triage-assess RHAIENG-XXXX`

## Default JQL

```jql
project = RHAIENG AND status = Backlog
AND issuetype in (Bug) AND component = Notebooks
ORDER BY priority DESC, updated DESC
```

Override with arguments: `/triage-run project = RHAIENG AND status = New ...`

## Label Rules

- Always add `ai-triaged` to every processed issue
- Add exactly one of `ai-fixable` or `ai-nonfixable` (mutually exclusive)
- When uncertain, default to `ai-nonfixable`

## Required MCP Tools

- `mcp__atlassian__searchJiraIssuesUsingJql` (scan)
- `mcp__atlassian__getJiraIssue` (assess)
- `mcp__atlassian__editJiraIssue` (label)
- `mcp__atlassian__addCommentToJiraIssue` (post analysis)

## CVE Triage

CVE tracker issues have a different structure — see `skills/assess-cve.md`.
- `/triage-assess-cve RHAIENG-XXXX` — assess a CVE tracker
- `/triage-close-vex` — bulk-close false positive CVEs with VEX justification
- `/triage-scan-image` — scan container image with Syft/Grype/Trivy

## Key References

- `guidelines.md` — safety rules, allowed tools, escalation
- `reference/bug-categories.md` — 8 bug categories with fixability heuristics
- `reference/label-taxonomy.md` — full label definitions
- `reference/jql-queries.md` — pre-built JQL variants
- `reference/ecosystem.md` — related repos and when to consult them
- `reference/comment-template.md` — starting-point Jira comment format
- `reference/manifestbox.md` — querying ProdSec manifest-box for SBOM data
- `reference/cve-remediation-guide.md` — full CVE investigation workflow
- `reference/cve-python.md` — Python CVE resolution (cve-constraints.txt)
- `reference/cve-nodejs.md` — Node.js CVE resolution (npm/pnpm)
- `reference/case-study-cve-*.md` — real-world CVE investigation examples
