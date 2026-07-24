# https://stackoverflow.com/questions/18136918/how-to-get-current-relative-directory-of-your-makefile
ROOT_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))
SELF ::= $(firstword $(MAKEFILE_LIST))

# https://tech.davis-hansson.com/p/make/
SHELL := bash
.ONESHELL:
# http://redsymbol.net/articles/unofficial-bash-strict-mode/
# https://vaneyckt.io/posts/safer_bash_scripts_with_set_euxo_pipefail/
.SHELLFLAGS := -Eeux -o pipefail -c
.DELETE_ON_ERROR:
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules
# Used where we need an empty expansion (avoids undefined variable warning).
empty :=

# todo: leave the default recipe prefix for now
ifeq ($(origin .RECIPEPREFIX), undefined)
$(error This Make does not support .RECIPEPREFIX. Please use GNU Make 4.0 or later)
endif
.RECIPEPREFIX =

IMAGE_REGISTRY   ?= quay.io/opendatahub/workbench-images
RELEASE	 		 ?= 3.5
RELEASE_PYTHON_VERSION	 ?= 3.12
# additional user-specified caching parameters for $(CONTAINER_ENGINE) build
CONTAINER_BUILD_CACHE_ARGS ?= --no-cache
# security options for podman (label=disable fixes permission denied on macOS rootful)
CONTAINER_BUILD_SECURITY_ARGS ?= $(if $(filter podman,$(CONTAINER_ENGINE)),--security-opt label=disable,)
# whether to push the images to a registry as they are built
PUSH_IMAGES ?= yes
# INDEX_MODE: auto (default), public-index, or rh-index - controls lock file generation
INDEX_MODE ?= auto
# PRODUCT: select ODH (odh) vs RHOAI (rhoai) build-args conf files
PRODUCT ?= odh
ifneq ($(filter odh rhoai,$(PRODUCT)),$(PRODUCT))
$(error PRODUCT must be 'odh' or 'rhoai', got '$(PRODUCT)')
endif


# OS dependant: Generate date, select appropriate cmd to locate container engine
ifdef OS
	ifeq ($(OS), Windows_NT)
		DATE 		?= $(shell powershell -Command "Get-Date -Format 'yyyyMMdd'")
		WHERE_WHICH ?= where
	endif
endif
DATE 		?= $(shell date +'%Y%m%d')
WHERE_WHICH ?= which


# linux/amd64 or darwin/arm64
OS_ARCH=$(shell go env GOOS)/$(shell go env GOARCH)
BUILD_ARCH ?= linux/amd64
# Map OCI platform arch to RPM arch (e.g. linux/amd64 → x86_64, linux/arm64 → aarch64)
RPM_ARCH := $(subst amd64,x86_64,$(subst arm64,aarch64,$(lastword $(subst /, ,$(BUILD_ARCH)))))

IMAGE_TAG		 ?= $(RELEASE)_$(DATE)
KUBECTL_BIN      ?= bin/kubectl
KUBECTL_VERSION  ?= v1.23.11
YQ_BIN      ?= bin/yq
YQ_VERSION  ?= v4.44.6
NOTEBOOK_REPO_BRANCH_BASE ?= https://raw.githubusercontent.com/opendatahub-io/notebooks/main
REQUIRED_RUNTIME_IMAGE_COMMANDS="curl python3"
REQUIRED_CODE_SERVER_IMAGE_COMMANDS="curl python oc code-server"

# Detect and select the system's available container engine
ifeq (, $(shell $(WHERE_WHICH) podman))
	DOCKER := $(shell $(WHERE_WHICH) docker)
	ifeq (, $(DOCKER))
		$(error "Neither Docker nor Podman is installed. Please install one of them.")
	endif
	CONTAINER_ENGINE := docker
else
	CONTAINER_ENGINE := podman
endif

