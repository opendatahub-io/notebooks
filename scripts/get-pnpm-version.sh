#!/usr/bin/env bash
# Extract the resolved pnpm version from a pnpm-lock.yaml lockfile.
# pnpm 11 stores the resolved version in the first YAML document under
# packageManagerDependencies (requires devEngines.packageManager in package.json).
#
# Usage: scripts/get-pnpm-version.sh [path/to/pnpm-lock.yaml]
# Default: tests/browser/pnpm-lock.yaml
set -euo pipefail

lockfile="${1:-tests/browser/pnpm-lock.yaml}"
ver=$(yq 'select(documentIndex == 0) | .importers.["."].packageManagerDependencies.pnpm.version' "$lockfile")

if ! [[ "${ver}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "::error::Failed to extract valid pnpm version from ${lockfile} (got '${ver}')" >&2
  exit 1
fi

echo "$ver"
