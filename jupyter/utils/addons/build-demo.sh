#!/bin/bash
# Local demo: copy a JupyterLab-like index template, then inject partials the same way as apply.sh.
set -Eeuxo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
TEMPLATE="$SCRIPT_DIR/demo/lab-index.template.html"
OUTPUT="$DIST_DIR/index.html"
HEAD_FILE="$SCRIPT_DIR/partial-head.html"
BODY_FILE="$SCRIPT_DIR/partial-body.html"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "ERROR: demo template not found: $TEMPLATE"
  exit 1
fi

if [[ ! -f "$HEAD_FILE" ]] || [[ ! -f "$BODY_FILE" ]]; then
  echo "ERROR: partial-head.html or partial-body.html not found"
  exit 1
fi

mkdir -p "$DIST_DIR"
cp "$TEMPLATE" "$OUTPUT"

# Mirror apply.sh injection; substitute static URL for file:// preview (JupyterLab resolves this at runtime).
head_raw=$(tr -d '\n' <"$HEAD_FILE" | sed 's|{{page_config.fullStaticUrl}}|.|g')
head_content=$(printf '%s' "$head_raw" | sed 's/@/\\@/g')
body_content=$(tr -d '\n' <"$BODY_FILE" | sed 's/@/\\@/g')

perl -i -0pe "s|</head>|$head_content\n</head>|" "$OUTPUT"
perl -i -0pe "s|</body>|$body_content\n</body>|" "$OUTPUT"

echo "Wrote $OUTPUT"