# Build function for the notebook image:
#   ARG 1: Image tag name.
#   ARG 2: Path of Dockerfile we want to build.
#   ARG 3: Path of the build-args conf file to use.
define build_image
	$(eval IMAGE_NAME := $(IMAGE_REGISTRY):$(1)-$(IMAGE_TAG))

	# Checks if there’s a build-args/*.conf matching the Dockerfile
	$(eval BUILD_DIR := $(dir $(2)))
	$(eval DOCKERFILE_NAME := $(notdir $(2)))
	$(eval CONF_FILE := $(3))

	# if the conf file exists, transform it into quoted --build-arg flags
	# NOTE: lines must match KEY=VALUE; single quotes in values are escaped
	$(eval _BUILD_ARGS_OUT := $(shell \
		if [ -f '$(CONF_FILE)' ]; then \
			awk '!/^[[:space:]]*#/ && NF { \
				gsub(/^[[:space:]]+|[[:space:]]+$$/, ""); \
				if (!/^[A-Za-z_][A-Za-z0-9_]*=/) { \
					printf "ERROR: malformed conf line (expected KEY=VALUE): %s\n", $$0 > "/dev/stderr"; \
					err=1; next; \
				} \
				gsub(/\047/, "\047\\\047\047"); \
				out = out sprintf("--build-arg \047%s\047 ", $$0); \
			} END { if (err) { printf "PARSE_FAILED"; exit 1 } else { printf "%s", out } }' '$(CONF_FILE)'; \
		fi))
	$(if $(findstring PARSE_FAILED,$(_BUILD_ARGS_OUT)),$(error Failed to parse $(CONF_FILE) — see stderr for details))
	$(eval BUILD_ARGS := $(_BUILD_ARGS_OUT))

