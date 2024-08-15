#!/bin/bash

# Check if the script is running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
  echo "Error: This script can only be run on Linux."
  exit 1
fi

# Detailed help message
print_help() {
  echo "Usage: $0 <directory> <library_name> <new_version> <include_paths_with> <exclude_paths_with> <lock_files>"
  echo
  echo "Parameters:"
  echo "  directory           The root directory to start searching for Pipfile and requirements-elyra.txt files."
  echo "  library_name        The name of the library to update."
  echo "  new_version         The new version to set for the library."
  echo "  include_paths_with  A pipe-separated list of substrings; only files in directories containing at least one of these substrings will be processed."
  echo "  exclude_paths_with  A pipe-separated list of substrings; files in directories containing any of these substrings will be excluded."
  echo "  lock_files          Whether to run 'pipenv lock' after updating the library version (true or false)."
  echo
  echo "Examples:"
  echo "  $0 ./myproject numpy 2.0.1 '' '' true"
  echo "  $0 ./myproject pandas 2.2.2 'include|this' 'exclude|that' false"
}

# Check if the correct number of arguments are passed
if [ "$#" -ne 6 ]; then
  print_help
  exit 1
fi

# Arguments
directory=$1
library_name=$2
new_version=$3
include_paths_with=$4
exclude_paths_with=$5
lock_files=$6

# Print arguments
echo "Arguments:"
echo "  directory          = $directory"
echo "  library_name       = $library_name"
echo "  new_version        = $new_version"
echo "  include_paths_with = $include_paths_with"
echo "  exclude_paths_with = $exclude_paths_with"
echo "  lock_files         = $lock_files"

