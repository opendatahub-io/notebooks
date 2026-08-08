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

echo "==> Preflight"
run rosa whoami | rg 'OCM Organization ID' | rg -q '1pwwsfazToamNegaehP6eaDg80K'
run aws sts get-caller-identity | jq -e '.Account == "585132637328"'

echo "==> Current machine pools"
run rosa list machinepools -c "$CLUSTER_NAME"

if run rosa describe machinepool "$NEW_POOL" -c "$CLUSTER_NAME" >/dev/null 2>&1; then
  echo "Pool $NEW_POOL already exists; skipping create"
else
  echo "==> Creating $NEW_POOL ($INSTANCE_TYPE)"
  run rosa create machinepool --cluster "$CLUSTER_NAME" --name "$NEW_POOL" \
    --instance-type "$INSTANCE_TYPE" --replicas 1 --subnet "$PRIVATE_SUBNET" --yes
fi

echo "==> Wait for new GPU node Ready:"
echo "    oc get nodes -l node.kubernetes.io/instance-type=$INSTANCE_TYPE -w"
echo ""
echo "When Ready, delete the old pool:"
echo "  rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete machinepool --cluster $CLUSTER_NAME $OLD_POOL --yes"
echo ""
echo "Driver reschedules to the new node and recompiles (~15-30 min on g5g.2xlarge)."
