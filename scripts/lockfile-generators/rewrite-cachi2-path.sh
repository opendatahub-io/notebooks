#!/usr/bin/env bash
# Rewrite npm registry URLs and relative file: paths to absolute file:///cachi2/output/deps/npm/
# in package-lock.json and npm-shrinkwrap.json. Source this file and call rewrite_cachi2_path <file>.
# Used by Dockerfile RUN steps and offline build scripts. Requires perl.

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
