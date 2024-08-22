#!/bin/bash

# Check if the script is running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
  echo "Error: This script can only be run on Linux."
  exit 1
fi

# Detailed help message
print_help() {
  echo "Usage: $0 <directory> <libraries> <include_paths_with> <exclude_paths_with> <lock_files>"
  echo
  echo "Parameters:"
  echo "  directory           The root directory to start searching for Pipfile and requirements-elyra.txt files."
  echo "  libraries           JSON formatted array of objects with 'name' and 'version' fields to update."
  echo "  include_paths_with  A pipe-separated list of substrings; only files in directories containing at least one of these substrings will be processed."
  echo "  exclude_paths_with  A pipe-separated list of substrings; files in directories containing any of these substrings will be excluded."
  echo "  lock_files          Whether to run 'pipenv lock' after updating the library version (true or false)."
  echo
  echo "Examples:"
  echo "  $0 ./myproject '[{\"name\": \"numpy\", \"version\": \"2.0.1\"}, {\"name\": \"pandas\", \"version\": \"2.2.2\"}]' '' '' true"
}

# Check if the correct number of arguments are passed
if [ "$#" -ne 5 ]; then
  print_help
  exit 1
fi

# Arguments
directory=$1
libraries_json=$2
include_paths_with=$3
exclude_paths_with=$4
lock_files=$5

# Storage for the directories that need to be locked at the end
files_to_lock_temp_file=$(mktemp)

# Print arguments
echo "Arguments:"
echo "  directory           = $directory"
echo "  libraries           = $libraries_json"
echo "  include_paths_with  = $include_paths_with"
echo "  exclude_paths_with  = $exclude_paths_with"
echo "  lock_files          = $lock_files"

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
  local files_to_lock_temp_file=$7
  local directory=$(dirname "$file")
  local filename=$(basename "$file")

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

    echo "$file" >> "$files_to_lock_temp_file"
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

# Skip double quotes that were not skipped in the libraries parameter
libraries_json=$(echo "$libraries_json" | sed -E 's/(^|[^\\])"/\1\\"/g')

# Find and update Pipfile files and requirements-elyra.txt files
find "$directory" -type f \( -name "Pipfile" -o -name "Pipfile.gpu" -o -name "Pipfile.cpu" -o -name "requirements-elyra.txt" \) -exec bash -c '
  file=$0
  libraries_json=$1
  include_paths_with=$2
  exclude_paths_with=$3
  lock_files=$4
  files_to_lock_temp_file=$5

  echo "'$libraries_json'" | jq -c ".[]" | while IFS= read -r lib_info; do
    lib_name=$(echo "$lib_info" | jq -r ".name")
    lib_version=$(echo "$lib_info" | jq -r ".version")

    case "$file" in
      *Pipfile* ) update_library_version_pipfile "$file" "$lib_name" "$lib_version" "$include_paths_with" "$exclude_paths_with" "$lock_files" "$files_to_lock_temp_file" ;;
      *requirements-elyra.txt* ) update_library_version_requirements "$file" "$lib_name" "$lib_version" "$include_paths_with" "$exclude_paths_with" ;;
    esac
  done
' {} "$libraries_json" "$include_paths_with" "$exclude_paths_with" "$lock_files" "$files_to_lock_temp_file" \;

# Lock the modified files if needed
modified_files=($(cat "$files_to_lock_temp_file"))
rm "$files_to_lock_temp_file"

if [ "$lock_files" == "true" ]; then
  for file in "${modified_files[@]}"; do
    directory=$(dirname "$file")
    filename=$(basename "$file")
    echo "Locking dependencies for $directory..."
    if [[ "$filename" == Pipfile* ]]; then
      if [[ "$filename" == Pipfile.gpu || "$filename" == Pipfile.cpu ]]; then
        mv "$file" "${directory}/Pipfile"
        mv "${directory}/Pipfile.lock.${filename##*.}" "${directory}/Pipfile.lock"
        (cd "$directory" && pipenv lock)
        mv "${directory}/Pipfile" "$file"
        mv "${directory}/Pipfile.lock" "${directory}/Pipfile.lock.${filename##*.}"
      else
        (cd "$directory" && pipenv lock)
      fi
    fi
  done
fi
