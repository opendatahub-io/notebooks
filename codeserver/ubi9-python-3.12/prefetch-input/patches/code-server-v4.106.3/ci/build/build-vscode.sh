#!/usr/bin/env bash
set -euo pipefail

# Builds vscode into lib/vscode/out-vscode.
# [ODH PATCH] Build for current architecture (like che-code) so we can use
# system Node (/usr/bin/node) instead of prefetched node tarballs.

# MINIFY controls whether a minified version of vscode is built.
MINIFY=${MINIFY-true}

delete-bin-script() {
  rm -f "${VSCODE_REH_DIR}/bin/$1"
}

copy-bin-script() {
  local script="$1"
  local dest="${VSCODE_REH_DIR}/bin/$script"
  cp "lib/vscode/resources/server/bin/$script" "$dest"
  sed -i.bak "s/@@VERSION@@/$(vscode_version)/g" "$dest"
  sed -i.bak "s/@@COMMIT@@/$BUILD_SOURCEVERSION/g" "$dest"
  sed -i.bak "s/@@APPNAME@@/code-server/g" "$dest"

  # Fix Node path on Darwin and Linux.
  # We do not want expansion here; this text should make it to the file as-is.
  # shellcheck disable=SC2016
  sed -i.bak 's/^ROOT=\(.*\)$/VSROOT=\1\nROOT="$(dirname "$(dirname "$VSROOT")")"/g' "$dest"
  sed -i.bak 's/ROOT\/out/VSROOT\/out/g' "$dest"
  # We do not want expansion here; this text should make it to the file as-is.
  # shellcheck disable=SC2016
  sed -i.bak 's/$ROOT\/node/${NODE_EXEC_PATH:-$ROOT\/lib\/node}/g' "$dest"

  # Fix Node path on Windows.
  sed -i.bak 's/^set ROOT_DIR=\(.*\)$/set ROOT_DIR=%~dp0..\\..\\..\\..\r\nset VSROOT_DIR=\1/g' "$dest"
  sed -i.bak 's/%ROOT_DIR%\\out/%VSROOT_DIR%\\out/g' "$dest"

  chmod +x "$dest"
  rm "$dest.bak"
}

