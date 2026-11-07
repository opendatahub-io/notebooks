#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 NAME COMMAND [ARGS...]" >&2
  exit 2
fi

name="$1"
shift

status_dir="${RUNNER_TEMP:-/tmp}/post-build-tests"
mkdir -p "${status_dir}"
status_file="${status_dir}/${name}.status"
rm -f "${status_file}"

trap 'printf "%s\n" "$?" >"${status_file}"' EXIT
"$@"
