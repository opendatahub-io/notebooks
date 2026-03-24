# Bugfix Workflow Guidelines

Safety rules, allowed tools, and escalation criteria for AI bug fixing.

## Principles

- **One issue at a time**: finish one issue (PR created or `ai-could-not-fix` applied) before starting the next. No parallel fixes.
- **Minimal diffs**: change only what's needed. Don't refactor, add docs, or "improve" surrounding code.
- **Show code, not concepts**: implement the actual fix, don't describe what should be done.
- **Follow repo conventions**: read `AGENTS.md` (repo root) for PEP 8, Python 3.14 syntax, ruff, pyright, and the inheritance model.

## Hard Limits

- **No direct commits to main** — always use a feature branch.
- **No force-push** — ever.
- **No skipping CI** — no `--no-verify`, no bypassing hooks.
- **No modifying security-critical code without human review** — flag it and pause.

## Circuit Breaker: Max 3 Fix Attempts

If tests fail after 3 fix attempts:
1. Stop immediately.
2. Label the issue `ai-could-not-fix`.
3. Push the branch as a **draft PR** for human review.
4. Add a Jira comment explaining what was tried and why it failed.
5. Clean up local state and return to previous branch.

## Allowed Tools Per Phase

| Phase | Tools |
|-------|-------|
| Start | `mcp__atlassian__getJiraIssue`, repo reading (Read, Grep, Glob) |
| Diagnose | Grep, Glob, Read, Bash (read-only git commands: `git log`, `git blame`), subagents for research |
| Fix | Edit, Write tools, Bash (`git checkout -b`, `make refresh-pipfilelock-files`) |
| Test | Bash (`make test`, `./uv run pytest`, `./uv run ruff check`, `./uv run pyright`) |
| PR | Bash (`git push`, `gh pr create`), `mcp__atlassian__editJiraIssue`, `mcp__atlassian__addCommentToJiraIssue` |

## HITL Checkpoints

Explicit human confirmation required at:
1. After **diagnose** presents root cause analysis — user confirms before fix begins
2. After **fix** shows the diff — user confirms before tests run
3. Before **pr** pushes and creates the PR

## Context Hygiene

- In **diagnose**: launch Explore subagent to search related PRs, read Slack discussions, check external repos. Subagent returns a summary, not raw data.
- After reading Jira description and logs, write a structured summary to `.artifacts/bugfix/{key}/context.md` and reference that file instead of keeping raw data in context.
- Use Grep to find specific patterns, not Read to load entire files.

## Cleanup on Failure

If the agent bails out at any phase:
- `git stash` or `git checkout -- .` to restore clean working tree
- If a remote branch was pushed, note it in the Jira comment for human cleanup
- Return to the branch you were on before starting

## Escalation: When to Stop

- Root cause is unclear after investigation
- Multiple valid solutions exist and an architectural decision is needed
- Fix requires changes in another repository
- Confidence in the fix is below 80%
- Tests require GPU hardware or a live cluster that isn't available
