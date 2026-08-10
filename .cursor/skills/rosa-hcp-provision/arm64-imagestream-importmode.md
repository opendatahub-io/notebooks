# arm64 workbench spawn fails with "Exec format error" on ROSA/ARO HCP

Root-caused and fixed live on `jd-arm64-36e1` (ROSA HCP, OCP 4.21.0, arm64
`g5g.2xlarge`/`m6g.2xlarge` worker NodePools). This is **not an RHOAI bug** —
it's a core OpenShift behavior gap specific to Hosted Control Plane
clusters, tracked upstream. Applies to any RHOAI version (GA or EA) on any
ROSA/ARO HCP cluster with non-amd64 worker NodePools.

## Symptom

A workbench (or any RHOAI-managed pod backed by an ImageStream) scheduled
correctly on an arm64 worker crash-loops:

```
exec container process `/opt/app-root/bin/start-notebook.sh`: Exec format error
```

...even though the underlying image genuinely ships an arm64 variant:

```bash
skopeo inspect --raw --no-tags docker://quay.io/rhoai/odh-workbench-jupyter-pytorch-cuda-py312-rhel9@<manifest-list-digest> | \
  jq -c '[.manifests[]? | {arch: .platform.architecture, os: .platform.os}] | unique'
# -> includes {"arch":"arm64","os":"linux"}
```

## Root cause

The ImageStreamTag resolved to the **amd64** sub-manifest despite the
manifest list containing arm64. Confirm via:

```bash
oc get imagestream <name> -n redhat-ods-applications -o json | \
  jq -c '.spec.tags[] | {name, importPolicy}'
# -> importPolicy.importMode: "Legacy" (or omitted, which defaults to Legacy)
```

`Legacy` import mode discards the manifest list and keeps only one
sub-manifest; platform selection falls back to the API server process's
own architecture — amd64, since **HCP control planes always run on Red
Hat's amd64 management infrastructure regardless of the guest workers'
architecture**. `PreserveOriginal` keeps the full manifest list so the
kubelet can select the right platform at pull time — this is what should
be happening, and isn't.

**Verified NOT to be an RHOAI defect** — the RHOAI/ODH ImageStream
manifests (`manifests/rhoai/base/*-imagestream.yaml` in
`opendatahub-io/notebooks` and its downstream fork) never set
`importPolicy` on any tag, and `workbenches-operator` applies them via
plain Server-Side Apply with no code touching `importPolicy`. The default
is injected entirely by core OpenShift:

1. `openshift/openshift-apiserver`, `pkg/image/apis/image/v1/defaults.go`
   — `SetDefaults_TagImportPolicy` fills in `apisimage.DefaultImportMode`
   whenever a tag omits `importPolicy`.
2. `pkg/image/apis/image/types.go` — that package variable's static
   initializer is `Legacy`.
3. `pkg/cmd/openshift-apiserver/openshiftapiserver/openshift_apiserver.go`
   — the variable *can* be overridden at process startup from
   `ExtraConfig.ImageStreamImportMode`.
4. `openshift/cluster-openshift-apiserver-operator`,
   `pkg/operator/configobservation/images/observe_images.go`'s
   `ObserveImagestreamImportMode` — a config-observer that's supposed to
   read `image.config.openshift.io/cluster`'s **`status.imageStreamImportMode`**
   and feed step 3.

On this cluster, step 4's observed value is correct —
`oc get image.config/cluster -o jsonpath='{.status}'` reports
`imageStreamImportMode: PreserveOriginal`, and
`oc get clusterversion version -o jsonpath='{.status.desired.architecture}'`
correctly reports `Multi` — but new/reconciled ImageStreamTags still land
on `Legacy` anyway. **Why it breaks specifically on HCP**: on ROSA HCP,
`openshift-apiserver` doesn't run in the guest cluster at all — it lives
in Red Hat's separately-managed Hypershift management cluster, entirely
outside anything an `oc --context <guest>` session can see. Whether the
config-observer's output has actually rolled out to that process (revision
rollout lag, or an HCP-specific wiring gap between the observer and the
actually-running apiserver) is invisible from the guest side — only the
symptom (new tags landing on `Legacy`) is observable.

