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
   `renovatebot/github-action` on a schedule and `workflow_dispatch`, using the same
   config file and a **`RENOVATE_TOKEN`** PAT so PRs can trigger normal CI.

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

```bash
# PAT: classic `repo` + `workflow` (or fine-grained equivalent on this repo only).
# Prefer reading from a file or env var; do not commit the token.
gh secret set RENOVATE_TOKEN --repo OWNER/REPO < pat-renovate.txt

# Same base64-encoded key as other workflows that unlock ci/secrets (see build workflows).
gh secret set GIT_CRYPT_KEY --repo OWNER/REPO < git-crypt-key.b64.txt

# Optional: quay.io/aipcc robot for Renovate image lookups (skip if unused).
gh secret set AIPCC_QUAY_BOT_USERNAME --repo OWNER/REPO --body 'robot$...'
gh secret set AIPCC_QUAY_BOT_PASSWORD --repo OWNER/REPO < aipcc-password.txt
```

Replace `OWNER/REPO` (for example `jiridanek/notebooks` on a fork or `opendatahub-io/notebooks` upstream). Use `gh auth refresh -s write:packages` if `gh secret set` fails on scope.

### Self-hosted run log quirks (forks)

- **Private image lookups (`no-result`)** — `renovatebot/github-action` runs Renovate in Docker and, by default, **does not pass `DOCKER_CONFIG`** into the container. The workflow sets **`env-regex`** to include `DOCKER_CONFIG` and stores merged **`config.json` under `/tmp`** so the action’s default **`/tmp:/tmp`** mount exposes registry auth inside the container.
- **`allowedCommands`, `inheritConfig`, `onboarding`, … “global only”** — Those keys exist for **MintMaker’s** merged global config. Self-hosted runs **warn** when they appear in repo `renovate.json5`; MintMaker continues to use them upstream. Harmless noise unless something actually fails.
- **`matchBaseBranches` / `baseBranchPatterns`** — Same as upstream comment in `renovate.json5`: top-level `baseBranchPatterns` is avoided so MintMaker’s per-branch behavior is not overridden; local dry-runs may warn.
- **`gitAuthor` / unverified commits** — Set **`RENOVATE_GIT_AUTHOR`** in the workflow env (or `gitAuthor` in config) to your own **`Name <email>`** if you dislike the default Mend address.
- **Dependency dashboard issue** — Requires **GitHub Issues enabled** on the repository; enable on the fork or ignore the log line.

## References

- `.github/renovate.json5`
- `.github/workflows/renovate-self-hosted.yaml`
- `.github/workflows/piplock-renewal.yaml`
- [ADR 0008 — Pin GitHub Actions by SHA](0008-harden-github-actions-pin-sha-digests.md)
