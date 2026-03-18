# 6. Configure test coverage reporting

Date: 2026-03-18

## Status

Proposed

## Context

The repository had no code coverage measurement or reporting (AI Bug Automation Readiness score: 0/100 for this category, weight: 3%).
Coverage data helps AI agents and human reviewers identify which code paths are exercised by tests, which is critical for confident bug fixing and prioritizing test writing efforts.

The opendatahub-io organization already uses Codecov in several repositories:
odh-dashboard, opendatahub-operator, vllm-tgis-adapter, caikit-nlp-client, kube-authkit, and model-registry-bf4-kf.

## Decision

### Python: pytest-cov

We adopt [pytest-cov](https://pytest-cov.readthedocs.io/) for Python coverage measurement.

**Why pytest-cov:**
- Wraps the stdlib `coverage.py` library — no proprietary dependencies
- Integrates seamlessly with pytest via `--cov` flags in `addopts`
- Supports multiple report formats: terminal (`term-missing`), XML (for Codecov upload), HTML
- Configuration lives in the existing `pyproject.toml` under `[tool.coverage.*]`

**What is measured:**
- `ntb/` — the shared Python library module
- `ci/` — CI utility scripts (Makefile helpers, PR change detection, validation)
- `scripts/` — build and maintenance scripts

**What is excluded:**
- `tests/` — test code itself
- `tests/containers/` — integration tests that require Docker/Podman and are run separately

**Configuration in `pyproject.toml`:**

```toml
[tool.coverage.run]
source = ["ntb", "ci", "scripts"]
branch = true
omit = ["tests/*", "*/__pycache__/*"]

[tool.coverage.report]
show_missing = true
skip_empty = true
```

### Go: `go test -coverprofile`

We use Go's built-in coverage support for the `scripts/buildinputs/` tool.

**Why `-coverprofile`:**
- Built into the Go toolchain — no external dependencies
- Produces output compatible with Codecov
- `-covermode=atomic` is safe for concurrent tests

**Command:**

```bash
go test -coverprofile=coverage-go.out -covermode=atomic ./...
```

This also introduces Go tests into CI for the first time — the tests existed in `buildinputs_test.go` and `heredoc_test.go` but were never run in the CI pipeline.

### Codecov integration

We adopt [Codecov](https://codecov.io/) for coverage aggregation and PR reporting.

**Why Codecov:**
- Already used by 6+ repositories in the opendatahub-io organization
- Provides PR comments with coverage diffs, file-level annotations, and trend tracking
- Free for public repositories
- Supports multiple languages and coverage formats in a single dashboard

**Key configuration choices:**

| Setting | Value | Rationale |
|---------|-------|-----------|
| `status.project.informational` | `true` | Non-blocking — establish baseline first |
| `status.patch.informational` | `true` | Non-blocking — don't gate PRs on new code coverage yet |
| `target` | `auto` | Track against default branch baseline, no fixed percentage |
| `threshold` | `2%` | Allow small regressions during initial adoption |
| `fail_ci_if_error` | `false` | CI doesn't break if token is missing or Codecov is down |
| `flags` | `python`, `go` | Separate coverage tracking per language |
| `carryforward` | `true` | Retain previous coverage when only one language's tests run |

### Test Analytics

Codecov Test Analytics tracks test run times, failure rates, and identifies flaky tests.
It requires uploading JUnit XML test results alongside coverage data.

**Python:** pytest produces JUnit XML natively with `--junitxml=junit.xml`.
We use `-o junit_family=legacy` (alias for xunit1) because Codecov recommends it for prettier test names in their UI.

**Go:** `go test` does not produce JUnit XML natively.
We use [gotestsum](https://github.com/gotestyourself/gotestsum) (`gotestsum --junitfile=junit-go.xml -- ./...`) which wraps `go test` and produces both console output and JUnit XML.

**Upload:** The `codecov/test-results-action@v1` action uploads JUnit XML files to Codecov, separate from the coverage upload action.

Results are visible in:
- PR comments (failed test reports)
- [Test Analytics dashboard](https://app.codecov.io/github/opendatahub-io/notebooks/tests)

## Consequences

### Positive

- Every PR gets a coverage report comment showing which files and lines are tested
- Baseline coverage is automatically tracked over time
- AI agents can use coverage data to identify untested code paths when investigating bugs
- Go tests now run in CI, catching regressions in the `buildinputs` Dockerfile parser

### Negative

- pytest runs slightly slower due to coverage instrumentation (typically <1s overhead)
- CI jobs take a few extra seconds for Codecov upload

### Future improvements

- Set `fail_under` threshold in `pyproject.toml` once a stable baseline is established
- Change `informational: true` to `informational: false` to make coverage checks required
- Add TypeScript/Playwright coverage when the test infrastructure matures
- Add a coverage badge to `README.md`

### Future: Image capability matrix

Code coverage (pytest-cov, Codecov) measures line coverage of CI tooling scripts (`ntb/`, `ci/`, `scripts/`).
It does not measure what runs *inside* the built container images — the project's primary output.

The container integration tests (`tests/containers/`) already verify many image capabilities:
package imports, GPU operations (CUDA/ROCm matrix multiplication), IDE startup (JupyterLab, RStudio, Code-Server),
CLI tools (`oc`, `skopeo`), file permissions, and network configuration.
However, there is no consolidated view of which capabilities are tested for each image family.

A **capability/feature matrix** — tracking what's verified per image — would be more meaningful
than code coverage for a container-image project. This is orthogonal to Codecov;
it's closer to a test results dashboard or generated report from pytest markers and test outcomes.

## References

- Issue: <https://github.com/opendatahub-io/notebooks/issues/3118>
- AI Bug Automation Readiness: <https://github.com/opendatahub-io/notebooks/issues/3111>
- pytest-cov docs: <https://pytest-cov.readthedocs.io/>
- Codecov docs: <https://docs.codecov.com/>
- Codecov GitHub Action: <https://github.com/codecov/codecov-action>
- Codecov onboarding: <https://app.codecov.io/github/opendatahub-io/notebooks/new>