# Hermetic local build: when cachi2/output/ exists AND this target uses a
# prefetch-input tree, mount pre-downloaded deps into the build.
# Some images (e.g. jupyter/minimal, datascience, pytorch+llmcompressor)
# reference repo-root prefetch-input/ in their Dockerfiles without having
# a local prefetch-input/ directory (symlinks were removed to work around
# Konflux Hermeto rejecting symlink segments in git submodule paths).
# The repos.d mount overlays /etc/yum.repos.d/ with hermeto-generated repos,
# making local builds behave like Konflux (repos already in place when the
# Dockerfile runs). The mount hides the base image's default repos.
# Konflux buildah-oci-ta task mounts YUM_REPOS_D_FETCHED at YUM_REPOS_D_TARGET (/etc/yum.repos.d).
# See https://github.com/konflux-ci/build-definitions/blob/main/task/buildah-oci-ta/
$(eval _DOCKERFILE_USES_PREFETCH := $(shell grep -q 'prefetch-input/' $(2) 2>/dev/null && echo yes))
$(eval PREFETCH_INPUT_DIR := $(or $(wildcard $(BUILD_DIR)prefetch-input),$(if $(_DOCKERFILE_USES_PREFETCH),$(wildcard $(ROOT_DIR)prefetch-input),)))
$(eval CACHI2_VOLUME := $(if $(and $(wildcard cachi2/output),$(PREFETCH_INPUT_DIR)),\
	--volume $(ROOT_DIR)cachi2/output:/cachi2/output:Z \
	--volume $(ROOT_DIR)cachi2/output/deps/rpm/$(RPM_ARCH)/repos.d/:/etc/yum.repos.d/:Z,))
	$(info # Building $(IMAGE_NAME) using $(DOCKERFILE_NAME) with $(CONF_FILE) and $(BUILD_ARGS)...)

	@if [ -n '$(PREFETCH_INPUT_DIR)' ] && [ ! -d cachi2/output ]; then \
	  echo "Prefetch required for hermetic build. Run: scripts/lockfile-generators/prefetch-all.sh --component-dir $(patsubst %/,%,$(BUILD_DIR)) -- see scripts/lockfile-generators/README.md"; \
	  exit 1; \
	fi
	@if [ -d cachi2/output ] && [ -n '$(PREFETCH_INPUT_DIR)' ] && [ ! -d 'cachi2/output/deps/rpm/$(RPM_ARCH)/repos.d' ]; then \
	  echo "Missing RPM repos for $(RPM_ARCH). Re-run: scripts/lockfile-generators/prefetch-all.sh --component-dir $(patsubst %/,%,$(BUILD_DIR))"; \
	  exit 1; \
	fi
	$(ROOT_DIR)/scripts/sandbox.py --dockerfile '$(2)' --platform '$(BUILD_ARCH)' -- \
		$(CONTAINER_ENGINE) build $(CONTAINER_BUILD_SECURITY_ARGS) $(CONTAINER_BUILD_CACHE_ARGS) $(CACHI2_VOLUME) --platform=$(BUILD_ARCH) --label release=$(RELEASE) --tag $(IMAGE_NAME) --file '$(2)' $(BUILD_ARGS) {}\;
endef

# Push function for the notebook image:
# 	ARG 1: Path of image context we want to build.
define push_image
	$(eval IMAGE_NAME := $(IMAGE_REGISTRY):$(subst /,-,$(1))-$(IMAGE_TAG))
	$(info # Pushing $(IMAGE_NAME) image...)
	DIGEST_FILE=$$(mktemp)
	$(CONTAINER_ENGINE) push --digestfile="$${DIGEST_FILE}" $(IMAGE_NAME)
	echo "# Pushed $(IMAGE_NAME)@$$(cat $${DIGEST_FILE})"
	rm -f "$${DIGEST_FILE}"
endef

# Build and push the notebook images:
#   ARG 1: Image tag name.
#   ARG 2: Path of Dockerfile we want to build.
#
# PUSH_IMAGES: allows skipping podman push
define image
	$(eval BUILD_DIRECTORY := $(shell echo $(2) | sed 's/\/Dockerfile.*//'))
	$(eval VARIANT := $(shell echo $(notdir $(2)) | awk -F. '{print $$NF}'))
	$(eval DOCKERFILE := $(BUILD_DIRECTORY)/Dockerfile.konflux.$(VARIANT))
	$(if $(wildcard $(DOCKERFILE)),,$(error Dockerfile not found for variant '$(VARIANT)' in '$(BUILD_DIRECTORY)'))

	$(eval CONF_FILE := $(BUILD_DIRECTORY)/build-args/$(if $(filter rhoai,$(PRODUCT)),konflux.,)$(shell echo $(VARIANT)).conf)
	$(info #*# Image build Dockerfile: <$(DOCKERFILE)> #(MACHINE-PARSED LINE)#*#...)
	$(info #*# Image build directory: <$(BUILD_DIRECTORY)> #(MACHINE-PARSED LINE)#*#...)

	$(call build_image,$(1),$(DOCKERFILE),$(CONF_FILE))

	$(if $(PUSH_IMAGES:no=),
		$(call push_image,$(1))
	)
endef

#######################################        Build helpers                 #######################################

# https://stackoverflow.com/questions/78899903/how-to-create-a-make-target-which-is-an-implicit-dependency-for-all-other-target
skip-init-for := all-images deploy% undeploy% test% validate% refresh-lock-files sync-build-args-from-versions sync-commit-env-files update-imagestream-annotations refresh-imagestream-metadata scan-image-vulnerabilities print-release
# CI uses the pre-built container image via buildinputs_runner.py instead
ifneq ($(CI),true)
ifneq (,$(filter-out $(skip-init-for),$(MAKECMDGOALS) $(.DEFAULT_GOAL)))
$(SELF): bin/buildinputs
endif
endif

bin/buildinputs: scripts/buildinputs/buildinputs.go scripts/buildinputs/go.mod scripts/buildinputs/go.sum
	$(info Building a Go helper for Dockerfile dependency analysis...)
	GOTOOLCHAIN=auto GONOSUMDB=golang.org/toolchain \
	  go build -C "scripts/buildinputs" -o "$(ROOT_DIR)/$@" ./...

####################################### Buildchain for Python using ubi9 #####################################

.PHONY: jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION)
jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,jupyter/minimal/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cpu)

.PHONY: jupyter-datascience-ubi9-python-$(RELEASE_PYTHON_VERSION)
jupyter-datascience-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,jupyter/datascience/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cpu)

.PHONY: cuda-jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION)
cuda-jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,jupyter/minimal/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cuda)

.PHONY: cuda-jupyter-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION)
cuda-jupyter-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,jupyter/tensorflow/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cuda)

.PHONY: cuda-jupyter-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION)
cuda-jupyter-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,jupyter/pytorch/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cuda)

.PHONY: cuda-jupyter-pytorch-llmcompressor-ubi9-python-$(RELEASE_PYTHON_VERSION)
cuda-jupyter-pytorch-llmcompressor-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,jupyter/pytorch+llmcompressor/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cuda)

.PHONY: jupyter-trustyai-ubi9-python-$(RELEASE_PYTHON_VERSION)
jupyter-trustyai-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,jupyter/trustyai/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cpu)

.PHONY: runtime-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION)
runtime-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,runtimes/minimal/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cpu)

