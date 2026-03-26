# JQL Queries for AAIET Notebooks Triage

Pre-built JQL queries for common triage scenarios.

## Jira Projects

- **RHAIENG**: Primary project for opendatahub-io/notebooks bugs. Component: `Notebooks`
- **RHOAIENG**: CVE/security tracking only (for our team). Component: `Notebooks Images`.
  Regular bugs should NOT be in RHOAIENG for this team — only CVEs.

For supported RHOAI versions and their downstream branch names, see `guidelines.md` → "Supported RHOAI Versions" table.

## Status Conventions

- **New**: Untriaged issues (not yet reviewed by a human)
- **Backlog**: Human-triaged issues (reviewed, prioritized, waiting for work)
- AI triage adds value to both, but **Backlog issues benefit most** — they already have human context, and AI can assess fixability and add fix steps.

## Canonical Default Triage Queue

This is the default used by the triage skill unless the user overrides it:

```jql
project = RHAIENG AND statusCategory not in (Done)
AND issuetype in (Bug) AND component = Notebooks
AND (labels not in (ai-triaged) OR labels is EMPTY)
ORDER BY priority DESC, updated DESC
```

Use this when you want the current untriaged queue across all active states.

## Backlog-Only Triage Queue (Highest-Value Subset)

Human-triaged bugs ready for AI fixability assessment:

```jql
project = RHAIENG AND status = Backlog
AND issuetype in (Bug) AND component = Notebooks
ORDER BY priority DESC, updated DESC
```

## Untriaged Bugs

New bugs not yet reviewed:

```jql
project = RHAIENG AND status = New
AND issuetype in (Bug) AND component = Notebooks
ORDER BY priority DESC, created DESC
```

## All Unresolved Bugs

```jql
project = RHAIENG AND resolution = Unresolved
AND issuetype in (Bug) AND component = Notebooks
ORDER BY priority DESC, updated DESC
```

## CVE / Security Issues

CVEs use `issuetype = Vulnerability` (not Bug). CVE triage is a separate workflow (to be added later). This query finds them:

```jql
project = RHOAIENG AND resolution = Unresolved
AND issuetype = Vulnerability AND component = "Notebooks Images"
ORDER BY updated DESC
```

## Already AI-Triaged (check progress)

```jql
project = RHAIENG AND labels = ai-triaged
AND component = Notebooks
ORDER BY updated DESC
```

## AI-Fixable Bugs Ready for Work

```jql
project = RHAIENG AND labels = ai-fixable
AND labels NOT IN (ai-fully-automated, ai-accelerated-fix, ai-could-not-fix, ai-verification-failed)
AND component = Notebooks
ORDER BY priority DESC, updated DESC
```

## Bugs Needing Retriage

```jql
project = RHAIENG AND labels = ai-retriage
AND component = Notebooks
ORDER BY updated DESC
```

## High-Priority Unassigned

```jql
project = RHAIENG AND issuetype = Bug
AND priority in (Critical, Blocker)
AND assignee IS EMPTY AND resolution = Unresolved
AND component = Notebooks
ORDER BY priority DESC, updated DESC
```

## Recently Updated (last 7 days)

```jql
project = RHAIENG AND issuetype = Bug
AND component = Notebooks AND updated >= -7d
ORDER BY updated DESC
```
