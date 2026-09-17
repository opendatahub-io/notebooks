# RHOAI additional notebooks overlay

Tier 1 notebook and runtime images supported by the ODH community but **not**
included in the RHOAI operator bundle (`manifests/rhoai/base/`).

The parent overlay renders the RHOAI base manifests with component labels.
Baseline images require a separate admin opt-in: neither this parent overlay nor
`manifests/rhoai/base/` includes `baseline/` in its resource list.

## Baseline images

| Sub-overlay | ImageStreams |
|-------------|--------------|
| [baseline/](baseline/) | `jupyter-baseline-notebook`, `code-server-baseline-notebook`, `runtime-baseline` |

Baseline images publish to `quay.io/opendatahub` and reuse ImageStream definitions
from `manifests/odh/base/`. On ODH clusters they are already present in the
operator bundle; on RHOAI clusters an admin must explicitly apply `baseline/` to
register them. Until then, their ImageStreams are absent from the cluster. See
[baseline/](baseline/) for the enable and remove commands.

## Render locally

```bash
# RHOAI base with component labels (no baseline images)
kustomize build manifests/rhoai/overlays/additional

# Explicit opt-in: render baseline ImageStreams only
kustomize build --load-restrictor LoadRestrictionsNone manifests/rhoai/overlays/additional/baseline
```
