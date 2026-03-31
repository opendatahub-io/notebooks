# Skill: Verify the Fix

Run tests to validate the fix. Circuit breaker: max 3 attempts.

## Inputs

Continues from `skills/fix.md`. Changes are staged on the feature branch.

## State

Track **`test_failure_cycles`**: the number of times you take the **Failures** branch in step 5 before eventually reaching **All pass**. Initialize to `0` on first entry. Increment by **1** each time tests fail (each time you loop back to step 1 after a failure).

This value selects the Jira success label in `skills/pr.md` (see **Handoff** below).

Also track **`verification_result`**:
- `all_pass` — the required verification passed
- `baseline_failures` — the target branch already fails on unrelated checks outside the fix scope
- `regression_failures` — the fix introduced or exposed a failure in the changed scope

## Procedure

### 1. Run Static Tests (always)

```bash
gmake test
```

Use `gmake` on macOS when `make` is BSD make; use `make test` when `make` is GNU Make.
This runs pytest for config/manifest consistency plus lint checks.

### 2. Run Unit Tests

```bash
./uv run pytest tests/unit/
```

If the target branch does not contain `tests/unit/`, record that explicitly and do not treat the
missing directory as a fix regression.

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

**All pass**: write the handoff file (below), then proceed to `skills/pr.md`.

**Baseline failures**: if the same command already fails on the clean target branch tip, or if the
failure is clearly outside the changed scope (for example branch-wide `.tekton` drift, unrelated
lint, or an absent `tests/unit/` directory), do **not** increment `test_failure_cycles`.

Write the handoff file with:
```yaml
test_failure_cycles: 0
verification_result: baseline_failures
baseline_failures:
  - command: <command>
    summary: <why this is outside the fix scope>
```

Then proceed to `skills/pr.md` only with explicit user approval to open a **draft PR** and apply
`ai-verification-failed`.

**Regression failures**: increment `test_failure_cycles` by 1.

- **`test_failure_cycles` <= 3**: analyze the failure, apply a targeted fix, and re-run tests. Go back to step 1.
- **`test_failure_cycles` > 3**: CIRCUIT BREAKER — stop. See below.

### Circuit Breaker (after 3 failed attempts)

1. Stop fixing.
2. Ensure the directory exists (`mkdir -p .artifacts/bugfix/{key}`), then write a summary of what was tried and why tests keep failing to `.artifacts/bugfix/{key}/test-failures.md`.
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

## Handoff to `pr.md`

After **All pass**, write `.artifacts/bugfix/{key}/test-handoff.md`:

```yaml
test_failure_cycles: N
verification_result: all_pass
```

Use the final `test_failure_cycles` value (after success). `pr.md` maps this to Jira labels:

| `test_failure_cycles` | Success label |
|------------------------|---------------|
| `0` | `ai-fully-automated` |
| `>= 1` | `ai-accelerated-fix` |
