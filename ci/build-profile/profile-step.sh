#!/usr/bin/env bash
# Emit build-step timings for GHA log parsing (BUILD_PROFILE_STEP <name> <seconds>).
set -Eeuo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <step-name> <command...>" >&2
  exit 2
fi

step="$1"
shift
start=$(date +%s)
"$@"
status=$?
end=$(date +%s)
elapsed=$((end - start))
echo "BUILD_PROFILE_STEP ${step} ${elapsed}"
echo "::notice title=build-profile::${step} elapsed=${elapsed}s"
exit "${status}"
