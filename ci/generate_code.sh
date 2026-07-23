#!/usr/bin/env bash
set -Eeuxo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PR_BASE=""
PR_TO_REF="HEAD"

usage() {
  cat <<'EOF'
Usage: ci/generate_code.sh [--pr-base REF] [--pr-to-ref REF]

  --pr-base REF    PR only: base ref for lock scoping (three-dot diff base...head).
                   CI passes origin/<base-branch>; locally: origin/main.
  --pr-to-ref REF  PR only: head ref for lock scoping. CI passes the fetched PR branch;
                   default HEAD for local runs.
                   Omit --pr-base on push for full regen.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr-base)
      [[ $# -ge 2 ]] || { echo "error: --pr-base requires a value" >&2; exit 1; }
      PR_BASE="$2"
      shift 2
      ;;
    --pr-to-ref)
      [[ $# -ge 2 ]] || { echo "error: --pr-to-ref requires a value" >&2; exit 1; }
      PR_TO_REF="$2"
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
  PYLOCKS_CI_CHECK=1 uv run scripts/pylocks_generator.py auto --pr-base "${PR_BASE}" --pr-to-ref "${PR_TO_REF}"
else
  PYLOCKS_CI_CHECK=1 uv run scripts/pylocks_generator.py
fi
