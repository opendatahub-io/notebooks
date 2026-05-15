#!/usr/bin/env bash
#=========================================================
# Script: dockerfile_diff_checker.sh
# Purpose: Scan a directory tree for Dockerfile.konflux.*
#          and compare each with its original Dockerfile,
#          requiring byte-identical content.
#=========================================================

set -euo pipefail

#---------------------------------------------------------
# Main script execution
#---------------------------------------------------------
main() {

    # Define multiple starting directories
    local start_dirs=("./jupyter" "./codeserver" "./runtimes")
    echo "Scanning ${start_dirs[*]} for directories containing Dockerfile.konflux.*"
    echo "Comparing Dockerfiles (byte-identical check)..."

    # Populate array of directories (while-read is portable; mapfile requires Bash 4+)
    local docker_dirs=()
    for dir in "${start_dirs[@]}"; do
        while IFS= read -r line; do
            docker_dirs+=("$line")
        done < <(find_docker_dirs "$dir")
    done

    # Process all directories and check for differences
    if process_dirs "${docker_dirs[@]}"; then
        echo "✅ All Dockerfiles are in sync."
    else
        echo "❌ Differences were found. Please inspect."
        exit 1
    fi
}

#---------------------------------------------------------
# Function: find_docker_dirs
# Description:
#   Recursively search for directories containing files named
#   "Dockerfile.konflux.*". Each directory is listed only once.
# Arguments:
#   $1 - starting directory
# Returns:
#   Prints each directory path containing at least one
#   Dockerfile.konflux.* file
#---------------------------------------------------------
find_docker_dirs() {
    local start_dir="$1"

    # Use 'find' to locate matching files, then 'dirname' to extract directories, 'sort -u' to remove duplicates
    find "$start_dir" -type f -name "Dockerfile.konflux.*" -exec dirname {} \; | sort -u
}

#---------------------------------------------------------
# Function: find_diff
# Description:
#   Compare a Dockerfile with its corresponding konflux version.
#   Files must be byte-identical. Returns 1 if differences exist.
# Arguments:
#   $1 - Directory containing the Dockerfiles
#   $2 - Original Dockerfile name (basename)
#   $3 - Konflux Dockerfile name (basename)
# Returns:
#   0 if no differences, 1 if differences exist
#---------------------------------------------------------
find_diff() {
    local dir="$1"
    local file_orig="$2"
    local file_konflux="$3"

    echo "---- diff $file_orig $file_konflux ----"

    local diff_output
    diff_output=$(diff "$dir/$file_orig" "$dir/$file_konflux" || true)

    if [ -n "$diff_output" ]; then
        echo "❌ Differences found between $file_orig and $file_konflux"
        # Uncomment the next line to see detailed differences
        echo "$diff_output"
        return 1
    else
        echo "✅ No differences"
        return 0
    fi
}

#---------------------------------------------------------
# Function: process_dirs
# Description:
#   Iterate over a list of directories, find konflux Dockerfiles
#   in each, and compare them with their originals.
# Arguments:
#   Array of directories
# Returns:
#   0 if all Dockerfiles match, 1 if any differences exist
#---------------------------------------------------------
process_dirs() {
    local dirs=("$@")
    local diff_found=0

    # Iterate over each directory
    for dir in "${dirs[@]}"; do
        echo "=== Processing $dir ==="

        # Iterate over each konflux Dockerfile
        for konflux_file in "$dir"/Dockerfile.konflux.*; do
            [ -e "$konflux_file" ] || continue

            # Derive the original Dockerfile name by removing the .konflux
            local dockerfile="${konflux_file/.konflux/}"

            # Check if the original Dockerfile exists
            if [ ! -f "$dockerfile" ]; then
                echo "⚠️  $dockerfile not found in $dir" >&2
                continue
            fi

            # Compare the files
            if ! find_diff "$dir" "$(basename "$dockerfile")" "$(basename "$konflux_file")"; then
                diff_found=1
            fi
        done
    done

    return $diff_found
}

# Call main with all script arguments
main "$@"
