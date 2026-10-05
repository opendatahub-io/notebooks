#!/bin/bash
# Shim: plain `podman` -> renamed binary (AppArmor path bypass on s390x).
#
# Also translate --userns=keep-id to --userns=host, always: the IBM LXD
# runners inconsistently block user-namespace mapping (crun: "write to
# gid_map: Operation not permitted") - reproduced on s390x and on some
# ppc64le runners. Inside this rootful container both are identity
# mappings (root -> root), so the translation is behavior-preserving.
if [ "$#" -gt 0 ]; then
  args=()
  for a in "$@"; do
    if [ "$a" = "--userns=keep-id" ]; then
      args+=("--userns=host")
    else
      args+=("$a")
    fi
  done
  set -- "${args[@]}"
fi
exec /usr/bin/podman-build "$@"
