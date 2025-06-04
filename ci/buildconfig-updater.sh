local file_path=$1
local version=$2

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

while IFS= read -r line; do
  if [[ "$line" == *"ref: rhoai-"* ]]; then
    if [[ -z "$version" ]]; then
      # Auto-increment minor version
      version_current="${line##*rhoai-}"
      IFS='.' read -r major minor <<< "$version_current"
      minor=$((minor + 1))
      echo "      ref: rhoai-${major}.${minor}" >> "$tmpfile"
    else
      # Use provided version
      echo "      ref: rhoai-${version}" >> "$tmpfile"
    fi
  else
    echo "$line" >> "$tmpfile"
  fi
done < "$file_path"

# Replace original file atomically
mv "$tmpfile" "$file_path"