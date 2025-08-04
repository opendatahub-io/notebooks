#!/bin/sh

# get_matched_files finds file for image extending
get_matched_files() {
  custom_dir="$1"
  default_dir="$2"
  files_matched="$3"
  find "$default_dir" -maxdepth 1 -type f -name "$files_matched" -printf "%f\n"
  [ -d "$custom_dir" ] && find "$custom_dir" -maxdepth 1 -type f -name "$files_matched" -printf "%f\n"
}

# process_extending_files process extending files in $1 and $2 directories
# - source all *.sh files
#   (if there are files with same name source only file from $1)
process_extending_files() {
  custom_dir=$1
  default_dir=$2
 get_matched_files "$custom_dir" "$default_dir" '*.sh' | sort -u | while read -r filename; do
  if [ "$filename" ]; then
    echo "=> sourcing $filename ..."
    if [ -f "$custom_dir/$filename" ]; then
      . "$custom_dir/$filename"
    elif [ -f "$default_dir/$filename" ]; then 
      . "$default_dir/$filename"
    fi
  fi
done
}