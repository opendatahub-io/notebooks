#!/usr/bin/env bash
# Remove proprietary Copilot / Claude agent npm artifacts from a code-server
# release tree after `npm run release`. Build still compiles Copilot during
# build:vscode (required on VS Code 1.122+); this script strips shipped bits.
set -euo pipefail

ROOT="${1:-}"
if [[ -z "${ROOT}" || ! -d "${ROOT}" ]]; then
  echo "usage: $0 <release-root>" >&2
  exit 1
fi

echo "==> Stripping proprietary AI packages under ${ROOT}"

remove_matching_dirs() {
  local pattern="$1"
  while IFS= read -r -d '' path; do
    echo "  removing ${path}"
    rm -rf "${path}"
  done < <(find "${ROOT}" -type d -path "${pattern}" -print0 2>/dev/null || true)
}

remove_matching_dirs '*/node_modules/@github/copilot'
remove_matching_dirs '*/node_modules/@github/copilot-*'
remove_matching_dirs '*/node_modules/@github/copilot-sdk'
remove_matching_dirs '*/node_modules/@anthropic-ai/claude-agent-sdk'
remove_matching_dirs '*/node_modules/@anthropic-ai/claude-agent-sdk-*'
remove_matching_dirs '*/node_modules/@vscode/copilot-api'
remove_matching_dirs '*/extensions/copilot'

for sub in lib/vscode node_modules; do
  if [[ -d "${ROOT}/${sub}/node_modules/@github" ]]; then
    find "${ROOT}/${sub}/node_modules/@github" -maxdepth 1 -type d \( \
      -name 'copilot' -o -name 'copilot-*' -o -name 'copilot-sdk' \
    \) -exec rm -rf {} + 2>/dev/null || true
  fi
  if [[ -d "${ROOT}/${sub}/node_modules/@anthropic-ai" ]]; then
    find "${ROOT}/${sub}/node_modules/@anthropic-ai" -maxdepth 1 -type d \
      -name 'claude-agent-sdk*' -exec rm -rf {} + 2>/dev/null || true
  fi
  copilot_api="${ROOT}/${sub}/node_modules/@vscode/copilot-api"
  extensions_copilot="${ROOT}/${sub}/extensions/copilot"
  rm -rf "${copilot_api}" 2>/dev/null || true
  rm -rf "${extensions_copilot}" 2>/dev/null || true
done

echo "==> Verification (should print nothing):"
if find "${ROOT}" \( \
  -path '*/node_modules/@github/copilot*' -o \
  -path '*/node_modules/@anthropic-ai/claude-agent-sdk*' -o \
  -path '*/node_modules/@vscode/copilot-api' -o \
  -path '*/extensions/copilot' \
\) -print -quit 2>/dev/null | grep -q .; then
  echo "ERROR: proprietary AI artifacts remain under ${ROOT}" >&2
  find "${ROOT}" \( \
    -path '*/node_modules/@github/copilot*' -o \
    -path '*/node_modules/@anthropic-ai/claude-agent-sdk*' -o \
    -path '*/node_modules/@vscode/copilot-api' -o \
    -path '*/extensions/copilot' \
  \) 2>/dev/null | head -20 >&2 || true
  exit 1
fi

echo "==> OK: no @github/copilot*, @anthropic-ai/claude-agent-sdk*, @vscode/copilot-api, or extensions/copilot found"
