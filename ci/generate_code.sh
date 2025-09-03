#!/usr/bin/env bash
set -Eeuxo pipefail

python3 scripts/dockerfile_fragments.py
bash scripts/sync-python-lockfiles.sh
