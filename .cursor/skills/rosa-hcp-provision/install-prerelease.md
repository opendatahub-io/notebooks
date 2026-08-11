# Installing an EA/pre-release RHOAI build (custom CatalogSource + Kyverno)

This covers installing a build that **isn't on any GA channel yet** — an
EA/pre-release like `3.6-ea.1`, installed from its own Konflux
`rhoai-fbc-fragment` catalog image rather than the standard
`redhat-operators` catalog. If you're installing an **already-released**
version, use [install-rhoai.md](install-rhoai.md) instead — no Kyverno, no
custom pull-secret, no custom CatalogSource.

Validated end-to-end on a real ROSA HCP cluster (`jd-arm64-36e1`, OCP
4.21.0, 2026-08-10): RHOAI 3.6.0-ea.1, `dashboard`+`workbenches`, arm64
(`m6g.2xlarge`) workers + a `g5g.2xlarge` GPU pool.

## 0. Pin the cluster context — do this before anything else

`~/.kube/config`'s `current-context` is shared, mutable, machine-wide
state — never rely on it implicitly. Capture it once and pass it
explicitly on every `oc` command below (see
[SKILL.md](SKILL.md#critical-always-pass---context-never-rely-on-the-ambient-current-context)
for why — a real incident had `oc` silently hit a different cluster
mid-session because something else on the same machine changed
`current-context`):

```bash
export CLUSTER_CONTEXT=$(oc config current-context)
oc --context "$CLUSTER_CONTEXT" whoami --show-server   # sanity check
```

## 1. Finding the latest EA build

Search Slack `#rhoai-build-notifications` for `"CI Build is available for
RHOAI vX.Y.Z-eaN"` — the message gives the exact
`quay.io/rhoai/rhoai-fbc-fragment@sha256:...` digest and source commit
directly, no digging through Konflux/Quay tags needed.

**Naming note:** `rhoai-fbc-fragment` *is* the correct image to use
directly as a `CatalogSource`. "`rhoai-catalog-dev`" is just an informal
name some people use for the `CatalogSource` object that points at this
image — not a separate quay.io repo to go looking for.

## 2. Prerequisite: `helm`

`brew install helm`. Kyverno's raw `install.yaml` hardcodes
`runAsUser: 65534`/`runAsGroup: 65534` in every controller's container
`securityContext`, which no SCC on ROSA HCP allows (`restricted-v2`
requires a UID in the namespace's allocated
`1000880000-1000889999` range) — pod creation fails with `FailedCreate`.
Helm's `--set ...securityContext=null` flags (step 4 below) are the
documented way around this. Without `helm`, the fallback is manually
patching `runAsUser`/`runAsGroup` out of each controller Deployment after
a raw `kubectl apply` — works, but only fall back to it if you genuinely
can't install `helm`.

## 3. Root cause to recognize early: `OCPBUGS-23901`

**ROSA HCP silently reverts any edit to the global
`openshift-config/pull-secret`.** Symptom signature, so a future run can
recognize this fast instead of re-deriving it: a Pod/Job/InstallPlan stuck
`ImagePullBackOff`/`ErrImagePull` with `unauthorized` or `manifest
unknown`, **despite** an independently verified-working credential
(`skopeo inspect` succeeds from your own machine) and an apparently
successful `oc set data secret/pull-secret` edit. The fix is **not**
another attempt at editing the global secret — it's the Kyverno-based
workaround below, sourced from the internal Red Hat Google Doc ["Installing
RHOAI pre-release on
ROSA-hosted"](https://docs.google.com/document/d/12FoMt1_djxEkhuAsRjU40aIxnlo-0SATK-E4qihYQdQ).

This bug is specific to `registry.redhat.io`/`quay.io` credentials you add
yourself; it did **not** reproduce for `servicemeshoperator3` in step 7
below, which pulls standard content already covered by ROSA's own default
pull-secret.

## 4. Install Kyverno

```bash
helm repo add kyverno https://kyverno.github.io/kyverno/ && helm repo update
helm --kube-context "$CLUSTER_CONTEXT" install kyverno kyverno/kyverno -n kyverno --create-namespace \
  --set securityContext=null \
  --set backgroundController.securityContext=null \
  --set cleanupController.securityContext=null \
  --set reportsController.securityContext=null \
  --set admissionController.container.securityContext=null \
  --set admissionController.initContainer.securityContext=null
```

Verified working end-to-end on OCP 4.21 (2026-08-10). **Fallback if `helm`
truly isn't available**:
```bash
KYVERNO_VERSION=v1.18.0   # pin a version — this session used v1.18.0
curl -fsSL -o /tmp/kyverno-install.yaml "https://github.com/kyverno/kyverno/releases/download/${KYVERNO_VERSION}/install.yaml"
less /tmp/kyverno-install.yaml   # skim before applying cluster-scoped RBAC/webhooks — see cost-optimization.md item 5 on why a checksum here wouldn't help
kubectl --context "$CLUSTER_CONTEXT" apply --server-side -f /tmp/kyverno-install.yaml
```
then patch out the incompatible fields on all 4 controller Deployments
(`kyverno-admission-controller`, `kyverno-background-controller`,
`kyverno-cleanup-controller`, `kyverno-reports-controller`):

```bash
for DEPLOYMENT_NAME in kyverno-admission-controller kyverno-background-controller \
  kyverno-cleanup-controller kyverno-reports-controller; do
  oc --context "$CLUSTER_CONTEXT" patch deployment "$DEPLOYMENT_NAME" -n kyverno --type=json -p='
[{"op":"remove","path":"/spec/template/spec/containers/0/securityContext/runAsUser"},
 {"op":"remove","path":"/spec/template/spec/containers/0/securityContext/runAsGroup"}]'
done
```

(`kyverno-admission-controller` also has an initContainer needing the same
two ops.)

Wait for `kyverno-svc` to have endpoints before relying on the admission
webhook — check events, don't just sleep blindly:

```bash
n=0
for i in $(seq 1 30); do
  n=$(oc --context "$CLUSTER_CONTEXT" get endpoints kyverno-svc -n kyverno -o jsonpath='{.subsets[*].addresses[*].ip}' | wc -w)
  [ "$n" -gt 0 ] && break
  oc --context "$CLUSTER_CONTEXT" get events -n kyverno --sort-by=.lastTimestamp | tail -5
  sleep 10
done
[ "$n" -gt 0 ] || { echo "ERROR: kyverno-svc has no endpoints after 300s — do not proceed to apply ClusterPolicies against a webhook that isn't up" >&2; exit 1; }
```

## 5. `kyverno-secret-manager` ClusterRole + `pull-secret-quay`

Grants the admission/background controllers permission to
get/list/watch/create/update/patch/delete `secrets` (needed by the
`sync-secrets` policy below):

```bash
cat <<EOF | oc --context "$CLUSTER_CONTEXT" apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kyverno-secret-manager
  labels:
    app.kubernetes.io/component: background-controller
    rbac.kyverno.io/aggregate-to-background-controller: "true"
rules:
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
EOF
```

Create `pull-secret-quay` in `openshift-config` — **not** the literal
`pull-secret` (that's the name OCPBUGS-23901 keeps reverting;
`pull-secret-quay` is a stable source name Kyverno's `sync-secrets` policy
clones from). This skill does **not** read your local
`~/.docker/config.json` automatically — a skill executed by an agent that
silently harvests a local registry credential and pushes it into a cluster
Secret is a real credential-theft pattern (same policy as
`arm64-rosa-gpu-smoke/SKILL.md` and `rosa-hcp-provision/SKILL.md` Option B).
Read the credentials interactively instead, so they never touch argv/ps/
shell history either:

```bash
oc config use-context "$CLUSTER_CONTEXT"
.cursor/skills/lib/create-pull-secret.sh pull-secret-quay openshift-config \
  "quay.io,quay.io/rhoai" registry.redhat.io
```

(`quay.io,quay.io/rhoai` writes the same Quay credential under both auth
keys — some clients do exact-key lookup rather than registry-prefix
matching. `registry.redhat.io` is entered as its own group; leave its
username blank at the prompt to omit it entirely if you don't have a
working credential for it yet.)

**If the cached `quay.io/rhoai` robot credential is dead** (`"Could not
find robot with username..."` — hit exactly this in the 2026-08-10 run):
fall back to a personal `quay.io` account credential if it has org read
access. Verify with a plain `skopeo inspect docker://quay.io/rhoai/<image>`
*before* wiring it into any cluster object — don't assume it works.

## 6. The 3 ClusterPolicies — **with one deviation from the source doc**

Sourced from the internal Google Doc linked above, adapted to the
`pull-secret-quay` name from step 5. **One correction applied and verified
live this session**: the doc's own `replace-image-registry` policy uses
`^registry\.redhat\.io/` (rewriting the *entire* registry) — this is
too broad and **breaks legitimate images** still correctly served from
`registry.redhat.io` that have nothing to do with RHOAI EA content. Hit
this exactly: `dashboard-redirect`'s pinned
`registry.redhat.io/ubi9/nginx-126@sha256:e8eb9cf...` (a real, valid,
multi-arch UBI base image) got rewritten to `quay.io/ubi9/nginx-126`,
which doesn't exist — only `quay.io/rhoai/*` is an actual RHOAI mirror
path. Confirmed via `skopeo inspect --raw` that the original
`registry.redhat.io` reference is fine on its own. **Scope the regex to
`^registry\.redhat\.io/rhoai/` instead**:

```bash
# Heredoc delimiter is quoted ('EOF') so bash performs NO expansion inside —
# this YAML contains literal Kyverno JMESPath backtick expressions
# (`` `[]` ``, `` `""` `` below) that an unquoted heredoc would otherwise
# treat as command substitution, corrupting the policy before oc ever sees it.
cat <<'EOF' | oc --context "$CLUSTER_CONTEXT" apply -f -
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: sync-secrets
spec:
  rules:
  - name: sync-pull-secret-quay
    match:
      any:
      - resources:
          kinds: ["Namespace"]
    # Scope generation to actual RHOAI namespaces + namespaces explicitly
    # opted in as Data Science Projects — without this, EVERY namespace on
    # the cluster gets a copy of the quay.io/registry.redhat.io credential,
    # readable by anyone with Secret-read access anywhere.
    preconditions:
      any:
      - key: "{{ request.object.metadata.name }}"
        operator: AnyIn
        value: ["redhat-ods-applications", "redhat-ods-operator", "redhat-ods-monitoring"]
      - key: '{{ request.object.metadata.labels."opendatahub.io/dashboard" || `""` }}'
        operator: Equals
        value: "true"
    generate:
      apiVersion: v1
      kind: Secret
      name: pull-secret-quay
      namespace: "{{request.object.metadata.name}}"
      synchronize: true
      generateExisting: true
      clone:
        namespace: openshift-config
        name: pull-secret-quay
---
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: add-imagepullsecrets
spec:
  rules:
  - name: add-pull-secret-quay
    match:
      any:
      - resources:
          kinds: ["Pod"]
          # Must match sync-secrets' namespace scope above — pull-secret-quay
          # only exists in these namespaces. Without this, a Pod in ANY
          # namespace pulling a public quay.io/registry.redhat.io image
          # (common, unrelated to RHOAI) gets a reference to a Secret that
          # doesn't exist there and fails to start.
          namespaces: ["redhat-ods-applications", "redhat-ods-operator", "redhat-ods-monitoring"]
    preconditions:
      any:
      - key: "{{ request.object.spec.containers[?contains(image, 'quay.io') || contains(image, 'registry.redhat.io')] | length(@) }}"
        operator: GreaterThan
        value: 0
      # Also check initContainers — without this branch, a Pod whose ONLY
      # quay.io/registry.redhat.io reference is on an initContainer never
      # gets the pull secret, and that initContainer fails to pull.
      - key: "{{ request.object.spec.initContainers[?contains(image, 'quay.io') || contains(image, 'registry.redhat.io')] || `[]` | length(@) }}"
        operator: GreaterThan
        value: 0
    mutate:
      patchStrategicMerge:
        spec:
          imagePullSecrets:
          - name: pull-secret-quay
    # Note: the namespace list above is a static subset of sync-secrets'
    # scope — it doesn't cover the label-matched ("opendatahub.io/dashboard")
    # Data Science Project namespaces, since Kyverno match.resources.namespaces
    # only accepts literal names/globs, not a label selector on the Pod's
    # own namespace. A Pod needing this secret in a DS Project namespace
    # still needs pull-secret-quay attached manually there for now.
---
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: replace-image-registry
spec:
  admission: true
  background: false
  failurePolicy: Ignore
  validationFailureAction: Audit
  rules:
  - name: replace-image-registry-pod-containers
    match:
      any:
      - resources: {kinds: [Pod]}
    skipBackgroundRequests: true
    mutate:
      foreach:
      - list: request.object.spec.containers
        patchStrategicMerge:
          metadata:
            labels: {kyverno-replace-image-registry: was-here}
          spec:
            containers:
            - name: '{{ element.name }}'
              image: '{{ regex_replace_all_literal(''^registry\.redhat\.io/rhoai/'', ''{{element.image}}'', ''quay.io/rhoai/'' )}}'
  - name: replace-image-registry-pod-initcontainers
    match:
      any:
      - resources: {kinds: [Pod]}
    preconditions:
      all:
      - key: '{{ request.object.spec.initContainers[] || `[]` | length(@) }}'
        operator: GreaterThanOrEquals
        value: 1
    skipBackgroundRequests: true
    mutate:
      foreach:
      - list: request.object.spec.initContainers
        patchStrategicMerge:
          metadata:
            labels: {kyverno-replace-image-registry: was-here}
          spec:
            initContainers:
            - name: '{{ element.name }}'
              image: '{{ regex_replace_all_literal(''^registry\.redhat\.io/rhoai/'', ''{{element.image}}'', ''quay.io/rhoai/'' )}}'
  - name: replace-image-registry-imagestream-tags
    match:
      any:
      - resources: {kinds: [ImageStream]}
    preconditions:
      all:
      - key: '{{ request.object.spec.tags[] || `[]` | length(@) }}'
        operator: GreaterThanOrEquals
        value: 1
    skipBackgroundRequests: true
    mutate:
      foreach:
      - list: request.object.spec.tags
        preconditions:
          all:
          - key: '{{ element.from.kind || `""` }}'
            operator: Equals
            value: DockerImage
        # patchesJson6902's own string content gets parsed as YAML a
        # second time by Kyverno. A double-quoted `value:` here would put
        # the regex's `\.` through YAML's double-quote escape rules,
        # where it isn't a valid escape sequence — single-quoted (with
        # '' for a literal quote, matching the Pod/initContainer rules
        # above) has no escape processing at all, so `\.` survives as a
        # literal backslash-dot, which is what the regex actually needs.
        patchesJson6902: |-
          - path: "/spec/tags/{{elementIndex}}/from/name"
            op: replace
            value: '{{ regex_replace_all_literal(''^registry\.redhat\.io/rhoai/'', element.from.name, ''quay.io/rhoai/'') }}'
EOF
```

Verified working live on the actual cluster (2026-08-10) — this is the
exact deployed YAML, not a draft. Note the Pod rules use
`patchStrategicMerge` (Kyverno knows Pod's `containers`/`initContainers`
merge key, `name`) while the **ImageStream rule must use
`patchesJson6902`** instead — **this is not a style choice, it's
required**. `ImageStream` is an OpenShift-only aggregated API type;
Kyverno has no built-in merge-key knowledge for it, so a
`patchStrategicMerge` on `spec.tags` (a list-of-maps field) doesn't merge
per-tag by `name` — it does a naive full-list replace on *every* foreach
iteration. The last edit tried this and it silently corrupted an
`ImageStream` from 4 tags down to 1 on the very first test. `patchesJson6902`
with an explicit `/spec/tags/{{elementIndex}}/...` path sidesteps the
merge-key problem entirely by never touching array semantics at all.

If a JSON-patch edit to an *already-applied* policy fails with a JMESPath
`SyntaxError: Unknown char: '^'` — this happened once this session, from
escaping getting mangled through both JSON-patch and Kyverno's JMESPath
template layers — don't fight the patch. Re-`oc apply -f -` the whole
corrected YAML document instead; that's reliable.

**If `dashboard-redirect` (or anything else pulling from
`registry.redhat.io`) shows `ImagePullBackOff` after applying policies**:
check `oc --context "$CLUSTER_CONTEXT" get pods -n redhat-ods-applications`, then verify the
*original* (pre-mutation) image reference with `skopeo inspect --raw`
against both its stated registry and any registry a Kyverno policy might
have rewritten it to — don't assume an upstream image is actually
missing before checking whether your own mutation broke it.

**If a corrupted ImageStream slips through anyway** (wrong rule, or the
merge-key trap above): just delete it. ImageStreams here have no
`ownerReferences`, but the `workbenches` operator continuously reconciles
them from its desired-state manifests — a deleted one reappears with the
full, correct tag set within seconds, this time correctly mutated by
whichever policy is live at the moment of recreation. Confirm recovery
with:

```bash
oc --context "$CLUSTER_CONTEXT" get imagestream "<name>" -n redhat-ods-applications -o json | \
  jq -r '.spec.tags[] | "\(.name) -> \(.from.name)"'
```

**ImageStream tag imports never self-retry once failed.** Unlike Pods
(which get rescheduled and re-admitted, so a policy fix takes effect on
the next natural restart), an `ImageStream` tag that already failed
import (`status.tags[].conditions[] | ImportSuccess=False`) stays failed
forever — OpenShift does not periodically re-attempt a digest-pinned tag
import on its own. A policy fix alone does **not** heal already-broken
tags; something has to trigger a fresh admission event on the object
(the operator's own reconcile loop already does this routinely in
practice — most existing ImageStreams in this session picked up the
corrected mutation and re-imported successfully within the operator's
normal ~10s reconcile cadence, with no manual action needed beyond fixing
the policy. Only the one ImageStream this session's own mutate-rule bug
had actively corrupted needed a manual delete to recover).

## 7. CatalogSource pointing at the EA build

```bash
cat <<EOF | oc --context "$CLUSTER_CONTEXT" apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: CatalogSource
metadata:
  name: rhoai-fbc-fragment-3-6-ea-1
  namespace: openshift-marketplace
spec:
  sourceType: grpc
  image: quay.io/rhoai/rhoai-fbc-fragment@sha256:<digest-from-slack>
  secrets:
  - pull-secret-quay
EOF
```

A Secret referenced by a ServiceAccount's `imagePullSecrets` must exist in
that **same namespace** — `pull-secret-quay` was only created in
`openshift-config` (step 5), so copy it into `openshift-marketplace` too
before referencing it here:

```bash
oc --context "$CLUSTER_CONTEXT" get secret pull-secret-quay -n openshift-config -o json | \
  jq 'del(.metadata.namespace, .metadata.resourceVersion, .metadata.uid, .metadata.creationTimestamp, .metadata.selfLink)' | \
  jq '.metadata.namespace = "openshift-marketplace"' | \
  oc --context "$CLUSTER_CONTEXT" apply -f -
```

**Gotcha**: `CatalogSource.spec.secrets` did **not** visibly propagate to
the CatalogSource pod's ServiceAccount in time this session — the
reliable path was patching the SA directly, then deleting the pod to pick
it up:

```bash
# OLM creates the CatalogSource's ServiceAccount asynchronously — `oc
# secrets link` fails outright if it races ahead of that creation, so
# poll for the SA to exist first rather than assuming it's already there.
for i in $(seq 1 12); do
  oc --context "$CLUSTER_CONTEXT" get sa rhoai-fbc-fragment-3-6-ea-1 -n openshift-marketplace >/dev/null 2>&1 && break
  echo "waiting for CatalogSource ServiceAccount to exist (attempt $i/12)..." >&2
  sleep 5
done
oc --context "$CLUSTER_CONTEXT" secrets link rhoai-fbc-fragment-3-6-ea-1 pull-secret-quay -n openshift-marketplace --for=pull
oc --context "$CLUSTER_CONTEXT" get sa rhoai-fbc-fragment-3-6-ea-1 -n openshift-marketplace \
  -o jsonpath='{.imagePullSecrets[*].name}' | grep -q pull-secret-quay \
  || { echo "ERROR: pull-secret-quay did not land in the SA's imagePullSecrets" >&2; exit 1; }
oc --context "$CLUSTER_CONTEXT" delete pod -n openshift-marketplace -l olm.catalogSource=rhoai-fbc-fragment-3-6-ea-1
```

**Channel/CSV discovery gotcha**: dump **all** channel entries, don't
trust `currentCSV` alone — a fresh CatalogSource's packagemanifest
projection can lag and under-report the real head:

```bash
oc --context "$CLUSTER_CONTEXT" get packagemanifest rhods-operator -o json | \
  jq '.status.channels[] | {channel: .name, entries: [.entries[]?.name]}'
```

The `3.6.0-ea.1` CSV showed up only in the full `entries[]` dump of the
`beta` channel — `currentCSV` reported an older version.

## 8. Namespace + OperatorGroup + Subscription

Same pattern as [install-rhoai.md](install-rhoai.md) step 2 (empty
`spec: {}` OperatorGroup, `installPlanApproval: Manual`, then
`.cursor/skills/lib/wait-for-csv.sh redhat-ods-operator "$CSV_NAME"` to
approve-and-wait by exact CSV match) — just point `source` at your
`CatalogSource` name from step 7 and `channel`/`startingCSV`/`CSV_NAME` at
what you found in step 7's channel dump.

**Bundle-unpack retry gotcha**: if the InstallPlan never appears and `oc
describe subscription` shows `BundleUnpackFailed: DeadlineExceeded`, OLM
does **not** self-retry — delete and recreate the Subscription (and any
partial CSV) once the ClusterPolicies are confirmed `Ready`:

```bash
oc --context "$CLUSTER_CONTEXT" delete subscription rhods-operator -n redhat-ods-operator
oc --context "$CLUSTER_CONTEXT" delete csv "rhods-operator.<version>" -n redhat-ods-operator --ignore-not-found
# then re-apply the Subscription
```

## 9. Apply minimal DSCI/DSC

Reuse [install-rhoai.md](install-rhoai.md) step 3's YAML verbatim.

## 10. RHOAI 3.6-ea.1 specific: the dashboard needs Gateway API → Service Mesh 3

**Fixing step 6's registry-rewrite regex is necessary but not sufficient**
to get `dsc/default-dsc` to `Ready`. RHOAI 3.6-ea.1 has moved the
dashboard from a plain OpenShift `Route` to Kubernetes **Gateway API**
(`HTTPRoute` + `Gateway` + `GatewayClass`, controller name
`openshift.io/gateway-controller/v1`) — matching upstream RHOAI 3.3+'s
documented shift away from Service Mesh 2/`Route`. The
`dashboard-operator` *does* auto-create the `HTTPRoute`/`Gateway`/
`GatewayClass`, but on a stock OCP 4.21 cluster nothing implements that
controller name, so they sit forever at `status.conditions:
Accepted=Unknown, reason: Pending, message: "Waiting for controller"`,
and the DSC stays `DashboardReady=False reason=RouteNotReady` no matter
how healthy `dashboard-redirect` is.

**Dead ends to skip** (both checked live this session, in this order):

- A manual stand-in `Route` doesn't help — the operator's readiness check
  wants an admitted `Gateway`/`HTTPRoute`, not a `Route`, and won't adopt
  one even after it's created.
- `TechPreviewNoUpgrade` is **not** the fix. The `GatewayAPI`/
  `GatewayAPIController` feature gates are already **enabled by default**
  on 4.21 — check with
  `oc --context "$CLUSTER_CONTEXT" get featuregate cluster -o json | jq '.status.featureGates[] | select(.version=="4.21.0")'`
  (not `.status.featureGates[0]`, which can silently pick the wrong
  version entry and make you think the gates are disabled when they
  aren't). Also, `FeatureGate` is locked on ROSA HCP guest clusters
  regardless of the gates' actual state — only settable from the
  management-cluster `HostedCluster` object, so even if it *were* needed,
  it isn't reachable from the customer side.

**Real, documented fix** — confirmed via the official [Red Hat Developer
article "Integrate OpenShift Gateway API with OpenShift Service
Mesh"](https://developers.redhat.com/articles/2025/12/09/integrate-openshift-gateway-api-openshift-service-mesh):
the supported way to get *any* Gateway API controller running on
OpenShift is to install **Red Hat OpenShift Service Mesh 3**
(`servicemeshoperator3`) — Service Mesh isn't otherwise used here, it's
purely the vehicle Red Hat ships the Envoy-based Gateway controller
through. This applies to any OCP 4.19+ cluster, not just ROSA HCP, and
isn't EA-specific either — it's a real prerequisite of RHOAI's newer
Gateway-API-based dashboard architecture in general.

```bash
cat <<EOF | oc --context "$CLUSTER_CONTEXT" apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: servicemeshoperator3
  namespace: openshift-operators
spec:
  channel: stable
  name: servicemeshoperator3
  source: redhat-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
EOF
oc config use-context "$CLUSTER_CONTEXT"
# No startingCSV is pinned above (see Gotcha 1), so the CSV name isn't known
# until OLM resolves it — discover it from the Subscription rather than
# waiting on a label selector, which can match an unrelated/older CSV.
CSV_NAME=""
for i in $(seq 1 12); do
  CSV_NAME=$(oc get subscription servicemeshoperator3 -n openshift-operators -o jsonpath='{.status.currentCSV}')
  [ -n "$CSV_NAME" ] && break
  echo "waiting for Subscription to resolve a currentCSV (attempt $i/12)..." >&2
  sleep 5
done
[ -n "$CSV_NAME" ] || { echo "ERROR: Subscription servicemeshoperator3 never resolved a currentCSV" >&2; exit 1; }
.cursor/skills/lib/wait-for-csv.sh openshift-operators "$CSV_NAME"
```

**Gotcha 1 — don't pin `startingCSV`.** A first attempt pinning
`startingCSV: servicemeshoperator3.v3.4.1` with `installPlanApproval:
Automatic` still resolved through an older intermediate CSV first
(`v3.2.0`, walking the channel's `replaces` chain) and needed a second
manual `InstallPlan` approval to actually reach `v3.4.1` — wasted ~5 min
for no benefit. Omit `startingCSV` entirely and let `Automatic` approval
install the `stable` channel head directly in one step.

**Gotcha 2 — may hit one transient `BundleUnpackFailed:
DeadlineExceeded`** on the very first attempt. Unlike step 3's
OCPBUGS-23901 gotcha, this is standard content already covered by ROSA's
default pull-secret and pulled fine from `registry.redhat.io` on retry —
delete the Subscription+CSV and recreate, same fix as the RHOAI-operator
bundle-unpack gotcha in step 8.

**No manual `Istio`/`IstioCNI` CR authoring needed.** Once
`servicemeshoperator3`'s CSV reaches `Succeeded`, the RHOAI platform
operator's own `GatewayConfig`/`DSCInitialization` controller
auto-creates an `Istio` CR (`sailoperator.io/v1`, name matching the
`Gateway`'s `istio.io/rev` label) within seconds. `GatewayClass`/
`Gateway`/`HTTPRoute` flip to `Accepted`/`Programmed`/`ResolvedRefs`
shortly after, and:

```bash
oc --context "$CLUSTER_CONTEXT" get dsc default-dsc -o jsonpath='{.status.phase}{"\n"}'   # Ready
```

**Dashboard URL note**: the Gateway-fronted dashboard is served from a
*different* hostname shape than the classic Route —
`https://rh-ai.apps.<cluster-domain>` (read it from
`oc --context "$CLUSTER_CONTEXT" get gatewayconfig default-gateway -o jsonpath='{.status.domain}'`),
not the `https://rhods-dashboard-redhat-ods-applications.apps.<cluster-domain>`
Route hostname `install-rhoai.md` documents for the GA/Route-based path.

## 11. arm64 verification recipe

The actual payoff of installing an EA build on arm64 workers — confirm
the images really ship arm64 variants, don't assume from the release
notes:

```bash
IMG="quay.io/rhoai/odh-workbench-jupyter-pytorch-cuda-py312-rhel9:rhoai-3.6-ea.1"
skopeo inspect --raw "docker://$IMG" | \
  jq -e '[.manifests[]? | select(.platform.architecture=="arm64" and .platform.os=="linux")] | length > 0' \
  || { echo "ERROR: no arm64/linux manifest found for $IMG" >&2; exit 1; }
skopeo inspect --raw "docker://$IMG" | \
  jq -c '[.manifests[]? | {arch: .platform.architecture, os: .platform.os}] | unique'
```

Confirmed present in the 3.6.0-ea.1 build (2026-08-10): the **CUDA**
pytorch workbench ships `[amd64, arm64]` (not just CPU images), and
`odh-workbench-jupyter-minimal-cpu-py312-rhel9`/
`odh-workbench-jupyter-datascience-cpu-py312-rhel9` ship
`[amd64, arm64, ppc64le, s390x]`.

**Resolved, not just flagged**: `WorkbenchesReady=True` initially came
with 18 ImageStream tag import warnings — those tags reference
`registry.redhat.io/rhoai/*`, which isn't mirrored for EA content (same
root cause as step 3's `odh-operator-bundle` pull failure). Step 6's
`replace-image-registry-imagestream-tags` rule handles this directly (the
"open tension" this used to describe — rewriting `ImageStream` tags vs.
not re-broadening the Pod-container regex — doesn't actually exist:
they're two independent rules in the same policy, scoped to different
resource kinds, with no overlap). After the policy was live, nearly every
existing `ImageStream` self-healed within the `workbenches` operator's
normal ~10s reconcile cadence with zero manual action; the one exception
was an `ImageStream` this session's *own* mutate-rule bug had actively
corrupted (see step 6's `patchStrategicMerge`-vs-`patchesJson6902`
gotcha), fixed with one `oc delete imagestream` to let the operator
recreate it. Confirmed cluster-wide after: zero `spec.tags[].from.name`
still on `registry.redhat.io/rhoai/*`, and every tag has a
`status.tags[].items` entry (i.e. actually imported, not just silently
unattempted).

## 12. Known gaps — explicitly not verified

- No notebook was actually spawned from the dashboard UI on arm64
  workers — only image-manifest-level arm64 presence (step 11) is
  confirmed, not that a spawn actually works end-to-end on this EA build.
- No GPU smoke pod was run against the `gpu-arm`/`g5g.2xlarge` pool for
  this specific build — see [arm64-rosa-gpu-smoke](../arm64-rosa-gpu-smoke/SKILL.md)
  Phase 3 for the procedure once you're ready to close this gap.
