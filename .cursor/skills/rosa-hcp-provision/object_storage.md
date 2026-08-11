# S3-compatible object storage on ROSA HCP (arm64)

Four lightweight, self-hosted S3-compatible stores evaluated and installed
on a real ROSA HCP arm64 cluster (`jd-arm64-36e1`, OCP 4.21.0, all worker
NodePools arm64 — `m6g.2xlarge` + `g5g.2xlarge`). None of these are
RHOAI components — this is general-purpose object storage for a
project/team that needs an S3 endpoint without provisioning ODF/Ceph or
paying for cloud object storage.

**Pin the cluster context first** — see
[SKILL.md](SKILL.md#critical-always-pass---context-never-rely-on-the-ambient-current-context):

```bash
export CLUSTER_CONTEXT=$(oc config current-context)
```

## Quick comparison (verified this session, not vendor claims)

| | Garage | RustFS | SeaweedFS | S4 |
|---|---|---|---|---|
| Default chart image | `dxflrs/amd64_garage` — **amd64-only**, real bug | `rustfs/rustfs` — multi-arch (amd64/arm64) out of the box | `chrislusf/seaweedfs` — multi-arch (amd64/arm/arm64/386) out of the box | `quay.io/rh-aiservices-bu/s4` — **amd64-only, no arm64 build exists** |
| Fix needed for arm64 | Override `image.repository` to `dxflrs/garage` (verified real multi-arch manifest list) | None | None | **None available** — upstream doesn't publish arm64 at all |
| Default chart securityContext | Hardcoded `runAsUser/runAsGroup/fsGroup: 1000` | Hardcoded `runAsUser/runAsGroup/fsGroup: 10001` | `podSecurityContext: {}` / `containerSecurityContext: {}` — empty | `runAsNonRoot: true` only, no hardcoded UID, drops ALL caps |
| Fix needed for `restricted-v2` | Null out `podSecurityContext.{runAsUser,runAsGroup,fsGroup}` in values, let OpenShift assign | Same as Garage | None — works with defaults | None — works with defaults |
| Native OpenShift Route | No (Ingress only) | No (Ingress only) | No (Ingress only) | **Yes** — `route.enabled=true`, ships its own `route.yaml`/`route-s3.yaml` templates |
| Default persistence | PVC (StatefulSet) | PVC (StatefulSet) | **hostPath by default** — must override to PVC for every component (`master`, `filer`, `volume`) | PVC |
| Registry | Docker Hub | Docker Hub | Docker Hub | quay.io |
| Status this session | **Installed, verified healthy** | **Installed, verified healthy** (2-node distributed, `restricted-v2`, arm64) | **Installed, verified healthy** (master/volume/filer all `1/1 Running`, S3 service listening) | **Confirmed fails** — `Exec format error`, case study below |

**Bottom line for an arm64-only ROSA HCP cluster**: all three
Kubernetes-native stores (Garage, RustFS, SeaweedFS) end up working with a
small values override each — none needs a custom image build or a
different SCC than `restricted-v2`. RustFS needed the least: no image fix,
just the UID-null override plus explicit non-default admin credentials
(the chart refuses to render with the well-known `rustfsadmin/rustfsadmin`
default) and a `storageclass` override since the chart defaults to
Rancher's `local-path` provisioner, which doesn't exist on OpenShift.
Garage needs one concrete image-repository override. SeaweedFS needs the
most values (PVC storage on 3 separate components) but no image or
securityContext fix. S4 cannot run at all until its maintainers publish
(or someone builds) an arm64 image — it's excluded from that "all three
just work" set entirely, not merely harder.

## Cross-cutting gotcha #1: CRI-O short-name resolution (`ImageInspectError`)

Both Garage's and SeaweedFS's charts reference their images **unqualified**
(`dxflrs/garage`, `chrislusf/seaweedfs` — no registry hostname). This
cluster's CRI-O has short-name resolution in `enforcing` mode (standard
OpenShift default, a security hardening feature against registry/namespace
squatting), so an unqualified name with multiple configured unqualified-
search registries is rejected outright:

