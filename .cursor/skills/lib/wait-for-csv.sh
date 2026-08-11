#!/usr/bin/env bash
# Shared by rosa-hcp-provision docs: after creating a Subscription with
# installPlanApproval: Manual, find the InstallPlan for an exact CSV
# name (never `tail -1`/label-selector matching, which can grab an
# unrelated or older InstallPlan when more than one exists in the
# namespace), approve it, and wait for that CSV to succeed.
#
# Usage: CLUSTER_CONTEXT=<ctx> wait-for-csv.sh <namespace> <csv-name>
#
# Requires CLUSTER_CONTEXT in the environment and passes it explicitly on
# every oc call — never relies on the ambient current-context, which is
# shared, mutable, machine-wide state a concurrent process could change
# between the caller's setup and this script's execution (see
# rosa-hcp-provision/SKILL.md's "always pass --context" rule). Assumes the
# Subscription referencing <csv-name> has already been applied (OLM
# creates the InstallPlan asynchronously afterward, so this script polls
# rather than querying once).
set -euo pipefail

: "${CLUSTER_CONTEXT:?Set CLUSTER_CONTEXT to the exact kubeconfig context of the target cluster}"

if [ "$#" -ne 2 ]; then
  echo "Usage: CLUSTER_CONTEXT=<ctx> $0 <namespace> <csv-name>" >&2
  exit 2
fi

NAMESPACE="$1"
CSV_NAME="$2"

INSTALLPLAN=""
for i in $(seq 1 12); do
  INSTALLPLAN=$(oc --context "$CLUSTER_CONTEXT" get installplan -n "$NAMESPACE" -o json | \
    jq -r --arg csv "$CSV_NAME" \
      '.items[] | select(.spec.clusterServiceVersionNames | index($csv)) | .metadata.name')
  MATCH_COUNT=$(printf '%s\n' "$INSTALLPLAN" | grep -c . || true)
  if [ "$MATCH_COUNT" -eq 1 ]; then
    break
  fi
  echo "Waiting for exactly one InstallPlan for ${CSV_NAME} (attempt ${i}/12, found ${MATCH_COUNT})..." >&2
  sleep 5
done

MATCH_COUNT=$(printf '%s\n' "$INSTALLPLAN" | grep -c . || true)
if [ "$MATCH_COUNT" -ne 1 ]; then
  echo "ERROR: expected exactly one InstallPlan for ${CSV_NAME} in ${NAMESPACE}, found ${MATCH_COUNT}" >&2
  exit 1
fi

oc --context "$CLUSTER_CONTEXT" patch installplan "$INSTALLPLAN" -n "$NAMESPACE" --type merge -p '{"spec":{"approved":true}}'

oc --context "$CLUSTER_CONTEXT" wait --for=jsonpath='{.status.phase}'=Succeeded "csv/${CSV_NAME}" -n "$NAMESPACE" --timeout=300s
echo "csv/${CSV_NAME} in ${NAMESPACE} reached Succeeded" >&2
