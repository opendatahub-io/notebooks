#!/usr/bin/env bash
set -Eeuxo pipefail

bash scripts/sync-requirements-txt.sh
PYTHONPATH=. python3 ci/cached-builds/konflux_generate_component_build_pipelines.py
