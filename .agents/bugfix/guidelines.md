# Bugfix Workflow Guidelines

Safety rules, allowed tools, and escalation criteria for AI bug fixing.

## Principles

- **One issue at a time**: finish one issue (PR created with `ai-fully-automated` or `ai-accelerated-fix`, or terminal failure labels applied) before starting the next. No parallel fixes.
- **Minimal diffs**: change only what's needed. Don't refactor, add docs, or "improve" surrounding code.
- **Show code, not concepts**: implement the actual fix, don't describe what should be done.
- **Follow repo conventions**: read `AGENTS.md` (repo root) for PEP 8, Python 3.14 syntax, ruff, pyright, and the inheritance model.
- **Fetch the real target first**: for release-branch / z-stream work, fetch the latest
  `rhds/rhoai-X.Y` ref before diagnose begins. Do not rely on a stale local remote-tracking ref.
- **Probe branch-local mechanisms before editing**: on release branches, check the actual
  dependency and tooling layout first (`dependencies/`, `scripts/pylocks_generator*`, `uv` /
  `uv.toml`, affected `pyproject.toml` files). Do not assume the same CVE fix mechanism exists on
  every branch.
- **Record lock refresh toolchain**: when relocking on release branches, note the exact command and
  `uv` / wrapper path used. Different branches may require different toolchain versions.

## Hard Limits

- **No direct commits to main** — always use a feature branch.
- **No force-push** — ever.
- **No skipping CI** — no `--no-verify`, no bypassing hooks.
- **No modifying security-critical code without human review** — flag it and pause.
  Security-critical code includes: authentication/authorization logic, secret/credential
  handling, input validation, cryptographic operations, access control, RBAC enforcement.

## Circuit Breaker: Max 3 Fix Attempts

If tests fail after 3 fix attempts:
1. Stop immediately.
2. Label the issue `ai-verification-failed`.
3. Push the branch as a **draft PR** for human review.
4. Add a Jira comment explaining what was tried and why it failed.
5. Clean up local state and return to previous branch.

## Allowed Tools Per Phase

| Phase | Tools |
|-------|-------|
| Start | `mcp__atlassian__getJiraIssue`, repo reading (Read, Grep, Glob), Bash (`git fetch`, `git branch -a`) |
| Diagnose | Grep, Glob, Read, Bash (read-only git commands: `git log`, `git blame`), subagents for research |
| Fix | Edit, Write tools, Bash (`git checkout -b`, `gmake refresh-lock-files`) |
| Test | Bash (`make test`, `./uv run pytest`, `./uv run prek --from-ref HEAD~1 --to-ref HEAD`) |
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
- `git clean -fd` to remove untracked files created during the fix attempt
- If a remote branch was pushed, note it in the Jira comment for human cleanup
- Return to the branch you were on before starting

## Escalation: When to Stop

- Root cause is unclear after investigation
- Multiple valid solutions exist and an architectural decision is needed
- Fix requires changes in another repository
- Confidence in the fix is below 80%
- Tests require GPU hardware or a live cluster that isn't available
- Release-branch verification already fails broadly on unrelated baseline checks and the user does
  not want a draft-PR handoff path
- **CVE-specific:** the vulnerable component is Go/RPM and `/fix-cve` does not apply
- **CVE-specific:** upstream source shows the fix but no released artifact contains it yet — document and stop
- **CVE-specific:** the tracker is mixed and the correct action is VEX closure for false-positive children, not a code fix
