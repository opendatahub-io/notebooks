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

total=$(find -L "${target}" | wc -l | tr -d ' ')
already_gw=$(find -L "${target}" -perm -g+w | wc -l | tr -d ' ')
need_gw=$(find -L "${target}" ! -perm -g+w | wc -l | tr -d ' ')

find -L "${target}" ! -perm -g+w -exec chmod g+w {} +

echo "BUILD_PROFILE_CHMOD_GW path=${target} total=${total} already_gw=${already_gw} changed=${need_gw}"
echo "::notice title=build-profile::chmod-gw path=${target} total=${total} already_gw=${already_gw} changed=${need_gw}"
