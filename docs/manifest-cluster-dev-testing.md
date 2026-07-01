# Testing notebook manifest changes on a cluster (ODH / RHOAI)

Apply local ImageStream manifest edits to a dev/test cluster using
`scripts/apply-manifests-dev.sh`. The same script and workflow work for
**Open Data Hub (ODH)** upstream and **Red Hat OpenShift AI (RHOAI)** downstream;
only the `--platform` flag and default namespaces differ.

**Not for production.** This bypasses the operator’s normal release path. It is a replacment for the recently deprecation of `devFlags` provided by the operator. 
Changes may be
overwritten on operator upgrade or workbenches reconcile.

For how manifests are normally consumed, see [manifests/README.md](../manifests/README.md).

## When to use this

- You changed ImageStream YAML, annotations, tags, or `.env` files under
  `manifests/odh/base/` or `manifests/rhoai/base/` and want to validate on a
  cluster before opening a PR.
- A colleague needs to repeat the same check on their cluster.

## Prerequisites

- `oc` logged in with permission to edit ImageStreams in the target namespace(s).
- `kustomize` installed locally.
- A checkout of this repo with your manifest edits.
- ODH or RHOAI operator running with workbenches **Managed**.

If you changed `kustomization.yaml` or added/removed ImageStreams, regenerate first:

```bash
# ODH
uv run manifests/tools/generate_kustomization.py manifests/odh/base

# RHOAI
uv run manifests/tools/generate_kustomization.py manifests/rhoai/base
```

## Quick start

Run from the **repo root**:

### Examples

```bash
# ODH 
./scripts/apply-manifests-dev.sh --platform odh apply
# RHOAI 
./scripts/apply-manifests-dev.sh --platform rhoai apply

# Both
./scripts/apply-manifests-dev.sh apply --target both

# Revert (platform read from snapshot if omitted)
./scripts/apply-manifests-dev.sh revert --clean-test
./scripts/apply-manifests-dev.sh --platform odh revert --clean-test
```

## Commands

| Command | Description |
|---------|-------------|
| `apply` | Snapshot operator baseline, build manifests with real image digests, apply, restart dashboard |
| `revert` | Re-apply saved operator baseline |
| `preview` | Print `kustomize build` output (no cluster changes) |
| `snapshot` | Save operator baseline only |

```bash
./scripts/apply-manifests-dev.sh --help
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--platform odh\|rhoai` | `rhoai` | Select manifest tree and cluster defaults |
| `--target applications` | yes | Apply to applications/dashboard namespace |
| `--target workbench` | | Apply to DSC `workbenchNamespace` |
| `--target both` | | Apply to both |
| `--clean-test` | | With `revert`: delete ImageStreams added by the last `apply` |
| `--dry-run` | | Client-side dry-run only |
| `--no-restart-dashboard` | | Skip dashboard rollout after apply |
| `--revert-dir DIR` | platform-specific | Snapshot directory |
| `--operator-ns NS` | see table above | Operator namespace |
| `--applications-ns NS` | see table above | Dashboard namespace |


## Verify after apply

```bash
# ODH
oc get imagestreams -n opendatahub -l opendatahub.io/component=true
oc get route -n opendatahub | grep -i dashboard

# RHOAI
oc get imagestreams -n redhat-ods-applications -l opendatahub.io/component=true
oc get route -n redhat-ods-applications | grep -i dashboard
```

Open the dashboard route → **Workbenches** and confirm images/tags. Hard-refresh if needed.

## Revert notes

- `revert` restores ImageStream **content** to the operator baseline from the last `apply`.
- ImageStreams **remain visible** after revert — expected. Use `--clean-test` to remove
  ImageStreams your apply added that were not in the operator bundle.
- Snapshots live in `/tmp/odh-manifests-revert` or `/tmp/rhoai-manifests-revert`.


## Platform defaults

| | **ODH** (`--platform odh`) | **RHOAI** (`--platform rhoai`, default) |
|---|---------------------------|----------------------------------------|
| Local manifests | `manifests/odh/base/` | `manifests/rhoai/base/` |
| Operator namespace | `opendatahub-operator` | `redhat-ods-operator` |
| Operator pod label | `name=opendatahub-operator` | `name=rhods-operator` |
| Applications / dashboard NS | `opendatahub` | `redhat-ods-applications` |
| Dashboard deployment | `odh-dashboard` | `rhods-dashboard` |
| Default workbench NS | `opendatahub` | `rhods-notebooks` (if set in DSC) |
| Revert snapshot dir | `/tmp/odh-manifests-revert` | `/tmp/rhoai-manifests-revert` |

Override namespaces when your install differs:

```bash
./scripts/apply-manifests-dev.sh --platform odh \
  --operator-ns openshift-operators apply
```

Use `--target applications` for dashboard UI testing (default). Use `--target both`
to apply to the applications namespace and the DSC `workbenchNamespace`.

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `Workbenches must be Managed` | Set `managementState: Managed` on DSC workbenches |
| `No operator pod` | Omit `--operator-ns` (auto-discovered). RHOAI default: `redhat-ods-operator`; ODH: `opendatahub-operator` |
| Dashboard shows old images | Use `--target applications`; hard-refresh browser |
| `No revert snapshot` | Run `apply` first (snapshots automatically) |
| ImageStreams still visible after revert | Pre-existing cluster ImageStreams are expected |
| Wrong platform on revert | Pass `--platform` or use matching `--revert-dir` |

## Related

- [manifests/README.md](../manifests/README.md) — manifest layout and operator pipeline
- [opendatahub-operator custom manifests](https://github.com/opendatahub-io/opendatahub-operator/blob/main/hack/component-dev/README.md)
- [rhods-operator custom manifests](https://github.com/red-hat-data-services/rhods-operator/blob/main/hack/component-dev/README.md)
