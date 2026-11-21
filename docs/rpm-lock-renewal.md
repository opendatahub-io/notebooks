# Automated RPM lockfile renewal

The RPM lockfile renewal workflow keeps the hermetic RPM inputs used by the
notebook images current. It is defined in
[`.github/workflows/rpms-lock-renewal.yaml`](../.github/workflows/rpms-lock-renewal.yaml)
and is synchronized between the upstream ODH repository and the downstream RHDS
repository.

The workflow file is shared, but its scheduled behavior is intentionally
repository-specific. It uses `github.repository` to decide which branches and
lockfile variants to process.

## Repository roles

| Repository | Role |
| --- | --- |
| [`opendatahub-io/notebooks`](https://github.com/opendatahub-io/notebooks) | Upstream generation point for ODH and RHDS lockfiles on `main`. |
| [`red-hat-data-services/notebooks`](https://github.com/red-hat-data-services/notebooks) | Downstream generation point for RHDS release branches. |

The workflow is expected to be changed in the ODH repository first and then
synchronized to RHDS. Repository-specific credentials and GitHub settings do
not synchronize with the file; see [Credentials and repository settings](#credentials-and-repository-settings).

## Schedule

Both repositories run the workflow on the following schedule:

```yaml
cron: "0 5 * * 3,5"
```

This is Wednesday and Friday at 05:00 UTC. Scheduled workflows run separately
in each repository after the workflow exists on that repository's default
branch.

## ODH scheduled run

When the scheduled event runs in `opendatahub-io/notebooks`, the workflow
selects:

```text
branches: main
variants: odh, rhds
```

The matrix therefore contains:

```text
main + odh
main + rhds
```

The run:

1. Checks out ODH `main`.
2. Generates the ODH lockfiles.
3. Generates the RHDS lockfiles for the same source branch.
4. Merges the variant results.
5. Runs repository validation with `make test`.
6. Creates or updates one combined renewal PR against ODH `main`.

The combined PR title is:

```text
GHA: (ODH+RHDS) Update RPM lock files
```

The ODH scheduled run is the upstream path that refreshes both variants for
`main`.

## RHDS scheduled run

When the scheduled event runs in `red-hat-data-services/notebooks`, the
workflow selects:

```text
branches: rhoai-2.25, rhoai-3.4, rhoai-3.5, rhoai-3.6
variant: rhds
```

The matrix contains one RHDS entry for each downstream release branch:

```text
rhoai-2.25 + rhds
rhoai-3.4  + rhds
rhoai-3.5  + rhds
rhoai-3.6  + rhds
```

The run:

1. Checks out each RHDS release branch.
2. Generates only the RHDS lockfiles.
3. Validates the generated changes.
4. Creates or updates a separate renewal PR for each release branch.

For example, the PR title for `rhoai-3.4` is:

```text
GHA: rhoai-3.4 - Update RHDS RPM lock files
```

The downstream scheduled run does not process ODH lockfiles and does not target
RHDS `main`.

### `rhoai-2.25` exception

The `rhoai-2.25` matrix entry is treated as a legacy branch. For this branch,
the workflow skips the RHDS-specific `git-crypt` unlock, registry
authentication, and subscription credential checks. Newer RHDS release
branches require those steps.

## Manual runs

The workflow can also be started from the Actions UI with `workflow_dispatch`.

In ODH, the supported choices are:

```text
variant: both, odh, rhds
branch: main, all
```

`all` currently resolves to the supported ODH branch set, which is `main`.

In RHDS, the repository-specific validation forces the variant to `rhds` and
supports:

```text
branch: rhoai-2.25, rhoai-3.4, rhoai-3.5, rhoai-3.6, all
```

`all` runs all supported RHDS release branches. A manual RHDS run targeting
`main` is rejected.

## Lockfile generation and cache behavior

Each matrix entry finds `rpms.in.yaml` files under the selected variant and
writes the corresponding `rpms.lock.yaml` files. The variant is selected from
paths such as:

```text
prefetch-input/odh/rpms.in.yaml
prefetch-input/rhds/rpms.in.yaml
```

The container build cache is scoped by repository, variant, and branch:

```text
ghcr.io/<repository>/rpm-lockfile-build-cache-<variant>-<branch>
```

The ODH variant can read and write its cache. The RHDS variant only reads its
cache; it does not publish new cache layers. This avoids publishing layers
that may contain content obtained from subscribed repositories.

## Credentials and repository settings

The workflow file is synchronized, but GitHub Actions secrets are configured
independently in each repository.

RHDS generation on newer release branches requires:

| Secret | Purpose |
| --- | --- |
| `GIT_CRYPT_KEY` | Unlocks encrypted RHDS repository configuration. |
| `SUBSCRIPTION_ACTIVATION_KEY` | Provides access to subscribed RPM repositories. |
| `SUBSCRIPTION_ORG` | Identifies the subscription organization. |
| `GH_ACCESS_TOKEN` | Allows the workflow to push temporary/renewal branches and create or update PRs. |

`GITHUB_TOKEN` is provided by GitHub and is used for operations such as GHCR
login, PR approval, and label updates. Its effective permissions still depend
on the repository's Actions settings.

The RHDS repository must independently have Actions enabled, the required
secrets configured, and the permissions/merge automation needed for the
renewal PRs. ODH secrets and repository settings are not copied by a source
sync.

## Branch and PR lifecycle

For each variant, the workflow creates a temporary branch similar to:

```text
rpm-lockfile-<variant>-<branch>-<run-id>-<attempt>
```

For a combined ODH run, the variant branches are cherry-picked into:

```text
rpm-lockfile-renewal-both-<branch>
```

The workflow then:

1. Runs `make test`.
2. Creates or updates the renewal PR.
3. Adds the `automated-rpms-lockfile-update` label.
4. Approves the PR using the workflow token.
5. Adds the merge labels used by the repository's merge automation.
6. Allows Tide/merge automation to merge after the required checks pass.

## Changing the workflow

Make workflow logic changes in ODH first:

1. Update `.github/workflows/rpms-lock-renewal.yaml` in
   `opendatahub-io/notebooks`.
2. Open and merge the ODH PR.
3. Synchronize the workflow file to
   `red-hat-data-services/notebooks`.
4. Confirm that the downstream sync includes
   `.github/workflows/rpms-lock-renewal.yaml`.
5. After the sync reaches RHDS `main`, manually dispatch the workflow there if
   an immediate verification is needed.

The same YAML will execute in the context of the repository where it runs. In
particular, `${{ github.repository }}` controls the repository-specific branch
and variant selection, while RHDS uses its own secrets and GHCR cache.

## Troubleshooting checklist

When the downstream job does not behave as expected, check:

- The workflow file reached RHDS `main`.
- The run was started in the expected repository; ODH and RHDS have different
  scheduled matrices.
- RHDS has `GIT_CRYPT_KEY`, `SUBSCRIPTION_ACTIVATION_KEY`, and
  `SUBSCRIPTION_ORG` configured.
- `GH_ACCESS_TOKEN` can push branches and create/update PRs in the target
  repository.
- The requested branch is valid for the repository.
- The `rhoai-2.25` legacy exception is not being confused with the newer RHDS
  credential flow.
- Required checks and Tide labels are available for the generated PR.