```
Failed to inspect image "": rpc error: code = Unknown desc = short name
mode is enforcing, but image name dxflrs/garage:v2.3.0 returns ambiguous list
```

**Fix**: always fully-qualify the image in your values override —
`docker.io/dxflrs/garage`, `docker.io/chrislusf/seaweedfs`, etc. — even
when the chart's own default value omits the registry hostname.

## Cross-cutting gotcha #2: Docker Hub anonymous pull rate limit

Both SeaweedFS and RustFS default to Docker Hub-hosted images
(`chrislusf/seaweedfs`, `rustfs/rustfs`). After a handful of pulls this
session (image inspection + repeated pod restarts across both installs),
this cluster's outbound IP hit Docker Hub's anonymous rate limit:

```
Failed to pull image "docker.io/chrislusf/seaweedfs:4.41": ...
toomanyrequests: You have reached your unauthenticated pull rate limit.
https://www.docker.com/increase-rate-limit
```

This is **not a chart or cluster misconfiguration** — it's an external,
per-source-IP limit on unauthenticated Docker Hub pulls, and a shared AWS
egress IP can easily be shared with other tenants already consuming the
quota. Options, in order of effort:

1. **Wait** — the anonymous limit window is a rolling several-hour period;
   it clears on its own. **Confirmed this session**: SeaweedFS hit the
   limit, was left alone (no retry loop, no credential) for roughly an
   hour while other work continued, and came up `1/1 Running` on its own
   once CRI-O's normal backoff-retry cycle happened to land after the
   window cleared — no manual intervention needed once you're willing to
   wait.
2. **Authenticate** — create a Docker Hub account + a read-only Personal
   Access Token (Account Settings → Security → Personal access tokens,
   *not* your account password), then create a pull secret and attach it:
   ```bash
   # create-pull-secret.sh reads the PAT interactively (never a CLI flag —
   # that would expose it via shell history and `ps` for the command's
   # lifetime) and never touches ~/.docker/config.json automatically.
   .cursor/skills/lib/create-pull-secret.sh dockerhub-pull "<namespace>" "https://index.docker.io/v1/"
   # `oc secrets link`, not a merge patch — a JSON merge patch replaces
   # imagePullSecrets wholesale, wiping out any secrets already on the
   # default SA (e.g. OpenShift's own auto-generated internal-registry
   # pull secret) instead of appending to them.
   oc --context "$CLUSTER_CONTEXT" secrets link default dockerhub-pull -n "<namespace>" --for=pull
   ```
   Authenticated pulls get a much higher limit. This skill does **not**
   auto-extract a Docker Hub credential from `~/.docker/config.json` by
   default — checked earlier this session and none was present there
   (only registry.redhat.io/quay.io/ghcr.io entries existed). Once you
   explicitly `docker login` yourself, the resulting entry under
   `auths["https://index.docker.io/v1/"]` in `~/.docker/config.json` is a
   credential *you* just created for this purpose — it's fine to read it
   back from there for the pull secret above, same as any other
   already-trusted credential file on your own machine; this skill still
   never does that extraction silently or without you having just run
   `docker login` yourself first.
3. Mirror the image into an internal/already-authenticated registry
   (e.g. `quay.io`) once, and repoint the chart's `image.repository` at
   that mirror instead of Docker Hub directly — the most durable fix if
   you'll be reinstalling repeatedly.

## Garage

Verified working end-to-end. Deuxfleurs Garage — lightweight,
geo-distributed S3-compatible store, zero external dependencies.

**Test-only, plain HTTP, in-cluster only.** No Route/Ingress is created
for this service anywhere in this doc — S3 clients (Elyra, DSPA) reach it
only via its `ClusterIP` at `garage.<namespace>.svc.cluster.local:3900`,
never from outside the cluster. `ClusterIP` scopes *which pods can route
to it*, but the connection itself is unencrypted HTTP, so the S3 access
key/secret still cross the pod network in cleartext to any workload that
*can* reach the namespace. Acceptable for this validation setup, but
don't reuse it as-is for anything beyond a disposable test cluster:
namespace-scope it with a `NetworkPolicy` restricting ingress on port 3900
to only the pods that legitimately need it (the workbench/DSPA pods in
the project namespace), rather than leaving it reachable from every
namespace on the cluster by default.

