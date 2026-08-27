#!/bin/bash
# Rebuild @vscode/sandbox-runtime apply-seccomp as a dynamically linked binary.
#
# VS Code 4.122+ ships a statically linked apply-seccomp helper under
# node_modules/@vscode/sandbox-runtime/vendor/seccomp/{x64,arm64}/. That fails
# Konflux FIPS check-payload (ErrNotDynLinked). Upstream intentionally builds
# with gcc -static; we rebuild from the bundled C sources without -static so
# the binary links against libseccomp.so.2 (RHAIENG-6849).
#
# On ppc64le/s390x, sandbox-runtime does not support seccomp on those arches;
# remove the unused static x64 blobs so check-payload does not fail.
set -euo pipefail

ROOT="${1:-${CODESERVER_SOURCE_PREFETCH:-}}"
if [[ -z "${ROOT}" || ! -d "${ROOT}" ]]; then
  echo "ERROR: usage: $0 <code-server-source-root>" >&2
  exit 1
fi

machine="$(uname -m)"
case "${machine}" in
  x86_64)
    native_dir=x64
    bpf_target=x86_64
    ;;
  aarch64)
    native_dir=arm64
    bpf_target=aarch64
    ;;
  ppc64le|s390x)
    removed=0
    while IFS= read -r -d '' blob; do
      rm -f "${blob}"
      removed=$((removed + 1))
      echo "Removed unsupported-arch apply-seccomp: ${blob}"
    done < <(find "${ROOT}" -type f -path '*/node_modules/@vscode/sandbox-runtime/vendor/seccomp/*/apply-seccomp' -print0 2>/dev/null)
    if [[ "${removed}" -eq 0 ]]; then
      echo "WARNING: no apply-seccomp binaries found under ${ROOT}" >&2
    else
      echo "Removed ${removed} apply-seccomp binary(ies) on ${machine}"
    fi
    exit 0
    ;;
  *)
    echo "ERROR: unsupported architecture ${machine}" >&2
    exit 1
    ;;
esac

if ! command -v gcc >/dev/null 2>&1; then
  echo "ERROR: gcc not found (enable gcc-toolset-14 in the build stage)" >&2
  exit 1
fi
if ! pkg-config --exists libseccomp 2>/dev/null && [[ ! -f /usr/include/seccomp.h ]]; then
  echo "ERROR: libseccomp-devel not installed" >&2
  exit 1
fi

rebuilt=0
while IFS= read -r -d '' pkg; do
  src="${pkg}/vendor/seccomp-src"
  if [[ ! -f "${src}/apply-seccomp.c" || ! -f "${src}/seccomp-unix-block.c" ]]; then
    echo "WARNING: skipping ${pkg} (missing seccomp C sources)" >&2
    continue
  fi

  out="${pkg}/vendor/seccomp/${native_dir}"
  mkdir -p "${out}"

  gen="${out}/seccomp-unix-block"
  gcc -O2 -Wall -Wextra -o "${gen}" "${src}/seccomp-unix-block.c" -lseccomp

  tmp_bpf="${out}/${bpf_target}.bpf"
  "${gen}" "${tmp_bpf}" "${bpf_target}"

  header="${out}/unix-block-bpf.h"
  if [[ "${machine}" == "x86_64" ]]; then
    python3 - "${tmp_bpf}" "${header}" <<'PY'
import pathlib, sys
b = pathlib.Path(sys.argv[1]).read_bytes()
hexes = [f"0x{b:02x}" for b in b]
lines = [" " + ", ".join(hexes[i:i + 8]) + "," for i in range(0, len(hexes), 8)]
body = "\n".join(lines)
pathlib.Path(sys.argv[2]).write_text(
    "#if defined(__x86_64__)\n"
    "static const unsigned char unix_block_bpf[] = {\n"
    f"{body}\n"
    "};\n"
    "#else\n"
    '#error "unsupported architecture for unix-block BPF filter"\n'
    "#endif\n"
)
PY
  else
    python3 - "${tmp_bpf}" "${header}" <<'PY'
import pathlib, sys
b = pathlib.Path(sys.argv[1]).read_bytes()
hexes = [f"0x{b:02x}" for b in b]
lines = [" " + ", ".join(hexes[i:i + 8]) + "," for i in range(0, len(hexes), 8)]
body = "\n".join(lines)
pathlib.Path(sys.argv[2]).write_text(
    "#if defined(__aarch64__)\n"
    "static const unsigned char unix_block_bpf[] = {\n"
    f"{body}\n"
    "};\n"
    "#else\n"
    '#error "unsupported architecture for unix-block BPF filter"\n'
    "#endif\n"
)
PY
  fi

  dest="${out}/apply-seccomp"
  gcc -O2 -Wall -Wextra -I "${out}" -o "${dest}" "${src}/apply-seccomp.c" -lseccomp
  strip "${dest}"
  chmod 0755 "${dest}"
  rm -f "${gen}" "${tmp_bpf}" "${header}"

  for other in x64 arm64; do
    if [[ "${other}" != "${native_dir}" ]]; then
      rm -f "${pkg}/vendor/seccomp/${other}/apply-seccomp"
    fi
  done

  if command -v readelf >/dev/null 2>&1; then
    if ! readelf -l "${dest}" | grep -q 'INTERP'; then
      echo "ERROR: rebuilt apply-seccomp is still static: ${dest}" >&2
      exit 1
    fi
    if ! readelf -d "${dest}" | grep -q 'libseccomp.so'; then
      echo "ERROR: rebuilt apply-seccomp does not link libseccomp: ${dest}" >&2
      exit 1
    fi
  fi

  rebuilt=$((rebuilt + 1))
  echo "Rebuilt dynamically linked apply-seccomp: ${dest}"
done < <(find "${ROOT}" -type d -path '*/node_modules/@vscode/sandbox-runtime' -print0 2>/dev/null)

if [[ "${rebuilt}" -eq 0 ]]; then
  echo "WARNING: no @vscode/sandbox-runtime packages found under ${ROOT}" >&2
else
  echo "Rebuilt apply-seccomp in ${rebuilt} sandbox-runtime package(s) on ${machine}"
fi
