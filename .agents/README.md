# AI Bug Bash Workflows

Tool-agnostic workflows for AI-driven Jira bug triage and fixing in the OpenDataHub Notebooks repository.

## Quick Start

```
/setup-preflight                    # verify tools are accessible
/triage-run                         # triage all backlog bugs
/triage-assess RHAIENG-3611         # triage a single bug
/fix-start RHAIENG-3611             # fix a specific ai-fixable bug
```

## Workflows

### Setup (`setup/`)
Preflight checks — verify Jira MCP, GitHub CLI, Python/uv, and optional tools before starting.

### Triage (`triage/`)
Analyze Jira bugs, classify fixability, apply labels (`ai-triaged` + `ai-fixable`/`ai-nonfixable`), and post structured analysis comments. Labels and comments are applied as-you-go — partial progress is visible in Jira even if the agent stops midway.

### Bugfix (`bugfix/`)
Fix a single `ai-fixable` bug: diagnose root cause, implement minimal fix on a feature branch, run tests (circuit breaker: max 3 attempts), create PR, update Jira. One issue at a time.

## Prerequisites

Non-negotiable:
- **Jira MCP** — Atlassian MCP with access to RHAIENG project
- **Local code** — this repo checked out

Strongly recommended: GitHub CLI, Python 3.14+, uv, make

Optional: Slack MCP, web search, GitLab CLI (`glab`), cluster access (`oc`), Google Docs (`gws`)

Full checklist: [`prerequisites.md`](prerequisites.md)

## Label Taxonomy

| Phase | Labels |
|-------|--------|
| Triage | `ai-triaged` + `ai-fixable` or `ai-nonfixable` |
| Execution | `ai-fully-automated`, `ai-could-not-fix`, `ai-verification-failed` |
| Post-merge | `regressions-found` |

Full definitions: [`triage/reference/label-taxonomy.md`](triage/reference/label-taxonomy.md)

## Artifacts

| Workflow | Location | Contents |
|----------|----------|----------|
| Triage | `.artifacts/triage/` | `ledger.json` (state), `report.md` (summary) |
| Bugfix | `.artifacts/bugfix/{key}/` | `context.md`, `root-cause.md`, `test-failures.md` |

## Directory Structure

```
.agents/
├── AGENTS.md              # AI tool context (auto-loaded)
├── README.md              # This file
├── prerequisites.md       # Preflight checklist
├── setup/                 # Preflight workflow
├── triage/                # Triage workflow
│   ├── AGENTS.md          # Triage-specific context
│   ├── SKILL.md           # Command router
│   ├── guidelines.md      # Safety rules
│   ├── commands/          # Thin command wrappers
│   ├── skills/            # Core logic (scan, assess, label, report, run)
│   └── reference/         # Bug categories, JQL, labels, ecosystem, templates
└── bugfix/                # Bugfix workflow
    ├── AGENTS.md          # Bugfix-specific context
    ├── SKILL.md           # Command router
    ├── guidelines.md      # Safety rules
    ├── commands/          # Thin command wrappers
    ├── skills/            # Core logic (start, diagnose, fix, test, pr)
    └── reference/         # Fix patterns
```

## Repo Context

For project structure, build system, testing, and code conventions, see the root [`AGENTS.md`](../AGENTS.md).
