#!/usr/bin/env bash
set -euo pipefail

# Builds vscode into lib/vscode/out-vscode.
# [ODH PATCH] Build for current architecture (like che-code) so we can use
# system Node (/usr/bin/node) instead of prefetched node tarballs. Also keeps
# upstream's compile-copilot-extension-full-build step from code-server 4.122+.

# MINIFY controls whether a minified version of vscode is built.
MINIFY=${MINIFY-true}

# Match upstream code-server 4.122+: gulp already emits platform-correct
# remote-cli/code-server and helpers/browser.sh. fix-bin-script patches their
# Node paths. KEEP_MODULES=1 release then deletes only the *extra* platform
# copies (code-linux.sh etc.); it must NOT delete the primary scripts.
# The old ODH 4.112 overlay deleted those primaries and relied on
# release:standalone's postinstall to recreate symlinks — that path is gone.
fix-bin-script() {
  local script="${VSCODE_REH_DIR}/bin/$1"
  if [[ ! -f "${script}" ]]; then
    echo "ERROR: expected gulp-emitted bin script missing: ${script}" >&2
    echo "Listing ${VSCODE_REH_DIR}/bin:" >&2
    find "${VSCODE_REH_DIR}/bin" -type f 2>/dev/null | sort >&2 || true
    exit 1
  fi
  sed -i.bak "s/@@VERSION@@/$(vscode_version)/g" "$script"
  sed -i.bak "s/@@COMMIT@@/$BUILD_SOURCEVERSION/g" "$script"
  sed -i.bak "s/@@APPNAME@@/code-server/g" "$script"

  # Fix Node path on Darwin and Linux.
  # We do not want expansion here; this text should make it to the file as-is.
  # shellcheck disable=SC2016
  sed -i.bak 's/^ROOT=\(.*\)$/VSROOT=\1\nROOT="$(dirname "$(dirname "$VSROOT")")"/g' "$script"
  sed -i.bak 's/ROOT\/out/VSROOT\/out/g' "$script"
  # We do not want expansion here; this text should make it to the file as-is.
  # shellcheck disable=SC2016
  sed -i.bak 's/$ROOT\/node/${NODE_EXEC_PATH:-$ROOT\/lib\/node}/g' "$script"

  # Fix Node path on Windows.
  sed -i.bak 's/^set ROOT_DIR=\(.*\)$/set ROOT_DIR=%~dp0..\\..\\..\\..\r\nset VSROOT_DIR=\1/g' "$script"
  sed -i.bak 's/%ROOT_DIR%\\out/%VSROOT_DIR%\\out/g' "$script"

  chmod +x "$script"
  rm "$script.bak"
}

copy-bin-script() {
  local script="$1"
  cp "lib/vscode/resources/server/bin/$script" "${VSCODE_REH_DIR}/bin/$script"
  fix-bin-script "$script"
}

main() {
  cd "$(dirname "${0}")/../.."

  source ./ci/lib.sh

  # Build for current arch (like che-code): use native gulp task and system Node.
  # setup-offline-binaries.sh / gulpfile.reh overlay add ppc64/s390x to BUILD_TARGETS.
  export NODE_ARCH
  NODE_ARCH=$(node -p "process.arch")
  export VSCODE_REH_DIR="lib/vscode-reh-web-linux-${NODE_ARCH}"
  GULP_ARCH="${NODE_ARCH}"
  # VS Code uses 'armhf' not 'armv7l' for the task name
  case "${NODE_ARCH}" in
    armv7l) GULP_ARCH="armhf" ;;
  esac
  # Keep VSCODE_TARGET aligned with the native output dir for release scripts.
  export VSCODE_TARGET="linux-${NODE_ARCH}"
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
    "win32AppUserModelId": "coder.code-server",
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

  # Upstream 4.122+: compile built-in Copilot extension before the REH bundle.
  VSCODE_QUALITY=stable npm run gulp compile-copilot-extension-full-build

  # Build for current architecture so we can use system Node (see setup-offline-binaries.sh).
  # ODH: ppc64/s390x builds run under QEMU with tsc (not tsgo); use a smaller heap to avoid OOM.
  # Upstream runs core-ci then the arch-specific *-ci package task; *-ci alone assumes
  # out-build/date and out-vscode-reh-web[-min] already exist from core-ci.
  NODE_HEAP_MB=16384
  case "${NODE_ARCH}" in
    # Leave headroom for QEMU user-mode + gulp children on 24GiB VMs.
    ppc64|s390x) NODE_HEAP_MB=4096 ;;
  esac

  # VS Code 1.122 esbuild transpile (build/next) Promise.all's ~6k sources at once.
  # Konflux/buildah often has soft RLIMIT_NOFILE=1024 → EMFILE during core-ci.
  # Raise the soft limit when possible, and cap transpile concurrency regardless.
  ulimit -n 65536 2>/dev/null || ulimit -n 16384 2>/dev/null || true
  # CWD is already lib/vscode (pushd above).
  python3 - <<'PY'
