#!/usr/bin/env bash
set -Eeuo pipefail

# tweak-gha.sh — Reduce VS Code build parallelism for GitHub Actions runners.
#
# GitHub Actions runners (ubuntu-24.04) have only 16GB RAM. The VS Code build
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

# Node heap: 16GB -> 8GB (runner only has 16GB total, OS needs some)
sed -i 's/max-old-space-size=16384/max-old-space-size=8192/' \
    ci/build/build-vscode.sh

# Mangler rename workers: 4 -> 2 (each spawns a separate process that loads
# the entire VS Code TS project into memory, ~500-700MB each)
sed -i 's/maxWorkers: 4/maxWorkers: 2/' \
    lib/vscode/build/lib/mangle/index.js
sed -i "s/minWorkers: 'max'/minWorkers: 2/" \
    lib/vscode/build/lib/mangle/index.js

# Transpiler workers: cap at 2 (default is cpus/2 which can be too many)
sed -i 's/Math\.floor((0, node_os_1\.cpus)()\.length \* \.5)/Math.min(2, Math.floor((0, node_os_1.cpus)().length * .5))/' \
    lib/vscode/build/lib/tsb/transpiler.js

echo "tweak-gha.sh: done"
