#!/bin/bash
# Local demo: copy a JupyterLab-like index template, then inject partials via apply.sh.
set -Eeuo pipefail

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

export JUPYTER_ADDONS_INDEX_FILE="$OUTPUT"
"$SCRIPT_DIR/apply.sh"

# file:// preview has no JupyterLab runtime to resolve {{page_config.fullStaticUrl}}
perl -pi -e 's|\{\{page_config.fullStaticUrl\}\}|.|g' "$OUTPUT"

echo "Wrote $OUTPUT"
