#!/usr/bin/env bash
# Compare dnf-helper install timings inside a hermetic build context.
set -Eeuxo pipefail

DNF_HELPER="${DNF_HELPER:-/utils/dnf-helper.sh}"
REPO_RPM_COUNT="${REPO_RPM_COUNT:-unknown}"

echo "BUILD_PROFILE_DNF repo_rpm_count=${REPO_RPM_COUNT}"

# cpu-base package set (jupyter/minimal cpu-base stage)
CPU_BASE_PKGS=(perl mesa-libGL skopeo compat-openssl11 openshift-clients)

echo "=== dnf benchmark: cpu-base packages (${#CPU_BASE_PKGS[@]}) ==="
/usr/local/bin/profile-step.sh dnf_cpu_base bash "${DNF_HELPER}" install "${CPU_BASE_PKGS[@]}"

echo "=== dnf benchmark: install_pdf_deps (texlive + pandoc) ==="
/usr/local/bin/profile-step.sh dnf_pdf_deps ./utils/install_pdf_deps.sh

# Optional: explicit rpm install of same cpu-base set (no solver) when RPM paths exist
RPM_DIR="/cachi2/output/deps/rpm/${RPM_ARCH:-x86_64}"
if [[ -d "${RPM_DIR}" ]]; then
  count=$(find "${RPM_DIR}" -name '*.rpm' | wc -l | tr -d ' ')
  export REPO_RPM_COUNT="${count}"
  mapfile -t rpm_files < <(
    for pkg in "${CPU_BASE_PKGS[@]}"; do
      find "${RPM_DIR}" -name "${pkg}-*.rpm" -print | head -1
    done
  )
  missing=0
  for f in "${rpm_files[@]}"; do
    [[ -n "${f}" && -f "${f}" ]] || missing=$((missing + 1))
  done
  if [[ "${missing}" -eq 0 && "${#rpm_files[@]}" -gt 0 ]]; then
    echo "=== rpm -Uvh benchmark: cpu-base explicit RPMs (${#rpm_files[@]}) ==="
    /usr/local/bin/profile-step.sh rpm_uvh_cpu_base rpm -Uvh --noscripts "${rpm_files[@]}"
  else
    echo "BUILD_PROFILE_DNF skip_rpm_uvh reason=missing_rpm_files missing=${missing}"
  fi
else
  echo "BUILD_PROFILE_DNF skip_rpm_uvh reason=no_rpm_dir"
fi
