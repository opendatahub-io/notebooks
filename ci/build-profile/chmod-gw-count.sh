#!/usr/bin/env bash
# chmod -R g+w with counters for overlap analysis vs fix-permissions.
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <path>" >&2
  exit 2
fi

target="$1"
if [[ ! -e "${target}" ]]; then
  echo "BUILD_PROFILE_CHMOD_GW missing_path=${target}" >&2
  exit 1
fi

total=0
already_gw=0
changed=0

while IFS= read -r -d '' path; do
  total=$((total + 1))
  if [[ -L "${path}" ]]; then
    continue
  fi
  if [[ -d "${path}" ]]; then
    if [[ -perm /g+w ]]; then
      already_gw=$((already_gw + 1))
    else
      chmod g+w "${path}"
      changed=$((changed + 1))
    fi
  elif [[ -f "${path}" ]]; then
    if [[ -perm /g+w ]]; then
      already_gw=$((already_gw + 1))
    else
      chmod g+w "${path}"
      changed=$((changed + 1))
    fi
  fi
done < <(find -L "${target}" -print0)

echo "BUILD_PROFILE_CHMOD_GW path=${target} total=${total} already_gw=${already_gw} changed=${changed}"
echo "::notice title=build-profile::chmod-gw path=${target} total=${total} already_gw=${already_gw} changed=${changed}"
