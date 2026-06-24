#!/bin/bash
# Local demo: copy a JupyterLab-like index template, then run apply.sh (same as Dockerfile).
set -Eeuxo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
TEMPLATE="$SCRIPT_DIR/demo/lab-index.template.html"
OUTPUT="$DIST_DIR/index.html"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "ERROR: demo template not found: $TEMPLATE"
  exit 1
fi

mkdir -p "$DIST_DIR"
cp "$TEMPLATE" "$OUTPUT"

export JUPYTER_ADDONS_STATIC_DIR="$DIST_DIR"
export JUPYTER_ADDONS_INDEX_FILE="$OUTPUT"
export JUPYTER_ADDONS_CSS_DIR="$DIST_DIR"
export JUPYTER_ADDONS_STATIC_URL="."

"$SCRIPT_DIR/apply.sh"
