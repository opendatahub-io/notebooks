# 16. Adopt Antigravity SDK for GitHub PR review and CI summaries

Date: 2026-06-06

## Status

Accepted

## Context

The repository previously used a Gemini CLI-based pull request review workflow
(`.github/workflows/gemini-pr-review.yml`) that:

- invoked `run-gemini-cli` inside GitHub Actions,
- depended on a Docker-hosted GitHub MCP server,
- exposed shell tools to the agent for diff inspection,
- and produced no reusable foundation for CI failure summarization.

At the same time, `Build Notebooks (pr)` fans out into many matrix jobs across
targets, platforms, and ODH/RHOAI variants. A single PR can fail in many places.
Issue [#2997](https://github.com/opendatahub-io/notebooks/issues/2997) asks for
a readable single-page summary instead of forcing maintainers to inspect many
jobs one by one. The issue comments also outline a desired long-term direction:
bounded log extraction, known failure signatures, and synthesized actionable
summaries.

In parallel, the downstream RHDS fork tracks the broader migration away from
Gemini CLI in issue
[#2334](https://github.com/red-hat-data-services/notebooks/issues/2334). That
issue explicitly combines:

- PR review migration from Gemini CLI to Antigravity SDK, and
- matrix CI summarization as an evolving PR comment.

This ADR records the implementation that satisfies both the upstream ODH
summary need (`#2997`) and the downstream RHDS migration plan (`#2334`).

The migration to Antigravity in GitHub Actions had several constraints:

1. **Headless CI must use the Python SDK, not `agy`.**
   The Antigravity CLI is not the right contract for GitHub Actions today
   because headless auth remains tied to the CLI/OAuth path
   ([agy#78](https://github.com/google-antigravity/antigravity-cli/issues/78)).

2. **GitHub MCP should be remote HTTP, not Docker in CI.**
   The GitHub remote MCP server at `api.githubcopilot.com` already exposes the
   pull-request and actions toolsets needed by the workflows, so local Docker is
   unnecessary for the GitHub Actions path.

3. **MCP access must be deny-by-default.**
   The original spike on `google-antigravity==0.1.0` relied on server-specific
   filtering headers. That was good enough for the spike, but not the preferred
   long-term API. `google-antigravity` 0.1.1 added per-server MCP tool filtering
   via `enabled_tools` / `disabled_tools`
   ([antigravity-sdk-python#28](https://github.com/google-antigravity/antigravity-sdk-python/issues/28)).

4. **CI summary comments must update incrementally.**
   Waiting for the whole matrix to finish before posting any summary wastes time,
   especially when slow jobs like code-server / Playwright finish last.

5. **LLM output must be bounded and auditable.**
   The model should not be responsible for reconstructing whole workflow state.
   Deterministic code should gather and render status tables; the model should
   only add value where synthesis is actually useful.

## Decision

### 1. Use `google-antigravity` in GitHub Actions

GitHub Actions automation will use the Python SDK (`google-antigravity`) with
`GEMINI_API_KEY`, not the `agy` CLI.

This decision is implemented in:

- `scripts/ci/review_pr.py`
- `scripts/ci/summarize_ci_run.py`
- `.github/workflows/antigravity-pr-review.yml`
- `.github/workflows/antigravity-ci-summary.yml`
- `.github/workflows/antigravity-ci-gated-review.yml`

The root dev dependency is now declared in `pyproject.toml`.

### 2. Use remote GitHub MCP over Streamable HTTP

GitHub integration uses `McpStreamableHttpServer` against the hosted GitHub MCP
endpoints:

- PR review: `https://api.githubcopilot.com/mcp/x/pull_requests`
- Actions summary fallback: `https://api.githubcopilot.com/mcp/x/actions/readonly`

This replaces the prior Docker-hosted GitHub MCP usage for the PR review flow.

### 3. Enforce a three-layer allowlist for PR review

PR review automation uses three layers of restriction:

1. **No builtin harness tools in context**
   via `CapabilitiesConfig(enable_subagents=False, enabled_tools=[])`.
2. **Per-server MCP allowlist**
   via `McpStreamableHttpServer(..., enabled_tools=[...])`.
3. **Runtime deny-by-default policies**
   via `policy.deny_all()` plus explicit MCP allowances.

The shared configuration lives in `scripts/ci/mcp_github.py`.

PR review summaries are upserted as a single issue comment (same marker pattern
as CI summaries) via `upsert_review_comment.py`. Inline findings still go through
MCP; the model outputs summary markdown for deterministic REST upsert.

The PR review allowlist is restricted to:

- `pull_request_read`
- `pull_request_review_write`
- `add_comment_to_pending_review`

The GitHub Actions summary allowlist is restricted to:

- `actions_get`
- `get_job_logs`

Because the SDK namespaces MCP tools internally as `mcp_<server>_<tool>`, the
runtime audit layer must verify those namespaced tool calls rather than the raw
server tool IDs.

### 4. Replace the Gemini review workflow with Antigravity review workflows

The old PR review workflow is replaced by:

- `.github/workflows/antigravity-dispatch.yml`
- `.github/workflows/antigravity-pr-review.yml`

The dispatch workflow handles:

- automatic review on trusted PR open/reopen/edit,
- `/agy review` requests,
- and the legacy `/gemini-cli review` alias during migration.

The old `.github/workflows/gemini-pr-review.yml` is removed.

### 5. Implement CI summarization as one evolving PR comment

CI summarization is implemented as a single upserted issue comment keyed by a
hidden HTML marker containing the workflow run ID.

This is driven by `workflow_run: completed` (with `workflow_dispatch` for manual
reruns), so the comment is posted once the workflow finishes.

The implementation is split as follows:

- `scripts/ci/prepare_ci_run_context.py`
  - collects workflow run state,
  - computes progress counts,
  - fetches bounded failed-step log tails,
  - emits `ci-run-context.json`,
  - and renders the deterministic progress body.
- `scripts/ci/summarize_ci_run.py`
  - uses the model only for failure analysis,
  - keeps success/progress output deterministic,
  - and optionally uses read-only Actions MCP only to fill log gaps.
- `scripts/ci/upsert_ci_comment.py`
  - creates or patches the single PR comment,
  - and supersedes older run comments when a newer workflow run exists.

The workflow entry point is `.github/workflows/antigravity-ci-summary.yml`.

### 6. Keep deterministic rendering responsible for run facts

The system does **not** let the model invent run metadata, tables, links, or
progress numbers.

Deterministic code renders:

- run title and link,
- progress summary,
- failed-jobs table,
- still-running section,
- and the hidden marker.

The model only contributes:

- `### Likely root causes`
- `### Suggested next steps`

This keeps the summary grounded in known workflow data and avoids hallucinated
run IDs, durations, or links.

### 7. Add CI-gated review context as a follow-on workflow path

After a successful `Build Notebooks (pr)` run, a separate workflow prepares a
bounded `review-context.json` and reuses the same `review_pr.py` engine for a
CI-gated follow-up review.

This is implemented in:

- `scripts/ci/prepare_review_context.py`
- `.github/workflows/antigravity-ci-gated-review.yml`

The prepared context includes:

- changed files with capped excerpts,
- check runs for the PR head SHA,
- and affected image targets derived from the existing matrix helper logic.

### 8. Provide local project plugins for Antigravity

Two workspace-local plugins are added under `.agents/plugins/`:

- `github-pr-review`
- `github-ci-summary`

These package:

- `plugin.json`
- `mcp_config.json`
- skill markdown under `skills/.../SKILL.md`

The CI implementation remains authoritative; the local plugin layer exists to
keep the same MCP endpoints and review/summary guidance available for local
Antigravity usage.

## Consequences

### Positive

- GitHub Actions no longer needs Docker just to expose GitHub MCP to the review
  agent.
- PR review is now deny-by-default and does not expose shell tools or general
  builtin write tools to the model.
- CI failure summaries appear earlier and update in place instead of creating a
  stream of separate bot comments.
- Failure analysis is bounded by deterministic context preparation, which keeps
  token use and hallucination risk lower than “give the model the full log”.
- The same GitHub MCP configuration is shared across PR review, CI summary, and
  local Antigravity plugins.
- The summary flow directly addresses the core maintainer pain described in
  issue [#2997](https://github.com/opendatahub-io/notebooks/issues/2997).
- The same implementation also serves as the concrete delivery for the RHDS
  migration tracked in
  [red-hat-data-services/notebooks#2334](https://github.com/red-hat-data-services/notebooks/issues/2334).

### Negative / risks

- The CI summary flow currently targets `Build Notebooks (pr)` first, not all
  PR checks or workflows.
- The failure classifier is still lightweight; it does not yet implement the
  full “known-pattern subtraction” pipeline described in the `#2997` comments.
- `workflow_run`-driven summaries post once per completed workflow; concurrency
  groups coalesce duplicate runs for the same workflow run ID.
- The repository’s `exclude-newer` dependency policy may temporarily resolve an
  older acceptable SDK patch release than the latest upstream patch.
- Local Antigravity plugin behavior depends on the CLI/IDE customization model,
  which is less stable than the SDK contract used by CI.

### Non-goals

- Replacing all PR-wide CI diagnosis with a single universal workflow in this
  change.
- Using `agy` as the execution surface in GitHub Actions.
- Letting the model post comments directly for CI summary or review-summary
  updates; REST upsert stays deterministic.

## References

- `scripts/ci/mcp_github.py`
- `scripts/ci/review_pr.py`
- `scripts/ci/prepare_ci_run_context.py`
- `scripts/ci/summarize_ci_run.py`
- `scripts/ci/upsert_ci_comment.py`
- `scripts/ci/pr_review_summary.py`
- `scripts/ci/upsert_review_comment.py`
- `scripts/ci/prepare_review_context.py`
- `.github/workflows/antigravity-dispatch.yml`
- `.github/workflows/antigravity-pr-review.yml`
- `.github/workflows/antigravity-ci-summary.yml`
- `.github/workflows/antigravity-ci-gated-review.yml`
- `.agents/plugins/github-pr-review/`
- `.agents/plugins/github-ci-summary/`
- [opendatahub-io/notebooks#2997](https://github.com/opendatahub-io/notebooks/issues/2997)
- [red-hat-data-services/notebooks#2334](https://github.com/red-hat-data-services/notebooks/issues/2334)
- [antigravity-sdk-python#28](https://github.com/google-antigravity/antigravity-sdk-python/issues/28)
- [antigravity-sdk-python#24](https://github.com/google-antigravity/antigravity-sdk-python/issues/24)
- [agy#78](https://github.com/google-antigravity/antigravity-cli/issues/78)
- [GitHub MCP remote server docs](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md)