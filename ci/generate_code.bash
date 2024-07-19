#!/usr/bin/env bash
set -Eeuo pipefail

if ! python3 ci/cached-builds/gen_gha_matrix_jobs.py; then
  # this returns nonzero when running outside of github; detect and print explanation
  if [[ ${GITHUB_ACTIONS:-} == true ]]; then exit 1
  else
    echo "Running outside of Github Actions, please ignore the undefined 'GITHUB_' variable error above."
    echo "Continuing"
  fi
fi
