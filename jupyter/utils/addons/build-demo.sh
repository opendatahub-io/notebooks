#!/bin/bash
# Generate dist/index.html demo page from partial HTML files (local preview only).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
OUTPUT="$DIST_DIR/index.html"

HEAD_FILE="$SCRIPT_DIR/partial-head.html"
BODY_FILE="$SCRIPT_DIR/partial-body.html"

if [[ ! -f "$HEAD_FILE" ]] || [[ ! -f "$BODY_FILE" ]]; then
  echo "ERROR: partial-head.html or partial-body.html not found"
  exit 1
fi

mkdir -p "$DIST_DIR"

# Substitute JupyterLab template var for local file:// preview
HEAD_CONTENT=$(sed 's|{{page_config.fullStaticUrl}}|.|g' "$HEAD_FILE")
BODY_CONTENT=$(cat "$BODY_FILE")

cat > "$OUTPUT" <<EOF
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8"/>
    <title>Example spinner page</title>
${HEAD_CONTENT}
</head>
<body>
<p>Check the following</p>
<ol>
    <li>the spinner is shown</li>
    <li>the spinner is not too thin at the beginning of animation (missing CSS manifested this way)</li>
    <li>if you scroll down as much as possible, the spinner is centered vertically and horizontally</li>
    <li>the spinner is not shown after the button is clicked</li>
</ol>
<button>Finish loading</button>
<script>
    function htmlToNode(html) {
        const template = document.createElement('template');
        template.innerHTML = html;
        return template.content.firstChild;
    }
    document.querySelector('button').addEventListener('click', function () {
        document.querySelector('button').replaceWith(
            htmlToNode(\`<div class="lm-Widget jp-LabShell" id="main">Jupyter is here.</div>\`)
        );
    });
</script>
${BODY_CONTENT}
</body>
</html>
EOF

echo "Wrote $OUTPUT"