.PHONY: runtime-datascience-ubi9-python-$(RELEASE_PYTHON_VERSION)
runtime-datascience-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,runtimes/datascience/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cpu)

.PHONY: runtime-cuda-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION)
runtime-cuda-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,runtimes/pytorch/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cuda)

.PHONY: runtime-cuda-pytorch-llmcompressor-ubi9-python-$(RELEASE_PYTHON_VERSION)
runtime-cuda-pytorch-llmcompressor-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,runtimes/pytorch+llmcompressor/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cuda)

.PHONY: runtime-cuda-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION)
runtime-cuda-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,runtimes/tensorflow/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cuda)

.PHONY: codeserver-ubi9-python-$(RELEASE_PYTHON_VERSION)
codeserver-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,codeserver/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cpu)

.PHONY: che-code-codeserver-ubi9-python-$(RELEASE_PYTHON_VERSION)
che-code-codeserver-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,codeserver/che-code-ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.cpu)

####################################### Buildchain for AMD Python using UBI9 #######################################
.PHONY: rocm-jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION)
rocm-jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,jupyter/minimal/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.rocm)

.PHONY: rocm-jupyter-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION)
rocm-jupyter-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,jupyter/rocm/tensorflow/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.rocm)

.PHONY: rocm-jupyter-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION)
rocm-jupyter-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,jupyter/rocm/pytorch/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.rocm)

.PHONY: rocm-runtime-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION)
rocm-runtime-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,runtimes/rocm-pytorch/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.rocm)

.PHONY: rocm-runtime-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION)
rocm-runtime-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,runtimes/rocm-tensorflow/ubi9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.konflux.rocm)

####################################### Deployments #######################################

# Download kubectl binary
.PHONY: bin/kubectl
bin/kubectl:
ifeq (,$(wildcard $(KUBECTL_BIN)))
	@mkdir -p bin
	@curl -sSL https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/$(OS_ARCH)/kubectl > \
		$(KUBECTL_BIN)
	@chmod +x $(KUBECTL_BIN)
endif

# Download yq binary
.PHONY: bin/yq
bin/yq:
	$(eval YQ_RELEASE_FILE := yq_$(subst /,_,$(OS_ARCH)))
ifeq (,$(wildcard $(YQ_BIN)))
	@mkdir -p bin
	@curl -sSL https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/${YQ_RELEASE_FILE} > \
		$(YQ_BIN)
	@chmod +x $(YQ_BIN)
endif

.PHONY: deploy9
deploy9-%: bin/kubectl bin/yq
	$(eval TARGET := $(shell echo $* | sed 's/-ubi9-python.*//'))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$(TARGET)))/ubi9-python-$(PYTHON_VERSION)/kustomize/base)
ifndef NOTEBOOK_TAG
	$(eval NOTEBOOK_TAG := $*-$(IMAGE_TAG))
endif
	$(info # Deploying notebook from $(NOTEBOOK_DIR) directory...)
	@arg=$(IMAGE_REGISTRY) $(YQ_BIN) e -i '.images[].newName = strenv(arg)' $(NOTEBOOK_DIR)/kustomization.yaml
	@arg=$(NOTEBOOK_TAG) $(YQ_BIN) e -i '.images[].newTag = strenv(arg)' $(NOTEBOOK_DIR)/kustomization.yaml
	$(KUBECTL_BIN) apply -k $(NOTEBOOK_DIR)

.PHONY: undeploy9
undeploy9-%: bin/kubectl
	$(eval TARGET := $(shell echo $* | sed 's/-ubi9-python.*//'))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$(TARGET)))/ubi9-python-$(PYTHON_VERSION)/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

.PHONY: deploy-c9s
deploy-c9s-%: bin/kubectl bin/yq
	$(eval TARGET := $(shell echo $* | sed 's/-c9s-python.*//'))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$(TARGET)))/c9s-python-$(PYTHON_VERSION)/kustomize/base)
ifndef NOTEBOOK_TAG
	$(eval NOTEBOOK_TAG := $*-$(IMAGE_TAG))
