#!/bin/bash
# Remove statically linked apply-seccomp helpers shipped with
# @vscode/sandbox-runtime (and legacy @anthropic-ai/sandbox-runtime).
#
# Those musl/static ELFs fail Konflux fips-check (ErrNotDynLinked).
# OpenShift workbenches cannot run the Linux agent sandbox anyway (no
# bubblewrap/socat in the image; unshare is ENOSYS under nonroot-v2).
#
# RHOAIENG-88676 / RHAIENG-6849
set -euo pipefail

ROOT="${1:-/usr/lib/code-server}"
if [[ ! -d "${ROOT}" ]]; then
  echo "ERROR: usage: $0 <code-server-root> (directory not found: ${ROOT})" >&2
  exit 1
fi

deleted=0
while IFS= read -r -d '' dest; do
  rm -f "${dest}"
  deleted=$((deleted + 1))
  echo "Removed apply-seccomp: ${dest}"
done < <(find "${ROOT}" -type f -name apply-seccomp -print0 2>/dev/null)

removed_dirs=0
while IFS= read -r -d '' dir; do
  rm -rf "${dir}"
  removed_dirs=$((removed_dirs + 1))
  echo "Removed seccomp vendor dir: ${dir}"
done < <(find "${ROOT}" -type d \( \
  -path '*/node_modules/@vscode/sandbox-runtime/vendor/seccomp' -o \
  -path '*/node_modules/@vscode/sandbox-runtime/dist/vendor/seccomp' -o \
  -path '*/node_modules/@anthropic-ai/sandbox-runtime/vendor/seccomp' -o \
  -path '*/node_modules/@anthropic-ai/sandbox-runtime/dist/vendor/seccomp' \
\) -print0 2>/dev/null)

if [[ "${deleted}" -eq 0 && "${removed_dirs}" -eq 0 ]]; then
  echo "WARNING: no apply-seccomp files or seccomp vendor dirs under ${ROOT}" >&2
else
  echo "Removed ${deleted} apply-seccomp file(s) and ${removed_dirs} seccomp vendor dir(s)"
fi

remaining="$(find "${ROOT}" -type f -name apply-seccomp 2>/dev/null || true)"
if [[ -n "${remaining}" ]]; then
  echo "ERROR: apply-seccomp ELF still present after strip:" >&2
  echo "${remaining}" >&2
  exit 1
fi
