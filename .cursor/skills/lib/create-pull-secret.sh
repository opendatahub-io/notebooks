#!/usr/bin/env bash
# Shared by rosa-hcp-provision and arm64-rosa-gpu-smoke: build a
# dockerconfigjson pull secret from interactively-entered credentials and
# create it in the cluster. Never accepts a credential as a CLI argument
# (would leak via shell history / `ps`) and never reads
# ~/.docker/config.json automatically (would silently harvest whatever
# credential happens to be cached there).
#
# Usage: CLUSTER_CONTEXT=<ctx> create-pull-secret.sh <secret-name> <namespace> <registry-host-group> [<registry-host-group> ...]
#
# Each <registry-host-group> is one or more comma-separated auth keys that
# share a single prompted credential, e.g. "quay.io,quay.io/rhoai" writes
# the same auth under both keys (useful when a client does exact-key
# lookup rather than prefix matching on the dockerconfigjson). Prompts for
# a username, and skips the whole group entirely (no entry in the secret)
# if the username is left blank — this is how a caller can conditionally
# omit a registry it doesn't need (e.g. registry.redhat.io when only a
# quay.io credential is available), without any special-cased flag. If a
# username is given, the password is required non-empty.
#
# Requires CLUSTER_CONTEXT in the environment and passes it explicitly on
# every oc call — never relies on / mutates the ambient current-context.
# `oc config use-context` changes shared, machine-wide kubeconfig state; a
# concurrent process changing it between the caller's setup and this
# script's execution would otherwise create the secret in the wrong
# cluster (see rosa-hcp-provision/SKILL.md's "always pass --context" rule).
set -euo pipefail

: "${CLUSTER_CONTEXT:?Set CLUSTER_CONTEXT to the exact kubeconfig context of the target cluster}"

if [ "$#" -lt 3 ]; then
  echo "Usage: CLUSTER_CONTEXT=<ctx> $0 <secret-name> <namespace> <registry-host-group> [<registry-host-group> ...]" >&2
  exit 2
fi

SECRET_NAME="$1"
NAMESPACE="$2"
shift 2

SECRET_FILE=$(umask 077 && mktemp)
AUTH_FILE=""
cleanup() { rm -f "$SECRET_FILE" "${AUTH_FILE:-}"; }
trap cleanup EXIT

AUTHS_JSON="{}"
ANY_HOST_CONFIGURED=false

for GROUP in "$@"; do
  read -r -p "Username for ${GROUP} (leave blank to skip this registry): " REG_USER
  if [ -z "$REG_USER" ]; then
    echo "Skipping ${GROUP} (no username given)" >&2
    continue
  fi
  read -rs -p "Password/token for ${GROUP}: " REG_PASS; echo
  if [ -z "$REG_PASS" ]; then
    echo "ERROR: a username was given for ${GROUP} but the password was empty" >&2
    exit 1
  fi
  AUTH_FILE=$(umask 077 && mktemp)
  printf '%s' "${REG_USER}:${REG_PASS}" | base64 | tr -d '\n' > "$AUTH_FILE"
  IFS=',' read -ra HOST_KEYS <<< "$GROUP"
  for HOST in "${HOST_KEYS[@]}"; do
    # --rawfile, not --arg $AUTH — --arg would put the (base64-encoded,
    # still sensitive) credential into jq's own process argument list.
    AUTHS_JSON=$(printf '%s' "$AUTHS_JSON" | jq --arg host "$HOST" --rawfile auth "$AUTH_FILE" \
      '.[$host] = {"auth": $auth}')
  done
  rm -f "$AUTH_FILE"
  ANY_HOST_CONFIGURED=true
  unset REG_USER REG_PASS AUTH_FILE
done

if [ "$ANY_HOST_CONFIGURED" != true ]; then
  echo "ERROR: no registry host was configured (every username was left blank)" >&2
  exit 1
fi

printf '%s' "$AUTHS_JSON" | jq '{"auths": .}' > "$SECRET_FILE"

oc --context "$CLUSTER_CONTEXT" create secret generic "$SECRET_NAME" -n "$NAMESPACE" \
  --from-file=.dockerconfigjson="$SECRET_FILE" \
  --type=kubernetes.io/dockerconfigjson \
  --dry-run=client -o yaml | oc --context "$CLUSTER_CONTEXT" apply -f -

rm -f "$SECRET_FILE"
echo "Created/updated secret ${SECRET_NAME} in namespace ${NAMESPACE}" >&2
