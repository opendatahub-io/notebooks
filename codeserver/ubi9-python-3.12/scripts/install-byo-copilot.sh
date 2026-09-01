#!/usr/bin/env bash
# Bring-your-own GitHub Copilot for stripped code-server images.
#
# Downloads GitHub.copilot + GitHub.copilot-chat VSIX from the Visual Studio
# Marketplace (user network fetch; not redistributed in the image), installs
# them into the workbench, enables AI features, and writes gallery config for
# the next workbench restart (required for post-sign-in chat setup).
#
# Usage (inside a running workbench container or pod):
#   install-byo-copilot.sh
#   install-byo-copilot.sh --copilot-version 1.388.0 --chat-version 0.48.1
#   install-byo-copilot.sh --offline /path/to/GitHub.copilot.vsix /path/to/GitHub.copilot-chat.vsix
#
# From the host:
#   podman exec -it <container> install-byo-copilot.sh
set -euo pipefail

readonly COPILOT_ID="GitHub.copilot"
readonly COPILOT_CHAT_ID="GitHub.copilot-chat"
readonly MARKETPLACE_API="https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"
readonly CODE_SERVER_DATA_DIR="${CODE_SERVER_DATA_DIR:-/opt/app-root/src/.local/share/code-server}"
readonly EXTENSIONS_DIR="${EXTENSIONS_DIR:-${CODE_SERVER_DATA_DIR}/extensions}"
readonly USER_SETTINGS="${USER_SETTINGS:-${CODE_SERVER_DATA_DIR}/User/settings.json}"
readonly CACHE_DIR="${BYO_COPILOT_CACHE:-${CODE_SERVER_DATA_DIR}/byo-copilot-cache}"
readonly BYO_COPILOT_DIR="${CODE_SERVER_DATA_DIR}/byo-copilot"
readonly BYO_GALLERY_ENV="${BYO_COPILOT_DIR}/gallery.env"

# Open VSX does not host Copilot; chat setup still queries the gallery after
# GitHub sign-in even when VSIX extensions are already installed locally.
readonly MS_EXTENSIONS_GALLERY='{"serviceUrl":"https://marketplace.visualstudio.com/_apis/public/gallery","itemUrl":"https://marketplace.visualstudio.com/items","cacheUrl":"https://vscode.blob.core.windows.net/gallery/index","resourceUrlTemplate":"https://{publisher}.vscode-unpkg.net/{publisher}/{name}/{version}/{path}"}'

COPILOT_VERSION=""
CHAT_VERSION=""
OFFLINE_COPILOT_VSIX=""
OFFLINE_CHAT_VSIX=""
DRY_RUN=0
ACCEPT_LICENSE=0

usage() {
  cat <<'EOF'
Bring-your-own GitHub Copilot for stripped code-server images.

Downloads GitHub.copilot + GitHub.copilot-chat VSIX from the Visual Studio
Marketplace (user network fetch; not redistributed in the image), installs
them, enables AI features, and configures the gallery for workbench restart.

Requires: curl, python3, code-server, outbound HTTPS to marketplace.visualstudio.com
and *.gallerycdn.vsassets.io. A GitHub Copilot subscription is required at sign-in.

Usage:
  install-byo-copilot.sh
  install-byo-copilot.sh --copilot-version 1.388.0 --chat-version 0.48.1
  install-byo-copilot.sh --offline /path/to/copilot.vsix /path/to/copilot-chat.vsix

From the host:
  podman exec -it <container> install-byo-copilot.sh
EOF
  echo
  echo "Options:"
  echo "  --copilot-version VER   Pin GitHub.copilot version (default: latest)"
  echo "  --chat-version VER      Pin GitHub.copilot-chat version (default: latest)"
  echo "  --offline COPILOT CHAT  Install from local VSIX files"
  echo "  --accept-license        Skip interactive license prompt (non-interactive/CI)"
  echo "  --dry-run               Print actions only"
  echo "  -h, --help              Show this help"
}