from pathlib import Path
path = Path("build/next/index.ts")
text = path.read_text()
old = """\tawait Promise.all(files.map(file => {
\t\tconst srcPath = path.join(REPO_ROOT, SRC_DIR, file);
\t\tconst destPath = path.join(REPO_ROOT, outDir, file.replace(/\\.ts$/, '.js'));
\t\treturn transpileFile(srcPath, destPath);
\t}));"""
new = """\t// ODH: cap concurrency so Konflux (low nofile) does not EMFILE on ~6k parallel opens.
\tconst transpileConcurrency = Math.max(8, Math.min(64, Number(process.env.VSCODE_TRANSPILE_CONCURRENCY || 64)));
\tfor (let i = 0; i < files.length; i += transpileConcurrency) {
\t\tconst chunk = files.slice(i, i + transpileConcurrency);
\t\tawait Promise.all(chunk.map(file => {
\t\t\tconst srcPath = path.join(REPO_ROOT, SRC_DIR, file);
\t\t\tconst destPath = path.join(REPO_ROOT, outDir, file.replace(/\\.ts$/, '.js'));
\t\t\treturn transpileFile(srcPath, destPath);
\t\t}));
\t}"""
if old not in text:
    raise SystemExit(f"ERROR: transpile Promise.all block not found in {path}")
if "transpileConcurrency" not in text:
    path.write_text(text.replace(old, new, 1))
    print(f"Patched {path}: capped esbuild transpile concurrency")
else:
    print(f"{path}: transpile concurrency patch already applied")
PY

  node --max-old-space-size="${NODE_HEAP_MB}" --optimize-for-size \
       ./node_modules/gulp/bin/gulp.js core-ci
  node --max-old-space-size="${NODE_HEAP_MB}" --optimize-for-size \
       ./node_modules/gulp/bin/gulp.js \
       "vscode-reh-web-linux-${GULP_ARCH}${MINIFY:+-min}-ci"

  # If gulp uses a different arch name (e.g. armv7l -> armhf), move output to NODE_ARCH dir.
  if [[ "${GULP_ARCH}" != "${NODE_ARCH}" ]]; then
    rm -rf "../vscode-reh-web-linux-${NODE_ARCH}"
    mv "../vscode-reh-web-linux-${GULP_ARCH}" "../vscode-reh-web-linux-${NODE_ARCH}"
  fi

  # Node process.arch is "ppc64" on ppc64le hosts; uname/ci/lib.sh use "ppc64le"
  # for VSCODE_TARGET in the separate `npm run release` Dockerfile step. Rename
  # gulp output so release finds lib/vscode-reh-web-linux-ppc64le.
  if [[ "${NODE_ARCH}" == "ppc64" ]]; then
    rm -rf ../vscode-reh-web-linux-ppc64le
    mv ../vscode-reh-web-linux-ppc64 ../vscode-reh-web-linux-ppc64le
    VSCODE_REH_DIR="lib/vscode-reh-web-linux-ppc64le"
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

  # Set vars and fix paths on the gulp-emitted primary scripts (kept by
  # KEEP_MODULES=1 release). Then include other-platform copies for NPM
  # postinstall; KEEP_MODULES=1 release deletes those extras.
  # Use lib.sh $OS (already sourced) so behavior matches upstream on all arches.
  case "${OS}" in
    windows)
      fix-bin-script remote-cli/code.cmd
      fix-bin-script helpers/browser.cmd
      ;;
    *)
      fix-bin-script remote-cli/code-server
      fix-bin-script helpers/browser.sh
      ;;
  esac

  # These provide a `code-server` command in the integrated terminal to open
  # files in the current instance (NPM / multi-platform installs).
  copy-bin-script remote-cli/code-darwin.sh
  copy-bin-script remote-cli/code-linux.sh
  copy-bin-script remote-cli/code.cmd

  # These provide a way for terminal applications to open browser windows.
  copy-bin-script helpers/browser-darwin.sh
  copy-bin-script helpers/browser-linux.sh
  copy-bin-script helpers/browser.cmd
}

main "$@"
