#!/usr/bin/env bash
set -Eeuxo pipefail

# CVE remediation
# remediate CVEs introduced through older embedded version of esbuild
rm "/usr/lib/rstudio-server/bin/quarto/bin/tools/$(uname -m)/esbuild"
npm ci
mv node_modules/esbuild/bin/esbuild "/usr/lib/rstudio-server/bin/quarto/bin/tools/$(uname -m)/"
# clean up
rm -r node_modules package.json package-lock.json
npm cache clean --force
