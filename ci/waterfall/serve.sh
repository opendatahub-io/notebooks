#!/usr/bin/env bash
# Authenticate to Konflux clusters (if needed), refresh data.json, serve the dashboard.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT="${PORT:-8888}"

find_context() {
  local grep_pattern="$1"
  oc config get-contexts -o name 2>/dev/null | grep "$grep_pattern" | head -n1 || true
}

context_authed() {
  local ctx="$1"
  [[ -n "$ctx" ]] && oc whoami --context="$ctx" >/dev/null 2>&1
}

ensure_cluster_login() {
  local grep_pattern="$1"
  local api_url="$2"
  local label="$3"
  local ctx

  ctx="$(find_context "$grep_pattern")"
  if context_authed "$ctx"; then
    echo "ok: ${label} already authenticated (${ctx})"
    return 0
  fi

  echo "logging in to ${label} (${api_url})..."
  oc login --web "$api_url"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: required command not found: $1" >&2
    exit 1
  fi
}

main() {
  require_cmd oc
  require_cmd python3
  require_cmd kubectl

  if ! kubectl ka get pipelineruns --help >/dev/null 2>&1; then
    echo "error: kubectl-ka plugin required (kubectl ka)" >&2
    exit 1
  fi

  ensure_cluster_login \
    stone-prd-rh01 \
    https://api.stone-prd-rh01.pg1f.p1.openshiftapps.com:6443 \
    "ODH (stone-prd-rh01)"
  ensure_cluster_login \
    stone-prod-p02 \
    https://api.stone-prod-p02.hjvn.p1.openshiftapps.com:6443 \
    "RHDS (stone-prod-p02)"

  python3 collect.py

  echo
  echo "Serving waterfall at http://localhost:${PORT}/"
  echo "  matrix:    http://localhost:${PORT}/"
  echo "  timeline:  http://localhost:${PORT}/waterfall.html"
  exec python3 -m http.server --bind 127.0.0.1 "$PORT"
}

main "$@"
