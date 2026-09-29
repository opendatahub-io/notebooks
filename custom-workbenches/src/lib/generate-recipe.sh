#!/usr/bin/env bash
# Copy src/ template into a sibling custom-image folder and apply wizard choices.

set -Eeuo pipefail

append_pyproject_deps() {
  local pyproject="$1"
  shift
  local pkg
  [[ $# -eq 0 ]] && return 0
  for pkg in "$@"; do
    [[ -z "${pkg}" ]] && continue
    awk -v pkg="${pkg}" '
      BEGIN { in_deps=0 }
      /^dependencies = \[/ { in_deps=1 }
      in_deps && /^]/ {
        printf "    \"%s\",\n", pkg
        in_deps=0
      }
      { print }
    ' "${pyproject}" >"${pyproject}.tmp"
    mv "${pyproject}.tmp" "${pyproject}"
  done
}

write_requirements_from_pyproject() {
  local pyproject="$1"
  local requirements="$2"
  python3 - <<'PY' "${pyproject}" "${requirements}"
import sys
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

data = tomllib.loads(Path(sys.argv[1]).read_text())
deps = data.get("project", {}).get("dependencies", [])
Path(sys.argv[2]).write_text("\n".join(deps) + ("\n" if deps else ""))
PY
}

# Print a string-array field from collection.toml (packages, constraints, conflicts_with).
collection_field() {
  local collection_toml="$1"
  local field="$2"
  python3 - <<'PY' "${collection_toml}" "${field}"
import sys
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

data = tomllib.loads(Path(sys.argv[1]).read_text())
field = sys.argv[2]
vals = data.get(field)
if vals is None:
    vals = data.get("collection", {}).get(field, [])
for item in vals or []:
    print(item)
PY
}

collection_packages() {
  collection_field "$1" packages
}

list_collections() {
  local d id name desc
  [[ -d "${SRC_DIR}/collections" ]] || return 0
  for d in "${SRC_DIR}/collections"/*/collection.toml; do
    [[ -f "${d}" ]] || continue
    id="$(basename "$(dirname "${d}")")"
    name="$(python3 -c "import tomllib,pathlib; print(tomllib.loads(pathlib.Path('${d}').read_text())['collection']['name'])" 2>/dev/null || echo "${id}")"
    desc="$(python3 -c "import tomllib,pathlib; print(tomllib.loads(pathlib.Path('${d}').read_text())['collection'].get('description',''))" 2>/dev/null || true)"
    printf '%s\t%s\t%s\n' "${id}" "${name}" "${desc}"
  done
}

apply_collection() {
  local output_dir="$1"
  local collection_id="$2"
  local applied_csv="$3"
  local collection_dir="${SRC_DIR}/collections/${collection_id}"
  local collection_toml="${collection_dir}/collection.toml"
  local pkg conflict dest

  [[ -f "${collection_toml}" ]] || die "Unknown collection: ${collection_id} (expected ${collection_toml})"

  while IFS= read -r conflict; do
    [[ -n "${conflict}" ]] || continue
    if [[ ",${applied_csv}," == *",${conflict},"* ]]; then
      die "Collection '${collection_id}' conflicts with '${conflict}' (incompatible numpy/pandas ABI). Build two images, or install one collection in an isolated venv — do not share site-packages."
    fi
  done < <(collection_field "${collection_toml}" conflicts_with)

  dest="${output_dir}/collections/${collection_id}"
  mkdir -p "${dest}"
  cp "${collection_toml}" "${dest}/"
  if [[ -f "${collection_dir}/validate.py" ]]; then
    cp "${collection_dir}/validate.py" "${dest}/"
  fi

  : >"${dest}/constraints.txt"
  while IFS= read -r pkg; do
    [[ -n "${pkg}" ]] || continue
    echo "${pkg}" >>"${dest}/constraints.txt"
  done < <(collection_field "${collection_toml}" constraints)

  while IFS= read -r pkg; do
    [[ -n "${pkg}" ]] || continue
    append_pyproject_deps "${output_dir}/pyproject.toml" "${pkg}"
  done < <(collection_packages "${collection_toml}")
}

generate_recipe() {
  local accel_key="$1"
  local stack="$2"           # minimal | pytorch | trustyai | llmcompressor
  local base_kind="$3"
  local index_kind="$4"
  local platform="$5"
  local image_name="$6"
  local image_ref="$7"
  local extra_packages="$8"
  local collections="${9:-}" # space-separated collection ids (optional extra)

  local base_image index_url flavor product conf_name
  local output_dir template_conf collection_id applied_collections=()

  case "${accel_key}" in
    cpu) flavor="cpu" ;;
    cuda_13_0 | cuda_12_9) flavor="cuda" ;;
    rocm_7_14) flavor="rocm" ;;
    *) die "Unknown accelerator: ${accel_key}" ;;
  esac

  if is_reserved_name "${image_name}"; then
    die "Folder name '${image_name}' is reserved. Choose another name (not: ${RESERVED_NAMES[*]})."
  fi

  case "${base_kind}" in
    odh)
      product="odh"
      case "${accel_key}" in
        cpu) base_image="${odh_cpu_BASE_IMAGE:-quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest}" ;;
        cuda_13_0) base_image="${odh_cuda_13_0_BASE_IMAGE}" ;;
        cuda_12_9) base_image="${odh_cuda_12_9_BASE_IMAGE}" ;;
        rocm_7_14) base_image="${odh_rocm_7_14_BASE_IMAGE}" ;;
      esac
      ;;
    aipcc)
      product="rhoai"
      case "${accel_key}" in
        cpu) base_image="${aipcc_cpu_BASE_IMAGE:-quay.io/aipcc/base-images/cpu-el9.8:latest}" ;;
        cuda_13_0) base_image="${aipcc_cuda_13_0_BASE_IMAGE}" ;;
        cuda_12_9) base_image="${aipcc_cuda_12_9_BASE_IMAGE}" ;;
        rocm_7_14) base_image="${aipcc_rocm_7_14_BASE_IMAGE}" ;;
      esac
      ;;
    *) die "Unknown base kind: ${base_kind}" ;;
  esac

  case "${index_kind}" in
    pypi) index_url="${pypi_INDEX_URL}" ;;
    aipcc)
      case "${accel_key}" in
        cpu) index_url="${aipcc_cpu_INDEX_URL:-https://packages.redhat.com/api/pypi/public-rhai/rhoai/cpu-ubi9/simple/}" ;;
        cuda_13_0) index_url="${aipcc_cuda_13_0_INDEX_URL}" ;;
        cuda_12_9) index_url="${aipcc_cuda_12_9_INDEX_URL}" ;;
        rocm_7_14) index_url="${aipcc_rocm_7_14_INDEX_URL}" ;;
      esac
      ;;
    *) die "Unknown index kind: ${index_kind}" ;;
  esac

  conf_name="${flavor}.conf"
  template_conf="${SRC_DIR}/build-args/${conf_name}"
  [[ -f "${template_conf}" ]] || die "Missing template conf: ${template_conf}"
  [[ -f "${SRC_DIR}/Containerfile" ]] || die "Missing ${SRC_DIR}/Containerfile"

  output_dir="${WIZARD_ROOT}/${image_name}"

  rm -rf "${output_dir}"
  mkdir -p "${output_dir}/build-args" "${output_dir}/bin/utils" "${output_dir}/collections"

  cp "${SRC_DIR}/Containerfile" "${output_dir}/Containerfile"
  cp "${SRC_DIR}/pyproject.toml" "${output_dir}/pyproject.toml"
  mkdir -p "${output_dir}/repos"
  cp "${SRC_DIR}/repos/openshift-clients.repo" "${output_dir}/repos/openshift-clients.repo"
  cp "${SRC_DIR}/bin/entrypoint.sh" "${output_dir}/bin/entrypoint.sh"
  chmod 0755 "${output_dir}/bin/entrypoint.sh"
  cp "${SRC_DIR}/collections/README.md" "${output_dir}/collections/README.md"

  cp "${REPO_ROOT}/jupyter/minimal/ubi9-python-3.12/start-notebook.sh" "${output_dir}/bin/start-notebook.sh"
  chmod 0755 "${output_dir}/bin/start-notebook.sh"
  cp -a "${REPO_ROOT}/jupyter/utils/." "${output_dir}/bin/utils/"
  cp "${REPO_ROOT}/jupyter/datascience/ubi9-python-3.12/setup-elyra.sh" "${output_dir}/bin/utils/"
  chmod 0755 "${output_dir}/bin/utils/setup-elyra.sh"
  cp "${REPO_ROOT}/prefetch-input/elyra-v4.3.1/elyra/kfp/bootstrapper.py" "${output_dir}/bin/utils/"
  cp "${REPO_ROOT}/base-images/utils/ensure-openshift-site-packages.sh" "${output_dir}/bin/"
  chmod 0755 "${output_dir}/bin/ensure-openshift-site-packages.sh"

  # Stack maps to optional curated collections (RHAIENG-7241 §3)
  case "${stack}" in
    minimal) ;;
    pytorch | trustyai | llmcompressor)
      apply_collection "${output_dir}" "${stack}" ""
      applied_collections+=("${stack}")
      ;;
    *)
      die "Unknown stack: ${stack}"
      ;;
  esac

  # Additional collections — rejected if constraints/ABI conflict
  if [[ -n "${collections}" ]]; then
    # shellcheck disable=SC2086
    for collection_id in ${collections}; do
      [[ " ${applied_collections[*]} " == *" ${collection_id} "* ]] && continue
      apply_collection "${output_dir}" "${collection_id}" "$(IFS=,; echo "${applied_collections[*]}")"
      applied_collections+=("${collection_id}")
    done
  fi

  if [[ -n "${extra_packages}" ]]; then
    # shellcheck disable=SC2086
    append_pyproject_deps "${output_dir}/pyproject.toml" ${extra_packages}
  fi
  write_requirements_from_pyproject "${output_dir}/pyproject.toml" "${output_dir}/requirements.txt"

# Always produce constraints.txt (pip -c). Empty/comment-only is fine for minimal.
python3 "${SRC_DIR}/lib/merge-constraints.py" "${output_dir}/constraints.txt" \
  "${output_dir}"/collections/*/constraints.txt

  local collections_csv=""
  if ((${#applied_collections[@]} > 0)); then
    collections_csv=$(IFS=,; echo "${applied_collections[*]}")
  fi

  cat >"${output_dir}/build-args/${conf_name}" <<EOF
# Generated from src/build-args/${conf_name} by interactive-image-builder.sh
# Edit freely — make build reads KEY=VALUE as podman --build-arg.

BASE_IMAGE=${base_image}
INDEX_URL=${index_url}
INDEX_KIND=${index_kind}
PRODUCT=${product}
ACCELERATOR=${flavor}
ACCEL_KEY=${accel_key}
STACK=${stack}
COLLECTIONS=${collections_csv}
PLATFORM=${platform}
IMAGE_REF=${image_ref}
LABEL_COMPONENT=custom-workbench-${flavor}-py312
RELEASE=custom
EOF
  ln -sfn "${conf_name}" "${output_dir}/build-args/default.conf"

  export RECIPE_NAME="${image_name}"
  export IMAGE_REF="${image_ref}"
  export BASE_IMAGE="${base_image}"
  export INDEX_URL="${index_url}"
  export INDEX_KIND="${index_kind}"
  export PRODUCT="${product}"
  export PLATFORM="${platform}"
  export ACCEL_KEY="${accel_key}"
  export STACK="${stack}"
  export CONF_NAME="${conf_name}"
  export COLLECTIONS="${collections_csv:-none}"

  envsubst '${RECIPE_NAME} ${IMAGE_REF} ${BASE_IMAGE} ${INDEX_URL} ${INDEX_KIND} ${PRODUCT} ${PLATFORM} ${ACCEL_KEY} ${STACK} ${CONF_NAME} ${COLLECTIONS}' \
    <"${SRC_DIR}/recipe-README.md.in" >"${output_dir}/README.md"

  envsubst '${IMAGE_REF} ${RECIPE_NAME} ${STACK} ${ACCEL_KEY}' \
    <"${SRC_DIR}/imagestream.yaml.in" >"${output_dir}/imagestream.yaml"

  echo "${output_dir}"
}
