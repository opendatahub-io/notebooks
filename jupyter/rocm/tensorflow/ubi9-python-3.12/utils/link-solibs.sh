#!/usr/bin/env bash
set -Eeuo pipefail

# TensorFlow-ROCm wants to link with `*.so` libraries without version suffixes.
# This would require us to install the -devel packages, but that's cumbersome with AIPCC bases.
# Therefore, simply create symlinks to the versioned libraries and (IMPORTANT!) run ldconfig afterwards.

ROCM_PATH=/opt/rocm-6.3.4
find "$ROCM_PATH/lib" -name '*.so.*' -type f -print0 |
while IFS= read -r -d '' f; do
  dir=${f%/*}                       # /opt/rocm-6.3.4/lib  (or sub-dir)
  bn=${f##*/}                       # libMIOpen.so.1.0.60304
  base=${bn%%.so*}                  # libMIOpen
  soname=$base.so                   # libMIOpen.so
  link=$dir/$soname                 # /opt/rocm-6.3.4/lib/libMIOpen.so
  [[ -e $link ]] && continue
  echo "ln -s $bn  →  $link"
  ln -s "$bn" "$link"
done

# Run ldconfig to update the cache.
ldconfig
