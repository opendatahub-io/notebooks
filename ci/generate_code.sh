#!/usr/bin/env bash
set -Eeuxo pipefail

python3 ci/cached-builds/gen_gha_matrix_jobs.py
bash scripts/sync-requirements-txt.sh
