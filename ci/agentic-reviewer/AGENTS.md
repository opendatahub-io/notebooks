# Agentic CI Reviewer

Antigravity agents in this package review pull requests and summarize CI failures for the notebooks repo.

## Architecture

PR review (`odh-ci-review-pr`) uses **in-process Python tools** registered on `LocalAgentConfig.tools`, not remote GitHub MCP:

| Tool | Role |
|------|------|
| `pull_request_read` | Optional fetch of PR sections (`get`, `get_diff`, `get_files`, …) via `gh api` |
| `pull_request_review_write` | Create/submit pending reviews |
| `add_comment_to_pending_review` | Inline review comments |

`odh-ci-prepare-review-context` runs before review in CI and supplies bounded JSON (metadata, file excerpts, check runs). The agent should use that first and call `pull_request_read` only when it needs a section missing from context (full diff, specific file list page, review comments, etc.).

Tool JSON schemas are defined in `src/odh_ci_agent/github_review_tools.py` (aligned with GitHub MCP). Do not duplicate schemas in prompts.

CI summary (`odh-ci-summarize-ci-run`) still uses read-only GitHub Actions MCP when local log context is insufficient.

## Commands

```bash
uv sync --locked --package odh-ci-agent
uv run --package odh-ci-agent odh-ci-prepare-review-context
uv run --package odh-ci-agent odh-ci-review-pr
make test-unit  # includes ci/agentic-reviewer/tests/unit/
```

Required env vars for review: `GEMINI_API_KEY`, `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `PULL_REQUEST_NUMBER`, `AGY_TRAJECTORY_DIR`. CI also sets `REVIEW_CONTEXT_PATH` and `AGY_RUN_STATISTICS_PATH` (defaults to `agy-run-statistics.json`).

After each agent run, `odh-ci-review-pr` and `odh-ci-summarize-ci-run` write `agy-run-statistics.json` with token usage, tool-call counts, configured `GEMINI_MODEL`, and a USD cost estimate when the model is in the hardcoded Gemini Flash / Flash-Lite pricing table. Workflows upload it as artifact `antigravity-run-statistics-<run_id>`.

## Debugging with Antigravity trajectory SQLite dumps

Workflows upload `agy-trajectory/pr-review/` (or `ci-summary/`) as an artifact. The harness writes one SQLite database per conversation:

```text
agy-trajectory/pr-review/<conversation_id>.db
```

### Download artifact

```bash
gh api repos/opendatahub-io/notebooks/actions/runs/<run_id>/artifacts --jq '.artifacts[] | select(.name|test("antigravity"))'
gh api repos/opendatahub-io/notebooks/actions/artifacts/<artifact_id>/zip > agy-artifact.zip
unzip agy-artifact.zip -d agy-artifact
```

### Schema

```bash
sqlite3 agy-artifact/<conversation_id>.db ".tables"
sqlite3 agy-artifact/<conversation_id>.db ".schema steps"
```

| Table | Contents |
|-------|----------|
| `steps` | Trajectory steps; `step_payload` is a protobuf blob |
| `trajectory_meta` | Conversation / cascade metadata |
| `gen_metadata`, `executor_metadata` | Harness internals |

### Quick inspection (no protobuf decode)

Most debugging does not need full protobuf parsing:

```bash
# Tool names and JSON arguments embedded in blobs
strings agy-artifact/<conversation_id>.db | rg 'call_mcp_tool|pull_request_read|ToolName|Arguments|Denied by policy'

# Step index and payload sizes
sqlite3 agy-artifact/<conversation_id>.db \
  "SELECT idx, step_type, length(step_payload) FROM steps ORDER BY idx"

# Extract printable prompt fragments from the first (large) step
python3 - <<'PY'
import sqlite3
blob = sqlite3.connect("agy-artifact/<conversation_id>.db").execute(
    "SELECT step_payload FROM steps WHERE idx=0"
).fetchone()[0]
text = blob.decode("utf-8", errors="replace")
print(text[text.find("You are an automated"):text.find("You are an automated") + 2000])
PY
```

### What to look for

- **Policy denials**: `Denied by policy` in strings output; hook name (`deny_all`, `allow_github_call_mcp_tool`, …).
- **Tool args**: For legacy MCP runs, `call_mcp_tool` wraps `ServerName`, `ToolName`, `Arguments`. For current Python tools, search for `pull_request_read` call JSON directly.
- **False success**: Agent text claims a review was posted but trajectory shows no successful `pull_request_review_write` / `add_comment_to_pending_review` results.
- **Conversation id**: Printed at end of `odh-ci-review-pr` stdout; matches the `.db` filename.

Pre-tool hooks in the Python SDK only return allow/deny to the Go harness; they cannot rewrite MCP `Arguments`. That is why PR review uses Python tools instead of remote GitHub MCP.

## Tests

Unit tests: `ci/agentic-reviewer/tests/unit/`. May require `git add -f` if locally excluded.
