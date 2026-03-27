# Triage Comment Template

Starting-point format for the structured analysis comment posted to Jira during triage.
This is a guideline, not gospel — adapt as needed for clarity.

## Template

```
AI Triage Analysis - {YYYY-MM-DD}
{issue_url} : {issue_summary}
Priority: {priority} | Status: {status} | Component: {component}
AI-Fixable: {Yes/No} | Recommendation: {BACKLOG/FIX_NOW/NEEDS_INFO}

Problem
{Concise description of what's wrong}

Root Cause
{Analysis of why it's happening and where in the code}

Files to Modify
{List of files with brief explanation of what changes are needed}

Steps to Resolve
{Numbered steps to fix the issue}

Testing
{What to verify after the fix}
```

## Field Notes

- **Recommendation**: `FIX_NOW` for high-priority bugs with clear fixes, `BACKLOG` for lower priority or complex bugs, `NEEDS_INFO` when the issue description is insufficient.
- **Root Cause**: Be specific about file paths and code patterns. If the cause is in another repo, say so.
- **Files to Modify**: Use paths relative to the repo root. If the fix spans repos, note that.
- **Steps to Resolve**: Actionable steps an agent or human could follow. Include commands where applicable.
- **Testing**: Specific test commands or manual verification steps.

## When AI-Nonfixable

For `ai-nonfixable` issues, the comment should still include Problem and Root Cause analysis,
but replace Steps to Resolve with a brief explanation of why it's not AI-fixable
(e.g., "Requires cluster access to reproduce", "Architectural decision needed").

## When Downstream Component Owner Exists

For `ai-nonfixable` issues where the vulnerable component is shipped via a packaged
binary owned by another team (e.g., `oc` via OpenShift, `skopeo` via RHEL), use:

```
AI Triage Analysis - {YYYY-MM-DD}
{issue_url} : {issue_summary}
Priority: {priority} | Status: {status} | Component: {component}
AI-Fixable: No | Recommendation: BACKLOG

Problem
{Standard CVE problem block}

Root Cause
{Identify the shipped binary path (e.g., /opt/app-root/bin/oc) and the owning
component (e.g., openshift4/ose-cli-rhel9)}

Downstream Tracking
{List the other-project Jira keys (e.g., OCPBUGS-XXXXX) with their current
status, assignee, and any resolution or handling notes}

Why Not Notebooks-Fixable
{The component is shipped as a pre-built binary; a notebooks repo source edit
would not address the actual exposure}

Remediation Path
{Blocked on [component owner] handling; monitor [specific tickets]}
```