log() { echo "==> $*" >&2; }
die() { echo "ERROR: $*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }

prompt_accept_copilot_terms() {
  if [[ "${ACCEPT_LICENSE}" -eq 1 ]]; then
    log "License acceptance confirmed via --accept-license"
    return 0
  fi
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Would prompt for Copilot license acceptance (pass --accept-license to skip)"
    return 0
  fi

  local tty=/dev/tty
  [[ -r "${tty}" ]] || die "not a TTY; re-run with -it or pass --accept-license"

  cat <<'EOF' >&2

You are about to download and install proprietary GitHub Copilot extensions
(GitHub.copilot, GitHub.copilot-chat) from the Visual Studio Marketplace.

This workbench image does not redistribute these components. You must:
  - Have your own active GitHub Copilot subscription
  - Accept Microsoft's and GitHub's terms for Copilot and the Marketplace

Review:
  - GitHub Copilot terms:
      https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features
  - Visual Studio Marketplace terms:
      https://aka.ms/vsmarketplace-ToU

EOF
  local ans
  read -r -p "Type 'yes' to accept and continue: " ans <"${tty}"
  [[ "${ans}" == "yes" ]] || die "aborted (license not accepted)"
}

code_server_install() {
  /usr/bin/code-server \
    --user-data-dir "${CODE_SERVER_DATA_DIR}" \
    --extensions-dir "${EXTENSIONS_DIR}" \
    --install-extension "$1"
}

extension_installed() {
  /usr/bin/code-server \
    --user-data-dir "${CODE_SERVER_DATA_DIR}" \
    --extensions-dir "${EXTENSIONS_DIR}" \
    --list-extensions 2>/dev/null | grep -Fxi "$1" >/dev/null
}

resolve_vsix_url() {
  python3 - "$1" "${2:-}" "${MARKETPLACE_API}" <<'PY'
import json, sys, urllib.request
extension_id, version, api_url = sys.argv[1:4]
payload = {"filters": [{"criteria": [{"filterType": 7, "value": extension_id}]}], "flags": 914}
req = urllib.request.Request(api_url, data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "Accept": "application/json;api-version=7.1-preview.1"})
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.load(resp)
extensions = data.get("results", [{}])[0].get("extensions", [])
if not extensions:
    sys.exit(f"extension not found on marketplace: {extension_id}")
ext = extensions[0]
versions = ext.get("versions", [])
chosen = next((v for v in versions if v.get("version") == version), None) if version else versions[0]
if version and not chosen:
    sys.exit(f"version {version} not found for {extension_id}")
for asset in chosen.get("files", []):
    if asset.get("assetType") == "Microsoft.VisualStudio.Services.VSIXPackage":
        print(chosen["version"])
        print(asset["source"])
        sys.exit(0)
sys.exit(f"VSIX package not listed for {extension_id}")
PY
}

download_vsix() {
  local extension_id="$1" version="$2" url="$3"
  local dest="${CACHE_DIR}/${extension_id}-${version}.vsix"
  mkdir -p "${CACHE_DIR}"
  if [[ -f "${dest}" ]]; then
    log "Using cached VSIX: ${dest}"
    printf '%s\n' "${dest}"
    return 0
  fi
  log "Downloading ${extension_id} ${version}"
  [[ "${DRY_RUN}" -eq 1 ]] && { log "Would download ${url} -> ${dest}"; printf '%s\n' "${dest}"; return 0; }
  curl -fsSL --retry 3 --retry-delay 2 -o "${dest}" "${url}"
  [[ -s "${dest}" ]] || die "download failed: ${dest}"
  file "${dest}" | grep -qi 'zip archive' || die "not a VSIX zip: ${dest}"
  printf '%s\n' "${dest}"
}

install_vsix() {
  [[ "${DRY_RUN}" -eq 1 ]] && { log "Would install $1 from $2"; return 0; }
  log "Installing $1"
  code_server_install "$2"
}