# Function to check if one version is higher than the other
# Returns 0 if the first version is greater and 1 if the second is greater or equal
is_version_higher() {
  local ver1=$1
  local ver2=$2

  # Remove any non-numeric, non-dot characters from the beginning (before the first number, which represents the version specifier)
  ver1=$(echo "$ver1" | sed 's/^[^0-9.]*//')
  ver2=$(echo "$ver2" | sed 's/^[^0-9.]*//')

  # Split each segment of the version numbers
  IFS='.' read -r -a ver1_parts <<< "$ver1"
  IFS='.' read -r -a ver2_parts <<< "$ver2"

  for ((i = 0; i < ${#ver1_parts[@]} || i < ${#ver2_parts[@]}; i++)); do
    # Use 0 if a part is missing
    v1=${ver1_parts[i]:-0}
    v2=${ver2_parts[i]:-0}
    
    # Compare the parts
    if ((v1 > v2)); then
      return 0
    fi
  done

  return 1
}

# Function to update the library version in Pipfile files, only if the new version is higher
update_library_version_pipfile() {
  local file=$1
  local lib=$2
  local new_ver=$3
  local include_paths_with=$4
  local exclude_paths_with=$5
  local lock_files=$6
  local directory=$(dirname "$file")
  local filename=$(basename "$file")

  # Determine if this is an architecture-specific Pipfile (with the "gpu" or "cpu" suffixes) and determine the corresponding lock file name
  local is_specific=false
  local lockfile=""
  if [[ "$filename" == Pipfile.gpu ]]; then
    is_specific=true
    lockfile="Pipfile.lock.gpu"
  elif [[ "$filename" == Pipfile.cpu ]]; then
    is_specific=true
    lockfile="Pipfile.lock.cpu"
  else
    lockfile="Pipfile.lock"
  fi
  
  # Check if the file directory has at least one of the substrings (separated by "|") in $include_paths_with 
  # and does not contain any of the substrings (separated by "|") in $exclude_paths_with
  if { [[ -z "$include_paths_with" ]] || [[ "$directory" =~ $include_paths_with ]]; } && { [[ -z "$exclude_paths_with" ]] || [[ ! "$directory" =~ $exclude_paths_with ]]; }; then
    echo "Processing $file (directory matches the pattern)"
  else
    echo "Skipping $file (directory does not match the pattern)"
    return
  fi

  # Extract the current version and qualifier from the Pipfile
  current_line=$(grep -E "^\"?$lib\"?[[:space:]]*=[[:space:]]*" "$file")

  if [[ $current_line =~ ^\"?$lib\"?[[:space:]]*=[[:space:]]*\"?([=><!~]*)?([0-9]+(\.[0-9]+)*)\"?$ ]]; then
    current_qualifier="${BASH_REMATCH[1]}"
    current_ver="${BASH_REMATCH[2]}"
  elif [[ $current_line =~ version[[:space:]]*=[[:space:]]*\"?([=><!~]*)?([0-9]+(\.[0-9]+)*)\" ]]; then
    current_qualifier="${BASH_REMATCH[1]}"
    current_ver="${BASH_REMATCH[2]}"
  else
    echo "$lib not found in $file."
    return
  fi

  # Compare the current and new versions
  is_version_higher "$new_ver" "$current_ver"
  comparison_result=$?

  if [ "$comparison_result" -eq 0 ]; then
    # Keep the original qualifier and update to the new version if it is higher
    if [[ $current_line =~ ^\"?$lib\"?[[:space:]]*=[[:space:]]*\"?([=><!~]*)?[0-9]+(\.[0-9]+)*\"?$ ]]; then
      new_line="${lib} = \"${current_qualifier}${new_ver}\""
      sed -i -E "s|^\"?$lib\"?[[:space:]]*=[[:space:]]*\"?[=><!~]*[0-9]+(\.[0-9]+)*\"?|${new_line}|" "$file"
    elif [[ $current_line =~ version[[:space:]]*=[[:space:]]*\"?([=><!~]*)?([0-9]+(\.[0-9]+)*)\" ]]; then
      new_line=$(echo "$current_line" | sed -E "s|(version[[:space:]]*=[[:space:]]*\")([=><!~]*[0-9]+(\.[0-9]+)*)\"|\1${current_qualifier}${new_ver}\"|")
      sed -i "s|^$current_line|$new_line|" "$file"
    fi
    echo "Updated $lib in $file to version ${current_qualifier}${new_ver}"

    # Handle renaming and pipenv lock, if necessary
    if [ "$lock_files" == "true" ]; then
      if [ "$is_specific" = true ]; then
        mv "$file" "${directory}/Pipfile"
        mv "${directory}/$lockfile" "${directory}/Pipfile.lock"
        (cd "$directory" && pipenv lock)
        mv "${directory}/Pipfile" "$file"
        mv "${directory}/Pipfile.lock" "${directory}/$lockfile"
      else
        (cd "$directory" && pipenv lock)
      fi
    fi
  else
    echo "$lib in $file is already up-to-date or has a higher version ($current_ver)."
  fi
}

# Function to update the library version in requirements-elyra.txt files, only if the new version is higher
update_library_version_requirements() {
  local file=$1
  local lib=$2
  local new_ver=$3
  local include_paths_with=$4
  local exclude_paths_with=$5
  local directory=$(dirname "$file")
  
  # Check if the file directory has at least one of the substrings (separated by "|") in $include_paths_with 
  # and does not contain any of the substrings (separated by "|") in $exclude_paths_with
  if { [[ -z "$include_paths_with" ]] || [[ "$directory" =~ $include_paths_with ]]; } && { [[ -z "$exclude_paths_with" ]] || [[ ! "$directory" =~ $exclude_paths_with ]]; }; then
    echo "Processing $file (directory matches the pattern)"
  else
    echo "Skipping $file (directory does not match the pattern)"
    return
  fi

  # Extract the current version from the requirements file
  current_line=$(grep -E "^$lib==[0-9]+(\.[0-9]+)*$" "$file")
  if [[ $current_line =~ ^$lib==([0-9]+(\.[0-9]+)*)$ ]]; then
    current_ver="${BASH_REMATCH[1]}"

    # Compare the current and new versions
    is_version_higher "$new_ver" "$current_ver"
    comparison_result=$?

    if [ "$comparison_result" -eq 0 ]; then
      # Update to the new version if it is higher
      new_line="${lib}==${new_ver}"
      sed -i -E "s|^$lib==[0-9]+(\.[0-9]+)*|${new_line}|" "$file"
      echo "Updated $lib in $file to version ${new_ver}"
    else
      echo "$lib in $file is already up-to-date or has a higher version ($current_ver)."
    fi
  else
    echo "$lib not found in $file."
  fi
}

# Export the functions so they are available in the subshell
export -f is_version_higher
export -f update_library_version_pipfile
export -f update_library_version_requirements

# Find and update Pipfile files and requirements-elyra.txt files
find "$directory" -type f \( -name "Pipfile" -o -name "Pipfile.gpu" -o -name "Pipfile.cpu" -o -name "requirements-elyra.txt" \) -exec bash -c '
  file=$0
  lib=$1
  new_ver=$2
  include_paths_with=$3
  exclude_paths_with=$4
  lock_files=$5

  case "$file" in
    *Pipfile* ) update_library_version_pipfile "$file" "$lib" "$new_ver" "$include_paths_with" "$exclude_paths_with" "$lock_files" ;;
    *requirements-elyra.txt* ) update_library_version_requirements "$file" "$lib" "$new_ver" "$include_paths_with" "$exclude_paths_with" ;;
  esac
' {} "$library_name" "$new_version" "$include_paths_with" "$exclude_paths_with" "$lock_files" \;

