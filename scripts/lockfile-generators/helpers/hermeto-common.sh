#!/usr/bin/env bash
declare -rx HERMETO_IMAGE="ghcr.io/hermetoproject/hermeto:0.51.0@sha256:8dc7d791fb7d874d208e145934e812e51736eea495fd2f11ad3a3acd5e831eff"
declare -rx HERMETO_OUTPUT="./cachi2/output"
# Ownership alternatives: --userns=keep-id, :U volume mounts, or idmap mounts.

repair_foreign_ownership() {
  local path=$1

  if find "$path" \
    \( ! -uid "$(id -u)" -o ! -gid "$(id -g)" \) \
    -print -quit | grep -q .; then
    sudo chown -R "$(id -u):$(id -g)" "$path"
  fi
}

cleanup_staging() {
  local status=$?
  local staging=$1
  local cert_dir=${2:-}
  trap - EXIT

  if ! repair_foreign_ownership "$staging"; then
    echo "Error: cannot repair Hermeto staging ownership: $staging" >&2
    if (( status == 0 )); then status=1; fi
  fi

  if ! rm -rf -- "$staging"; then
    echo "Error: cannot clean up Hermeto staging: $staging" >&2
    if (( status == 0 )); then status=1; fi
  fi

  if [[ -n $cert_dir ]] && ! rm -rf -- "$cert_dir"; then
    echo "Error: cannot clean up CDN certificate staging: $cert_dir" >&2
    if (( status == 0 )); then status=1; fi
  fi

  exit "$status"
}
