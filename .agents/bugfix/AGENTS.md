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

## Required Test Commands

```bash
make test                    # static tests (always)
./uv run pytest tests/unit/  # unit tests
./uv run ruff check          # linting
./uv run pyright             # type checking
```

## Execution Labels (applied at PR phase)

| Outcome | Label |
|---------|-------|
| Tests pass, PR created | `ai-fully-automated` |
| Fix attempt failed | `ai-could-not-fix` |
| Tests failed after max retries | `ai-verification-failed` |

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
