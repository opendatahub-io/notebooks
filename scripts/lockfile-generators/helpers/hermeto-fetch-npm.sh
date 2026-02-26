#!/usr/bin/env bash
set -euo pipefail

# hermeto-fetch-npm.sh — Fetch npm packages using the Hermeto tool (container).
#
# Alternative to download-npm.sh for fetching npm packages for offline/cachi2
# builds.  The difference is the approach:
#   • download-npm.sh   — parses package-lock.json with jq, downloads with wget.
#   • hermeto-fetch-npm — runs the Hermeto Project tool
#     (https://github.com/hermetoproject/hermeto) in a container.  Hermeto
#     fetches dependencies per source directory (package.json/package-lock.json)
#     and writes them to a deps directory; this script then rsyncs all results
#     into a single output directory.
#
# Edit the `sources` array below to choose which directories to fetch.
# Requires podman and network access.

# Run hermeto in a container; requires podman and network access.
hermeto() {
  TTY_FLAG=""
  [ -t 0 ] && TTY_FLAG="-t"
  podman run --rm -i $TTY_FLAG \
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