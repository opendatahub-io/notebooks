---
name: ci-summary
description: Summarize notebook matrix CI runs into one evolving GitHub PR comment using GitHub Actions and pull request MCP data. Use when triaging build-notebooks failures, summarizing matrix progress, or updating a living CI status comment.
---

# CI Summary

## Goal

Maintain one useful PR comment for notebook matrix CI instead of many scattered findings.
Surface failures early, cluster likely shared causes, and keep the running jobs visible while the workflow is still in flight.

## Workflow

1. Start from the prepared CI run context JSON when available.
2. Use GitHub Actions MCP only to fill in missing details for failed jobs.
3. Summarize failures in terms of likely shared causes, not one paragraph per job.
4. Keep the comment concise enough to update repeatedly during the same workflow run.

## Failure taxonomy

Use these buckets when they match the evidence:

- `hermeto_prefetch` for hermetic prefetch / Cachi2 issues
- `make_build` for image build failures during `make`
- `oom_or_killed` for runner OOMs, `Killed process`, or exit 137
- `trivy_scan` for vulnerability scan failures
- `fips_check` for `check-payload` failures
- `playwright` for code-server browser-test failures

If the evidence is incomplete, say the cause is likely rather than certain.

## Comment shape

Prefer this structure:

```markdown
## CI status [antigravity]

**Run:** [<workflow name> #<run id>](<run url>) — <progress summary>
_Last updated: <timestamp> after `<job name>` completed_

### Failures so far
<table when failures exist>

### Likely root causes
<numbered list when failures exist>

### Still running
<short list while jobs are in progress>

### Suggested next steps
<0-3 bullets when helpful>
```

## Repo-specific guidance

- This repository fans out notebook builds across target, platform, and variant, so call out when several jobs are failing for the same underlying reason.
- Keep references actionable: mention the failed step and keep the job links intact.
- Avoid noisy narration on all-green runs; a short success digest is enough.
