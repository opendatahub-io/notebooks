#!/usr/bin/env bash
set -Eeuxo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

uv --version || pip install "uv==0.10.6"

"${REPO_ROOT}/uv" run scripts/dockerfile_fragments.py
"${REPO_ROOT}/uv" run manifests/tools/generate_kustomization.py
"${REPO_ROOT}/uv" run scripts/pylocks_generator.py
