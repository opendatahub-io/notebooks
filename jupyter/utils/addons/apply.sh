#!/bin/bash
set -Eeuo pipefail

# See https://github.com/jupyterlab/jupyterlab/issues/5463
# This is a hack to apply partial HTML code to JupyterLab's `index.html` file

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

index_file="${JUPYTER_ADDONS_INDEX_FILE:-/opt/app-root/share/jupyter/lab/static/index.html}"
static_dir="$(dirname "$index_file")"

head_file="$script_dir/partial-head.html"
body_file="$script_dir/partial-body.html"
css_file="$script_dir/dist/pf.css"

if [ ! -f "$index_file" ]; then
  echo "File '$index_file' not found"
  exit 1
fi

if [ ! -f "$head_file" ]; then
  echo "File '$head_file' not found"
  exit 1
fi

if [ ! -f "$body_file" ]; then
  echo "File '$body_file' not found"
  exit 1
fi

if [ ! -f "$css_file" ]; then
  echo "Tree-shaken CSS file not found. Building it now..."
  cd "$script_dir" && pnpm run build:css
  if [ ! -f "$css_file" ]; then
    echo "Failed to build CSS file"
    exit 1
  fi
fi

# Install tree-shaken CSS with group-writable mode for OpenShift arbitrary UID (gid 0)
css_dest="$static_dir/pf.css"
if [ "$css_file" != "$css_dest" ]; then
  install -m 0664 "$css_file" "$css_dest"
fi

head_content=$(tr -d '\n' <"$head_file" | sed 's/@/\\@/g')
body_content=$(tr -d '\n' <"$body_file" | sed 's/@/\\@/g')

perl -i -0pe "s|</head>|$head_content\n</head>|" "$index_file"
perl -i -0pe "s|</body>|$body_content\n</body>|" "$index_file"

echo "Content from partial HTML files successfully injected into JupyterLab's 'index.html' file"
