#!/usr/bin/env bash
# Verify a built codeserver image or release tree has no proprietary Copilot bits.
set -euo pipefail

TARGET="${1:-}"
if [[ -z "${TARGET}" ]]; then
  echo "usage:" >&2
  echo "  $0 <image-name>          # inspect image filesystem" >&2
  echo "  $0 --release <dir>       # inspect local release directory" >&2
  exit 1
fi

search_root() {
  local root="$1"
  if [[ ! -d "${root}" ]]; then
    echo "FAIL: scan root does not exist or is not a directory: ${root}" >&2
    return 1
  fi
  echo "==> Scanning ${root}"
  local first_match
  if ! first_match="$(find "${root}" \( \
    -path '*/node_modules/@github/copilot*' -o \
    -path '*/node_modules/@anthropic-ai/claude-agent-sdk*' -o \
    -path '*/node_modules/@vscode/copilot-api' -o \
    -path '*/extensions/copilot' \
  \) -print -quit)"; then
    echo "FAIL: unable to scan ${root}" >&2
    return 1
  fi
  if [[ -n "${first_match}" ]]; then
    echo "FAIL: found proprietary AI artifacts:"
    find "${root}" \( \
      -path '*/node_modules/@github/copilot*' -o \
      -path '*/node_modules/@anthropic-ai/claude-agent-sdk*' -o \
      -path '*/node_modules/@vscode/copilot-api' -o \
      -path '*/extensions/copilot' \
  \) | head -30
    return 1
  fi
  echo "PASS: no proprietary Copilot/Claude SDK packages found"
}

if [[ "${TARGET}" == "--release" ]]; then
  search_root "${2:?release dir required}"
  exit $?
fi

CID="$(podman create "${TARGET}")"
ROOTFS="$(podman mount "${CID}")"
trap 'podman unmount "${CID}" >/dev/null 2>&1 || true; podman rm -f "${CID}" >/dev/null 2>&1 || true' EXIT
search_root "${ROOTFS}/usr/lib/code-server"
