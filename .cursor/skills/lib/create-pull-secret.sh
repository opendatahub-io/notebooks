#!/usr/bin/env bash
# Shared by rosa-hcp-provision and arm64-rosa-gpu-smoke: build a
# dockerconfigjson pull secret from interactively-entered credentials and
# create it in the cluster. Never accepts a credential as a CLI argument
# (would leak via shell history / `ps`) and never reads
# ~/.docker/config.json automatically (would silently harvest whatever
# credential happens to be cached there).
#
# Usage: create-pull-secret.sh <secret-name> <namespace> <registry-host-group> [<registry-host-group> ...]
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
# Assumes the caller has already selected the right cluster context
# (`oc config use-context ...` or an already-current context) — this
# script does not take a --context flag, to avoid a second place that
# has to be kept in sync with however the surrounding doc names its
# context variable.
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "Usage: $0 <secret-name> <namespace> <registry-host-group> [<registry-host-group> ...]" >&2
  exit 2
fi

SECRET_NAME="$1"
NAMESPACE="$2"
shift 2

SECRET_FILE=$(umask 077 && mktemp)
trap 'rm -f "$SECRET_FILE"' EXIT

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
  AUTH=$(printf '%s' "${REG_USER}:${REG_PASS}" | base64 | tr -d '\n')
  IFS=',' read -ra HOST_KEYS <<< "$GROUP"
  for HOST in "${HOST_KEYS[@]}"; do
    AUTHS_JSON=$(printf '%s' "$AUTHS_JSON" | jq --arg host "$HOST" --arg auth "$AUTH" \
      '.[$host] = {"auth": $auth}')
  done
  ANY_HOST_CONFIGURED=true
  unset REG_USER REG_PASS AUTH
done

if [ "$ANY_HOST_CONFIGURED" != true ]; then
  echo "ERROR: no registry host was configured (every username was left blank)" >&2
  exit 1
fi

printf '%s' "$AUTHS_JSON" | jq '{"auths": .}' > "$SECRET_FILE"

oc create secret generic "$SECRET_NAME" -n "$NAMESPACE" \
  --from-file=.dockerconfigjson="$SECRET_FILE" \
  --type=kubernetes.io/dockerconfigjson \
  --dry-run=client -o yaml | oc apply -f -

rm -f "$SECRET_FILE"
echo "Created/updated secret ${SECRET_NAME} in namespace ${NAMESPACE}" >&2
