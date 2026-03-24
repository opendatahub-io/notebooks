# Bugfix Workflow

Route commands to the appropriate skill.

## Commands

| Command | Skill | Description |
|---------|-------|-------------|
| `/fix-start` | `skills/start.md` | Load issue, build context, present plan |
| `/fix-diagnose` | `skills/diagnose.md` | Deep root cause analysis |
| `/fix-fix` | `skills/fix.md` | Implement the fix on a feature branch |
| `/fix-test` | `skills/test.md` | Run tests (max 3 attempts) |
| `/fix-pr` | `skills/pr.md` | Push, create PR, update Jira |

## Before Starting

1. Read `guidelines.md` for safety rules (circuit breaker, HITL checkpoints).
2. Ensure the issue is labeled `ai-fixable` (or proceed with user approval).
3. Read the root `AGENTS.md` (repo root) for code conventions and build system.

## Usage

```
/fix-start RHAIENG-3611
```

Phases run sequentially with human confirmation between diagnose->fix, fix->test, and before PR.

## One Issue at a Time

Finish one issue (PR created or `ai-could-not-fix` applied) before starting the next.

## Artifacts

Per-issue output goes to `.artifacts/bugfix/{key}/`:
- `context.md` — summarized issue context
- `root-cause.md` — diagnosis with evidence
- `test-failures.md` — if circuit breaker triggered
