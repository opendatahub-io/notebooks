#!/usr/bin/env bash
# Classify paths under site-packages by type + mode vs find -perm -g+w (chmod-gw-count logic).
set -Eeuo pipefail

target="${1:-/opt/app-root/lib/python3.12/site-packages}"
if [[ ! -d "${target}" ]]; then
  echo "missing: ${target}" >&2
  exit 1
fi

echo "BUILD_PROFILE_MODE_ANALYSIS target=${target}"
echo "BUILD_PROFILE_MODE_ANALYSIS uid=$(id -u) gid=$(id -g) umask=$(umask)"

# find -perm -g+w: all group read+write bits set (GNU find)
total=$(find -L "${target}" | wc -l | tr -d ' ')
has_gw=$(find -L "${target}" -perm -g+w | wc -l | tr -d ' ')
lacks_gw=$(find -L "${target}" ! -perm -g+w | wc -l | tr -d ' ')
echo "BUILD_PROFILE_MODE_ANALYSIS total=${total} has_gw_perm=${has_gw} lacks_gw_perm=${lacks_gw}"

for label type perm_expr in \
  "file_644" "-type f" "-perm 644" \
  "file_664" "-type f" "-perm 664" \
  "file_775" "-type f" "-perm 775" \
  "file_other" "-type f" "! -perm 644 ! -perm 664 ! -perm 775" \
  "dir_755" "-type d" "-perm 755" \
  "dir_775" "-type d" "-perm 775" \
  "dir_other" "-type d" "! -perm 755 ! -perm 775" \
  "symlink" "-type l" "" \
  "other_type" "! -type f ! -type d ! -type l" ""; do
  # shellcheck disable=SC2086
  n=$(find -L "${target}" ${type} ${perm_expr} 2>/dev/null | wc -l | tr -d ' ')
  echo "BUILD_PROFILE_MODE_ANALYSIS bucket=${label} count=${n}"
done

echo "BUILD_PROFILE_MODE_ANALYSIS lacks_gw_by_type:"
for t in f d l; do
  n=$(find -L "${target}" ! -perm -g+w -type "${t}" 2>/dev/null | wc -l | tr -d ' ')
  echo "BUILD_PROFILE_MODE_ANALYSIS lacks_gw type=${t} count=${n}"
done

echo "BUILD_PROFILE_MODE_ANALYSIS sample_lacks_gw (first 15):"
find -L "${target}" ! -perm -g+w 2>/dev/null | head -15 | while read -r p; do
  stat -c 'BUILD_PROFILE_MODE_ANALYSIS sample %F %a %u:%g %n' "${p}" 2>/dev/null || ls -la "${p}"
done

# Cross-check: files with octal 664 but still ! -perm -g+w (should be zero)
n664_lacks=$(find -L "${target}" -type f -perm 664 ! -perm -g+w 2>/dev/null | wc -l | tr -d ' ')
echo "BUILD_PROFILE_MODE_ANALYSIS file_664_but_lacks_gw_perm=${n664_lacks}"
