#!/usr/bin/env bash
# rewrite-cachi2-path.sh — Rewrite npm URLs to local cachi2 paths.
#
# Source this file (do NOT run standalone) and call:
#   rewrite_cachi2_path <package-lock.json or npm-shrinkwrap.json>
#
# Replaces npm registry URLs (https://registry.npmjs.org/...) and relative
# file: paths with absolute file:///cachi2/output/deps/npm/ paths so that
# `npm install` uses the prefetched tarballs during --network=none builds.
#
# Used by Dockerfile RUN steps (e.g. setup-offline-binaries.sh).
# Requires: perl.

rewrite_cachi2_path() {
  local file="$1"
  [[ -n "$file" && -f "$file" ]] || return 1
  # 1) Registry URLs -> file:///cachi2/output/deps/npm/
  perl -i -pe 's#https://registry\.npmjs\.org/(?:@([^/]+)/)?[^/]+/-/([^"]+)# "file:///cachi2/output/deps/npm/" . ($1 ? "$1-$2" : "$2") #ge' "$file"
  # 2) file:../...cachi2/... -> file:///cachi2/...
  perl -i -pe 's#"resolved": "file:(\.\./)+cachi2/output/deps/npm/([^"]+)"#"resolved": "file:///cachi2/output/deps/npm/$2"#g' "$file"
  # 3) file:cachi2/... -> file:///cachi2/...
  perl -i -pe 's#"resolved": "file:cachi2/output/deps/npm/([^"]+)"#"resolved": "file:///cachi2/output/deps/npm/$1"#g' "$file"
}

# Export so subshells (e.g. in Dockerfile RUN) can use it
export -f rewrite_cachi2_path
