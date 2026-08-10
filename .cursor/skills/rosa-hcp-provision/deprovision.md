# ROSA HCP Deprovisioning

Validated on **`jd-arm64-ea1`** (Jul 2026): ROSA HCP, OCP 4.21.0, pools `workers` (2× `m6g.2xlarge`) + `gpu-arm2` (1× `g5g.2xlarge`).

## When to use

| Goal | Action |
|------|--------|
| Done with all testing | **Full deprovision** (this doc) |
| Pause GPU spend, keep cluster | Delete GPU machine pool only — see [SKILL.md](SKILL.md#resize-gpu-pool-instance-type-is-immutable) |
| Short break (< few days) | Leave cluster running or scale GPU pool to 0 replicas (still recompiles driver on scale-up with default DTK) |

Full delete stops **~$2.45/hr** (EC2 + ROSA fees for 2× m6g.2xlarge + 1× g5g.2xlarge + HCP cluster fee in `us-east-1`).

## Prerequisites

```bash
export CLUSTER_NAME=<name>   # must be set before any command below

# macOS — refresh Kerberos if rh-aws-saml-login fails with CLIENT_NOT_FOUND
kinit --keychain <user>@IPA.REDHAT.COM

# Confirm cluster exists and note operator-role prefix before delete
rh-aws-saml-login iaps-rhods-odh-dev -- rosa list clusters | grep "$CLUSTER_NAME"
rh-aws-saml-login iaps-rhods-odh-dev -- rosa list machinepools -c "$CLUSTER_NAME"
```

Operator-role **prefix** is shown at cluster create time (e.g. `jd-arm64-ea1-w7f2`) and in `rosa delete cluster` output. Save it — you need it after uninstall completes.

## Full teardown (recommended order)

### 1. Delete the cluster

Deletes **all machine pools** (CPU + GPU) and the hosted control plane subscription. No need to delete pools individually first.

```bash
export CLUSTER_NAME=jd-arm64-ea1   # max 15 chars at create time
# ⚠️ copy this verbatim from YOUR cluster's `rosa delete cluster` output —
# never reuse the example value below, it deletes another cluster's IAM roles
export OPERATOR_PREFIX=jd-arm64-ea1-w7f2   # from create / delete output

rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete cluster \
  --cluster "$CLUSTER_NAME" --yes
```

`rosa delete cluster` prints:

- Remaining **operator IAM roles** (clean up in step 2)
- **OIDC provider URL** — do **not** delete (shared team resource)
- Suggested commands including `rosa delete operator-roles --prefix …`

Watch uninstall logs (optional):

```bash
rh-aws-saml-login iaps-rhods-odh-dev -- rosa logs uninstall -c "$CLUSTER_NAME" --watch
```

### 2. Wait until cluster is gone

Poll until the cluster disappears from OCM (observed **~15–20 min** for `jd-arm64-ea1`):

```bash
if ! clusters="$(rh-aws-saml-login iaps-rhods-odh-dev -- rosa list clusters)"; then
  echo "Unable to query cluster state — retry, don't assume it's gone" >&2
else
  if printf '%s\n' "$clusters" | grep -Fq "$CLUSTER_NAME"; then
    echo "still present"
  else
    echo "gone"
  fi
fi
```

State may show `uninstalling` then drop from the list entirely.

### 3. Delete operator IAM roles

**Must pass `--mode auto`** in non-interactive environments — otherwise `rosa` prompts `auto|manual` and fails with `invalid mode: EOF`.

**Double-check `$OPERATOR_PREFIX` before running this** — it's paired with
`--yes` and deletes IAM roles unconditionally. Confirm it matches *this*
cluster's prefix (from step 1's output), not a value copied from an
example or a different cluster.

```bash
rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete operator-roles \
  --prefix "$OPERATOR_PREFIX" --mode auto --yes
```

Expect 8 roles for a typical HCP cluster (kube-system + openshift operators). Success: `Successfully deleted the operator roles`.

Alternative if you still have cluster metadata:

```bash
rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete operator-roles \
  --cluster "$CLUSTER_NAME" --mode auto --yes
```

(Only works while cluster record exists; use `--prefix` after uninstall.)

### 4. Do **not** delete the OIDC provider

```bash
# ⚠️ NEVER run unless you own a dedicated OIDC config and know no other clusters use it
# rosa delete oidc-provider --oidc-config-id 23c734st3pn7l167mq97d0ot8848lgrl
```

Shared RHOAI dev account OIDC: `23c734st3pn7l167mq97d0ot8848lgrl` — used by many team clusters.

### 5. Local cleanup (optional)

Remove stale kubeconfig context so `oc` does not hang (the domain suffix
after `${CLUSTER_NAME}` is cluster-specific, so discover it instead of
hardcoding it):

```bash
kubectl config get-contexts -o name | grep "$CLUSTER_NAME" | xargs -r -n1 kubectl config delete-context
```

Validation artifacts (logs, matrices) live in the repo under `.cursor-tmp-artifact/` — not on the cluster; deprovision does not remove them.

## What gets removed vs left behind

| Resource | Deleted? |
|----------|----------|
| EC2 worker / GPU nodes | Yes (via cluster uninstall) |
| ROSA HCP cluster + per-cluster fee | Yes |
| Operator IAM roles (`<prefix>-*`) | Yes (step 3) |
| Shared VPC / subnets | No — team infra |
| OIDC provider | **No** — shared |
| Installer / support / worker **shared** IAM roles | No |
| Local test logs / results matrix | No — on disk in repo |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `CLIENT_NOT_FOUND` on `rh-aws-saml-login` | `kinit --keychain user@IPA.REDHAT.COM` |
| `rosa delete operator-roles` prompts for mode | Add `--mode auto --yes` |
| `invalid mode: EOF` | Same — non-TTY shell needs `--mode auto` |
| Cluster stuck `uninstalling` > 45 min | `rosa logs uninstall -c … --watch`; check AWS console for stuck ENI/EBS |
| Operator roles already deleted | `aws iam list-roles --query "Roles[?starts_with(RoleName, '${OPERATOR_PREFIX}')].RoleName"` |
| Accidentally deleted OIDC provider | Escalate in **#rhoai-devtestops-requests** — breaks other clusters |

## Example: jd-arm64-ea1 (Jul 2026)

```bash
export CLUSTER_NAME=jd-arm64-ea1
export OPERATOR_PREFIX=jd-arm64-ea1-w7f2

rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete cluster --cluster "$CLUSTER_NAME" --yes
# … wait ~18 min …
rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete operator-roles \
  --prefix "$OPERATOR_PREFIX" --mode auto --yes
```

Machine pools at delete time: `workers` 2/2 `m6g.2xlarge`, `gpu-arm2` 1/1 `g5g.2xlarge`.

## Related

- [SKILL.md](SKILL.md) — create, GPU pools, pull secrets
- [nvidia-driver-compilation.md](nvidia-driver-compilation.md) — driver compile; irrelevant after full delete
- [arm64-rosa-gpu-smoke](../arm64-rosa-gpu-smoke/SKILL.md) — validation workflow before teardown
