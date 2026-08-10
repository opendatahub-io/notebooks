# Installing a released RHOAI version (GA OperatorHub channel)

This covers installing an **already-released** RHOAI version via the
standard `redhat-operators` OperatorHub catalog. If you need a
**pre-release** build instead, see [SKILL.md](SKILL.md)'s
`## Pre-Release Images (Pull Secret)` section — that path needs Kyverno
and a namespace pull-secret for `quay.io/rhoai`; this one needs neither.

Validated end-to-end on a real ROSA HCP cluster (2026-08-08): RHOAI 2.25.9,
`dashboard`+`workbenches` only, from operator subscribe to dashboard pods
`Running` in ~2-4 minutes.

## 1. Discover the exact channel/CSV for your target version

```bash
oc get packagemanifest rhods-operator -o jsonpath='{.status.channels[*].name}'
# e.g.: stable stable-2.10 stable-2.13 stable-2.16 stable-2.19 stable-2.22
#       stable-2.25 stable-3.3 stable-3.4 stable-3.x eus-2.16 eus-2.25 eus-2.8
#       fast fast-3.x alpha beta ...

oc get packagemanifest rhods-operator -o json | \
  jq -r '.status.channels[] | select(.name=="stable-2.25") | .currentCSV'
# rhods-operator.2.25.9
```

`currentCSV` is always the **channel head** — if you need a specific
earlier patch that's still present in the channel, select it explicitly
from `.entries[]` instead:

```bash
oc get packagemanifest rhods-operator -o json | \
  jq -r '.status.channels[] | select(.name=="stable-2.25") | .entries[] | select(.name=="rhods-operator.2.25.9") | .name'
```

`eus-X.Y` channels track Extended Update Support releases; `stable-X.Y`
pins to a specific minor without EUS commitments. Pick whichever matches
what you're actually validating against — don't default to the bare
`stable` channel, it tracks the latest minor and will drift out from under
a pinned validation run.

## 2. OperatorGroup must be `AllNamespaces`, not `OwnNamespace`

A scoped `OperatorGroup` (`targetNamespaces: [redhat-ods-operator]`) fails
with this exact error, reproduced verbatim so it's searchable:

```text
OwnNamespace InstallModeType not supported, cannot configure to watch own namespace
UnsupportedOperatorGroup
```

The fix is an **empty `spec: {}`**:

```yaml
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
```

Manual approval means OLM won't silently install a newer CSV pushed to
`stable-2.25` after you pinned this. Approve the pinned InstallPlan before
waiting for `Succeeded` — select it by exact CSV match, not output order,
since a namespace can have more than one InstallPlan:

```bash
CSV_NAME=rhods-operator.2.25.9
INSTALLPLAN=$(oc get installplan -n redhat-ods-operator -o json | \
  jq -r --arg csv "$CSV_NAME" '.items[] | select(.spec.clusterServiceVersionNames | index($csv)) | .metadata.name')
[ "$(echo "$INSTALLPLAN" | grep -c .)" -eq 1 ] || { echo "ERROR: expected exactly one InstallPlan for $CSV_NAME, found: $INSTALLPLAN" >&2; exit 1; }
oc patch installplan "$INSTALLPLAN" -n redhat-ods-operator --type merge -p '{"spec":{"approved":true}}'
```

**If a `Subscription`/CSV was already created against the wrong
`OperatorGroup`**, fixing the `OperatorGroup` alone isn't enough — OLM
doesn't retry a `Failed` CSV automatically. Delete and recreate:

```bash
oc delete subscription rhods-operator -n redhat-ods-operator
oc delete csv rhods-operator.<version> -n redhat-ods-operator
oc delete installplan -n redhat-ods-operator --all
# then re-apply the Subscription above
```

Wait for `Succeeded` (`-w` only streams — it neither blocks until the
condition nor times out, so use `oc wait` for anything scripted):

```bash
oc wait --for=jsonpath='{.status.phase}'=Succeeded csv/rhods-operator.2.25.9 -n redhat-ods-operator --timeout=300s
```

## 3. Minimal DSC/DSCI for IDE/spawn/clone-focused testing

Everything except `dashboard`+`workbenches` set to `Removed` — this is
exactly what produced the small idle resource footprint documented in
[cost-optimization.md](cost-optimization.md). Adjust the `Removed`
components if your test target needs `kserve`, `datasciencepipelines`,
etc.

```yaml
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
```

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
oc get pods -n redhat-ods-applications
oc get route -n redhat-ods-applications rhods-dashboard
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