This matches two open upstream OpenShift bugs exactly, both linked from
[RHOAIENG-82528](https://redhat.atlassian.net/browse/RHOAIENG-82528) (the
tracking issue filed for this):
- [OCPBUGS-73844](https://redhat.atlassian.net/browse/OCPBUGS-73844) —
  "ImageStream imports single-arch despite PreserveOriginal on multi-arch
  cluster" (status POST) — identical repro via `oc import-image`.
- [OCPBUGS-74567](https://redhat.atlassian.net/browse/OCPBUGS-74567) —
  "The importMode of imagestreams managed by sample operator are not
  correct in multiarch cluster" (status New) — explicitly documents that
  on a *heterogeneous hypershift cluster*, even deleting/recreating the
  managed ImageStream doesn't pick up `PreserveOriginal` — independently
  reproduced live below.

## Diagnosis checklist

```bash
export CLUSTER_CONTEXT=$(oc config current-context)

# 1. Confirm the cluster genuinely is multi-arch and thinks import mode should be PreserveOriginal
oc --context "$CLUSTER_CONTEXT" get clusterversion version -o jsonpath='{.status.desired.architecture}{"\n"}'
oc --context "$CLUSTER_CONTEXT" get image.config/cluster -o jsonpath='{.status}{"\n"}'

# 2. Confirm the affected tag's importPolicy
oc --context "$CLUSTER_CONTEXT" get imagestream <name> -n redhat-ods-applications -o json | \
  jq -c '.spec.tags[] | {name, importPolicy}'

# 3. Confirm the source manifest genuinely is a multi-arch list, not single-arch
skopeo inspect --raw --no-tags docker://<image>@<manifest-list-digest> | \
  jq -c '{mediaType, manifests: [.manifests[]? | {arch: .platform.architecture, digest}]}'

# 4. Check systemically across every RHOAI ImageStream (not just the one that crashed)
for is in $(oc --context "$CLUSTER_CONTEXT" get imagestream -n redhat-ods-applications -o name | sed 's#.*/##'); do
  oc --context "$CLUSTER_CONTEXT" get imagestream "$is" -n redhat-ods-applications -o json | \
    jq -r --arg is "$is" '.spec.tags[]? | "\($is):\(.name) importMode=\(.importPolicy.importMode // "Legacy(default)")"'
done
```

**Delete/recreate does NOT self-heal** (confirms OCPBUGS-74567's claim):
deleting an ImageStream causes `workbenches-operator`'s reconcile loop to
recreate it within ~1s (new UID) — but the recreated tag lands on the
identical `Legacy`/amd64 resolution. This rules out a stale-cache
explanation and confirms the gap is structural, not transient.

**`oc import-image` without an explicit flag does NOT pick up the
cluster's default either** — and this is a genuine gotcha, not the
`ImageStreamImport`-vs-`ImageStream` API-kind distinction it might look
like at first: the `oc` CLI itself hardcodes a client-side default of
`Legacy` when `--import-mode` is omitted, so `oc import-image <tag>
--confirm` alone reproduces the exact same bug from the client side. You
must pass the flag explicitly:
```bash
oc --context "$CLUSTER_CONTEXT" import-image <tag> -n redhat-ods-applications --import-mode=PreserveOriginal --confirm
```

## Customer-friendly workaround, in order of effort

**Tier 1 (recommended default) — explicit per-tag `import-image`, run once
after install/upgrade:**
```bash
for is in $(oc --context "$CLUSTER_CONTEXT" get imagestream -n redhat-ods-applications -o name | sed 's#.*/##'); do
  for tag in $(oc --context "$CLUSTER_CONTEXT" get imagestream "$is" -n redhat-ods-applications -o jsonpath='{.spec.tags[*].name}'); do
    oc --context "$CLUSTER_CONTEXT" import-image "$is:$tag" -n redhat-ods-applications --import-mode=PreserveOriginal --confirm
  done
done
```
No operator, no webhook, nothing to install — a standard, documented `oc`
flag. **Caveat**: confirmed NOT durable against a full delete+recreate of
the ImageStream (e.g. driven by an RHOAI upgrade) — re-run after upgrading.
Durability against a routine non-delete reconcile (Server-Side Apply) is
plausible but unverified.

**Tier 2 — a namespace-scoped `CronJob`** looping the tier-1 command (or
`oc import-image --all -n redhat-ods-applications --import-mode=PreserveOriginal --confirm`)
on a schedule, so upgrades self-heal without a human re-running anything —
still no cluster-wide admission infrastructure, much easier to get past a
customer's security review than Kyverno.

**Tier 3 — Kyverno mutate policy** (what was actually used this session,
for a fast, durable, no-human-babysitting live-cluster fix during
validation): correct and durable across every future ImageStream
create/reconcile, but heavy — needs a cluster-wide operator with webhooks
and a background controller. Fine for an internal validation cluster; not
something to hand a customer as the *primary* recommended workaround.

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: fix-imagestream-import-mode
spec:
  background: true
  rules:
  - name: preserve-original-import-mode
    match:
      any:
      - resources:
          kinds:
          - ImageStream
          namespaces:
          - redhat-ods-applications
    mutate:
      foreach:
      - list: "request.object.spec.tags"
        patchesJson6902: |-
          - op: add
            path: /spec/tags/{{elementIndex}}/importPolicy/importMode
            value: PreserveOriginal
```
Apply, then force a fresh import by deleting the affected ImageStream(s)
(the operator recreates them — see the delete/recreate note above; this
time the recreate is a genuine `ImageStream` CREATE that Kyverno's
`match.resources.kinds: [ImageStream]` intercepts and mutates before
`SetDefaults_TagImportPolicy` ever runs):
```bash
oc --context "$CLUSTER_CONTEXT" apply -f fix-imagestream-import-mode.yaml
oc --context "$CLUSTER_CONTEXT" get clusterpolicy fix-imagestream-import-mode   # Ready=True
oc --context "$CLUSTER_CONTEXT" delete imagestream <name> -n redhat-ods-applications
# recreated within ~1s by workbenches-operator's reconcile loop, this time with PreserveOriginal
oc --context "$CLUSTER_CONTEXT" get imagestream <name> -n redhat-ods-applications -o json | \
  jq '.spec.tags[] | {name, importPolicy}'   # -> PreserveOriginal
oc --context "$CLUSTER_CONTEXT" delete pod <affected-workbench-pod> -n <project>   # force a fresh pull
```

**Tier 4 (the actual upstream fix, not a workaround)**:
`workbenches-operator` (and any other RHOAI component creating
ImageStreams) should set `importPolicy.importMode: PreserveOriginal`
explicitly in its bundled manifests as a defensive measure — but
**conditionally**, checking `ClusterVersion.status.desired.architecture
== "Multi"` first, mirroring what core OpenShift's own (currently broken)
dynamic-default mechanism is supposed to do, so that single-arch clusters
(the vast majority) don't pay any cost for a benefit they'll never use.
Suggested in RHOAIENG-82528; not implemented anywhere yet.

**On the "won't this cost etcd/registry overhead on single-arch clusters"
concern** — real, but narrower than it sounds. Registry storage growth is
**not** a real problem: the internal registry's pull-through cache is
lazy and keyed per specific blob digest, so if nothing on a single-arch
cluster ever runs an arm64 (or any other) workload, no non-native bytes
are ever fetched or stored — zero actual storage cost. The only
unconditional cost is the small `Image` API object's own etcd metadata
(one extra object per platform per tag) — bounded and small, not a
registry-storage concern. Similarly, don't conflate this with *external*
mirroring (e.g. `oc-mirror`/CatalogSource mirroring for disconnected
installs): mirroring a manifest list does copy every sub-manifest's blobs
unconditionally (a real, separate cost for disconnected environments) —
but that's a different layer from the cluster's own internal registry
cache, and spawning an amd64 pod does **not** cause arm64 blobs to be
pulled into that internal cache, or vice versa.

## Image object fields under `PreserveOriginal` (empirical findings)

Captured directly from a recreated `Image` object (manifest-list digest):

- **`dockerImageReference`** — populated, points at the manifest-list
  digest itself (not a per-platform digest). Fully valid, pullable — any
  client pulling it gets normal manifest-list negotiation.
- **`dockerImageMetadata`** — not fully empty, but degenerate: only
  bookkeeping fields (`Id`, `Created`, `apiVersion`, `kind`) and an empty
  `ContainerConfig`. Missing everything inherently per-platform
  (`Architecture`, `Os`, `Config.Env`, `Config.Entrypoint`, `Size`, etc.)
  — correct, since a manifest list has no single value for any of those.
- **`dockerImageLayers`** — empty at the manifest-list level, as expected;
  layers only exist per sub-manifest.
- **`dockerImageManifests`** — **fully populated**, one entry per
  sub-manifest with `architecture`, `os`, `digest`, `mediaType`,
  `manifestSize` (and `variant` for arm64's `v8`). The per-platform
  structural metadata isn't actually lost under `PreserveOriginal` — it's
  relocated here instead of the top-level `dockerImageMetadata`/
  `dockerImageLayers` fields.
- **`dockerImageManifestMediaType`** — correctly reports
  `application/vnd.docker.distribution.manifest.list.v2+json`.

**Practical implication**: the "metadata gap" concern under
`PreserveOriginal` is real only for tooling that reads
`dockerImageMetadata`/`dockerImageLayers` directly and expects
single-platform fields (matching OCPBUGS-73844's own repro needing
`oc image info --filter-by-os`) — a manifest-list-aware caller can recover
full per-platform detail from `dockerImageManifests` instead.

## Cross-references

- [RHOAIENG-82528](https://redhat.atlassian.net/browse/RHOAIENG-82528) —
  tracking issue, blocked by OCPBUGS-73844/74567.
- [SKILL.md](SKILL.md)'s troubleshooting table — the `Exec format error`
  row now points here instead of only suggesting an x86_64 recreate.
- [install-prerelease.md](install-prerelease.md) — its Kyverno
  `replace-image-registry` policy is a **different** fix (registry
  rewriting for pull-secret routing on EA builds) from this doc's
  `fix-imagestream-import-mode` policy; both can coexist on the same
  Kyverno install.
