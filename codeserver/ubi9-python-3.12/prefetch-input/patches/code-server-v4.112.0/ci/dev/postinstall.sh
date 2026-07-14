#!/usr/bin/env bash
set -euo pipefail

# Hermetic GHA builds prefetch @parcel/watcher-linux-* optional deps. lib/vscode
# .npmrc still forces node-gyp via lifecycle scripts on 16GB runners (npm exit 244).
# Skip lifecycle scripts for heavy trees and run the few patched scripts we need.
run_gha_vscode_install_scripts() {
  local ripgrep_js="node_modules/@vscode/ripgrep/lib/postinstall.js"
  if [[ -f "${ripgrep_js}" ]]; then
    echo "Running @vscode/ripgrep postinstall (GHA ignore-scripts follow-up)"
    node "${ripgrep_js}"
  fi
  # lib/vscode postinstall normally runs npm ci in build/, remote/, extensions/, etc.
  # Outer --ignore-scripts skips that; re-run it with scripts disabled for nested trees.
  if [[ -f build/npm/postinstall.ts ]]; then
    echo "Running VS Code build/npm/postinstall.ts (nested npm ci, ignore-scripts)"
    VSCODE_FORCE_INSTALL=1 \
      npm_config_ignore_scripts=true \
      npm_command=ci \
      node build/npm/postinstall.ts
  fi
  # Outer --ignore-scripts skips native addon builds; rebuild runtime modules only.
  echo "Rebuilding GHA runtime native modules (@vscode/spdlog, node-pty)"
  npm rebuild @vscode/spdlog
  if [[ -d remote/node_modules/node-pty ]]; then
    npm rebuild --prefix remote node-pty
  fi
}

# Install dependencies in $1.
install-deps() {
  local dir="$1"
  local args=()
  local gha_ignore_scripts=false
  if [[ ${CI-} ]]; then
    args+=(ci)
    if [[ "${GHA_BUILD:-false}" == "true" ]]; then
      args+=(--foreground-scripts)
      if [[ "${dir}" == "custom-packages" || "${dir}" == "lib/vscode" ]]; then
        gha_ignore_scripts=true
        args+=(--ignore-scripts)
      fi
    fi
  else
    args+=(install)
  fi
  # If there is no package.json then npm will look upward and end up installing
  # from the root resulting in an infinite loop (this can happen if you have not
  # checked out the submodule yet for example).
  if [[ ! -f "${dir}/package.json" ]]; then
    echo "${dir}/package.json is missing; did you run git submodule update --init?"
    exit 1
  fi
  pushd "${dir}"
  echo "Installing dependencies for $PWD"
  npm "${args[@]}"
  if [[ "${gha_ignore_scripts}" == "true" && "${dir}" == "lib/vscode" ]]; then
    run_gha_vscode_install_scripts
  fi
  popd
}

main() {
  cd "$(dirname "$0")/../.."
  source ./ci/lib.sh

  # [ODH] Install custom-packages first (same install-deps as test). Uses version ranges
  # in package.json so npm ci uses the lockfile and populates the cache for lib/vscode.
  if [[ -f custom-packages/package.json ]]; then
    install-deps custom-packages
  fi
  install-deps test
  install-deps test/e2e/extensions/test-extension
  # We don't need these when running the integration tests
  # so you can pass SKIP_SUBMODULE_DEPS
  if [[ ! ${SKIP_SUBMODULE_DEPS-} ]]; then
    install-deps lib/vscode
  fi
}

main "$@"
