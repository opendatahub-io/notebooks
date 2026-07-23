# Agentic CI Reviewer

Antigravity SDK agents for GitHub pull request review and CI failure summaries in this repository.

See [AGENTS.md](AGENTS.md) for architecture, trajectory debugging, and agent conventions.

## Quick start

```shell
# Run a PR review locally (requires GEMINI_API_KEY and GITHUB_TOKEN)
uv run --package odh-ci-agent odh-ci-review-pr

# Prepare bounded CI context for a workflow run
uv run --package odh-ci-agent odh-ci-prepare-ci-run-context
```

## Tests

Unit tests live under `tests/unit/` and run with the root test suite:

```shell
make test-unit
```
