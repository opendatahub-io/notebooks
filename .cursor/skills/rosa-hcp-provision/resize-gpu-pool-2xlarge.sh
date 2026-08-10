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

echo "==> Wait for new GPU node Ready, THEN wait for the driver to actually be usable on it"
echo "    (node Ready alone does not mean the GPU is schedulable yet):"
echo "    oc get nodes -l node.kubernetes.io/instance-type=$INSTANCE_TYPE -w"
echo "    oc wait --for=condition=Ready pod -l app=nvidia-driver-daemonset -n nvidia-gpu-operator --timeout=1800s"
echo "    oc get node -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].status.allocatable.nvidia\.com/gpu}{\"\n\"}'  # expect 1"
echo ""
echo "Only after nvidia.com/gpu is allocatable, delete the old pool:"
echo "  rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete machinepool --cluster $CLUSTER_NAME $OLD_POOL --yes"
echo ""
echo "Driver reschedules to the new node and recompiles (~15-30 min on g5g.2xlarge)."
