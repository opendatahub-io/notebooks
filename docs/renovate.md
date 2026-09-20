# Renovate Bot Configuration

This repository uses [Renovate](https://docs.renovatebot.com/) for automated dependency updates, configured via `.github/renovate.json5`.

## Config file format

The config uses [JSON5](https://json5.org/) (`.json5` extension) to allow inline comments.
If both `.github/renovate.json` and `.github/renovate.json5` exist, Renovate ignores the `.json5` file.

## Enabled managers

| Manager | Purpose | Schedule |
|---------|---------|----------|
| `tekton` | Updates task digests in `.tekton/` pipeline definitions | After 5am on Saturday |
| `dockerfile` | Updates `FROM` statements in Dockerfiles | Before 5am |
| `custom.regex` | Tracks `BASE_IMAGE=` references in Konflux and ODH build-args files | Default |
| `github-actions` | Updates and pins GitHub Actions references | Default |

### Custom regex manager: BASE_IMAGE tracking

Workbench and runtime images store their base image references in shell-variable syntax (`BASE_IMAGE=registry/repo:tag`) inside build-args files. The built-in `dockerfile` manager cannot parse these, so two `customManagers` entries with `customType: "regex"` handle them:

- Konflux files: `(jupyter|codeserver|runtimes)/.+/build-args/konflux\..+\.conf$`
- ODH files: `(jupyter|codeserver|runtimes)/.+/build-args/(cpu|cuda|rocm)\.conf$`

Konflux versioning supports stable tags such as `3.4.0-1773428606` and EA tags such as `3.4.0-ea.<sequence>-<timestamp>`. ODH build-args use Docker versioning because they track `latest` plus a digest.

### Base image upgrade policy

| Branch / Repo | Major/minor upgrades | Patch/build upgrades |
|---------------|---------------------|---------------------|
| `main` on `opendatahub-io/notebooks` | Allowed | Allowed |
| `rhoai-2.25`, `rhoai-3.3`, `rhoai-3.4`, `rhoai-3.5` on `red-hat-data-services/notebooks` | Blocked | Allowed |
| Other branches, including RHDS `main` | Blocked | Allowed |

## Deprecated options and migrations

Key Renovate option renames to be aware of when editing the config:

| Deprecated | Replacement | Notes |
|------------|-------------|-------|
| `fileMatch` | `managerFilePatterns` | Patterns must be wrapped in `/pattern/` delimiters. Deprecated since Renovate v40.9.1 (May 2025). Applies to both built-in managers and `customManagers`. |
| `regexManagers` | `customManagers` | Renamed; `customType` field distinguishes manager types. |
| `lookupNameTemplate` | `packageNameTemplate` | Auto-migrated. |
| `versionScheme` | `versioning` | Auto-migrated. |
| `allowedPostUpgradeCommands` | `allowedCommands` | Auto-migrated. |
| `masterIssue` | `dependencyDashboard` | Auto-migrated. |

Options currently used by this repository and not part of the migration table above:
- `datasourceTemplate` (valid in `customManagers`)
- `versioningTemplate` (valid in `customManagers`)
- `customType` (valid in `customManagers`)

## Tekton task references

MintMaker handles Tekton task references from `quay.io/redhat-appstudio-tekton-catalog/` and `quay.io/konflux-ci/tekton-catalog/`. They are grouped into a single PR per branch (`branchPrefix: "konflux/references/"`). The self-hosted workflow excludes the `tekton` manager because MintMaker supplies server-side migration support for these updates.

For major/minor updates, the PR body includes a link to the task's `MIGRATION.md` file in the [build-definitions](https://github.com/redhat-appstudio/build-definitions) repository.

## MintMaker and self-hosted Renovate

MintMaker runs on `opendatahub-io/notebooks` `main` and on the supported RHDS release branches `rhoai-2.25`, `rhoai-3.3`, `rhoai-3.4`, and `rhoai-3.5`. It is disabled on ODH non-main branches and on RHDS `main`, EA, and EOL branches. MintMaker uses `platformCommit: "enabled"` and creates branches with the `konflux/mintmaker/` prefix.

The repository also has a self-hosted workflow at `.github/workflows/renovate-self-hosted.yaml`. It runs daily at 05:00 UTC for the configured repositories and can be started manually with `workflow_dispatch`, including lookup, full, and extract dry-run modes. Self-hosted runs process Dockerfiles, custom regex managers, and GitHub Actions; Tekton is intentionally excluded because MintMaker handles it.

`"forkProcessing": "enabled"` permits Renovate to process forks, but does not independently schedule or launch runs there. Actual execution is controlled by MintMaker's branch configuration or the self-hosted workflow.

Validate the repository-specific configuration with:

```bash
make validate-renovate-config
```

## References

- [Renovate configuration options](https://docs.renovatebot.com/configuration-options/)
- [Konflux MintMaker docs](https://konflux.pages.redhat.com/docs/users/mintmaker/user.html)
- [Upstream MintMaker config](https://github.com/konflux-ci/mintmaker/blob/main/config/renovate/renovate.json)
