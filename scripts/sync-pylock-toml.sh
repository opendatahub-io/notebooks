#!/usr/bin/env bash
set -Eeuxo pipefail

# The following will create a pylock.toml file for every jupyter/ requirements.txt we have.
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
  image_name="${image_name/+/-}"

  if [[ "$path" == *"rocm/"* ]]; then
    image_name="${image_name#*/}-rocm"
  fi

  # NOTE: --format requirements.txt is useless because of https://github.com/astral-sh/uv/issues/15534
  # uv pip compile --format requirements.txt --python ${python_version} -o jupyter/${path} --generate-hashes --emit-index-url --group jupyter-${image_name}-image --python-platform linux --no-annotate -q
  uv pip compile --format pylock.toml --python "${python_version}" -o "jupyter/${path%requirements.txt}pylock.toml" --generate-hashes --emit-index-url --group "jupyter-${image_name}-image" --python-platform "linux" --no-annotate -q

done < jupyter/files.txt

rm jupyter/files.txt
