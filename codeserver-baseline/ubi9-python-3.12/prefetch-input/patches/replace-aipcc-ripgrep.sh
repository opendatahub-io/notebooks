#!/bin/bash
# Replace statically-linked Microsoft ripgrep binaries with the AIPCC/RHOAI
# dynamically-linked `rg` from the Python wheel (RIPGREP_BINARY_PATH).
#
# VS Code 1.122+ ships @vscode/ripgrep-universal (and Copilot SDK embeds its own
# ripgrep tree). Those musl/static binaries fail FIPS check-payload
# (ErrNotDynLinked). Upstream/main hermetic builds used the AIPCC wheel via a
# patched @vscode/ripgrep postinstall; this script does the equivalent for the
# universal package layout (bin/<platform>-<arch>/rg).
set -euo pipefail

# Later Dockerfile RUN layers may not inherit RIPGREP_BINARY_PATH from setup-offline.
if [[ -z "${RIPGREP_BINARY_PATH:-}" || ! -x "${RIPGREP_BINARY_PATH}" ]]; then
  RIPGREP_BINARY_PATH="$(command -v rg || true)"
fi
if [[ -z "${RIPGREP_BINARY_PATH}" || ! -x "${RIPGREP_BINARY_PATH}" ]]; then
  for candidate in /opt/app-root/bin/rg /usr/local/bin/rg /usr/bin/rg; do
    if [[ -x "${candidate}" ]]; then
      RIPGREP_BINARY_PATH="${candidate}"
      break
    fi
  done
fi
if [[ -z "${RIPGREP_BINARY_PATH:-}" || ! -x "${RIPGREP_BINARY_PATH}" ]]; then
  echo "ERROR: AIPCC/RHOAI ripgrep binary not found (set RIPGREP_BINARY_PATH or install the wheel)" >&2
  exit 1
fi
export RIPGREP_BINARY_PATH

ROOT="${1:-${CODESERVER_SOURCE_PREFETCH:-}}"
if [[ -z "${ROOT}" || ! -d "${ROOT}" ]]; then
  echo "ERROR: usage: $0 <code-server-source-root>" >&2
  exit 1
fi

replaced=0
while IFS= read -r -d '' dest; do
  cp -f "${RIPGREP_BINARY_PATH}" "${dest}"
  chmod 0755 "${dest}"
  replaced=$((replaced + 1))
  echo "Replaced static ripgrep with AIPCC rg: ${dest}"
done < <(find "${ROOT}" -type f \( \
  -path '*/node_modules/@vscode/ripgrep-universal/bin/*/rg' -o \
  -path '*/node_modules/@vscode/ripgrep/bin/rg' -o \
  -path '*/@github/copilot/sdk/ripgrep/bin/*/rg' -o \
  -path '*/.build/extensions/copilot/*/ripgrep/bin/*/rg' -o \
  -path '*/.build/extensions/copilot/node_modules/@github/copilot/sdk/ripgrep/bin/*/rg' \
\) -print0 2>/dev/null)

if [[ "${replaced}" -eq 0 ]]; then
  echo "WARNING: no ripgrep binaries found under ${ROOT} to replace" >&2
else
  echo "Replaced ${replaced} ripgrep binary(ies) with ${RIPGREP_BINARY_PATH}"
  # Confirm the replacement is dynamically linked (FIPS-friendly).
  if command -v file >/dev/null 2>&1; then
    sample="$(find "${ROOT}" -type f -path '*/@vscode/ripgrep-universal/bin/*/rg' | head -1 || true)"
    if [[ -n "${sample}" ]]; then
      info="$(file "${sample}" || true)"
      echo "${info}"
      # Only enforce on Linux ELF builds (macOS `file` output differs).
      if echo "${info}" | grep -qi 'ELF' && echo "${info}" | grep -qi 'statically linked'; then
        echo "ERROR: replaced ripgrep still reports as statically linked: ${sample}" >&2
        exit 1
      fi
    fi
  fi
fi
