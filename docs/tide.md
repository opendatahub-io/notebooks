# Tide & Prow Reference for opendatahub-io/notebooks

Tide is the Prow component that automatically merges PRs when all conditions are met.
This document describes how Tide, Prow commands, and GitHub reviews interact for this repository.

## Where the configuration lives

All Prow/Tide configuration is centralized in the [openshift/release](https://github.com/openshift/release) repository.
Nothing can be configured locally in this repo (except the `OWNERS` file).

There are **separate configs** for the midstream and downstream repos:

| Repo | Config in openshift/release |
|------|----------------------------------|
| `opendatahub-io/notebooks` | [`core-services/prow/02_config/opendatahub-io/notebooks/_prowconfig.yaml`](https://github.com/openshift/release/blob/master/core-services/prow/02_config/opendatahub-io/notebooks/_prowconfig.yaml) |
| `red-hat-data-services/notebooks` | [`core-services/prow/02_config/red-hat-data-services/notebooks/_prowconfig.yaml`](https://github.com/openshift/release/blob/master/core-services/prow/02_config/red-hat-data-services/notebooks/_prowconfig.yaml) |

The config for `opendatahub-io/notebooks` currently looks like this:

```yaml
branch-protection:
  orgs:
    opendatahub-io:
      repos:
        notebooks:
          branches:
            main:
              protect: false
tide:
  merge_method:
    opendatahub-io/notebooks: merge
  queries:
  - labels:
    - approved
    - lgtm
    missingLabels:
    - do-not-merge/hold
    - do-not-merge/invalid-owners-file
    - do-not-merge/work-in-progress
    - needs-rebase
    repos:
    - opendatahub-io/notebooks
```

## Prow vs GitHub Actions on main

We previously used Prow presubmit jobs (ci-operator based) to build and test images on PRs to `main`.
These have been replaced by GitHub Actions workflows and Konflux pipelines. Prow presubmit jobs are still used on
other branches (e.g. older `rhoai-2.*` branches in `red-hat-data-services/notebooks`).

Tide (the merge automation) and the Prow label-management plugins (`/lgtm`, `/approve`, `/hold`)
remain active on `main` for `opendatahub-io/notebooks`.

## Merge requirements (our config)

These requirements come from the `tide.queries` and `tide.context_options` sections in
[`_prowconfig.yaml`](#where-the-configuration-lives) shown above. They can be changed by
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

The `OWNERS` file at the repo root controls who can use `/approve` and `/lgtm`:

```yaml
approvers:    # can use /approve
  - atheo89
  - daniellutz
  - jiridanek
  - ysok

reviewers:    # can use /lgtm
  - atheo89
  - ayush17
  - daniellutz
  - dibryant
  - jiridanek
  - ysok
```

Subdirectories can have their own `OWNERS` files to scope approval rights to specific paths.

## Prow commands

### `/lgtm`

- Adds the `lgtm` label to the PR.
- Can be used by anyone listed in `reviewers` or `approvers` in the `OWNERS` file.
- Removed automatically when new commits are pushed (to force re-review).
- To remove manually: `/lgtm cancel`.

### `/approve`

- Adds the `approved` label to the PR.
- Can only be used by people listed in `approvers` in the `OWNERS` file.
- **Not** removed when new commits are pushed (unlike `/lgtm`).
- To remove: `/approve cancel`.

### `/hold`

- Adds the `do-not-merge/hold` label, preventing Tide from merging.
- Any contributor can use it.
- To remove: `/hold cancel`.

### `/override <context-name>`

- Forces a specific commit status context to be reported as passing.
- Useful when a CI check fails for infrastructure reasons unrelated to the PR.
- Requires the commenter to be listed in the `OWNERS` file (approver level) or have admin access.
- Example: `/override validation-of-sw-versions-in-imagestreams`
- The override applies to the current HEAD commit only; pushing new commits requires a new override.

### `/retest`

- Re-triggers all failed Prow presubmit jobs.
- Does **not** re-trigger GitHub Actions workflows (use the GitHub UI "Re-run" for those).

### Other useful commands

| Command | Effect |
|---------|--------|
| `/cc @user` | Request review from a specific user |
| `/uncc @user` | Remove review request |
| `/assign @user` | Assign the PR |
| `/unassign @user` | Unassign |
| `/label <name>` | Add a label |
| `/remove-label <name>` | Remove a label |
| `/retitle <new title>` | Change PR title |
| `/wip` | Toggle `do-not-merge/work-in-progress` |

Full command reference: <https://prow.ci.openshift.org/command-help?repo=opendatahub-io%2Fnotebooks>

## GitHub review approval vs Prow `/lgtm` and `/approve`

GitHub's built-in review system (the "Approve" / "Request changes" buttons) and Prow's
label-based system are **independent but complementary**:

| Action | What it does | Effect on Tide |
|--------|-------------|----------------|
| GitHub "Approve" review | Sets GitHub review state to "approved" | No direct effect on Tide labels |
| GitHub "Request changes" review | Sets GitHub review state to "changes requested" | No direct effect on Tide labels |
| `/lgtm` comment | Adds `lgtm` label via Prow | Required for Tide to merge |
| `/approve` comment | Adds `approved` label via Prow | Required for Tide to merge |

Tide merges based on **labels**, not GitHub review state. A PR can have a GitHub "Approve"
review but still lack the `lgtm` or `approved` labels if nobody commented the Prow commands.

In practice, for users who are listed in the `OWNERS` file (which includes everyone on the
dev team), clicking the GitHub "Approve" button automatically triggers both `/lgtm` and
`/approve`, adding both labels at once. This means a single GitHub approval review from an
OWNERS approver is sufficient to satisfy Tide's merge requirements.

If branch protection requires GitHub approvals (e.g. `required_approving_review_count: 1`
in `_prowconfig.yaml`), then GitHub review state matters too. For `opendatahub-io/notebooks`
on `main`, branch protection is currently **disabled** (`protect: false`), so only Prow
labels matter.

## Context options and optional checks

By default, Tide requires **all** reported commit statuses and check runs to pass.
There is no `context_options` configured for this repo, which means:

- Every GitHub Actions workflow that runs on a PR commit must pass.
- Every Prow check must pass.
- There is no way to mark a check as optional without modifying the config in openshift/release.

To make a check optional, add `context_options` to the `_prowconfig.yaml`:

```yaml
tide:
  context_options:
    orgs:
      opendatahub-io:
        repos:
          notebooks:
            optional-contexts:
            - "some-flaky-check-name"
            # or skip all unknown contexts:
            # skip-unknown-contexts: true
```

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
- [OpenShift CI docs: Tide](https://docs.ci.openshift.org/docs/architecture/ci-operator/#automating-merges-with-tide)
