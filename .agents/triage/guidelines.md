# Triage Workflow Guidelines

Safety rules, allowed tools, and escalation criteria for AI bug triage.

## Principles

- **Conservative classification**: when uncertain, mark as `ai-nonfixable`. False positives (claiming fixable when it isn't) waste more time than false negatives.
- **Every assessment must include reasoning**: never label without explanation.
- **Label and comment as you go**: don't batch labels — apply to each issue immediately after assessment. Partial progress is visible in Jira even if the agent stops midway.
- **Reference repo context**: read `AGENTS.md` (repo root) for the inheritance model, build system, and testing approach before assessing fixability.

## Hard Limits

- **Never close or transition issues** — only modify labels and add comments.
- **Never modify fields other than labels** — no changing assignee, priority, status, etc.
- **Never fabricate data** — if you can't determine fixability, say so.
- **Always add `ai-triaged`** to every processed issue.
- **`ai-fixable` and `ai-nonfixable` are mutually exclusive** — never apply both.

## Allowed Tools Per Phase

| Phase | Tools |
|-------|-------|
| Scan | `mcp__atlassian__searchJiraIssuesUsingJql`, `mcp__atlassian__getJiraIssue` |
| Assess | Jira read tools + repo filesystem (Read, Grep, Glob), subagents for deep research |
| Label + Comment | `mcp__atlassian__editJiraIssue` (labels only), `mcp__atlassian__addCommentToJiraIssue` |
| Report | Local file writing only |

## HITL Checkpoint

After assessing the **first issue**, show the analysis comment and label decision to the user before posting to Jira. Once the user approves the format, proceed with remaining issues without pausing (but the user can interrupt anytime).

## Context Hygiene

- Use **subagents** for research that produces large output (Slack search, GitHub PR history, reading external repos). The subagent summarizes; you keep a clean context for assessment.
- Use **Grep** to find specific patterns in the repo, not Read to load entire files.
- Save scan results to `.artifacts/triage/ledger.json` — all phases read/update this central state file.

## Escalation: When to Stop

- Jira access fails or returns errors consistently
- More than 50% of issues lack descriptions (data quality problem)
- Issue requires cluster access, GPU hardware, or live browser testing to diagnose
- Issue spans multiple repos and root cause is unclear
- You're unsure about the team's codebase conventions — ask the user

## Quality

- Similar bugs should receive similar assessments — be consistent.
- Every `ai-fixable` decision must reference which files in the repo would need to change.
- Every `ai-nonfixable` decision must explain why (what's blocking autonomous fix).
