#!/usr/bin/env bash
set -euo pipefail

# hermeto-fetch-npm: Fetch npm dependencies for offline/Cachi2 use (same goal as download-npm).
#
# This script does the same thing as download-npm — it fetches npm packages so they can be used
# offline or by Cachi2-based builds — but the difference is how it works: hermeto-fetch-npm uses
# the Hermeto Project (https://github.com/hermetoproject/hermeto) tool in a container. Hermeto
# fetches dependencies per source directory (package.json/package-lock.json) and writes them to
# a deps directory; we then rsync into a single output dir. download-npm instead reads a single
# package-lock.json, extracts resolved URLs with jq, and downloads with wget.

# Run hermeto in a container; requires podman and network access.
hermeto() {
  podman run --rm -ti \
    -v "$PWD:$PWD:z" \
    -w "$PWD" \
    ghcr.io/hermetoproject/hermeto:latest \
    "$@"
}

# npm source directories to fetch (edit to enable/disable).
# Note: hermeto may fail with "UnsupportedFeature: no 'origin' remote" for some repos.
declare -a sources=(
    codeserver/ubi9-python-3.12/prefetch-input/code-server/test
    codeserver/ubi9-python-3.12/prefetch-input/code-server/lib/vscode/extensions/microsoft-authentication
)
output_dir="./cachi2/output/deps/npm-test"
mkdir -p "$output_dir"

# Fetch each source independently, then merge them all into one output directory using rsync.
for i in "${!sources[@]}"; do
    index=$((i + 1))
    echo "${i}: Fetching npm dependencies for ${sources[$i]}"
    hermeto fetch-deps npm \
        --source "${sources[$i]}" \
        --output "./cachi2/tmp/npm-$index" \
        --dev-package-managers
    rsync -a "./cachi2/tmp/npm-$index/deps/npm/" "$output_dir/"
done

echo "Successfully fetched npm packages into $output_dir"