#!/usr/bin/env bash
set -Eeuox pipefail

python3 ci/cached-builds/gen_gha_matrix_jobs.py
