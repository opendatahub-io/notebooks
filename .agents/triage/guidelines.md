# Triage Workflow Guidelines

Safety rules, allowed tools, and escalation criteria for AI bug triage.

## Trust Hierarchy

**Jira lies. Slack lies. Docs lie. Only code can be (more or less) trusted.**

Do not take Jira descriptions, Slack threads, or even ARCHITECTURE.md at face value.
They may be stale, wrong, or aspirational. Always verify claims against actual code,
workflows, and CI configuration.

For every claim in the Jira description, identify the file/code it references and verify it.
If the Jira says "nudges update X", find the code that does the updating and confirm.
If it says "branch Y is retired", check the branch exists and its support lifecycle.

**ODH vs RHOAI manifest pipelines** — a common source of stale docs:
- **ODH** (`manifests/odh/base/`): `params-latest.env` updated by GHA workflows
  (`build-notebooks-push.yaml`, `params-env.yaml`). Images on quay.io/opendatahub.
- **RHOAI** (`manifests/rhoai/base/`): `params-latest.env` values are overridden at
  deploy time by opendatahub-operator via `RELATED_IMAGE_*` env vars from the
  ClusterServiceVersion. Images on registry.redhat.io/rhoai.
- `commit-latest.env` is updated by nightly GHA `update-commit-latest-env.yaml`
  using `scripts/update-commit-latest-env.py` (skopeo inspect). Same for both ODH and RHOAI.
- Nudge annotations have been disabled for 6+ months despite docs saying otherwise.

## RHOAI Product Perspective

RHAIENG issues are filed from a customer/product perspective — they're about
Red Hat OpenShift AI (RHOAI), not ODH upstream. When triaging:
- Focus on the RHOAI product impact first (that's what the customer needs)
- Frame the problem and fix from RHOAI perspective
- The Jira comment's first paragraph must mention RHOAI product impact

However: ODH code IS RHOAI code. Code flows opendatahub-io/notebooks →
red-hat-data-services/notebooks (downstream). Fixes must flow through the ODH repo.
So when proposing code changes, the files to modify are in the ODH repo, but the
issue impact is about RHOAI.

**Exception: z-stream fixes** (patch releases like 2.25.3) go directly to the
`rhoai-X.Y` branch in `red-hat-data-services/notebooks`. These are hotfixes for
supported releases that can't wait for the upstream → downstream flow.

## Supported RHOAI Versions

| Version | Downstream Branch | Python | Lock Format | Wheel Source | Notes |
|---------|-------------------|--------|-------------|--------------|-------|
| 2.16 EUS | `release-2024a` / `release-2024b` | py311 | Pipfile.lock | PyPI | Ends June 30, 2026. Tags: 2024.1 / 2024.2 |
| 2.25 EUS | `rhoai-2.25` | py312 | pylock.toml | PyPI | |
| 3.3 | `rhoai-3.3` | py312 | pylock.toml | PyPI | Last release with PyPI wheels |
| main (3.4+) | n/a (local) | py312 | pylock.toml | AIPCC | Wheels from packages.redhat.com |

Release branches are in **red-hat-data-services/notebooks**, not opendatahub-io/notebooks.
Fixes on main do NOT flow to release branches — each version needs its own fix (separate PR on separate branch).

Release branches are NOT "retired" just because their paths don't exist on main. Check the
RHOAI product lifecycle / support dates. `release-2024a` maps to RHOAI 2.16 EUS, supported until June 30, 2026.

## Investigate Across Repos

When a fix involves the operator or other repos, actually look at the code there:
- **Operator repo**: `~/IdeaProjects/opendatahub-operator/`
- Don't guess from notebooks-side docs — read the actual operator code
- Check how the operator implements `RELATED_IMAGE_*` override for `params-latest.env`

For issues in other repos, check the cross-repo table in `reference/bug-categories.md`.

## Principles

- **Conservative classification**: when uncertain, mark as `ai-nonfixable`. False positives (claiming fixable when it isn't) waste more time than false negatives.
- **Every assessment must include reasoning**: never label without explanation.
- **Label and comment as you go**: don't batch labels — apply to each issue immediately after assessment. Partial progress is visible in Jira even if the agent stops midway.
- **Reference repo context**: read `AGENTS.md` (repo root) for the inheritance model, build system, and testing approach before assessing fixability.
- **For CVEs, built-image SBOM evidence outranks repo grep**: when deciding whether a component is actually in the shipped image, prefer manifest-box `sourceInfo` over source-tree lockfiles or docs.
- **Sample representative children before generalizing**: if a tracker spans multiple image families (`codeserver`, `jupyter-*`, `runtime-*`), check one child per family before making tracker-wide claims.

## Hard Limits

- **Never close or transition issues** — only modify labels and add comments.
- **Never modify fields other than labels** — no changing assignee, priority, status, etc.
- **Never fabricate data** — if you can't determine fixability, say so.
- **Always add `ai-triaged`** to every processed issue.
- **`ai-fixable` and `ai-nonfixable` are mutually exclusive** — never apply both.
- **One Jira at a time** — post one issue's labels+comment, let the user see it, then proceed to the next. Never batch multiple MCP calls for different issues in one message.
- **Check existing Jira comments before posting** — avoid duplicating analysis someone already wrote.
- **`parked` is a PM scheduling label, not a fixability assessment** — an issue can be `ai-fixable` AND `parked`.
- **Jira tracks delivery, not just code**:
  - **Resolved** = code is fixed, tested, prepared to ship (not yet in customers' hands)
  - **Closed** = delivered to customers (a release happened that includes the fix)
  - Recommend "Resolved" for fixed CVEs, never "Closed" (can't know if the fix has shipped)
- **Don't claim upstream packages need "team coordination"** unless they are in the Red Hat maintained packages list (see `reference/bug-categories.md`). Packages like tensorflow, keras, urllib3 are upstream — bumping them needs compat testing on EUS, but not team coordination.

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
- **Concrete trigger**: if the file is >200 lines OR requires checking >1 external repo, spawn an Explore subagent.
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
- Mixed trackers should clearly separate real remediation targets from likely VEX `Component not Present` candidates.