endif
	$(info # Deploying notebook from $(NOTEBOOK_DIR) directory...)
	@arg=$(IMAGE_REGISTRY) $(YQ_BIN) e -i '.images[].newName = strenv(arg)' $(NOTEBOOK_DIR)/kustomization.yaml
	@arg=$(NOTEBOOK_TAG) $(YQ_BIN) e -i '.images[].newTag = strenv(arg)' $(NOTEBOOK_DIR)/kustomization.yaml
	$(KUBECTL_BIN) apply -k $(NOTEBOOK_DIR)

.PHONY: undeploy-c9s
undeploy-c9s-%: bin/kubectl
	$(eval TARGET := $(shell echo $* | sed 's/-c9s-python.*//'))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$(TARGET)))/c9s-python-$(PYTHON_VERSION)/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

.PHONY: deploy-rhel9
deploy-rhel9-%: bin/kubectl bin/yq
	$(eval TARGET := $(shell echo $* | sed 's/-rhel9-python.*//'))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$(TARGET)))/rhel9-python-$(PYTHON_VERSION)/kustomize/base)
ifndef NOTEBOOK_TAG
	$(eval NOTEBOOK_TAG := $*-$(IMAGE_TAG))
endif
	$(info # Deploying notebook from $(NOTEBOOK_DIR) directory...)
	@arg=$(IMAGE_REGISTRY) $(YQ_BIN) e -i '.images[].newName = strenv(arg)' $(NOTEBOOK_DIR)/kustomization.yaml
	@arg=$(NOTEBOOK_TAG) $(YQ_BIN) e -i '.images[].newTag = strenv(arg)' $(NOTEBOOK_DIR)/kustomization.yaml
	$(KUBECTL_BIN) apply -k $(NOTEBOOK_DIR)

.PHONY: undeploy-rhel9
undeploy-rhel9-%: bin/kubectl
	$(eval TARGET := $(shell echo $* | sed 's/-rhel9-python.*//'))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$(TARGET)))/rhel9-python-$(PYTHON_VERSION)/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

