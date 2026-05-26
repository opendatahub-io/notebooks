# Bugfix Workflow

Take an `ai-fixable` Jira issue through diagnosis, fix, test, and PR creation.

## Phases

1. **Start**: Fetch issue, verify `ai-fixable` label, read triage assessment, present plan
2. **Diagnose**: Root cause analysis — search code, trace history, identify affected files
3. **Fix**: Implement minimal fix on a feature branch
4. **Test**: Run tests — max 3 attempts, then stop
5. **PR**: Push branch, create PR, update Jira labels and add comment

Single issue at a time: `/fix-start RHAIENG-XXXX`
Individual phases: `/fix-diagnose`, `/fix-fix`, `/fix-test`, `/fix-pr`

## Branch Naming

`fix/{RHAIENG-XXXX}-{short-description}`

## Execution Context

- **Upstream / mainline work**: use the ODH checkout on `main`
- **Z-stream / release-branch work**: use `red-hat-data-services/notebooks` on the matching
  `rhoai-X.Y` branch
- Before diagnose or fix on a release branch, fetch the latest target ref and record which exact
  branch tip you are using

## Required Test Commands

```bash
gmake test                   # macOS; use `make test` when make is GNU Make
./uv run pytest tests/unit/  # unit tests, if the target branch has tests/unit/
./uv run ruff check          # linting
./uv run pyright             # type checking
```

## Execution Labels (applied at PR phase)

| Outcome | Label |
|---------|-------|
| Tests pass on first verify run, PR created | `ai-fully-automated` |
| Tests pass after at least one failure cycle, PR created | `ai-accelerated-fix` |
| Fix attempt failed | `ai-could-not-fix` |
| Tests failed after max retries | `ai-verification-failed` |

See `skills/test.md` → `test-handoff.md` and `skills/pr.md` for the success-label split.

## Safety

- No direct commits to main — always feature branch
- No force-push
- No skipping CI
- Max 3 fix-test loop iterations (circuit breaker)
- Human confirmation at diagnose->fix, fix->test, and before PR

## Key References

- `guidelines.md` — full safety rules, allowed tools, escalation criteria
- `reference/fix-patterns.md` — common fix patterns for this repo
- Root `AGENTS.md` — repo conventions (PEP 8, Python 3.14, ruff, inheritance model)
