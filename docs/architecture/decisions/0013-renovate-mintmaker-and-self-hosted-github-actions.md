# 13. Renovate: MintMaker config and optional self-hosted GitHub Actions

Date: 2026-04-11

## Status

Accepted

## Context

### Mend MintMaker (Konflux)

Red Hat AI/Konflux uses **Mend MintMaker**—a managed Renovate deployment—to open PRs
for dependency and base-image updates on GitHub repos that are wired into the Konflux
release pipeline. Maintainer documentation:

- [MintMaker user guide](https://konflux.pages.redhat.com/docs/users/mintmaker/user.html)
- [Upstream MintMaker Renovate preset](https://github.com/konflux-ci/mintmaker/blob/main/config/renovate/renovate.json)

Enabling Renovate for a component often involves **Konflux release data** changes (for
example, GitLab MRs under `releng/konflux-release-data`) so MintMaker tracks the correct
repository and branches—not only committing `renovate.json5` to the repo.

### Repository config (this repo)

The bot reads **`.github/renovate.json5`**. It extends MintMaker-oriented settings and
enables managers for **Tekton** (`.tekton/**`), **Dockerfile** `FROM` updates, a
**custom regex** manager for `BASE_IMAGE=` in Konflux `build-args/konflux.*.conf` files,
and **GitHub Actions** digest pinning (see [ADR 0008](0008-harden-github-actions-pin-sha-digests.md)).
Python notebook lockfiles are **not** managed by Renovate; they are refreshed by
`make refresh-lock-files` and
[`piplock-renewal.yaml`](../../../.github/workflows/piplock-renewal.yaml).

`inheritConfig: true` and other globals are intended to cooperate with **server-side**
MintMaker configuration; local `renovate --dry-run` may warn about options that belong in
the hosted bot config.

### Operational gap: ODH vs RHDS GitHub org

In practice, MintMaker **does not always run against every GitHub remote** for a given
codebase. Maintainers observed that Renovate was **not** opening updates on
**`opendatahub-io/notebooks`** while it **was** running for **`red-hat-data-services/notebooks`**.

Discussion (internal Slack, including investigation of missing PRs, `dependencyDashboard`,
`baseBranches` / `matchBaseBranches`, and Tekton schedule):

- [Thread in `#C07SBP17R7Z`](https://redhat-internal.slack.com/archives/C07SBP17R7Z/p1774883190029089?thread_ts=1774883072.749099&cid=C07SBP17R7Z)

That gap is the main reason to add an **optional, self-hosted** Renovate path on the ODH
repository: contributors still get automated dependency PRs when the org bot is not
processing this remote.

## Decision

1. **Keep `.github/renovate.json5` as the repo-local Renovate contract** for MintMaker
   when it *does* run (managers, `packageRules`, branch prefixes, schedules, allowed
   digest/grouping rules).

2. **Add `.github/workflows/renovate-self-hosted.yaml`** (optional) to run
   [`scripts/ci/renovate_run.py`](../../../scripts/ci/renovate_run.py) (Renovate container via Docker on CI, `CONTAINER_ENGINE=docker`) on a schedule and `workflow_dispatch`, using the same config file and a **`RENOVATE_TOKEN`** PAT so PRs can trigger normal CI. The workflow no longer uses `renovatebot/github-action`; the Renovate **image tag** is pinned with **`RENOVATE_IMAGE`** (default `ghcr.io/renovatebot/renovate:43`), so bump that env var in the workflow or script when upgrading.

3. **The self-hosted workflow** uses a split gate:
   `github.event_name != 'schedule' || github.repository_owner == 'opendatahub-io'`
   (any manual trigger; scheduled runs only on `opendatahub-io`).

4. **On `opendatahub-io/notebooks`**, if MintMaker is later confirmed to run reliably,
   **remove the self-hosted workflow schedule** (or delete the workflow) to avoid
   **duplicate PRs** for the same updates.

5. **Use the Dependency Dashboard** (`dependencyDashboard` in config) when diagnosing
   silent failures (auth, regex, schedule, or ignored rules)—as recommended in the same
   thread and exercised in
   [#3240](https://github.com/opendatahub-io/notebooks/pull/3240),
   [#3246](https://github.com/opendatahub-io/notebooks/issues/3246),
   [#3257](https://github.com/opendatahub-io/notebooks/pull/3257).

## Consequences

### Positive

- ODH maintainers get Renovate PRs even when MintMaker is only attached to the RHDS fork.
- Single config file (`.github/renovate.json5`) for both MintMaker and self-hosted runs.
- Manual **Run workflow** allows on-demand runs without waiting for MintMaker’s queue.

### Negative / risks

- **Forks** do not get scheduled runs; they can still use **Run workflow** manually if
  they configure secrets.
- **Duplicate PRs** if both MintMaker and self-hosted Renovate run against the same repo;
  operators must disable one path.
- **PAT hygiene**: `RENOVATE_TOKEN` must be scoped and rotated; it is more powerful than
  `GITHUB_TOKEN` for PR creation and check triggering.
- **inheritConfig**: self-hosted runs may lack Mend’s parent config; if runs error or
  behave differently, set `RENOVATE_INHERIT_CONFIG=false` in the workflow env or adjust
  `renovate.json5` (see comments in `renovate-self-hosted.yaml`).

### Non-goals

- Moving Python **pylock** / **`uv pip compile`** renewal into Renovate (remains the
  lockfile renewal workflow and `scripts/pylocks_generator.py`).

## Operational setup (fork or upstream)

Configure repository secrets before the workflow can succeed. Using the [GitHub CLI](https://cli.github.com/):

### RENOVATE_TOKEN: GitHub PAT permissions

Renovate clones with the token, **pushes** update branches, and opens or updates **pull requests**. A read-only or metadata-only token can still “work” until the first `git push`, which then fails with **HTTP 403** (`Permission denied` / `unable to access`).

GitHub publishes the same scope names for **classic PATs** as in [Scopes for OAuth apps](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps#available-scopes) (see the **Available scopes** table).

**Classic PAT (tokens “classic”)**

| Scope | When you need it |
| --- | --- |
| **`repo`** | Full read/write to **public and private** repositories you can access, including code. Use for **private** repos or when you want one broad scope. ([`repo`](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps#available-scopes)) |
| **`public_repo`** | Read/write limited to **public** repositories only—narrower than `repo` when Renovate targets only a **public** fork (for example `YOUR_USER/notebooks`). ([`public_repo`](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps#available-scopes)) |
| **`workflow`** | Required when commits change **GitHub Actions workflow** files under `.github/workflows/`. This repository enables the **`github-actions`** Renovate manager, so PRs often retarget action SHAs in workflows; without `workflow`, pushes that touch those files can be rejected. ([`workflow`](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps#available-scopes)) |

For PRs from Renovate to run **GitHub Actions** checks on the fork, the token must be allowed to do that (the workflow already documents **`workflow`** on the classic PAT; org policies may still block workflows from forks).

**Fine-grained PAT**

1. Under **Repository access**, choose **Only select repositories** and include **exactly** the repo Renovate updates (for example your fork).
2. Under **Repository permissions**, set at least:
   - **Contents**: **Read and write** — push branches and commits (GitHub’s token UI labels this “Read and write”; the REST prefill parameter is `contents=write`). See [Managing your personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token) and the permissions table under **Repository Permissions** (`contents`, `pull_requests`, `workflows`).
   - **Pull requests**: **Read and write** — create and update PRs.
   - **Workflows**: **Write** (the only access level GitHub documents for this permission) — same reason as classic `workflow` when Renovate updates `.github/workflows/**`.
3. Optional: **Issues**: **Read and write** — only if you rely on Renovate’s **dependency dashboard** (`dependencyDashboard`), which creates an issue.
4. **Metadata** is read-only and always included.

GitHub’s own “update code and open a PR” template pre-selects **`contents=write`**, **`pull_requests=write`**, and **`workflows=write`** ([link to token creation with those parameters](https://github.com/settings/personal-access-tokens/new?name=Core-loop+token&description=Write%20code%20and%20push%20it%20to%20main%21%20Includes%20permission%20to%20edit%20workflow%20files%20for%20Actions%20-%20remove%20%60workflows%3Awrite%60%20if%20you%20don%27t%20need%20to%20do%20that&contents=write&pull_requests=write&workflows=write)).

Fine-grained PATs **cannot do everything** classic PATs can (for example some org/outside-collaborator and public-repo scenarios). See [Fine-grained personal access tokens limitations](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#fine-grained-personal-access-tokens-limitations). Renovate’s bot also documents tradeoffs (for example some GraphQL/Checks-related behavior) in [renovatebot/renovate discussions](https://github.com/renovatebot/renovate/discussions/25545).

```bash
# PAT: classic — typically `public_repo` or `repo`, plus `workflow` (see table above).
# Or fine-grained — Contents + Pull requests + Workflows (and optional Issues) on this repo only.
# Prefer reading from a file or env var; do not commit the token.
gh secret set RENOVATE_TOKEN --repo OWNER/REPO < pat-renovate.txt

# Same base64-encoded key as other workflows that unlock ci/secrets (see build workflows).
gh secret set GIT_CRYPT_KEY --repo OWNER/REPO < git-crypt-key.b64.txt

# Optional: quay.io/aipcc robot for Renovate image lookups (skip if unused).
gh secret set AIPCC_QUAY_BOT_USERNAME --repo OWNER/REPO --body 'robot$...'
gh secret set AIPCC_QUAY_BOT_PASSWORD --repo OWNER/REPO < aipcc-password.txt
```

Replace `OWNER/REPO` (for example `jiridanek/notebooks` on a fork or `opendatahub-io/notebooks` upstream). Use `gh auth refresh -s write:packages` if `gh secret set` fails on scope.

### GitHub org ruleset: "File path is restricted" (422 on `POST /git/trees`)

The `opendatahub-io` org has a **file path restriction** ruleset (managed in
[`opendatahub-io/security-config`](https://github.com/opendatahub-io/security-config))
that protects files like `semgrep.yaml`, `.coderabbit.yaml`, and `.gitleaksignore`
from modification by non-bypass actors.

Renovate's `pushFiles` sends the **entire repo tree** (via `listCommitTree`) to
`POST /repos/{owner}/{repo}/git/trees` without `base_tree`. GitHub validates all
file paths in the submitted tree — including unchanged protected files — and returns
**422 "Repository rule violations found / File path is restricted"**, even when
Renovate only changed unrestricted paths like `build-args/konflux.*.conf`.

- **Upstream bug**: [renovatebot/renovate#42554](https://github.com/renovatebot/renovate/issues/42554)
- **`platformCommit: "disabled"`** does NOT help — `commitFiles()` always calls `pushFiles()`
- **Workaround**: ask the org admin (Ugo Giordano / `@U02AADEDP7B` in Slack
  `#wg-openshift-ai-odh-github`) to add the Renovate PAT user (`ide-developer`)
  as a **bypass actor** on the file path restriction ruleset. This was already done
  for [`opendatahub-io/opendatahub-tests`](https://redhat-internal.slack.com/archives/C09BV0L6ULQ/p1773076687051249?thread_ts=1772554653.543679&cid=C09BV0L6ULQ).
- **Proposed fix**: use `base_tree` + only changed files in `POST /git/trees` instead of
  the full tree. A patched image is available at `quay.io/jdanek/renovate:43-fix42554`
  (amd64 + arm64); to test, set `RENOVATE_IMAGE` in the workflow env.

### Self-hosted run log quirks (forks)

- **HTTP 403 on `git push`** — The PAT can read the repo but cannot **write** contents (or **workflows** when workflow files change). Fix scopes or fine-grained permissions per **RENOVATE_TOKEN: GitHub PAT permissions** above; **Contents: Read-only** on a fine-grained token is a common cause.
- **Private image lookups (`no-result`)** — The workflow merges pull-secret (and optional `quay.io/aipcc` login) into **`config.json` under `DOCKER_CONFIG`**, mounts that directory read-only into the container, runs **`scripts/ci/docker_config_to_renovate_host_rules.py`** to set **`RENOVATE_HOST_RULES`**, and **`renovate_run.py`** forwards both to the Renovate process (Renovate often still reports `no-result` for private tags when only `DOCKER_CONFIG` is present).
- **`allowedCommands`, `inheritConfig`, `onboarding`, … “global only”** — Those keys exist for **MintMaker’s** merged global config. Self-hosted runs **warn** when they appear in repo `renovate.json5`; MintMaker continues to use them upstream. Harmless noise unless something actually fails.
- **`matchBaseBranches` / `baseBranchPatterns`** — Same as upstream comment in `renovate.json5`: top-level `baseBranchPatterns` is avoided so MintMaker’s per-branch behavior is not overridden; local dry-runs may warn.
- **`gitAuthor` / unverified commits** — Set **`RENOVATE_GIT_AUTHOR`** in the workflow env (or `gitAuthor` in config) to your own **`Name <email>`** if you dislike the default Mend address.
- **Dependency dashboard issue** — Requires **GitHub Issues enabled** on the repository; enable on the fork or ignore the log line.

## References

- `.github/renovate.json5`
- `.github/workflows/renovate-self-hosted.yaml`
- `scripts/ci/docker_config_to_renovate_host_rules.py`
- `.github/workflows/piplock-renewal.yaml`
- [ADR 0008 — Pin GitHub Actions by SHA](0008-harden-github-actions-pin-sha-digests.md)
