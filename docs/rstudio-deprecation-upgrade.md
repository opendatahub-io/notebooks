# RStudio deprecation after RHOAI 3.4 → 3.5 upgrade

RStudio workbench images were removed from the notebooks repository in [RHAIENG-4776](https://redhat.atlassian.net/browse/RHAIENG-4776) and are no longer shipped with RHOAI 3.5. Fresh 3.5 installs do not include RStudio.

When upgrading an existing cluster from **RHOAI 3.4** to **3.5**, orphaned RStudio resources can remain in the workbenches namespace:

| Resource kind | Name | Action |
| --- | --- | --- |
| BuildConfig | `rstudio-server-rhel9` | Delete |
| BuildConfig | `cuda-rstudio-server-rhel9` | Delete |
| ImageStream | `rstudio-rhel9` | Delete (build output) |
| ImageStream | `cuda-rstudio-rhel9` | Delete (build output) |
| ImageStream | `rstudio-gpu-notebook` | Deprecate all tags |
| ImageStream | `rstudio-notebook` | Deprecate all tags (if present) |

These leftovers do not block the upgrade or normal RHOAI operation, but they can confuse operators and still expose RStudio in the workbench spawner.

## Who should run this

Platform or cluster administrators with `oc` access to the RHOAI/ODH applications namespace, typically after the operator upgrade to 3.5 has completed.

## Prerequisites

- Logged in to the target cluster (`oc login`)
- `jq` installed
- Permission to delete BuildConfigs/ImageStreams and patch ImageStreams in the workbenches namespace

## Script

[`scripts/deprecate-rstudio-on-upgrade.sh`](../scripts/deprecate-rstudio-on-upgrade.sh)

### Usage

Preview changes:

```bash
./scripts/deprecate-rstudio-on-upgrade.sh --dry-run
```

Apply on RHOAI (default namespace auto-detection tries `redhat-ods-applications`, then `opendatahub`):

```bash
./scripts/deprecate-rstudio-on-upgrade.sh
```

Explicit namespace:

```bash
./scripts/deprecate-rstudio-on-upgrade.sh -n redhat-ods-applications
```

### What the script does

1. **Deletes** the two legacy RStudio BuildConfigs and their internal build ImageStreams.
2. **Deprecates** remaining RStudio notebook ImageStreams by setting on every tag:
   - `opendatahub.io/image-tag-outdated: "true"`
   - `opendatahub.io/workbench-image-recommended: "false"`

Deprecation follows the same pattern used for N-1 workbench image tags elsewhere in this repository. Existing RStudio workbenches continue to run; the images are hidden from the spawner for new workbenches.

The script is idempotent: missing resources are skipped safely.

## Verification

```bash
# BuildConfigs should be gone
oc get buildconfig -n redhat-ods-applications | grep -i rstudio || echo "no rstudio buildconfigs"

# Notebook imagestreams should show outdated tags (if still present)
oc get imagestream rstudio-gpu-notebook -n redhat-ods-applications \
  -o jsonpath='{range .spec.tags[*]}{.name}{": outdated="}{.annotations.opendatahub\.io/image-tag-outdated}{"\n"}{end}'
```

## Related work

- [RHAIENG-5327](https://redhat.atlassian.net/browse/RHAIENG-5327) — operator/build-config removal for 3.5
- [RHAIENG-4776](https://redhat.atlassian.net/browse/RHAIENG-4776) — notebooks repo RStudio removal
