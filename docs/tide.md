# Tide & Prow Reference for opendatahub-io/notebooks

[Tide](https://docs.prow.k8s.io/docs/components/core/tide/) is the
[Prow](https://docs.prow.k8s.io/docs/) component that automatically merges PRs when all
conditions are met. This document describes how Tide, Prow commands, and GitHub reviews
interact for this repository.

## Where the configuration lives

All Prow/Tide configuration is centralized in the [openshift/release](https://github.com/openshift/release) repository.
Nothing can be configured locally in this repo (except the `OWNERS` file).

There are **separate configs** for the midstream and downstream repos:

| Repo | Config in openshift/release |
|------|----------------------------------|
| `opendatahub-io/notebooks` | [`core-services/prow/02_config/opendatahub-io/notebooks/_prowconfig.yaml`](https://github.com/openshift/release/blob/master/core-services/prow/02_config/opendatahub-io/notebooks/_prowconfig.yaml) |
| `red-hat-data-services/notebooks` | [`core-services/prow/02_config/red-hat-data-services/notebooks/_prowconfig.yaml`](https://github.com/openshift/release/blob/master/core-services/prow/02_config/red-hat-data-services/notebooks/_prowconfig.yaml) |

Key points from the current config (click the links above to see the full up-to-date YAML):

- **Branch protection on `main` is disabled** (`protect: false`).
  Initially enabled, then removed in [openshift/release#56929](https://github.com/openshift/release/pull/56929)
  (Sep 2024) and explicitly disabled in [openshift/release#59991](https://github.com/openshift/release/pull/59991)
  (Dec 2024, [RHOAIENG-15393](https://issues.redhat.com/browse/RHOAIENG-15393)) because the
  `piplock-renewal` GitHub Action needs to push directly to `main` without status checks blocking it.
- **Merge method is `merge`** (not squash), changed in [openshift/release#43851](https://github.com/openshift/release/pull/43851)
  (Sep 2023, related to [notebooks#231](https://github.com/opendatahub-io/notebooks/issues/231)).
- **Tide requires** `approved` + `lgtm` labels.
- **Tide blocks on** `do-not-merge/hold`, `do-not-merge/work-in-progress`,
  `do-not-merge/invalid-owners-file`, and `needs-rebase` labels.
  Use `/hold` and `/wip` commands to prevent merge while work is in progress.

## Prow vs GitHub Actions on main

We previously used Prow presubmit jobs (ci-operator based) to build and test images on PRs to `main`.
These have been replaced by GitHub Actions workflows and Konflux pipelines. Prow presubmit jobs are still used on
other branches (e.g. older `rhoai-2.*` branches in `red-hat-data-services/notebooks`).

Tide (the merge automation) and the Prow label-management plugins (`/lgtm`, `/approve`, `/hold`)
remain active on `main` for `opendatahub-io/notebooks`.

## Merge requirements (our config)

These requirements come from the `tide.queries` and `tide.context_options` sections in
[`_prowconfig.yaml`](#where-the-configuration-lives) above. They can be changed by
submitting a PR to openshift/release.

For Tide to merge a PR on this repo, **all** of these must be true:

1. The PR has the **`approved`** label (from `/approve`)
2. The PR has the **`lgtm`** label (from `/lgtm`)
3. The PR does **not** have any blocking labels:
   - `do-not-merge/hold`
   - `do-not-merge/invalid-owners-file`
   - `do-not-merge/work-in-progress`
   - `needs-rebase`
4. All reported commit status checks and check runs are **passing**

## OWNERS file

The [`OWNERS`](/OWNERS) file at the repo root lists `approvers` and `reviewers`.
Subdirectories can have their own `OWNERS` files to scope approval rights to specific paths.
See the [Kubernetes OWNERS reference](https://www.kubernetes.dev/docs/guide/owners/) for
the full spec (`approvers`, `reviewers`, `labels`, `emeritus_approvers`, `options`).

## Prow commands

Key commands used in this repo:

- **`/lgtm`** -- adds the `lgtm` label. Any org member can use it (not restricted
  to OWNERS reviewers). Automatically removed when new commits are pushed.
- **`/approve`** -- adds the `approved` label. Only OWNERS `approvers` can use it.
  **Not** removed on new commits (unlike `/lgtm`).
- **`/hold`** -- adds `do-not-merge/hold` to block merge. Any contributor can use it.
  Remove with `/hold cancel`.
- **`/override <context-name>`** -- forces a failing check to pass. Requires approver
  or admin access. Applies to the current HEAD commit only.
  Example: `/override validation-of-sw-versions-in-imagestreams`
- **`/retest`** -- re-triggers failed Prow presubmit jobs.
  Does **not** re-trigger GitHub Actions (use the GitHub UI "Re-run" for those).
- **`/wip`** -- toggles `do-not-merge/work-in-progress`.

Full command reference: <https://prow.ci.openshift.org/command-help?repo=opendatahub-io%2Fnotebooks>

## GitHub review approval vs Prow `/lgtm` and `/approve`

Prow's [`lgtm`](https://docs.prow.k8s.io/docs/components/core/plugins/lgtm/) and
[`approve`](https://docs.prow.k8s.io/docs/components/core/plugins/approve/) plugins
watch GitHub review events and map them to labels (unless
[`ignore_review_state`](https://docs.prow.k8s.io/docs/components/core/plugins/approve/)
is set to `true`, which is not the case for this repo):

| Who clicks "Approve" | `lgtm` label | `approved` label |
|----------------------|-------------|-----------------|
| OWNERS **approver** | Added | Added |
| OWNERS **reviewer** (not approver) | Added | Not added |
| Non-OWNERS collaborator | Not added | Not added |

A "Request Changes" review from an OWNERS approver removes the `approved` label.

Since everyone on the dev team is an OWNERS approver, a single GitHub "Approve" review
is sufficient to satisfy Tide's merge requirements.

## Context options and optional checks

By default, Tide requires **all** reported commit statuses and check runs to pass.
There is no `context_options` configured for this repo, which means every GitHub Actions
workflow and Prow check must pass before Tide will merge.

To mark a check as optional or skip unknown contexts, add `context_options` to the
[`_prowconfig.yaml`](#where-the-configuration-lives). See the
[Tide context policy docs](https://docs.prow.k8s.io/docs/components/core/tide/config/#context-policy-options)
for the available fields (`optional-contexts`, `required-contexts`, `skip-unknown-contexts`).

## Related Jira tickets

- [RHAIENG-2346](https://redhat.atlassian.net/browse/RHAIENG-2346) -- Whether to switch from Prow `OWNERS` to GitHub `CODEOWNERS`
- [RHAIENG-4232](https://redhat.atlassian.net/browse/RHAIENG-4232) -- Disable Prow/Tide auto-merge on `main` (documents a race condition where Tide merged a PR after `lgtm` was removed)
- [RHAIENG-4233](https://redhat.atlassian.net/browse/RHAIENG-4233) -- Adopt Mergify as a Tide replacement
- [RHAIENG-5018](https://redhat.atlassian.net/browse/RHAIENG-5018) -- Evaluate GitOps-based GitHub settings management tooling

## Tide dashboard and endpoints

Tide has no CLI. It runs as a controller inside the OpenShift CI cluster, watching GitHub
state and merging PRs that meet all conditions. You interact with it only through PR labels
and the config in openshift/release.

For observability, Prow exposes these web endpoints:

| Endpoint | What it shows |
|----------|---------------|
| [Tide Status](https://prow.ci.openshift.org/tide) | Current merge pool: which PRs are queued, batched, or blocked, and why |
| [Tide History](https://prow.ci.openshift.org/tide-history?repo=opendatahub-io/notebooks) | Log of recent merge actions for the `opendatahub-io/notebooks` repo |
| [tide.js](https://prow.ci.openshift.org/tide.js) | Raw JSON of the current merge pool (internal/undocumented, but useful for scripting) |

Tide also posts a `tide` commit status on every PR explaining its merge pool state.
You can query it via the GitHub API:

```bash
gh api /repos/opendatahub-io/notebooks/commits/<sha>/statuses \
  --jq '.[] | select(.context == "tide") | .description'
```

## Useful links

- [Prow plugins for this repo](https://prow.ci.openshift.org/plugins?repo=opendatahub-io%2Fnotebooks)
- [Prow command help](https://prow.ci.openshift.org/command-help?repo=opendatahub-io%2Fnotebooks)
- [OpenShift CI docs: Branch Protection](https://docs.ci.openshift.org/architecture/branch-protection/)
- [OpenShift CI docs: Tide](https://docs.ci.openshift.org/architecture/ci-operator/#automating-merges-with-tide)
