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

| ImageStream | Quay image |
|-------------|------------|
| `jupyter-baseline-notebook` | `odh-workbench-jupyter-baseline-cpu-py312-c9s` |
| `code-server-baseline-notebook` | `odh-workbench-codeserver-baseline-cpu-py312-c9s` |
| `runtime-baseline` | `odh-pipeline-runtime-baseline-cpu-py312-c9s` |

## Preview

```bash
kustomize build --load-restrictor LoadRestrictionsNone \
  manifests/rhoai/overlays/additional/baseline
```

## Apply on a cluster

```bash
# Enable baseline images in the applications namespace
./scripts/apply-baseline-imagestreams.sh apply

# Remove all resources created by the enable command
./scripts/apply-baseline-imagestreams.sh revert
```

Registration makes the images available to users of that applications namespace;
it does not start workbenches or pipeline runs. This is an admin opt-in, not a
per-user visibility setting.
