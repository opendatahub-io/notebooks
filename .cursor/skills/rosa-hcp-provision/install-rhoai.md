# Installing a released RHOAI version (GA OperatorHub channel)

This covers installing an **already-released** RHOAI version via the
standard `redhat-operators` OperatorHub catalog. If you need an
**EA/pre-release** build instead (not yet on any GA channel), see
[install-prerelease.md](install-prerelease.md) — that path needs Kyverno,
a namespace pull-secret for `quay.io/rhoai`, a custom `CatalogSource`, and
(for RHOAI 3.3+ dashboard builds) Red Hat OpenShift Service Mesh 3 for
Gateway API; this doc needs none of that.

Validated end-to-end on a real ROSA HCP cluster (2026-08-08): RHOAI 2.25.9,
`dashboard`+`workbenches` only, from operator subscribe to dashboard pods
`Running` in ~2-4 minutes.

## 0. Pin the cluster context — do this before anything else

`~/.kube/config`'s `current-context` is shared, mutable, machine-wide
state — never rely on it implicitly. Capture it once and pass it
explicitly on every `oc` command below (see
[SKILL.md](SKILL.md#critical-always-pass---context-never-rely-on-the-ambient-current-context)
for why: a real incident had `oc` silently hit a different cluster
mid-session because something else on the same machine changed
`current-context`):

```bash
export CLUSTER_CONTEXT=$(oc config current-context)
oc --context "$CLUSTER_CONTEXT" whoami --show-server   # sanity check
```

## 1. Discover the exact channel/CSV for your target version

```bash
oc --context "$CLUSTER_CONTEXT" get packagemanifest rhods-operator -o jsonpath='{.status.channels[*].name}'
# e.g.: stable stable-2.10 stable-2.13 stable-2.16 stable-2.19 stable-2.22
#       stable-2.25 stable-3.3 stable-3.4 stable-3.x eus-2.16 eus-2.25 eus-2.8
#       fast fast-3.x alpha beta ...

oc --context "$CLUSTER_CONTEXT" get packagemanifest rhods-operator -o json | \
  jq -r '.status.channels[] | select(.name=="stable-2.25") | .currentCSV'
# rhods-operator.2.25.9
```

`currentCSV` is always the **channel head** — if you need a specific
earlier patch that's still present in the channel, select it explicitly
from `.entries[]` instead:

```bash
oc --context "$CLUSTER_CONTEXT" get packagemanifest rhods-operator -o json | \
  jq -r '.status.channels[] | select(.name=="stable-2.25") | .entries[] | select(.name=="rhods-operator.2.25.9") | .name'
```

`eus-X.Y` channels track Extended Update Support releases; `stable-X.Y`
pins to a specific minor without EUS commitments. Pick whichever matches
what you're actually validating against — don't default to the bare
`stable` channel, it tracks the latest minor and will drift out from under
a pinned validation run.

**The `channel`/`startingCSV`/`CSV_NAME` values below (`stable-2.25`,
`rhods-operator.2.25.9`) are this session's concrete worked example, not
generic placeholders** — if step 1 discovers a different channel/CSV for
your target version, replace all three occurrences below (the
Subscription YAML, the `CSV_NAME` variable, and the final `oc wait`
command) consistently; they're not derived from each other automatically.

## 2. OperatorGroup must be `AllNamespaces`, not `OwnNamespace`

A scoped `OperatorGroup` (`targetNamespaces: [redhat-ods-operator]`) fails
with this exact error, reproduced verbatim so it's searchable:

```text
OwnNamespace InstallModeType not supported, cannot configure to watch own namespace
UnsupportedOperatorGroup
```

The fix is an **empty `spec: {}`**:

```bash
cat <<EOF | oc --context "$CLUSTER_CONTEXT" apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: redhat-ods-operator
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: rhods-operator
  namespace: redhat-ods-operator
spec: {}
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: rhods-operator
  namespace: redhat-ods-operator
spec:
  channel: stable-2.25
  name: rhods-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
  startingCSV: rhods-operator.2.25.9   # pin to the CSV discovered in step 1
  installPlanApproval: Manual
EOF
```

Manual approval means OLM won't silently install a newer CSV pushed to
`stable-2.25` after you pinned this. Approve the pinned InstallPlan before
waiting for `Succeeded` — select it by exact CSV match, not output order,
since a namespace can have more than one InstallPlan. OLM creates the
InstallPlan asynchronously after the Subscription is applied, so poll for
it rather than querying once:

```bash
CSV_NAME=rhods-operator.2.25.9
INSTALLPLAN=""
for i in $(seq 1 12); do
  INSTALLPLAN=$(oc --context "$CLUSTER_CONTEXT" get installplan -n redhat-ods-operator -o json | \
    jq -r --arg csv "$CSV_NAME" '.items[] | select(.spec.clusterServiceVersionNames | index($csv)) | .metadata.name')
  [ "$(echo "$INSTALLPLAN" | grep -c .)" -eq 1 ] && break
  echo "waiting for InstallPlan referencing $CSV_NAME (attempt $i/12)..." >&2
  sleep 5
done
[ "$(echo "$INSTALLPLAN" | grep -c .)" -eq 1 ] || { echo "ERROR: expected exactly one InstallPlan for $CSV_NAME, found: $INSTALLPLAN" >&2; exit 1; }
oc --context "$CLUSTER_CONTEXT" patch installplan "$INSTALLPLAN" -n redhat-ods-operator --type merge -p '{"spec":{"approved":true}}'
```

**If a `Subscription`/CSV was already created against the wrong
`OperatorGroup`**, fixing the `OperatorGroup` alone isn't enough — OLM
doesn't retry a `Failed` CSV automatically. Delete and recreate:

```bash
oc --context "$CLUSTER_CONTEXT" delete subscription rhods-operator -n redhat-ods-operator
oc --context "$CLUSTER_CONTEXT" delete csv rhods-operator.<version> -n redhat-ods-operator
# Delete only the failed InstallPlan, not --all — the namespace can hold
# InstallPlans for other subscriptions/CSVs that --all would also delete.
FAILED_CSV=rhods-operator.<version>
oc --context "$CLUSTER_CONTEXT" get installplan -n redhat-ods-operator -o json | \
  jq -r --arg csv "$FAILED_CSV" '.items[] | select(.spec.clusterServiceVersionNames | index($csv)) | .metadata.name' | \
  xargs -r -n1 oc --context "$CLUSTER_CONTEXT" delete installplan -n redhat-ods-operator
# then re-apply the Subscription above
```

Wait for `Succeeded` (`-w` only streams — it neither blocks until the
condition nor times out, so use `oc wait` for anything scripted):

```bash
oc --context "$CLUSTER_CONTEXT" wait --for=jsonpath='{.status.phase}'=Succeeded csv/rhods-operator.2.25.9 -n redhat-ods-operator --timeout=300s
```

## 3. Minimal DSC/DSCI for IDE/spawn/clone-focused testing

Everything except `dashboard`+`workbenches` set to `Removed` — this is
exactly what produced the small idle resource footprint documented in
[cost-optimization.md](cost-optimization.md). Adjust the `Removed`
components if your test target needs `kserve`, `datasciencepipelines`,
etc.

```bash
cat <<EOF | oc --context "$CLUSTER_CONTEXT" apply -f -
apiVersion: dscinitialization.opendatahub.io/v1
kind: DSCInitialization
metadata:
  name: default-dsci
spec:
  applicationsNamespace: redhat-ods-applications
  monitoring:
    managementState: Managed
    namespace: redhat-ods-monitoring
  serviceMesh:
    managementState: Removed
  trustedCABundle:
    managementState: Managed
    customCABundle: ''
---
apiVersion: datasciencecluster.opendatahub.io/v1
kind: DataScienceCluster
metadata:
  name: default-dsc
spec:
  components:
    dashboard:
      managementState: Managed
    workbenches:
      managementState: Managed
    datasciencepipelines:
      managementState: Removed
    kserve:
      managementState: Removed
    modelmeshserving:
      managementState: Removed
    codeflare:
      managementState: Removed
    ray:
      managementState: Removed
    kueue:
      managementState: Removed
    trainingoperator:
      managementState: Removed
    trustyai:
      managementState: Removed
    modelregistry:
      managementState: Removed
EOF
```

**Component rename in RHOAI 3.6-ea.1+: `datasciencepipelines` → `aipipelines`.**
The YAML above uses `datasciencepipelines`, correct for GA releases through
3.5. On a 3.6-ea.1+ EA build the DSC schema instead expects `aipipelines`
— check with `oc get dsc default-dsc -o json | jq '.spec.components | keys'`
before assuming either name; applying the wrong key for your version is a
silent no-op (the DSC just ignores an unrecognized component key), not an
error. To enable pipelines post-install regardless of which key your
version uses:
```bash
# Select the key the DSC actually supports — patching the wrong one is a
# silent no-op (see above), so don't hardcode either name, and don't
# silently fall back to one if the DSC has neither (a schema this doc
# hasn't seen yet) — fail loudly instead of patching a nonexistent key.
COMPONENT_KEY=$(oc --context "$CLUSTER_CONTEXT" get dsc default-dsc -o json | \
  jq -r 'if .spec.components | has("aipipelines") then "aipipelines"
         elif .spec.components | has("datasciencepipelines") then "datasciencepipelines"
         else "" end')
[ -n "$COMPONENT_KEY" ] || { echo "ERROR: DSC has neither aipipelines nor datasciencepipelines — check 'oc get dsc default-dsc -o json | jq .spec.components'" >&2; exit 1; }
oc --context "$CLUSTER_CONTEXT" patch dsc default-dsc --type merge \
  -p "{\"spec\":{\"components\":{\"$COMPONENT_KEY\":{\"managementState\":\"Managed\"}}}}"
```

**Gotcha: leaving pipelines `Removed` triggers a blocking Kale error popup
in every workbench.** Any workbench image bundling the Kale/Elyra
pipeline-editor extension (i.e. most of them) pings the Kubeflow Pipelines
API every ~30s in the background (`kfp.ping()`) regardless of whether the
user touches any pipeline feature. With pipelines `Removed`, the target
service doesn't exist, DNS resolution fails, and Kale surfaces this as a
recurring, unprompted, blocking "Error — You can find more information
under /opt/app-root/src/kale.log" modal dialog in JupyterLab — cosmetic
(doesn't affect IDE/spawn/clone testing) but confusing if you don't expect
it. Filed as
[RHOAIENG-82538](https://redhat.atlassian.net/browse/RHOAIENG-82538) — no
workaround from the RHOAI side today short of enabling pipelines (see
[arm64-rosa-gpu-smoke's Phase 3c](../arm64-rosa-gpu-smoke/SKILL.md) for a
full pipelines-enabled setup, including an S3-compatible storage backend).

**The operator auto-creates a default `DSCInitialization` on install** —
applying your own `dsci.yaml` on top just patches the existing one. You'll
see:

```text
Warning: resource dscinitializations/default-dsci is missing the
kubectl.kubernetes.io/last-applied-configuration annotation which is
required by oc apply.
```

This is harmless (`oc apply` patches it automatically) — not a sign
anything's wrong.

## 4. Confirm it's up

```bash
oc --context "$CLUSTER_CONTEXT" get pods -n redhat-ods-applications
oc --context "$CLUSTER_CONTEXT" get route -n redhat-ods-applications rhods-dashboard
```

Dashboard route host looks like
`rhods-dashboard-redhat-ods-applications.apps.rosa.<cluster>.<hash>.p3.openshiftapps.com`
— note the `rosa.` prefix on ROSA HCP apps domains, easy to miss when
constructing URLs by hand (e.g. for `test-variables.yml`).

## htpasswd auth for testing (if not already done)

See [SKILL.md](SKILL.md)'s `## Post-Create Setup` — `rosa create idp
--type htpasswd` + `rosa grant user cluster-admin`. If the goal is
admin-level testing (as in this doc), one user reused for both
`TEST_USER` and `OCP_ADMIN_USER` in ods-ci-style `test-variables.yml`
files is fine. If the goal is testing **non-admin** permission behavior,
create a separate least-privileged `TEST_USER` (`rosa create idp` a
second htpasswd entry, no `cluster-admin` grant) and keep `cluster-admin`
scoped to `OCP_ADMIN_USER` only — reusing the admin account there would
mask any RBAC defects the test is meant to catch.
