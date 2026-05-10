# CI Systems Overview

This repo uses three CI systems simultaneously. Each handles a different concern:

| System | What it does | Config location |
|--------|-------------|-----------------|
| **GitHub Actions** | Code quality, static analysis, security scans, docs, notifications | `.github/workflows/` |
| **Konflux / Pipelines-as-Code** | Container image builds, integration testing | `.tekton/` |
| **Prow / Tide** | Merge automation, label management (`/lgtm`, `/approve`, `/hold`) | [openshift/release](https://github.com/openshift/release) |

Detailed docs for each:
- [docs/tide.md](tide.md) -- Prow/Tide merge automation, OWNERS file, Prow commands
- [docs/konflux.md](konflux.md) -- Konflux build system, pipeline triggers, Renovate/MintMaker
- [docs/konflux-integration.md](konflux-integration.md) -- Konflux group testing, ephemeral clusters

## Slash commands

All three systems use PR comment commands, and some commands are consumed by multiple
systems simultaneously. Prow and PaC both watch for `/retest` and `/test`, responding
independently based on their own job/pipeline registries.

### Common commands (shared between Prow and PaC)

| Command | Prow response | PaC/Konflux response |
|---------|--------------|---------------------|
| `/retest` (bare) | Retriggers all failed Prow presubmit jobs | Retriggers all failed PaC pipelines. Ignores successful and in-progress ones. |
| `/retest <name>` | Retriggers the named Prow job if it failed | Triggers the named PaC pipeline regardless of previous outcome — even if it never ran on this PR |
| `/test <name>` | Same as `/retest <name>` for Prow | Same as `/retest <name>` for PaC |
| `/ok-to-test` | Trusts a fork PR for Prow CI | Trusts a fork PR for PaC pipelines |

Since Prow presubmit jobs are no longer configured for `main`, Prow responds to `/test`
and `/retest` with *"No presubmit jobs available"* while PaC proceeds to trigger the
matching pipeline.

### Prow-only commands (merge automation)

These commands are handled exclusively by Prow. See [docs/tide.md](tide.md) for details.

| Command | Effect |
|---------|--------|
| `/lgtm` | Adds `lgtm` label (required for merge) |
| `/approve` | Adds `approved` label (required for merge) |
| `/hold` | Adds `do-not-merge/hold` to block merge |
| `/override <context>` | Forces a failing check to pass |

Clicking the GitHub "Approve" review button triggers `/lgtm` and `/approve` automatically
for OWNERS approvers. See the [review mapping table](tide.md#github-review-approval-vs-prow-lgtm-and-approve).

### Konflux-only commands (build triggers)

These commands are handled exclusively by PaC. See [docs/konflux.md](konflux.md#triggering-builds)
for the full list.

**ODH (`opendatahub-io/notebooks`):**

| Command | Effect |
|---------|--------|
| `/kfbuild all` | Triggers all PR build pipelines |
| `/kfbuild <component>` | Triggers a single component build |
| `/kfbuild <source-path>` | Triggers by source directory |
| `/group-test` | Triggers the integration test pipeline |

**RHDS (`red-hat-data-services/notebooks`):**

| Command | Effect |
|---------|--------|
| `/build-konflux` | Triggers all RHDS PR build pipelines |
| `/build-<image-type>` | Triggers a specific image build |

RHDS also supports label-based triggers (`kfbuild-all`, `kfbuild-cuda`, etc.).

### GitHub Actions

GitHub Actions workflows are **not** triggered by slash commands. They run automatically
on PR events based on `on:` triggers in `.github/workflows/*.yaml`. To re-run a failed
GHA workflow, use the GitHub UI "Re-run" button on the Actions or Checks tab.

## How the systems interact

```
PR opened/updated
  ├── GitHub Actions: runs automatically (code-quality, security, etc.)
  ├── Konflux/PaC: runs if pathChanged() matches .tekton/ CEL expressions
  │                 or triggered manually via /kfbuild, /test, /retest
  └── Prow/Tide: watches for label state
                  └── When lgtm + approved + all checks green → auto-merge
```

Tide considers checks from **all** systems when deciding to merge. A failing GitHub
Actions workflow or a failing Konflux pipeline will both block Tide from merging,
unless overridden with `/override <context-name>`.
