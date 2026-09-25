#!/usr/bin/env bash
#
# Interactive wizard: customer-built workbenches + use-case package collections.
# Copies src/ into a sibling folder and applies accelerator / collection choices.
#
set -Eeuo pipefail

WIZARD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/lib/common.sh
source "${WIZARD_ROOT}/src/lib/common.sh"
# shellcheck source=src/lib/generate-recipe.sh
source "${WIZARD_ROOT}/src/lib/generate-recipe.sh"

main() {
  require_tools

  screen_reset
  ui "OpenShift AI — custom workbench builder"
  ui ""
  ui "Uses src/ to create a folder next to it, e.g.:"
  ui "  custom-workbenches/src/"
  ui "  custom-workbenches/my-trustyai/"
  ui ""
  ui "Optional curated collections (TrustyAI, LLM Compressor) install from"
  ui "the Python index instead of specialized OOTB images."
  ui ""
  ui "Before building AIPCC/RHEL images, set up entitlements once:"
  ui "  docs/subscribed-builds.md  (or custom-workbenches/README.md § Recommended workflow)"
  ui "  1) subscription-manager register → entitlement/ + consumer/"
  ui "  2) podman mounts.conf"
  ui "  3) ./interactive-image-builder.sh  then  make build RECIPE=<folder>"
  ui ""
  read -r -p "Press Enter to begin… " _ </dev/tty

  local accel_choice stack_choice base_choice index_choice platform_choice
  local accel_key stack base_kind index_kind platform

  ask_menu accel_choice \
    "Which accelerator base do you need?" \
    "CPU only (no GPU)" \
    "NVIDIA — CUDA 13.0  (recommended for GPU)" \
    "NVIDIA — CUDA 12.9" \
    "AMD — ROCm 7.14"

  case "${accel_choice}" in
    1) accel_key="cpu" ;;
    2) accel_key="cuda_13_0" ;;
    3) accel_key="cuda_12_9" ;;
    4) accel_key="rocm_7_14" ;;
    *) die "Invalid selection" ;;
  esac

  ask_menu stack_choice \
    "Which software stack / package collection?" \
    "Minimal — Jupyter only" \
    "PyTorch — torch + torchvision" \
    "TrustyAI — curated collection (explainability)" \
    "LLM Compressor — curated collection (model compression)"

  case "${stack_choice}" in
    1) stack="minimal" ;;
    2) stack="pytorch" ;;
    3) stack="trustyai" ;;
    4) stack="llmcompressor" ;;
    *) die "Invalid selection" ;;
  esac

  if [[ "${stack}" == "llmcompressor" && "${accel_key}" == "cpu" ]]; then
    ui ""
    ui "LLM Compressor usually needs CUDA. Continuing with CPU may limit usability."
    read -r -p "Press Enter to continue… " _ </dev/tty
  fi

  ask_menu base_choice \
    "Which base OS image?" \
    "CentOS Stream 9 (ODH / quay.io/opendatahub bases — no RHSM)" \
    "AIPCC RHEL 9.8 (RHOAI — requires entitlements; see README)"

  case "${base_choice}" in
    1) base_kind="odh" ;;
    2)
      base_kind="aipcc"
      ui ""
      ui "AIPCC builds need entitlement certs mounted (register + mounts.conf)."
      ui "If you have not done that yet, stop after generate and follow:"
      ui "  custom-workbenches/README.md → Recommended workflow §1"
      ui "  or docs/subscribed-builds.md"
      read -r -p "Press Enter to continue… " _ </dev/tty
      ;;
    *) die "Invalid selection" ;;
  esac

  # Collections prefer AIPCC index when selected
  local index_default=1
  if [[ "${stack}" == "trustyai" || "${stack}" == "llmcompressor" ]]; then
    index_default=2
  fi

  ask_menu index_choice \
    "Where should Python packages come from?" \
    "${index_default}" \
    "PyPI — public pypi.org" \
    "AIPCC / Red Hat index — curated RH wheels (recommended for collections)"

  case "${index_choice}" in
    1) index_kind="pypi" ;;
    2) index_kind="aipcc" ;;
    *) die "Invalid selection" ;;
  esac

  if [[ "${index_default}" -eq 2 && "${index_kind}" == "pypi" ]]; then
    ui ""
    ui "Note: TrustyAI / LLM Compressor collections are validated against the RH index."
    read -r -p "Press Enter to continue with PyPI… " _ </dev/tty
  fi

  ask_menu platform_choice \
    "Which CPU architecture should the image target?" \
    "linux/amd64 (x86_64) — most common" \
    "linux/arm64 (aarch64)" \
    "linux/ppc64le" \
    "linux/s390x"

  case "${platform_choice}" in
    1) platform="linux/amd64" ;;
    2) platform="linux/arm64" ;;
    3) platform="linux/ppc64le" ;;
    4) platform="linux/s390x" ;;
    *) die "Invalid selection" ;;
  esac

  if [[ "${accel_key}" == "rocm_7_14" && "${platform}" != "linux/amd64" ]]; then
    ui ""
    ui "Note: ROCm is typically validated on linux/amd64 only."
    read -r -p "Press Enter to continue… " _ </dev/tty
  fi

  screen_reset
  ui "Quay registry and folder name"
  ui ""

  local quay_org_raw quay_org quay_repo_raw quay_repo image_tag
  local default_folder image_name_raw image_name image_ref extra
  local accel_slug

  case "${accel_key}" in
    cpu) accel_slug="cpu" ;;
    cuda_13_0) accel_slug="cuda" ;;
    cuda_12_9) accel_slug="cuda129" ;;
    rocm_7_14) accel_slug="rocm" ;;
    *) accel_slug="${accel_key}" ;;
  esac
  default_folder="my-${stack}-${accel_slug}"
  prompt_var quay_org_raw "What is your Quay organization or username?  quay.io/" "MY-ORG"
  quay_org=$(normalize_quay_org "${quay_org_raw}")
  [[ -n "${quay_org}" ]] || die "Quay organization/username cannot be empty."

  ui ""
  prompt_var quay_repo_raw "What is your repository name?  quay.io/${quay_org}/" "${default_folder}"
  quay_repo=$(normalize_quay_repo "${quay_repo_raw}" "${quay_org}")
  [[ -n "${quay_repo}" ]] || die "Repository name cannot be empty."

  ui ""
  prompt_var image_tag "Image tag" "latest"
  image_tag="${image_tag#:}"
  image_ref="quay.io/${quay_org}/${quay_repo}:${image_tag}"

  ui ""
  prompt_var image_name_raw "Local folder name (next to src/)" "$(sanitize_name "${quay_repo}")"
  image_name=$(sanitize_name "${image_name_raw}")
  [[ -n "${image_name}" ]] || die "Folder name cannot be empty."
  if is_reserved_name "${image_name}"; then
    die "Folder name '${image_name}' is reserved. Choose another name (not: ${RESERVED_NAMES[*]})."
  fi
  prompt_var extra "Extra pip packages, unpinned (optional, space-separated)" ""

  ui ""
  ui "Will create:  custom-workbenches/${image_name}/"
  ui "Stack:        ${stack}"
  ui "Image:        ${image_ref}"
  ui "Platform:     ${platform}"
  ui "Base / index: ${base_kind} / ${index_kind}"
  ui ""
  read -r -p "Press Enter to generate… " _ </dev/tty

  screen_reset
  ui "Writing ${image_name}/ from src/…"
  ui ""

  local out_dir
  out_dir=$(generate_recipe \
    "${accel_key}" "${stack}" "${base_kind}" "${index_kind}" \
    "${platform}" "${image_name}" "${image_ref}" "${extra}" "")

  screen_reset
  ui "Custom image ready"
  ui ""
  ui "  ${out_dir}"
  ui ""
  ui "Build / push / validate (from custom-workbenches/):"
  ui "  make build    RECIPE=${image_name} PUSH_IMAGES=no"
  ui "  make validate RECIPE=${image_name}"
  ui "  make push     RECIPE=${image_name}"
  if [[ "${base_kind}" == "aipcc" ]]; then
    ui ""
    ui "AIPCC: entitlements must be set up before make build (README § Recommended workflow)."
  fi
  ui ""
  ui "Discover collections:  make collections"
  ui "Import: Settings → Workbench images → ${image_ref}"
  ui ""
  ui "Details: ${out_dir}/README.md"
  ui ""
}

main "$@"
