# 6. Adopt structured logging in CI and scripts (structlog, log/slog, tslog)

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

- **Python**: We adopt [structlog](https://www.structlog.org/), configured via a shared
  `ci/logging_config.py` module.
- **Go**: We adopt [`log/slog`](https://pkg.go.dev/log/slog) (stdlib since Go 1.21),
  with JSON handler enabled when `$CI` is set.
- **TypeScript**: We adopt [tslog](https://tslog.js.org/) for Playwright tests and
  scripts, configured via `tests/browser/tests/logger.ts`. Playwright built-ins
  (`test.step()`) are used alongside tslog for test-level structure.

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

### t-string support (Python 3.14+)

Since the project targets Python 3.14, log calls can use
[t-strings (PEP 750)](https://peps.python.org/pep-0750/) for automatic
structured key extraction:

```python
# t-string: interpolated values become structured keys automatically
filepath = "/data/images/minimal"
log.info(t"Processing {filepath}")
# → event="Processing /data/images/minimal", filepath="/data/images/minimal"

# Multiple values
user_id = 123
action = "login"
log.info(t"User {user_id} performed {action}")
# → event="User 123 performed login", user_id=123, action="login"
```

The `t_string_processor` in `ci/logging_config.py` detects `Template` objects,
extracts each interpolated expression as a key-value pair, and renders the
template to a plain string for the `event` field. Explicitly passed kwargs
take precedence over auto-extracted values.

Unlike f-strings (which immediately render to a fixed string), t-strings
create a `Template` object that structlog can inspect before rendering.
This enables lazy evaluation — the string is only rendered if the log level
is active.

### Output examples

**Dev mode** (local terminal, colorized):
```text
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

### Go: log/slog in buildinputs

The repository has one Go tool (`scripts/buildinputs/`) that parses Dockerfiles to
determine build inputs. It used `log.Printf` from the old `log` package.

We switched to `log/slog` (stdlib, no new dependencies) for consistency:

```go
// Before
log.Printf(rulename, description, url, fmtmsg, location)

// After
slog.Warn("Dockerfile lint warning",
    "rule", rulename,
    "description", description,
    "url", url,
    "message", fmtmsg,
    "location", location,
)
```

JSON handler is activated when `$CI` is set, matching the Python side:

```go
func init() {
    if os.Getenv("CI") != "" {
        slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stderr, nil)))
    }
}
```

**Dev mode** output:
```text
2026/03/17 23:10:00 WARN Dockerfile lint warning rule=JSONArgsRecommended description=... url=... message=...
```

**CI mode** (JSON):
```json
{"time":"2026-03-17T23:10:00Z","level":"WARN","msg":"Dockerfile lint warning","rule":"JSONArgsRecommended","description":"...","url":"...","message":"..."}
```

### TypeScript: tslog in Playwright tests

The Playwright browser tests (`tests/browser/`) used `console.log` for logging, with
one page object model (`codeserver.ts`) having a custom logger wrapping `console.log`.

We chose [tslog](https://tslog.js.org/) because:
- **TypeScript-native**: built for TypeScript from the ground up, excellent type safety
- **Synchronous**: no async flush issues in short-lived test processes
- **Universal**: works in Node.js, Deno, Bun, and browser
- **JSON/pretty dual mode**: same `$CI` env var toggle as Python and Go

```typescript
// tests/browser/tests/logger.ts
import { Logger } from "tslog";

export const log = new Logger({
  name: "notebooks-tests",
  type: process.env.CI ? "json" : "pretty",
});
```

Usage in page object models with sub-loggers:

```typescript
import { log as rootLog } from "../logger";

export class CodeServer {
    private readonly logger = rootLog.getSubLogger({ name: "CodeServer" });

    async focusTerminal() {
        this.logger.debug(`retrying terminal focus (${attempts}/∞)`);
    }
}
```

Playwright's built-in `test.step()` is used alongside tslog for test-level structure
(already in use in `codeserver.spec.ts`), while tslog handles debug/info/error output.

Files converted: `tests/browser/tests/models/codeserver.ts`,
`tests/browser/tests/codeserver.spec.ts`, `tests/browser/scripts/add_snyk_target.ts`,
`tests/browser/scripts/start_browser.ts`.

### What was NOT converted

- **Data output scripts** that print JSON/YAML/tables to stdout (`package_versions.py`,
  `gen_gha_matrix_jobs.py`, `konflux_generate_*.py`, `generate_pull_request_pipelineruns.py`)
  — these produce structured data, not log messages
- **User-facing CLI tools** with formatted table output (`cve_due_dates.py`,
  `sbom_analyze.py`, `create_cve_trackers.py`) — separate, larger effort
- **GitHub Actions magic strings** (`::group::`, `GITHUB_OUTPUT` writes) — must remain
  as `print()` since GHA parses them from stdout

## Consequences

- New dependencies: `structlog` (Python, `pyproject.toml` dev group), `tslog` (TypeScript,
  `tests/browser/package.json5`); no new Go dependencies (`log/slog` is stdlib)
- **Python**: new scripts in `ci/` and `scripts/` should use `configure_logging()` +
  `structlog.get_logger()` instead of `logging.basicConfig()` or bare `print()`
- **Go**: new Go code should use `log/slog` with key-value pairs instead of `log.Printf`
  or `fmt.Fprintf(os.Stderr, ...)`
- **TypeScript**: new test utilities should import from `tests/browser/tests/logger.ts`;
  test specs should combine tslog with `test.step()` for structured test flow
- CI logs become machine-parseable (JSON) without losing human readability in local dev
- Both languages auto-detect CI mode via the `$CI` environment variable
- The `ci/logging_config.py` module is the single source of truth for Python log
  configuration; individual scripts should not call `logging.basicConfig()` directly

## OpenTelemetry readiness

If the project ever needs to ship logs to an OpenTelemetry collector (e.g. for distributed
tracing in an OpenShift cluster), the chosen libraries have varying levels of support:

| Language | Library | OTel support | How |
|----------|---------|-------------|-----|
| Python | structlog | Good | structlog routes through stdlib `logging`; the OTel SDK's `LoggingHandler` bridges stdlib → OTel Logs transitively. A custom ~5-line processor can inject `trace_id`/`span_id` from the active span. |
| Go | log/slog | First-class | Official bridge `go.opentelemetry.io/contrib/bridges/otelslog` sends slog records as OTel log entries. Trace context correlation is natural since slog accepts `context.Context`. |
| TypeScript | tslog | None | No built-in OTel integration. Would require manual trace context extraction, or swapping to Pino which has official support via `@opentelemetry/instrumentation-pino`. |

This is not a current need — the repository's scripts run in CI pipelines and local dev,
not in instrumented services. Noted here for future reference if observability requirements
change.

## Log loss on crash / exit

All three chosen libraries write synchronously, so no log entries are lost when a
process exits unexpectedly (panic, test failure, `sys.exit()`, unhandled exception):

| Library | Write target | Mode | Risk of lost logs on crash |
|---------|-------------|------|---------------------------|
| structlog → `StreamHandler(stderr)` | stderr | Sync | None |
| log/slog → `JSONHandler(stderr)` | stderr | Sync | None |
| tslog → `console.log` | stdout/stderr | Sync | None |

This was a deliberate consideration in the library choices. Alternatives like Pino
(TypeScript) default to async buffered writes for performance and require explicit
`sync: true` to avoid log loss in short-lived processes like test runners. Since our
use cases are CI scripts and Playwright tests — both short-lived — synchronous output
is the correct default.

## References

- Issue: https://github.com/opendatahub-io/notebooks/issues/3119
- AI Bug Automation Readiness report: https://github.com/opendatahub-io/notebooks/issues/3111
- structlog docs: https://www.structlog.org/
