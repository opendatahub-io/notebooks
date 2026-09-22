# Baseline ImageStreams (RHOAI additional overlay)

Baseline workbench and runtime images are **not** in `manifests/rhoai/base/` because
they are community-tier, public-index images on CentOS Stream 9 (`c9s`). They ship
in the ODH product bundle (`manifests/odh/base/`) instead.

This overlay adds the three baseline `ImageStream` resources to a RHOAI deployment
**only when an admin explicitly applies it**. Neither `rhoai/base/` nor the parent
`additional/` overlay references it, so a default RHOAI installation does not
create these ImageStreams. The operator does not discover subdirectories automatically.

ImageStream YAMLs are reused from `manifests/odh/base/`; `quay.io/opendatahub/...`
refs resolve from the ODH `params-latest.env`.

Kustomize will not load those ODH files unless you pass
`--load-restrictor LoadRestrictionsNone`. `oc apply -k` cannot set that flag;
use the helper script (or pipe `kustomize build` into `oc apply`).


| ImageStream                     | Quay image                                        |
| ------------------------------- | ------------------------------------------------- |
| `jupyter-baseline-notebook`     | `odh-workbench-jupyter-baseline-cpu-py312-c9s`    |
| `code-server-baseline-notebook` | `odh-workbench-codeserver-baseline-cpu-py312-c9s` |
| `runtime-baseline`              | `odh-pipeline-runtime-baseline-cpu-py312-c9s`     |




## Preview

```bash
# confirm the right cluster
oc whoami
oc project -q

# optional: inspect rendered YAML first
./scripts/apply-baseline-imagestreams.sh preview
```

## Apply on a cluster

Run from the repository root, logged in as a cluster admin. The applications
namespace defaults to `redhat-ods-applications`.

```bash
# Enable baseline images (sets namespace, applies, restarts rhods-dashboard)
./scripts/apply-baseline-imagestreams.sh apply

# Remove all resources created by the enable command
./scripts/apply-baseline-imagestreams.sh revert
```

Registration makes the images available to users of that applications namespace;
it does not start workbenches or pipeline runs. This is an admin opt-in, not a
per-user visibility setting.