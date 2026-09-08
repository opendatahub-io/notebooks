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

# OLM creates the CSV object asynchronously after the InstallPlan is
# approved. Poll for it to exist before starting the Succeeded-vs-Failed
# race below — some oc/kubectl client versions return NotFound immediately
# for `oc wait` against a not-yet-existing resource instead of waiting for
# it to appear, which would otherwise let the race start handicapped.
CSV_EXISTS=false
for i in $(seq 1 12); do
  if oc --context "$CLUSTER_CONTEXT" get csv "$CSV_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    CSV_EXISTS=true
    break
  fi
  echo "Waiting for csv/${CSV_NAME} to be created (attempt ${i}/12)..." >&2
  sleep 5
done
if [ "$CSV_EXISTS" != true ]; then
  echo "ERROR: csv/${CSV_NAME} in ${NAMESPACE} was not created within 60s of InstallPlan approval" >&2
  exit 1
fi

# Race Succeeded against Failed instead of a single `--for=Succeeded` wait.
# A CSV has a well-known binary failure signal (status.phase can reach
# "Failed", distinct from "Succeeded") — unlike most resources (e.g. a
# Pod, which has no single "give up early" condition), so this doesn't
# need a heuristic: whichever phase is reached first is authoritative, and
# the other wait is killed instead of blocking for the rest of the
# 300s timeout after the outcome is already known. Portable to macOS's
# stock bash 3.2 (no `wait -n`, which needs bash 4.3+) via a small polling
# loop over two flag files instead.
RESULT_DIR=$(mktemp -d)
SUCCEEDED_PID=""
FAILED_PID=""
trap 'rm -rf "$RESULT_DIR"; kill "$SUCCEEDED_PID" "$FAILED_PID" 2>/dev/null || true' EXIT

(oc --context "$CLUSTER_CONTEXT" wait --for=jsonpath='{.status.phase}'=Succeeded "csv/${CSV_NAME}" -n "$NAMESPACE" --timeout=300s >/dev/null 2>&1 \
  && touch "$RESULT_DIR/succeeded") &
SUCCEEDED_PID=$!

(oc --context "$CLUSTER_CONTEXT" wait --for=jsonpath='{.status.phase}'=Failed "csv/${CSV_NAME}" -n "$NAMESPACE" --timeout=300s >/dev/null 2>&1 \
  && touch "$RESULT_DIR/failed") &
FAILED_PID=$!

while true; do
  if [ -f "$RESULT_DIR/succeeded" ]; then
    kill "$FAILED_PID" 2>/dev/null || true
    echo "csv/${CSV_NAME} in ${NAMESPACE} reached Succeeded" >&2
    exit 0
  fi
  if [ -f "$RESULT_DIR/failed" ]; then
    kill "$SUCCEEDED_PID" 2>/dev/null || true
    echo "ERROR: csv/${CSV_NAME} in ${NAMESPACE} reached Failed" >&2
    oc --context "$CLUSTER_CONTEXT" get csv "$CSV_NAME" -n "$NAMESPACE" -o jsonpath='{.status.message}{"\n"}' >&2 || true
    exit 1
  fi
  if ! kill -0 "$SUCCEEDED_PID" 2>/dev/null && ! kill -0 "$FAILED_PID" 2>/dev/null; then
    echo "ERROR: csv/${CSV_NAME} in ${NAMESPACE} reached neither Succeeded nor Failed within 300s" >&2
    exit 1
  fi
  sleep 2
done
