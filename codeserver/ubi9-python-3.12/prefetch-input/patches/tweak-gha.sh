#!/usr/bin/env bash
set -Eeuo pipefail

# tweak-gha.sh — Reduce VS Code build parallelism for GitHub Actions runners.
#
# GitHub Actions runners (ubuntu-26.04) have only 16GB RAM. The VS Code build
# spawns multiple worker processes that each load the full TypeScript project
# via ts.createLanguageService (~2-3GB per worker). With upstream defaults
# (4 mangler workers + cpus/2 transpiler workers + 16GB Node heap), total
# memory exceeds what the runner provides.
#
# Called by apply-patch.sh when GHA_BUILD=true. Expects CWD to be the
# code-server source root (CODESERVER_SOURCE_PREFETCH).
#
# Build output is byte-for-byte identical to upstream; only parallelism changes.
# See: https://github.com/microsoft/vscode/issues/243708 (upstream OOM reports)

echo "tweak-gha.sh: reducing VS Code build parallelism for 16GB GitHub runner"

# lib/vscode/.npmrc sets build_from_source=true (upstream dev default). That makes
# @parcel/watcher's install script spawn node-gyp during lib/vscode npm ci. Konflux
# builders have enough RAM; GHA runners OOM here (npm exit 244). Hermetic builds
# prefetch @parcel/watcher-linux-* optional deps, so prebuilds are used when this is false.
for npmrc in lib/vscode/.npmrc lib/vscode/remote/.npmrc lib/vscode/build/.npmrc; do
	if [[ -f "${npmrc}" ]]; then
		sed -i 's/build_from_source="true"/build_from_source="false"/' "${npmrc}"
	fi
done

# Node heap: 16GB -> 8GB (runner only has 16GB total, OS needs some)
if grep -q 'NODE_HEAP_MB=16384' ci/build/build-vscode.sh 2>/dev/null; then
	sed -i 's/NODE_HEAP_MB=16384/NODE_HEAP_MB=8192/' ci/build/build-vscode.sh
else
	sed -i 's/max-old-space-size=16384/max-old-space-size=8192/' ci/build/build-vscode.sh
fi

# Mangler rename workers: 4 -> 2 (each spawns a separate process that loads
# the entire VS Code TS project into memory, ~500-700MB each)
# VS Code 1.112+: mangle sources are TypeScript (index.ts), not index.js.
sed -i 's/maxWorkers: 4/maxWorkers: 2/' \
    lib/vscode/build/lib/mangle/index.ts
sed -i "s/minWorkers: 'max'/minWorkers: 2/" \
    lib/vscode/build/lib/mangle/index.ts

# Transpiler workers: cap at 2 (default is cpus/2 which can be too many)
# VS Code 1.112+: transpiler sources are TypeScript (transpiler.ts).
sed -i 's/Math\.floor(cpus()\.length \* \.5)/Math.min(2, Math.floor(cpus().length * .5))/' \
    lib/vscode/build/lib/tsb/transpiler.ts

echo "tweak-gha.sh: done"
