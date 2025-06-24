#!/bin/bash

set -euo pipefail

# Ensure at least one argument (file path) is provided
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <file_path> [version]" >&2
  exit 1
fi

file_path=$1
version=$2

while IFS= read -r line; do
    if [[ "$line" == *"ref: rhoai-"* ]]; then
    if [[ -z "$version" ]]; then
        # Auto-increment logic
        numstr=${line#*2.}
        num=$(expr "$numstr" + 1)
        echo "      ref: rhoai-2.$num" >> tmp.yaml
    else
        # Use provided version
        echo "      ref: rhoai-$version" >> tmp.yaml
    fi
    else
    echo "$line" >> tmp.yaml
    fi
done < "$file_path"

cat tmp.yaml > "$file_path"
rm tmp.yaml