# Verify the notebook's readiness by pinging the /api endpoint and executing the corresponding test_notebook.ipynb file in accordance with the build chain logic.
.PHONY: test
test-%: bin/kubectl
	$(info # Running tests for $* notebook...)
	@./scripts/test_jupyter_with_papermill.sh $*

# Validate that runtime image meets minimum criteria
# This validation is created from subset of https://github.com/elyra-ai/elyra/blob/9c417d2adc9d9f972de5f98fd37f6945e0357ab9/Makefile#L325
# Elyra pins are applied from ci/requirements-elyra.txt (kubectl cp) so CI stays reproducible when PyPI drops a pin.
.PHONY: validate-runtime-image
validate-runtime-image: bin/kubectl
	$(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$*)))
	$(info # Running tests for $(NOTEBOOK_NAME) runtime...)
	$(KUBECTL_BIN) wait --for=condition=ready pod runtime-pod --timeout=300s
	@required_commands=$(REQUIRED_RUNTIME_IMAGE_COMMANDS)
	fail=0
	if [[ $$image == "" ]] ; then
		echo "Usage: make validate-runtime-image image=<container-image-name>"
		exit 1
	fi
	for cmd in $$required_commands ; do
		echo "=> Checking container image $$image for $$cmd..."
		if ! $(KUBECTL_BIN) exec runtime-pod which $$cmd > /dev/null 2>&1 ; then
			echo "ERROR: Container image $$image  does not meet criteria for command: $$cmd"
			fail=1
			continue
		fi
		if [ $$cmd == "python3" ]; then
			echo "=> Checking notebook execution..."
			if ! $(KUBECTL_BIN) cp "$(CURDIR)/ci/requirements-elyra.txt" runtime-pod:/tmp/requirements-elyra.txt || \
				! $(KUBECTL_BIN) exec runtime-pod -- /bin/sh -c "python3 -m pip install -r /tmp/requirements-elyra.txt > /dev/null && \
					python3 -m papermill \$$(python3 -c \"import papermill, pathlib; print(pathlib.Path(papermill.__file__).parent / 'tests/notebooks/simple_execute.ipynb')\") /tmp/output.ipynb > /dev/null" ; then
				echo "ERROR: Image does not meet Python requirements criteria in pipfile"
				fail=1
			fi
		fi
	done
	if [ $$fail -eq 1 ]; then
		echo "=> ERROR: Container image $$image is not a suitable Elyra runtime image"
		exit 1
	else
		echo "=> Container image $$image is a suitable Elyra runtime image"
	fi;

.PHONY: validate-codeserver-image
validate-codeserver-image: bin/kubectl
	$(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$*)))
	$(info # Running tests for $(NOTEBOOK_NAME) code-server image...)
	$(KUBECTL_BIN) wait --for=condition=ready pod codeserver-pod --timeout=300s
	@required_commands=$(REQUIRED_CODE_SERVER_IMAGE_COMMANDS)
	if [[ $$image == "" ]] ; then
		echo "Usage: make validate-codeserver-image image=<container-image-name>"
		exit 1
	fi
	for cmd in $$required_commands ; do
		echo "=> Checking container image $$image for $$cmd..."
		if ! $(KUBECTL_BIN) exec codeserver-pod which $$cmd > /dev/null 2>&1 ; then
			echo "ERROR: Container image $$image  does not meet criteria for command: $$cmd"
			fail=1
			continue
		fi
	done

# ======================================================================================
# Refresh lock files
# Usage examples:
#   gmake refresh-lock-files                                                   <- auto mode (rh-index if uv.lock.d/ exists, else public-index)
#   gmake refresh-lock-files INDEX_MODE=public-index                           <- force public-index
#   gmake refresh-lock-files INDEX_MODE=public-index DIR=jupyter/minimal/ubi9-python-3.12
# Optional: UV_EXTRA_INDEX_URL / PIP_EXTRA_INDEX_URL (e.g. RH CUDA *-test/simple/) are
# forwarded to the lock generator as UV_LOCK_* / PIP_LOCK_* only, then unset so
# `uv run` at the repo root is not affected (see scripts/pylocks_generator.py).
# ======================================================================================
DIR ?=
.PHONY: refresh-lock-files
refresh-lock-files:
	@echo "==================================================================="
	@echo "🔁 Refreshing lock files using INDEX_MODE=$(INDEX_MODE)"
	@echo "    (orchestrator: uv run; pip compile inside pylocks_generator: ./uv → dependencies/uv-image-lock-version)"
	@echo "==================================================================="
	@cd $(ROOT_DIR) && \
		export UV_LOCK_EXTRA_INDEX_URL="$(UV_EXTRA_INDEX_URL)" && \
		export PIP_LOCK_EXTRA_INDEX_URL="$(PIP_EXTRA_INDEX_URL)" && \
		unset UV_EXTRA_INDEX_URL PIP_EXTRA_INDEX_URL && \
		uv run scripts/pylocks_generator.py "$(INDEX_MODE)" $(DIR)

# ======================================================================================
# Sync build-args BASE_IMAGE values from versions_config.yml
# Usage examples:
#   gmake sync-build-args-from-versions
#   gmake sync-build-args-from-versions SYNC_BUILD_ARGS_ARGS=--check
#   gmake sync-build-args-from-versions SYNC_BUILD_ARGS_ARGS=--dry-run
#   gmake sync-build-args-from-versions SYNC_BUILD_ARGS_ARGS=--rhds-stable-repo-override=cuda=quay.io/<org>/cuda-stable
# Prerequisites:
#   - skopeo on PATH (RHDS tag resolution uses skopeo list-tags)
#   - Registry access for quay.io/aipcc/base-images when syncing RHDS build args
# ======================================================================================
SYNC_BUILD_ARGS_ARGS ?=
SYNC_BUILD_ARGS_ALLOWED := --dry-run --check --rhds-stable-repo-override=%
SYNC_BUILD_ARGS_INVALID := $(strip $(filter-out $(SYNC_BUILD_ARGS_ALLOWED),$(value SYNC_BUILD_ARGS_ARGS)))
.PHONY: sync-build-args-from-versions
sync-build-args-from-versions:
	$(if $(SYNC_BUILD_ARGS_INVALID),$(error Invalid SYNC_BUILD_ARGS_ARGS token(s): $(SYNC_BUILD_ARGS_INVALID) (allowed: $(SYNC_BUILD_ARGS_ALLOWED))))
	@echo "==================================================================="
	@echo "🔁 Syncing build-args BASE_IMAGE values from versions_config.yml"
	@echo "==================================================================="
	@cd "$(ROOT_DIR)" && ./uv run scripts/update_build_args_from_versions.py $(value SYNC_BUILD_ARGS_ARGS)

# ======================================================================================
#   gmake update-imagestream-annotations
#   gmake update-imagestream-annotations IMAGESTREAM_VARIANT=rhoai DRY_RUN=1
# Prerequisites:
#   - uv sync --locked (or make setup) so scripts run in the project venv
#   - skopeo on PATH (sync-commit-env-files inspects images from params*.env)
#   - For private registry pulls: mkdir -p ~/.config/containers &&
#       cp ci/secrets/pull-secret.json ~/.config/containers/auth.json
#   - Full clone / fetch-depth 0 helps update-imagestream-annotations when git show needs SHAs
#       not already in the local object database (script can fetch from GitHub when needed).
# ======================================================================================
IMAGESTREAM_VARIANT ?=
DRY_RUN ?=
.PHONY: update-imagestream-annotations
update-imagestream-annotations:
	@echo "==================================================================="
	@echo "📋 Refreshing ImageStream notebook dependency annotations (IMAGESTREAM_VARIANT=$(or $(IMAGESTREAM_VARIANT),odh+rhoai))"
	@echo "==================================================================="
	@cd $(ROOT_DIR) && \
	if [[ -n "$(IMAGESTREAM_VARIANT)" ]]; then \
		uv run python manifests/tools/update_imagestream_annotations_from_pylock.py \
			--variant "$(IMAGESTREAM_VARIANT)" $(if $(filter 1 true yes,$(DRY_RUN)),--dry-run,); \
	else \
		uv run python manifests/tools/update_imagestream_annotations_from_pylock.py --variant odh \
			$(if $(filter 1 true yes,$(DRY_RUN)),--dry-run,) && \
		uv run python manifests/tools/update_imagestream_annotations_from_pylock.py --variant rhoai \
			$(if $(filter 1 true yes,$(DRY_RUN)),--dry-run,); \
	fi

# This is only for the workflow action
# For running manually, set the required environment variables
.PHONY: scan-image-vulnerabilities
scan-image-vulnerabilities:
	python ci/security-scan/quay_security_analysis.py

# This is used primarily for gen_gha_matrix_jobs.py to we know the set of all possible images we may want to build
.PHONY: all-images
ifeq ($(RELEASE_PYTHON_VERSION), 3.12)
all-images: \
	jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	jupyter-datascience-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	cuda-jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	cuda-jupyter-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	cuda-jupyter-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	cuda-jupyter-pytorch-llmcompressor-ubi9-python-$(RELEASE_PYTHON_VERSION) \
 	codeserver-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	che-code-codeserver-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	jupyter-trustyai-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	runtime-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	runtime-datascience-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	runtime-cuda-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	runtime-cuda-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	runtime-cuda-pytorch-llmcompressor-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	rocm-jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION) \
 	rocm-jupyter-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	rocm-runtime-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	rocm-runtime-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	rocm-jupyter-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION)
