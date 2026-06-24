#!/bin/bash

# See https://github.com/jupyterlab/jupyterlab/issues/5463
# This is a hack to apply partial HTML code to JupyterLab's `index.html` file

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

static_dir="${JUPYTER_ADDONS_STATIC_DIR:-/opt/app-root/share/jupyter/lab/static}"
index_file="${JUPYTER_ADDONS_INDEX_FILE:-$static_dir/index.html}"
css_dest_dir="${JUPYTER_ADDONS_CSS_DIR:-$static_dir}"

head_file="$script_dir/partial-head.html"
body_file="$script_dir/partial-body.html"
css_file="$script_dir/dist/pf.css"
css_dest="$css_dest_dir/pf.css"

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
  cd "$script_dir" && webpack --mode production
  if [ ! -f "$css_file" ]; then
    echo "Failed to build CSS file"
    exit 1
  fi
fi

# Copy the tree-shaken CSS file to the static directory
cp "$css_file" "$css_dest"

head_raw=$(tr -d '\n' <"$head_file")
if [ -n "${JUPYTER_ADDONS_STATIC_URL:-}" ]; then
  head_raw=$(printf '%s' "$head_raw" | sed "s|{{page_config.fullStaticUrl}}|${JUPYTER_ADDONS_STATIC_URL}|g")
fi
head_content=$(printf '%s' "$head_raw" | sed 's/@/\\@/g')
body_content=$(tr -d '\n' <"$body_file" | sed 's/@/\\@/g')

perl -i -0pe "s|</head>|$head_content\n</head>|" "$index_file"
perl -i -0pe "s|</body>|$body_content\n</body>|" "$index_file"

echo "Content from partial HTML files successfully injected into '$index_file'"