```bash
oc --context "$CLUSTER_CONTEXT" new-project garage
git clone https://git.deuxfleurs.fr/Deuxfleurs/garage.git
# Pin to a reviewed tag/commit before using this beyond a quick check —
# a bare clone tracks the moving default branch, and the chart falls back
# to .Chart.AppVersion for image.tag when unset (also pin that explicitly
# below once you know the chart version you're actually running).
```

**Values override** (`garage-values.yaml`) — fixes both gotchas found this
session:

```yaml
image:
  repository: docker.io/dxflrs/garage   # NOT the chart default dxflrs/amd64_garage (amd64-only)

podSecurityContext:
  runAsUser: null      # let restricted-v2 assign a UID from the namespace's allocated range
  runAsGroup: null
  fsGroup: null
```

```bash
helm --kube-context "$CLUSTER_CONTEXT" install garage garage/script/helm/garage \
  --namespace garage \
  -f garage-values.yaml
```

Confirmed on the running pod: `restricted-v2` SCC (no `anyuid` needed),
auto-assigned `fsGroup` from the namespace's allocated range (e.g.
`1000920000`, not the chart's hardcoded `1000`), scheduled on an arm64
node, S3 API server started cleanly in logs.

**Initialize the cluster layout** (peer-to-peer — the S3 API won't accept
traffic until every node is assigned a zone):

```bash
for p in garage-0 garage-1 garage-2; do
  NODE_ID=$(oc --context "$CLUSTER_CONTEXT" exec "$p" -n garage -c garage -- /garage node id -q)
  oc --context "$CLUSTER_CONTEXT" exec garage-0 -n garage -c garage -- /garage layout assign -z zone1 -c 10G "$NODE_ID"
done
oc --context "$CLUSTER_CONTEXT" exec garage-0 -n garage -c garage -- /garage layout apply --version 1
oc --context "$CLUSTER_CONTEXT" exec garage-0 -n garage -c garage -- /garage status   # all 3 nodes HEALTHY
```

Note: the chart's image is a minimal/distroless-style build — no
`id`/`uname`/`wget` binaries in the container for ad-hoc debugging; rely on
`oc get pod -o jsonpath` for the resolved SCC/UID and on the pod's own logs
for startup confirmation instead of `oc exec ... id`.

## RustFS

Verified working end-to-end. 2-node distributed erasure-coded cluster,
`restricted-v2` SCC, arm64, no image or securityContext fix needed beyond
the standard UID-null treatment.

```bash
git clone https://github.com/rustfs/helm.git rustfs-helm
# rustfs-helm is a packaged Helm *repository* (gh-pages style, .tgz releases
# + index.yaml) — the chart source itself is not checked in there. Extract
# the latest release to inspect/override values:
mkdir -p /tmp/rustfs-extracted
tar -xzf rustfs-helm/rustfs-<version>.tgz -C /tmp/rustfs-extracted
```

**Values override** (`rustfs-values.yaml`) — the chart's default image
(`rustfs/rustfs`) is already multi-arch and pulls fine unqualified once
the short-name gotcha above is worked around by fully qualifying it
anyway; three real fixes were needed:

