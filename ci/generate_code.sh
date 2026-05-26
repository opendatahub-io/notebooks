#!/usr/bin/env bash
set -Eeuxo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"
uv --version || pip install 'uv>=0.10,<0.12'

uv run scripts/dockerfile_fragments.py
uv run manifests/tools/generate_kustomization.py
PYLOCKS_CI_CHECK=1 uv run scripts/pylocks_generator.py