else
	$(error Invalid Python version $(RELEASE_PYTHON_VERSION))
endif

# This is used primarily for `konflux_generate_component_build_pipelines.py` to we know the build release version
.PHONY: print-release
print-release:
	@echo "$(RELEASE)"

.PHONY: setup
setup:
	uv sync --locked

.PHONY: validate-renovate-config
validate-renovate-config:
	@echo "Validating .github/renovate.json5 semantics"
	./uv run python scripts/ci/validate_renovate_config.py

.PHONY: test
test:
	@echo "Running quick static tests"
	uv run pytest -m 'not buildonlytest'

.PHONY: check-actions
check-actions:
	@echo "Checking GitHub Actions SHA pinning"
	@set +x; GITHUB_TOKEN=$$(gh auth token) pinact run --check --verify

.PHONY: test-unit
test-unit:
	@echo "Running Python unit tests"
	uv run pytest -m 'not buildonlytest' --ignore=tests/containers tests/ ntb/
	@echo "Running Go unit tests"
	GOTOOLCHAIN=auto GONOSUMDB=golang.org/toolchain \
	  go test -C scripts/buildinputs -cover ./...

PYTEST_ARGS ?=

.PHONY: test-integration
test-integration:
ifeq ($(PYTEST_ARGS),)
	$(error Usage: make test-integration PYTEST_ARGS="--image=<image>")
endif
	@echo "Running container integration tests"
	uv run pytest tests/containers -m 'not openshift and not cuda and not rocm and not manifest_validation' $(PYTEST_ARGS)

.PHONY: unit-test integration-test
unit-test: test-unit
integration-test: test-integration
