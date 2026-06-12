# GitHub Configuration for opendatahub-io/notebooks

Reference for GitHub apps, org settings, and tooling across the opendatahub-io org.

## Org overview

- **Org**: [opendatahub-io](https://github.com/opendatahub-io) (ID: `57720972`)
- **Total repos**: ~184 (many archived)
- **Org-level `.github` repo**: [opendatahub-io/.github](https://github.com/opendatahub-io/.github) — contains only `ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE.md`, `LICENSE`, and `profile/`
- **No GitOps repo settings tool** (no `settings.yml`, no safe-settings, no Probot Settings).
  Repo settings (merge buttons, labels, team permissions, Actions permissions) are configured
  manually via the GitHub UI by org admins. However, security config files are managed as code
  via [security-config](#org-level-push-rulesets).

## Active GitHub Apps

As of May 2026, these apps were observed active across the org (detected via check-runs
and commit statuses on default branches -- may undercount apps that only act on PRs).
For authoritative installation state, see [Checking installed apps](#checking-installed-apps).

| App | Notes |
|-----|-------|
| [GitHub Actions](https://github.com/features/actions) | Primary CI for most repos |
| [Red Hat Konflux](https://github.com/konflux-ci) | Container image builds (Tekton pipelines) |
| [GitHub Advanced Security](https://github.com/features/security) | Code scanning (CodeQL) |
| [Tide](https://docs.prow.k8s.io/docs/components/core/tide/) (Prow) | Merge automation; see [docs/tide.md](tide.md) |
| [Codecov](https://github.com/apps/codecov) | Coverage reporting |
| [Mergify](https://github.com/apps/mergify) | Auto-merge and auto-backport |
| [CodeRabbit](https://github.com/apps/coderabbitai) | AI code review (free plan); org-wide |
| [pre-commit.ci](https://github.com/apps/pre-commit-ci) | Auto-fix linting |
| [Dependabot](https://github.com/dependabot) | Dependency updates |
| [DCO](https://github.com/apps/dco) | Developer Certificate of Origin check |

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

```text
https://github.com/apps/<app-slug>/installations/new/permissions?target_id=57720972
```

Repos showing "installed" already have the app enabled. This requires org member access.

The org admin install page (requires admin role):

```text
https://github.com/organizations/opendatahub-io/settings/installations
```

## Requesting new app installations

GitHub app installations for the opendatahub-io org require **org admin approval**.
Individual team members cannot install apps — even repo maintainers.

### Process

1. Post a request in one of these Slack channels:
   - `#rhoai-devtestops-requests` — for RHOAI / notebooks team requests
   - `#ai-core-platform-requests` — for OpenShift AI platform-level requests
   - `#forum-pge-cloud-ops` — for broader OpenShift org-level requests (handled by PGE Cloud Ops team)
2. A **DPP-\*** Jira ticket is created (or create one yourself via the [DevServices portal](https://devservices.dpp.openshift.com/support/))
3. PGE Cloud Ops team reviews and installs the app

### Requesting Mergify on a new repo

Mergify is already installed on the org but only enabled for select repos.
To enable it on an additional repo, request in `#rhoai-devtestops-requests` — an org admin
needs to add the repo to the Mergify app's repository access list.

## Org-level push rulesets

The opendatahub-io org has a **push ruleset** that protects security configuration files
from being modified directly in repos. These files are managed centrally via
[opendatahub-io/security-config](https://github.com/opendatahub-io/security-config) and
synced to repos listed in `sync-config.yml`:

- `semgrep.yaml` -- custom security rules for CodeRabbit PR reviews
- `.coderabbit.yaml` -- org-wide CodeRabbit configuration (inheritance baseline)
- `.gitleaks.toml` -- gitleaks secret scanning configuration
- `.gitleaksignore` -- gitleaks false positive suppressions

Changes to these files must go through the security-config repo. PRs that modify them
directly in a repo will be rejected by the push ruleset. See the
[security-config sync config](https://github.com/opendatahub-io/security-config/blob/main/sync-config.yml)
for the full list of synced repos.

**Renovate and org rulesets:** Renovate's `pushFiles` used to send the full tree via
`POST /git/trees` without `base_tree`, so GitHub validated all file paths -- including
unchanged protected ones -- and rejected the push with 422 "File path is restricted".
MintMaker was unblocked by adding the MintMaker GitHub App as a bypass actor on the
ruleset. Upstream fixed this in [renovatebot/renovate#42556](https://github.com/renovatebot/renovate/pull/42556)
(released in 43.216.3); self-hosted Renovate now uses upstream `ghcr.io/renovatebot/renovate`.
Original report: [renovatebot/renovate#42554](https://github.com/renovatebot/renovate/issues/42554).

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

Org-wide fallback config lives in [opendatahub-io/coderabbit](https://github.com/opendatahub-io/coderabbit).
Per-repo `.coderabbit.yaml` overrides are synced from [security-config](#org-level-push-rulesets)
for repos in the sync list. This repo has its own `.coderabbit.yaml` with custom branch filters
and PR title conventions (set `inheritance: true` to inherit the org baseline).

Also used for [spam PR detection](https://github.com/opendatahub-io/security-config/pull/12)
across the org — flags reputation-farming PRs from automated accounts.

## Qodo

AI code review tool, GA across Red Hat since March 2026. Per-repo enablement via
[DPP request form](https://devservices.dpp.openshift.com/support/install_qodo_on_a_repo/).
User licenses requested separately via
[license request form](https://devservices.dpp.openshift.com/support/qodo_user_license_request/).

## Related docs

- [docs/ci.md](ci.md) — CI systems overview, slash command comparison
- [docs/tide.md](tide.md) — Tide merge automation, Prow commands, OWNERS file
- [docs/konflux.md](konflux.md) — Konflux build system, pipeline triggers
- [CONTRIBUTING.md](/CONTRIBUTING.md) — Review and merge process
- [OWNERS](/OWNERS) — Approvers and reviewers list

## Related Jira tickets

- [RHAIENG-5018](https://redhat.atlassian.net/browse/RHAIENG-5018) — Evaluate GitOps-based GitHub settings management tooling
- [RHAIENG-4233](https://redhat.atlassian.net/browse/RHAIENG-4233) — Adopt Mergify as Tide replacement
- [RHAIENG-4232](https://redhat.atlassian.net/browse/RHAIENG-4232) — Disable Prow/Tide auto-merge on main
- [RHAIENG-2346](https://redhat.atlassian.net/browse/RHAIENG-2346) — Switch from Prow OWNERS to GitHub CODEOWNERS
