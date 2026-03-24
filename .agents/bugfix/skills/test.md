# Skill: Verify the Fix

Run tests to validate the fix. Circuit breaker: max 3 attempts.

## Inputs

Continues from `skills/fix.md`. Changes are staged on the feature branch.

## State

Track the attempt counter. Initialize to 0 on first entry.

## Procedure

### 1. Run Static Tests (always)

```bash
make test
```

This runs pytest for config/manifest consistency plus lint checks.

### 2. Run Unit Tests

```bash
./uv run pytest tests/unit/
```

### 3. Run Pre-commit Checks

```bash
./uv run prek --from-ref HEAD~1 --to-ref HEAD
```

This wraps ruff check, ruff format, pyright, toml validity, uv-lock consistency, and more.

### 4. Run Targeted Tests (if applicable)

Based on what changed, pick the right test type:

| Test type | Command | Verifies |
|-----------|---------|----------|
| Static/config | `make test` | Manifest consistency, pyproject validity, lint |
| Container | `pytest tests/containers --image=<img>` | Package availability, runtime behavior in image |
| Browser | Playwright (`tests/browser/`) | UI rendering, extensions |
| GPU | Needs GPU hardware | CUDA/ROCm operations |

Specific guidance:
- If test files were modified: run those specific tests
- If Dockerfiles were modified: `make test` covers static checks; container build requires podman
- If manifests were modified: `make test` covers manifest consistency

### 5. Evaluate Results

**All pass**: proceed to `skills/pr.md`.

**Failures**: increment attempt counter.

- **Attempt <= 3**: analyze the failure, apply a targeted fix, and re-run tests. Go back to step 1.
- **Attempt > 3**: CIRCUIT BREAKER — stop. See below.

### Circuit Breaker (after 3 failed attempts)

1. Stop fixing.
2. Write a summary of what was tried and why tests keep failing to `.artifacts/bugfix/{key}/test-failures.md`.
3. Commit the current state with a WIP message.
4. Push as a **draft PR** for human review:
   ```bash
   git push -u origin fix/{key}-{desc}
   gh pr create --draft --title "WIP: fix/{key} — needs human review" --body "AI attempted 3 fixes but tests still fail. See .artifacts/bugfix/{key}/test-failures.md"
   ```
5. Update Jira: add `ai-verification-failed` label, post a comment explaining the failures.
6. Clean up: return to the previous branch.
   ```bash
   git checkout -
   ```
7. Report to user: "Tests failed after 3 attempts. Draft PR created for human review."