enable_ai_features() {
  mkdir -p "$(dirname "${USER_SETTINGS}")"
  if [[ ! -f "${USER_SETTINGS}" ]]; then
    printf '%s\n' '{"chat.disableAIFeatures": false}' >"${USER_SETTINGS}"
    return 0
  fi
  if grep -q '"chat.disableAIFeatures"[[:space:]]*:[[:space:]]*false' "${USER_SETTINGS}"; then
    log "AI features already enabled"
    return 0
  fi
  if grep -q '"chat.disableAIFeatures"' "${USER_SETTINGS}"; then
    [[ "${DRY_RUN}" -eq 1 ]] && return 0
    sed -i.bak -E 's/"chat\.disableAIFeatures"[[:space:]]*:[[:space:]]*true/"chat.disableAIFeatures": false/' \
      "${USER_SETTINGS}"
    rm -f "${USER_SETTINGS}.bak"
    return 0
  fi
  [[ "${DRY_RUN}" -eq 1 ]] && return 0
  python3 - "${USER_SETTINGS}" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text().rstrip()
entry = '  "chat.disableAIFeatures": false'
if text.endswith('}'):
    body = text[:-1].rstrip()
    updated = (body + ('\n' if body.endswith('{') else ',\n') + entry + '\n}\n')
else:
    updated = text + '\n' + entry + '\n'
path.write_text(updated)
PY
}

enable_byo_gallery_config() {
  mkdir -p "${BYO_COPILOT_DIR}"
  [[ "${DRY_RUN}" -eq 1 ]] && { log "Would write ${BYO_GALLERY_ENV}"; return 0; }
  cat >"${BYO_GALLERY_ENV}" <<EOF
# Written by install-byo-copilot.sh (user BYO; not shipped in the image).
export EXTENSIONS_GALLERY='${MS_EXTENSIONS_GALLERY}'
EOF
  log "Wrote ${BYO_GALLERY_ENV}"
}

print_next_steps() {
  cat <<'EOF'

Done. Next steps:
  1. Restart the workbench (gallery config loads at startup):
       podman restart <container>
  2. Open code-server and reload the browser tab.
  3. Sign in to GitHub when Copilot prompts you.
  4. Confirm your GitHub account has an active Copilot subscription.

Run install-byo-copilot.sh BEFORE signing in. Copilot extensions live under
your user directory only; the base image stays stripped of proprietary binaries.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copilot-version) COPILOT_VERSION="${2:?}"; shift 2 ;;
    --chat-version) CHAT_VERSION="${2:?}"; shift 2 ;;
    --offline) OFFLINE_COPILOT_VSIX="${2:?}"; OFFLINE_CHAT_VSIX="${3:?}"; shift 3 ;;
    --accept-license) ACCEPT_LICENSE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

need_cmd curl python3 code-server file
mkdir -p "${EXTENSIONS_DIR}" "$(dirname "${USER_SETTINGS}")"

log "BYO GitHub Copilot installer"

if [[ -n "${OFFLINE_COPILOT_VSIX}" ]]; then
  [[ -f "${OFFLINE_COPILOT_VSIX}" && -f "${OFFLINE_CHAT_VSIX}" ]] || die "offline VSIX path missing"
  if ! extension_installed "${COPILOT_ID}" || ! extension_installed "${COPILOT_CHAT_ID}"; then
    prompt_accept_copilot_terms
  fi
  copilot_vsix="${OFFLINE_COPILOT_VSIX}"
  chat_vsix="${OFFLINE_CHAT_VSIX}"
elif extension_installed "${COPILOT_ID}" && extension_installed "${COPILOT_CHAT_ID}"; then
  log "Copilot extensions already installed"
  enable_ai_features
  enable_byo_gallery_config
  print_next_steps
  exit 0
else
  prompt_accept_copilot_terms
  mapfile -t copilot_meta < <(resolve_vsix_url "${COPILOT_ID}" "${COPILOT_VERSION}")
  mapfile -t chat_meta < <(resolve_vsix_url "${COPILOT_CHAT_ID}" "${CHAT_VERSION}")
  copilot_vsix="$(download_vsix "${COPILOT_ID}" "${copilot_meta[0]}" "${copilot_meta[1]}")"
  chat_vsix="$(download_vsix "${COPILOT_CHAT_ID}" "${chat_meta[0]}" "${chat_meta[1]}")"
fi

extension_installed "${COPILOT_ID}" || install_vsix "${COPILOT_ID}" "${copilot_vsix}"
extension_installed "${COPILOT_CHAT_ID}" || install_vsix "${COPILOT_CHAT_ID}" "${chat_vsix}"

enable_ai_features
enable_byo_gallery_config
print_next_steps
