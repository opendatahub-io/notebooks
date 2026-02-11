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
  # 4) git+ssh GitHub tarball refs -> file:///cachi2/output/deps/npm/<org>-<repo>-<commit>.tar.gz
  perl -i -pe 's#"resolved": "git\+ssh://git\@github\.com/([^/]+)/([^.]+)\.git\#([0-9a-f]+)"#"resolved": "file:///cachi2/output/deps/npm/$1-$2-$3.tar.gz"#g' "$file"
  # 5) GitHub shorthand git refs in dependency specifiers -> file: tarball URL
  #    e.g. "@parcel/watcher": "parcel-bundler/watcher#<40-hex-sha>" -> file:///cachi2/...
  #    NOTE: This only handles 40-hex commit hashes. Git shorthand deps with branch/tag
  #    names (e.g. "ramya-rao-a/css-parser#vscode") are handled separately in
  #    setup-offline-binaries.sh, which looks up the commit hash from the resolved field.
  perl -i -pe 's#": "([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)\#([0-9a-f]{40})"#": "file:///cachi2/output/deps/npm/$1-$2-$3.tar.gz"#g' "$file"
  # 6) Remove integrity hashes for rewritten git->file dependencies
  #    GitHub source tarballs differ from npm's git-packaged tarballs, so the
  #    original integrity hash won't match. Removing it lets npm skip the check.
  perl -i -0777 -pe 's/("resolved": "file:\/\/\/cachi2\/output\/deps\/npm\/[^"]*-[0-9a-f]{40}\.tar\.gz",)\s*\n\s*"integrity": "[^"]*",/$1/g' "$file"
}








# Export so subshells (e.g. in Dockerfile RUN) can use it
export -f rewrite_cachi2_path
