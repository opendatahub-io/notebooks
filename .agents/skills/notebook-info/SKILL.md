---
name: notebook-info
description: Generate the reusable Notebook status report from Jira and Org Pulse, and optionally post it to Slack. Use when asked to inspect or report Notebook release status.
---

# Notebook Info

Generate a Notebook status report from Jira and Org Pulse, and optionally post it to Slack.

## Usage

Run from the repository root:

```bash
python -m scripts.notebook_info --dry-run
```

Set these environment variables before running:

- `JIRA_URL`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`
- `ORG_PULSE_API_BASE`
- `ORG_PULSE_UI_URL`
- `ORG_PULSE_TOKEN`
- `SLACK_CHANNEL`
- `SLACK_APP_TOKEN`

Use `--dry-run` to print the report without posting it to Slack.

The same package is used by the internal GitHub Actions workflow in
`red-hat-data-services/rhods-devops-infra`; that workflow owns all internal
endpoints, secrets, and CA configuration.
