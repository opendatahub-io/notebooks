#!/usr/bin/env bash
# Replace g5g.xlarge GPU pool with g5g.2xlarge (more CPU/RAM for DTK driver compile).
# Requires: kinit (or kinit --keychain on macOS), rh-aws-saml-login, rosa logged into org 7081269.
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-jd-arm64-ea1}"
OLD_POOL="${OLD_POOL:-gpu-arm}"
NEW_POOL="${NEW_POOL:-gpu-arm2}"
INSTANCE_TYPE="${INSTANCE_TYPE:-g5g.2xlarge}"
PRIVATE_SUBNET="${PRIVATE_SUBNET:-subnet-0a2ab6507448d7c17}"

run() {
  rh-aws-saml-login iaps-rhods-odh-dev -- "$@"
}

if [ "$OLD_POOL" = "$NEW_POOL" ]; then
  echo "ERROR: OLD_POOL and NEW_POOL must differ (both are '$OLD_POOL')" >&2
  exit 1
fi

echo "==> Preflight"
run rosa whoami | rg 'OCM Organization ID' | rg -q '1pwwsfazToamNegaehP6eaDg80K'
run aws sts get-caller-identity | jq -e '.Account == "585132637328"'

echo "==> Current machine pools"
run rosa list machinepools -c "$CLUSTER_NAME"

if describe_output=$(run rosa describe machinepool "$NEW_POOL" -c "$CLUSTER_NAME" 2>&1); then
  # case-insensitive match since the exact label casing in `rosa describe
  # machinepool`'s human-readable output isn't pinned here — verify against
  # a real cluster and tighten this if it ever silently matches nothing.
  actual_type=$(echo "$describe_output" | awk -F': *' 'tolower($0) ~ /instance type/{print $2; exit}')
  if [ "$actual_type" != "$INSTANCE_TYPE" ]; then
    echo "ERROR: existing pool $NEW_POOL is '$actual_type', expected '$INSTANCE_TYPE' — resolve manually before reusing it" >&2
    exit 1
  fi
  echo "Pool $NEW_POOL already exists with matching instance type; skipping create"
elif echo "$describe_output" | grep -qi 'not found'; then
  echo "==> Creating $NEW_POOL ($INSTANCE_TYPE)"
  run rosa create machinepool --cluster "$CLUSTER_NAME" --name "$NEW_POOL" \
    --instance-type "$INSTANCE_TYPE" --replicas 1 --subnet "$PRIVATE_SUBNET" --yes
else
  echo "ERROR: could not determine state of pool $NEW_POOL:" >&2
  echo "$describe_output" >&2
  exit 1
fi

printf '%s\n' "==> Wait for new GPU node Ready, THEN wait for the driver to actually be usable on it"
printf '%s\n' "    (node Ready alone does not mean the GPU is schedulable yet)."
printf '%s\n' "    Scope the check to the NEW pool specifically ($NEW_POOL) — a generic"
printf '%s\n' "    nvidia.com/gpu.present=true selector can also match the still-healthy"
printf '%s\n' "    OLD pool and falsely bless deleting the only working GPU capacity:"
printf '%s\n' "    oc get nodes -l hypershift.openshift.io/nodePool=$NEW_POOL -w"
printf '%s\n' "    NEW_NODE=\$(oc get node -l hypershift.openshift.io/nodePool=$NEW_POOL -o json)"
printf '%s\n' "    [ \"\$(echo \"\$NEW_NODE\" | jq '.items | length')\" -eq 1 ] || { echo \"ERROR: expected exactly one node in pool $NEW_POOL\" >&2; exit 1; }"
printf '%s\n' "    NEW_NODE_NAME=\$(echo \"\$NEW_NODE\" | jq -r '.items[0].metadata.name')"
printf '%s\n' "    oc wait --for=condition=Ready pod -l app.kubernetes.io/component=nvidia-driver -n nvidia-gpu-operator --field-selector spec.nodeName=\"\$NEW_NODE_NAME\" --timeout=1800s"
printf '%s\n' "    oc get node \"\$NEW_NODE_NAME\" -o jsonpath='{.status.allocatable.nvidia\.com/gpu}{\"\n\"}'  # expect 1"
printf '%s\n' ""
printf '%s\n' "Only after nvidia.com/gpu is allocatable on that node, delete the old pool:"
printf '%s\n' "  rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete machinepool --cluster $CLUSTER_NAME $OLD_POOL --yes"
printf '%s\n' ""
printf '%s\n' "Driver reschedules to the new node and recompiles (~15-30 min on g5g.2xlarge)."
