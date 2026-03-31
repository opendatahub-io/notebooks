# Triage Workflow

Analyze Jira bugs, classify fixability, apply labels, and post structured analysis comments.

## Phases

1. **Scan**: Fetch bugs from Jira via JQL -> save to `.artifacts/triage/ledger.json`
2. **Assess**: For each issue, analyze fixability -> immediately label and comment in Jira
3. **Report**: Generate a summary of triage results

End-to-end: `/triage-run` chains scan -> assess -> report.
Single issue: `/triage-assess RHAIENG-XXXX`

## Default JQL

The canonical default lives in `reference/jql-queries.md` under
**Canonical Default Triage Queue**.

Use the **Backlog-Only Triage Queue** from that file when the user or runbook wants
the highest-value human-triaged subset rather than the full active untriaged queue.

Override with arguments: `/triage-run project = RHAIENG AND status = New ...`

## Label Rules

- Always add `ai-triaged` to every processed issue
- Add exactly one of `ai-fixable` or `ai-nonfixable` (mutually exclusive)
- When uncertain, default to `ai-nonfixable`
- When re-triaging an issue that already has `ai-triaged`, remove the existing verdict labels (`ai-fixable`, `ai-nonfixable`) before applying updated ones. Never leave contradictory verdict labels.

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
- [ProdSec scanning guide](https://gitlab.cee.redhat.com/data-hub/guide/-/blob/main/docs/notebooks/product-security-scanning.md) — how Konflux/ProdSec generate CVE tickets and why we get false positives (Red Hat internal; use `glab` CLI to fetch)
- `reference/manifestbox.md` — querying ProdSec manifest-box for SBOM data
- `reference/cve-remediation-guide.md` — full CVE investigation workflow
- `reference/cve-python.md` — Python CVE resolution (cve-constraints.txt); [internal version](https://gitlab.cee.redhat.com/data-hub/guide/-/blob/main/docs/notebooks/cves/python.md) has team handles and contacts
- `reference/cve-nodejs.md` — Node.js CVE resolution (npm/pnpm)
- `reference/case-study-cve-*.md` — real-world CVE investigation examples