main() {
  cd "$(dirname "${0}")/../.."

  source ./ci/lib.sh

  # Build for current arch (like che-code): use native gulp task and system Node.
  # setup-offline-binaries.sh adds ppc64/s390x to BUILD_TARGETS so the native task exists.
  export NODE_ARCH
  NODE_ARCH=$(node -p "process.arch")
  export VSCODE_REH_DIR="lib/vscode-reh-web-linux-${NODE_ARCH}"
  GULP_ARCH="${NODE_ARCH}"
  # VS Code uses 'armhf' not 'armv7l' for the task name
  case "${NODE_ARCH}" in
    armv7l) GULP_ARCH="armhf" ;;
  esac
  echo "Building VS Code for linux-${NODE_ARCH} (gulp task: linux-${GULP_ARCH})"

  # Set the commit Code will embed into the product.json.  We need to do this
  # since Code tries to get the commit from the `.git` directory which will fail
  # as it is a submodule.
  #
  # Also, we use code-server's commit rather than VS Code's otherwise it would
  # not update when only our patch files change, and that will cause caching
  # issues where the browser keeps using outdated code.
  export BUILD_SOURCEVERSION
  BUILD_SOURCEVERSION=$(git rev-parse HEAD)

  pushd lib/vscode

  if [[ ! ${VERSION-} ]]; then
    echo "VERSION not set. Please set before running this script:"
    echo "VERSION='0.0.0' npm run build:vscode"
    exit 1
  fi

  # Add the date, our name, links, enable telemetry (this just makes telemetry
  # available; telemetry can still be disabled by flag or setting), and
  # configure trusted extensions (since some, like github.copilot-chat, never
  # ask to be trusted and this is the only way to get auth working).
  #
  # This needs to be done before building as Code will read this file and embed
  # it into the client-side code.
  git checkout product.json             # Reset in case the script exited early.
  cp product.json product.original.json # Since jq has no inline edit.
  jq --slurp '.[0] * .[1]' product.original.json <(
    cat << EOF
  {
    "enableTelemetry": true,
    "quality": "stable",
    "codeServerVersion": "$VERSION",
    "nameShort": "code-server",
    "nameLong": "code-server",
    "applicationName": "code-server",
    "dataFolderName": ".code-server",
    "win32MutexName": "codeserver",
    "licenseUrl": "https://github.com/coder/code-server/blob/main/LICENSE",
    "win32DirName": "code-server",
    "win32NameVersion": "code-server",
    "win32AppUserModelId": "coder.code.server",
    "win32ShellNameShort": "c&ode-server",
    "darwinBundleIdentifier": "com.coder.code.server",
    "linuxIconName": "com.coder.code.server",
    "reportIssueUrl": "https://github.com/coder/code-server/issues/new",
    "documentationUrl": "https://go.microsoft.com/fwlink/?LinkID=533484#vscode",
    "keyboardShortcutsUrlMac": "https://go.microsoft.com/fwlink/?linkid=832143",
    "keyboardShortcutsUrlLinux": "https://go.microsoft.com/fwlink/?linkid=832144",
    "keyboardShortcutsUrlWin": "https://go.microsoft.com/fwlink/?linkid=832145",
    "introductoryVideosUrl": "https://go.microsoft.com/fwlink/?linkid=832146",
    "tipsAndTricksUrl": "https://go.microsoft.com/fwlink/?linkid=852118",
    "newsletterSignupUrl": "https://www.research.net/r/vsc-newsletter",
    "linkProtectionTrustedDomains": [
      "https://open-vsx.org"
    ],
    "trustedExtensionAuthAccess": [
      "vscode.git", "vscode.github",
      "github.vscode-pull-request-github",
      "github.copilot", "github.copilot-chat"
    ],
    "aiConfig": {
      "ariaKey": "code-server"
    }
  }
EOF
  ) > product.json

  # Build for current architecture so we can use system Node (see setup-offline-binaries.sh).
  node --max-old-space-size=16384 --optimize-for-size \
       ./node_modules/gulp/bin/gulp.js \
       "vscode-reh-web-linux-${GULP_ARCH}${MINIFY:+-min}"

  # If gulp uses a different arch name (e.g. armv7l -> armhf), move output to NODE_ARCH dir.
  if [[ "${GULP_ARCH}" != "${NODE_ARCH}" ]]; then
    rm -rf "../vscode-reh-web-linux-${NODE_ARCH}"
    mv "../vscode-reh-web-linux-${GULP_ARCH}" "../vscode-reh-web-linux-${NODE_ARCH}"
  fi

  # Reset so if you develop after building you will not be stuck with the wrong
  # commit (the dev client will use `oss-dev` but the dev server will still use
  # product.json which will have `stable-$commit`).
  git checkout product.json

  popd

  pushd "${VSCODE_REH_DIR}"
  # Make sure Code took the version we set in the environment variable.  Not
  # having a version will break display languages.
  if ! jq -e .commit product.json; then
    echo "'commit' is missing from product.json"
    exit 1
  fi
  popd

  # These provide a `code-server` command in the integrated terminal to open
  # files in the current instance.
  delete-bin-script remote-cli/code-server
  copy-bin-script remote-cli/code-darwin.sh
  copy-bin-script remote-cli/code-linux.sh
  copy-bin-script remote-cli/code.cmd

  # These provide a way for terminal applications to open browser windows.
  delete-bin-script helpers/browser.sh
  copy-bin-script helpers/browser-darwin.sh
  copy-bin-script helpers/browser-linux.sh
  copy-bin-script helpers/browser.cmd
}

main "$@"
