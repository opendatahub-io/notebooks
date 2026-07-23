#!/usr/bin/env bash
set -Eeuxo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PR_BASE=""
PR_CHANGED_FILES=""

usage() {
  cat <<'EOF'
Usage: ci/generate_code.sh [--pr-base REF] [--pr-changed-files FILE]

  --pr-base REF            PR only: merge-base ref for lock scoping. Locally:
                           git merge-base <base> HEAD. Omit on push for full regen.
  --pr-changed-files FILE  PR only: changed paths (one per line). CI passes GitHub
                           compare API files[].filename so git diff is not needed.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr-base)
      [[ $# -ge 2 ]] || { echo "error: --pr-base requires a value" >&2; exit 1; }
      PR_BASE="$2"
      shift 2
      ;;
    --pr-changed-files)
      [[ $# -ge 2 ]] || { echo "error: --pr-changed-files requires a value" >&2; exit 1; }
      PR_CHANGED_FILES="$2"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

cd "${REPO_ROOT}"
uv --version || pip install 'uv>=0.10,<0.12'

uv run scripts/dockerfile_fragments.py
uv run manifests/tools/generate_kustomization.py

if [[ -n "${PR_BASE}" ]]; then
  pylocks_args=(auto --pr-base "${PR_BASE}")
  if [[ -n "${PR_CHANGED_FILES}" ]]; then
    pylocks_args+=(--pr-changed-files-file "${PR_CHANGED_FILES}")
  fi
  PYLOCKS_CI_CHECK=1 uv run scripts/pylocks_generator.py "${pylocks_args[@]}"
else
  PYLOCKS_CI_CHECK=1 uv run scripts/pylocks_generator.py
fi