```yaml
replicaCount: 2        # chart default is 4 — 2 is the documented minimum for
drivesPerNode: 1        # a distributed erasure-coded cluster and enough to prove the setup

image:
  rustfs:
    repository: docker.io/rustfs/rustfs
  initImage:
    repository: docker.io/library/busybox   # chart default is bare busybox, same short-name issue

podSecurityContext:
  fsGroup: null      # let restricted-v2 assign a UID/GID from the namespace's range
  runAsUser: null
  runAsGroup: null

storageclass:
  name: gp3-csi        # chart defaults to Rancher's local-path provisioner, which
  dataStorageSize: 5Gi  # doesn't exist on OpenShift — must override to a real StorageClass
  logStorageSize: 1Gi

# The chart REFUSES to render (a real, deliberate guardrail, not a bug) unless
# you either set secret.existingSecret, or set both of these to something
# other than the well-known "rustfsadmin/rustfsadmin" default, or explicitly
# opt into that default via secret.allowInsecureDefaults=true.
#
# Generate your own unique secret_key — never reuse the value below.
# Anyone who copy-pastes this doc verbatim without changing it ends up
# with the exact same S3 credential as every other RustFS deployment made
# from it. e.g.: openssl rand -base64 24
# Prefer secret.existingSecret pointing at a pre-created Kubernetes Secret
# over inlining values here at all, where practical.
secret:
  rustfs:
    access_key: rustfsadmin-arm64test
    secret_key: "<generate-your-own-e.g.-openssl-rand-base64-24>"
```

```bash
oc --context "$CLUSTER_CONTEXT" new-project rustfs
helm --kube-context "$CLUSTER_CONTEXT" install rustfs /tmp/rustfs-extracted/rustfs \
  --namespace rustfs \
  -f rustfs-values.yaml
```

Confirmed on the running pods: both `rustfs-0`/`rustfs-1` `1/1 Running`
within ~30s (image pulled from Docker Hub cleanly, no rate-limit hit this
time), scheduled on two different arm64 nodes, `restricted-v2` SCC with
auto-assigned `fsGroup` (e.g. `1000950000`), and the container logs show
the two pods discovering each other over the headless service
(`rustfs-1.rustfs-headless.rustfs.svc.cluster.local:9000`), disks coming
online, and peer connectivity established — a genuinely working
distributed cluster, not just two isolated pods.

The real chart's `mode.standalone`/`mode.distributed` values match what
various online guides describe, but double-check before trusting a pasted
guide verbatim — `mode.distributed.enabled: true` is already the chart's
*default*, so a guide's explicit `--set mode.distributed.enabled=true` is
redundant, not wrong. `replicaCount: 4` is also the chart default, but
this session used `replicaCount: 2` instead (the documented minimum for a
distributed cluster) to keep the footprint small for a validation
install — bump back to 4 (or higher) for anything beyond a quick check.

## SeaweedFS

Verified working end-to-end after the Docker Hub rate limit (gotcha #2
above) cleared on its own — `master`/`filer`/`volume` all `1/1 Running`,
S3 service (`seaweedfs-s3`) listening on port 8333.

```bash
helm repo add seaweedfs https://seaweedfs.github.io/seaweedfs/helm
helm repo update seaweedfs
oc --context "$CLUSTER_CONTEXT" new-project seaweedfs
# Pin --version to the chart release you actually tested against before
# installing (helm search repo seaweedfs/seaweedfs --versions) — an
# unversioned install tracks whatever the chart repo currently publishes,
# and a chart update can change value paths or restore hostPath defaults
# out from under the values override below.
```

**Values override** (`seaweedfs-values.yaml`) — three fixes, none of which
match a naive/pasted guide's assumed key structure:

```yaml
# Real key paths differ from most published guides — verify against the
# actual values.yaml (helm show values seaweedfs/seaweedfs), not a
# third-party guide. In particular there is no top-level master.storage.type
# or volume.storage.type — see the real structure below.

master:
  data:                                    # NOT master.storage
    type: persistentVolumeClaim            # default is hostPath, which restricted-v2 rejects
    size: 2Gi
  logs:
    type: persistentVolumeClaim
    size: 1Gi

volume:
  dataDirs:                                # a LIST, not a single volume.storage block
    - name: data1
      type: persistentVolumeClaim
      size: 20Gi
      maxVolumes: 0

filer:
  data:
    type: persistentVolumeClaim
    size: 2Gi
  logs:
    type: persistentVolumeClaim
    size: 1Gi

s3:
  enabled: true                            # top-level `s3:` key, NOT filer.s3.enabled

global:
  seaweedfs:
    image:
      name: docker.io/chrislusf/seaweedfs  # fully-qualified, see short-name gotcha above
```

```bash
helm --kube-context "$CLUSTER_CONTEXT" install seaweedfs seaweedfs/seaweedfs \
  --namespace seaweedfs \
  -f seaweedfs-values.yaml
```

