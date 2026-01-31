#!/usr/bin/env bash
set -euo pipefail

# Once we have an NPM package, use this script to copy it to a separate
# directory (./release-standalone) and install the dependencies.  This new
# directory can then be packaged as a platform-specific release.

main() {
  cd "$(dirname "${0}")/../.."

  source ./ci/lib.sh

  rsync "$RELEASE_PATH/" "$RELEASE_PATH-standalone"
  RELEASE_PATH+=-standalone

  # Package managers may shim their own "node" wrapper into the PATH, so run
  # node and ask it for its true path.
  local node_path
  node_path="$(node -p process.execPath)"

  mkdir -p "$RELEASE_PATH/bin"
  mkdir -p "$RELEASE_PATH/lib"
  rsync ./ci/build/code-server.sh "$RELEASE_PATH/bin/code-server"
  rsync "$node_path" "$RELEASE_PATH/lib/node"

  chmod 755 "$RELEASE_PATH/lib/node"

  # Rewrite shrinkwrap resolved URLs to file:///cachi2 for offline install
  # (in case paths were relative or not rewritten earlier).
  if [ -f /root/scripts/lockfile-generators/rewrite-cachi2-path.sh ]; then
    . /root/scripts/lockfile-generators/rewrite-cachi2-path.sh
    rewrite_cachi2_path "$RELEASE_PATH/npm-shrinkwrap.json"
    rewrite_cachi2_path "$RELEASE_PATH/lib/vscode/npm-shrinkwrap.json"
    rewrite_cachi2_path "$RELEASE_PATH/lib/vscode/extensions/npm-shrinkwrap.json"
  fi

  pushd "$RELEASE_PATH"
  npm install --unsafe-perm --omit=dev
  # Code deletes some files from the extension node_modules directory which
  # leaves broken symlinks in the corresponding .bin directory.  nfpm will fail
  # on these broken symlinks so clean them up.
  rm -fr "./lib/vscode/extensions/node_modules/.bin"
  popd
}

main "$@"
