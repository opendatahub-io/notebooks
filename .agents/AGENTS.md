# AI Bug Bash Workflows

This directory provides three workflows for AI-driven Jira bug resolution in the OpenDataHub Notebooks repository.

## Workflows

| Workflow | Purpose | Entry point |
|----------|---------|-------------|
| **setup/** | Preflight checks — verify all tools are accessible | `/setup-preflight` |
| **triage/** | Analyze bugs, classify fixability, apply labels, post analysis comments | `/triage-run` or `/triage-assess RHAIENG-XXXX` |
| **triage/** (CVE) | Assess CVE trackers, locate vulnerable packages, close false positives with VEX | `/triage-assess-cve RHAIENG-XXXX` |
| **bugfix/** | Fix a single ai-fixable bug: diagnose, implement, test, create PR | `/fix-start RHAIENG-XXXX` |
| **bugfix/** (CVE) | Fix a Python CVE: update constraints, refresh locks, create PR | `/fix-cve RHAIENG-XXXX` |

## First Time? Run `/setup-preflight`

Verifies Jira access, GitHub CLI, Python/uv, and optional tools before you start real work. See `prerequisites.md` for the full checklist.

## Prerequisites (Non-Negotiable)

- **Jira MCP**: Atlassian MCP configured with access to RHAIENG project
- **Local code**: This repo checked out with `AGENTS.md` at the root

See `prerequisites.md` for the complete list including optional capabilities.

## Label Taxonomy

| Phase | Labels |
|-------|--------|
| Triage | `ai-triaged` + (`ai-fixable` or `ai-nonfixable`) |
| Execution | `ai-fully-automated` or `ai-accelerated-fix` (success), or `ai-could-not-fix`, `ai-verification-failed`; post-merge: `regressions-found` |

Full definitions: `triage/reference/label-taxonomy.md`

## Repo Context

For project structure, build system, testing, and code conventions, see the root [`AGENTS.md`](../AGENTS.md).

## Convention

Each subdirectory has its own `AGENTS.md` with workflow-specific context. AI tools entering a subdirectory automatically pick up the relevant scope.