A `PodSecurity "restricted:latest"` admission **warning** (not a hard
failure) about a `hostPath` "logs" volume printed even with the above
override in place — worth re-checking on a clean install whether every
`logs`/`data` block across `master`/`filer`/`volume` was actually
overridden, since the chart has several near-identical but independently-
configured storage blocks.

Bonus finding: the chart exposes `volume.rust: false` — an option to run
SeaweedFS's own Rust-reimplemented volume server (`/usr/bin/weed-volume`)
instead of the Go one, "requires an image that ships the Rust binary
(amd64/arm64)". Not evaluated this session; worth a look if pursuing a
Rust-based storage stack theme further.

## S4 — confirmed does not work on this cluster (case study)

[rh-aiservices-bu/s4](https://github.com/rh-aiservices-bu/s4) — a
lightweight Ceph RGW + SQLite + web-UI S3 store, intentionally minimal
(POC/demo/dev tool, not for scale). Has first-class OpenShift support
(native `route.enabled=true` Helm value, ships its own `route.yaml`) and a
genuinely `restricted`-compliant default securityContext
(`runAsNonRoot: true`, drops all capabilities, no hardcoded UID) — better
OpenShift posture than any of the three stores above, by design.

**But its published image (`quay.io/rh-aiservices-bu/s4`) is amd64-only —
no arm64 build exists at all**, confirmed via direct manifest inspection:

```bash
skopeo inspect --raw --no-tags docker://quay.io/rh-aiservices-bu/s4:latest
# -> application/vnd.oci.image.manifest.v1+json (single-arch, not a manifest list)
skopeo inspect --no-tags docker://quay.io/rh-aiservices-bu/s4:latest
# -> {"Architecture": "amd64", "Os": "linux"}
```

Installed anyway to confirm the failure mode directly (image pull itself
succeeds fine from quay.io — no ImageStream, no CRI-O short-name issue,
no rate limit — this is a completely different, simpler failure than
anything else in this doc):

```bash
git clone https://github.com/rh-aiservices-bu/s4.git
oc --context "$CLUSTER_CONTEXT" new-project s4
# Read the password without echo and pass it via --set-file, not --set —
# a literal --set auth.password=... exposes it via shell history and `ps`.
read -rs -p "S4 admin password: " S4_PASSWORD; echo
PASSWORD_FILE=$(umask 077 && mktemp)
trap 'rm -f "$PASSWORD_FILE"' EXIT
printf '%s' "$S4_PASSWORD" > "$PASSWORD_FILE"
helm --kube-context "$CLUSTER_CONTEXT" install s4 s4/charts/s4 \
  --namespace s4 \
  --set route.enabled=true \
  --set auth.username=admin \
  --set-file auth.password="$PASSWORD_FILE"
rm -f "$PASSWORD_FILE"   # don't wait for the trap/EXIT fallback — clean up as soon as it's no longer needed
```

Result: `CrashLoopBackOff`,

```
oc --context "$CLUSTER_CONTEXT" logs deploy/s4 -n s4
exec container process `/opt/ceph-container/bin/entrypoint.sh`: Exec format error
```

This is the same `Exec format error` signature seen throughout this
session's RHOAI ImageStream investigation (see
[RHOAIENG-82528](https://redhat.atlassian.net/browse/RHOAIENG-82528)), but
here the root cause is much simpler and not fixable from the client side
at all: the upstream image genuinely has no arm64 build, full stop —
there's no manifest-list/import-mode trick that helps when the arm64
sub-manifest doesn't exist upstream in the first place. Do not attempt S4
on an arm64-only cluster until the maintainers publish (or you build) an
arm64 image.

## Cleanup

```bash
for ns in garage rustfs seaweedfs s4; do
  helm --kube-context "$CLUSTER_CONTEXT" uninstall "$ns" -n "$ns"   # let a real uninstall failure print, don't swallow it before deleting the project out from under it
  oc --context "$CLUSTER_CONTEXT" delete project "$ns" --ignore-not-found
done
```
