# 6. Adopt structlog for structured logging in CI and scripts

Date: 2026-03-18

## Status

Proposed

## Context

The repository's Python utilities in `ci/` and `scripts/` used an inconsistent mix of
logging approaches: 5 files used Python's stdlib `logging` with different `basicConfig()`
settings, ~9 more used bare `print()` for status/error output, and one script
(`pylocks_generator.py`) had its own ANSI color wrapper functions. There was no structured
logging at all — no JSON output, no key-value context binding.

This made it difficult to:
- Correlate log output with specific code paths (especially in CI, where multiple scripts
  run in sequence and logs are interleaved)
- Parse logs programmatically (for AI agents or monitoring tools)
- Debug build failures when a script prints `"Error occurred"` with no context about
  which image, target, or file caused it

The AI Bug Automation Readiness report (issue #3111) scored the repository 20/100 on
Structured Logging / Errors, identifying it as the #3 biggest improvement opportunity.

## Decision

We adopt [structlog](https://www.structlog.org/) as the structured logging library,
configured via a shared `ci/logging_config.py` module.

### Why structlog over a hand-rolled JSON formatter

- **Context binding**: `log = log.bind(target="minimal", variant="cpu")` carries context
  through all subsequent log calls without repeating it in every f-string
- **Dual rendering**: JSON lines in CI (auto-detected via `$CI` env var), colorized
  human-readable output in local dev — same code, one config toggle
- **stdlib integration**: structlog wraps Python's `logging` module, so existing
  `logging.getLogger()` calls route through structlog's processors automatically
- **Battle-tested**: edge cases around encoding, exception formatting, thread safety
  are already handled

### Quick start

```python
import structlog
from ci.logging_config import configure_logging

configure_logging()  # call once at script startup
log = structlog.get_logger()

# Simple message (f-strings are fine for straightforward cases)
log.info(f"Processing {filepath}")

# Key-value pairs (useful when values should be machine-searchable)
log.info("Container started", container_id=container_id, image=image_link)

# Binding context for a sequence of operations
log = log.bind(target=target, directory=build_dir)
log.info("Starting build")   # target= and directory= are included automatically
log.info("Build complete")   # ...in both of these log lines
```

The `configure_logging()` function accepts optional parameters:

```python
configure_logging(level="DEBUG")           # set log level
configure_logging(json_output=True)        # force JSON (normally auto-detected from $CI)
configure_logging(json_output=False)       # force human-readable
```

### Output examples

**Dev mode** (local terminal, colorized):
```
2026-03-17T22:54:03.235342Z [info     ] Container started              [__main__] container_id=abc123 image=quay.io/foo/bar
```

**CI mode** (JSON, when `$CI` is set):
```json
{"container_id": "abc123", "image": "quay.io/foo/bar", "event": "Container started", "level": "info", "logger": "__main__", "timestamp": "2026-03-17T22:54:03.235342Z"}
```

### What was converted

14 files were converted from stdlib `logging` or bare `print()` to structlog:

| Category | Files |
|----------|-------|
| Already using `logging` (config swap) | `ci/check-software-versions.py`, `scripts/new_python_based_image.py`, `scripts/sandbox.py`, `scripts/sandbox_tests.py`, `scripts/update-commit-latest-env.py` |
| Using `print()` for status/errors | `ci/validate_json.py`, `ci/cached-builds/make_test.py`, `ci/cached-builds/has_tests.py`, `ci/cached-builds/makefile_helper.py`, `scripts/pylocks_generator.py`, `scripts/fix_package_naming.py`, `scripts/lockfile-generators/create-artifact-lockfile.py` |

### What was NOT converted

- **Data output scripts** that print JSON/YAML/tables to stdout (`package_versions.py`,
  `gen_gha_matrix_jobs.py`, `konflux_generate_*.py`, `generate_pull_request_pipelineruns.py`)
  — these produce structured data, not log messages
- **User-facing CLI tools** with formatted table output (`cve_due_dates.py`,
  `sbom_analyze.py`, `create_cve_trackers.py`) — separate, larger effort
- **GitHub Actions magic strings** (`::group::`, `GITHUB_OUTPUT` writes) — must remain
  as `print()` since GHA parses them from stdout

## Consequences

- New dependency: `structlog` (added to `pyproject.toml` dev group)
- All new scripts in `ci/` and `scripts/` should use `configure_logging()` + `structlog.get_logger()`
  instead of `logging.basicConfig()` or bare `print()` for status/error messages
- CI logs become machine-parseable (JSON) without losing human readability in local dev
- The `ci/logging_config.py` module is the single source of truth for log configuration;
  individual scripts should not call `logging.basicConfig()` directly

## References

- Issue: https://github.com/opendatahub-io/notebooks/issues/3119
- AI Bug Automation Readiness report: https://github.com/opendatahub-io/notebooks/issues/3111
- structlog docs: https://www.structlog.org/
