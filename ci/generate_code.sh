#!/usr/bin/env bash
set -Eeuxo pipefail

uv --version || pip install "uv==0.9.6"

uv run scripts/dockerfile_fragments.py
bash scripts/pylocks_generator.sh
