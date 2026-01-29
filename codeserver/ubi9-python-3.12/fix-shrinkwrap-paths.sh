#!/bin/bash
set -euo pipefail

# Script to restore absolute file:// paths in npm-shrinkwrap.json files
# npm shrinkwrap converts absolute paths to relative paths, this fixes them back

echo "=== Fixing npm-shrinkwrap.json files: Converting relative paths to absolute ==="

# Load shared path-rewrite logic
source "/root/scripts/lockfile-generators/rewrite-cachi2-path.sh"

# Find all npm-shrinkwrap.json files
FOUND=0
while IFS= read -r -d '' file; do
    FOUND=1
    echo ""
    echo "Processing: $file"
    
    # Check if file has relative paths or registry URLs
    if grep -q '"resolved": "file:\.\./\.\.' "$file" 2>/dev/null || grep -q '"resolved": "file:cachi2' "$file" 2>/dev/null || grep -q '"resolved": "https://registry\.npmjs\.org' "$file" 2>/dev/null; then
        echo "  Found paths to fix, applying..."
        rewrite_cachi2_path "$file"
    elif grep -q '"resolved": "file:///cachi2' "$file" 2>/dev/null; then
        echo "  ✓ Already has absolute paths"
    else
        echo "  ? No cachi2 paths found in this file"
    fi
done < <(find . -name "npm-shrinkwrap.json" -type f -print0 2>/dev/null)
