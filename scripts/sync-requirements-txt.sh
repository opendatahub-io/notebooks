#!/usr/bin/env bash
set -Eeuxo pipefail

# Our build tooling depends on requirements.txt files with hashes
# Namely, Konflux (https://konflux-ci.dev/), and Cachi2 (https://github.com/containerbuildsystem/cachi2).

# The following will create an extra requirement.txt file for every Pipfile.lock we have.
uv --version || pip install uv
cd jupyter
find . -name "requirements.txt" -type f > files.txt
cd ..
while read -r file; do

  echo "Processing $file"
  path="${file#./*}"
  image_name="${path%/*/*}"
  python_version="${path%/*}"
  python_version="${python_version##*-}"

  if [[ "$path" == *"rocm/"* ]]; then
    image_name="${image_name#*/}-rocm"
  fi
  
  uv pip compile --format requirements.txt --python ${python_version} -o jupyter/${path} --generate-hashes --group jupyter-${image_name}-image --python-platform linux --no-annotate -q

done < jupyter/files.txt

rm jupyter/files.txt
