#!/usr/bin/env bash
set -Eeuxo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

uv --version || pip install "uv==0.8.12"

"${REPO_ROOT}/uv" run scripts/dockerfile_fragments.py
if [[ -d "${REPO_ROOT}/manifests/odh/base" ]]; then
  "${REPO_ROOT}/uv" run manifests/tools/generate_kustomization.py
else
  "${REPO_ROOT}/uv" run manifests/tools/generate_kustomization.py --target base
fi
bash scripts/pylocks_generator.sh
