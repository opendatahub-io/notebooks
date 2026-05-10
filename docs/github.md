# GitHub Configuration for opendatahub-io/notebooks

Reference for GitHub apps, org settings, and tooling across the opendatahub-io org.

## Org overview

- **Org**: [opendatahub-io](https://github.com/opendatahub-io) (ID: `57720972`)
- **Total repos**: ~184 (many archived)
- **Org-level `.github` repo**: [opendatahub-io/.github](https://github.com/opendatahub-io/.github) — contains only `ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE.md`, `LICENSE`, and `profile/`
- **No GitOps repo config tool** (no `settings.yml`, no safe-settings, no Probot Settings)
- Repo settings (merge buttons, labels, team permissions, Actions permissions) are configured manually via the GitHub UI by org admins

## Installed GitHub Apps

As of May 2026, these apps are active across the org (detected via check-runs and commit statuses on default branches):

| App | Repos | Notes |
|-----|-------|-------|
| **GitHub Actions** | 96 | Primary CI for most repos |
| **Red Hat Konflux** | 26 | Container image builds (Tekton pipelines) |
| **GitHub Advanced Security** | 5 | Code scanning (CodeQL) |
| **Tide** (Prow) | 4 | Merge automation via commit status; see [docs/tide.md](tide.md) |
| **Codecov** | 3 | Coverage reporting (odh-dashboard, opendatahub-operator, spark-operator) |
| **Mergify** | 2 | Auto-merge and auto-backport (trainer, trustyai-service-operator) |
| **CodeRabbit** | org-wide | AI code review, installed on free plan across all repos |
| **pre-commit.ci** | 1 | Auto-fix linting (opendatahub-tests) |
| **Dependabot** | 1 | Dependency updates (autofix-skills) |
| **DCO** | 1 | Developer Certificate of Origin check (modelmesh-serving) |

### Apps on notebooks specifically

On PRs to `opendatahub-io/notebooks`, these are active:

- **GitHub Actions** — all CI workflows (code-quality, software-versions, build, etc.)
- **GitHub Advanced Security** — code scanning
- **OpenShift CI** — Prow check runs (label management, `/lgtm`, `/approve`)
- **CodeRabbit** — AI review comments (commit status)
- **Tide** — merge automation (commit status)

### Checking installed apps

To see which apps posted check runs on a specific commit:

```bash
gh api /repos/opendatahub-io/notebooks/commits/<sha>/check-runs --paginate \
  --jq '[.check_runs[].app.slug] | unique[]'
```

To see commit status contexts (Tide, CodeRabbit, etc.):

```bash
gh api /repos/opendatahub-io/notebooks/commits/<sha>/statuses --paginate \
  --jq '[.[].context] | unique[]'
```

To check if a specific app is installed on the org via the browser, visit:

```
https://github.com/apps/<app-slug>/installations/new/permissions?target_id=57720972
```

Repos showing "installed" already have the app enabled. This requires org member access.

The org admin install page (requires admin role):

```
https://github.com/organizations/opendatahub-io/settings/installations
```

## Requesting new app installations

GitHub app installations for the opendatahub-io org require **org admin approval**.
Individual team members cannot install apps — even repo maintainers.

### Process

1. Post a request in one of these Slack channels:
   - `#rhoai-devtestops-requests` — for RHOAI / notebooks team requests
   - `#forum-pge-cloud-ops` — for broader OpenShift org-level requests (handled by PGE Cloud Ops team)
2. A **DPP-\*** Jira ticket is created (or create one yourself via the [DevServices portal](https://devservices.dpp.openshift.com/support/))
3. PGE Cloud Ops team reviews and installs the app

### Requesting Mergify on a new repo

Mergify is already installed on the org but only enabled for select repos.
To enable it on an additional repo, request in `#rhoai-devtestops-requests` — an org admin
needs to add the repo to the Mergify app's repository access list.

## Branch protection

Branch protection for repos using OpenShift CI is managed by Prow's **branchprotector**
component, configured in [openshift/release](https://github.com/openshift/release).
See [docs/tide.md](tide.md) for details.

For `opendatahub-io/notebooks` on `main`, branch protection is currently **disabled**
(`protect: false`). Merge gating is handled entirely by Tide's label requirements.

GitHub-native branch protection (configured in the UI under Settings > Branches) is
independent of Prow's config. Both can coexist, but conflicts can cause confusion —
e.g., GitHub requiring approvals while Prow uses OWNERS-based `/approve`.

## Renovate

Self-hosted Renovate runs via GitHub Actions (not as a GitHub App).
See [ADR 0013](architecture/decisions/0013-renovate-mintmaker-and-self-hosted-github-actions.md)
and the workflow at `.github/workflows/renovate-self-hosted.yaml`.

## CodeRabbit

Configured org-wide via [opendatahub-io/coderabbit](https://github.com/opendatahub-io/coderabbit).
Per-repo overrides in `.coderabbit.yaml` (this repo has one with custom branch filters and
PR title conventions).

Also used for [spam PR detection](https://github.com/opendatahub-io/security-config/pull/12)
across the org — flags reputation-farming PRs from automated accounts.

## Qodo

AI code review tool, GA across Red Hat since March 2026. Per-repo enablement via
[DPP request form](https://devservices.dpp.openshift.com/support/install_qodo_on_a_repo/).
User licenses requested separately via
[license request form](https://devservices.dpp.openshift.com/support/qodo_user_license_request/).

## Related docs

- [docs/tide.md](tide.md) — Tide merge automation, Prow commands, OWNERS file
- [CONTRIBUTING.md](/CONTRIBUTING.md) — Review and merge process
- [OWNERS](/OWNERS) — Approvers and reviewers list

## Related Jira tickets

- [RHAIENG-5018](https://redhat.atlassian.net/browse/RHAIENG-5018) — Evaluate GitOps-based GitHub settings management tooling
- [RHAIENG-4233](https://redhat.atlassian.net/browse/RHAIENG-4233) — Adopt Mergify as Tide replacement
- [RHAIENG-4232](https://redhat.atlassian.net/browse/RHAIENG-4232) — Disable Prow/Tide auto-merge on main
- [RHAIENG-2346](https://redhat.atlassian.net/browse/RHAIENG-2346) — Switch from Prow OWNERS to GitHub CODEOWNERS
