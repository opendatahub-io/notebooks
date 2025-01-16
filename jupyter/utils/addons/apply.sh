#!/bin/bash

# See https://github.com/jupyterlab/jupyterlab/issues/5463
# This is a hack to apply partial HTML code to JupyterLab's `index.html` file
# Look for the other duplicates in case a change is needed to this file

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pf_url="https://unpkg.com/@patternfly/patternfly@6.0.0/patternfly.min.css"

static_dir="/opt/app-root/share/jupyter/lab/static"
index_file="$static_dir/index.html"

head_file="$script_dir/partial-head.html"
body_file="$script_dir/partial-body.html"

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

curl -o "$static_dir/pf.css" "$pf_url"

head_content=$(tr -d '\n' <"$head_file" | sed 's/@/\\@/g')
body_content=$(tr -d '\n' <"$body_file" | sed 's/@/\\@/g')

perl -i -0pe "s|</head>|$head_content\n</head>|" "$index_file"
perl -i -0pe "s|</body>|$body_content\n</body>|" "$index_file"

echo "Content from partial HTML files successfully injected into JupyterLab's 'index.html' file"
