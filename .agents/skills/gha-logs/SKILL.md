---
name: gha-logs
description: Fetch per-job logs for a GitHub Actions workflow run with the gh CLI. Use when asked to collect or inspect logs for a known run; use another workflow to locate failing runs across a PR.
---

# GitHub Actions Job Logs

Collect logs for completed jobs in a GitHub Actions workflow run, then inspect
the relevant job logs to explain failures.

## Fetch logs

Use the run ID from the provided URL or context. If the target repository is
not the helper's default, set `REPO=owner/repo`. The GitHub CLI must be
authenticated and have access to that repository.

Run the bundled helper from the repository root:

```bash
./.agents/skills/gha-logs/scripts/fetch-gha-job-logs.sh RUN_ID [OUTPUT_DIR]
```

The output directory defaults to `gha-job-logs-RUN_ID`. The helper fetches
logs for jobs completed when it runs; it does not wait for the whole workflow
to finish. If no jobs have completed yet, it exits with an error. Run it again
later if logs for subsequently completed jobs are needed. A log that is
expired or unavailable is reported and skipped while other jobs continue.

## Report findings

Inspect logs for failed jobs first, then summarize the failing job, the error
that caused it, and any useful surrounding context. Mention jobs whose logs
could not be retrieved, and include the output directory so the user can open
the downloaded files.
