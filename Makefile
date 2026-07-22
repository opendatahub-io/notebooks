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

# todo: leave the default recipe prefix for now
ifeq ($(origin .RECIPEPREFIX), undefined)
$(error This Make does not support .RECIPEPREFIX. Please use GNU Make 4.0 or later)
endif
.RECIPEPREFIX =

# PRODUCT: rhoai-only on this branch (see RHAIENG-6036)
PRODUCT ?= rhoai
ifneq ($(filter rhoai,$(PRODUCT)),$(PRODUCT))
$(error PRODUCT must be 'rhoai' on rhoai-2.25, got '$(PRODUCT)')
endif

IMAGE_REGISTRY   ?= quay.io/opendatahub/workbench-images
RELEASE	 		 ?= 2025b
RELEASE_PYTHON_VERSION	 ?= 3.12
# additional user-specified caching parameters for $(CONTAINER_ENGINE) build
CONTAINER_BUILD_CACHE_ARGS ?= --no-cache
# whether to push the images to a registry as they are built
PUSH_IMAGES ?= yes

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
RPM_ARCH := $(subst amd64,x86_64,$(subst arm64,aarch64,$(lastword $(subst /, ,$(BUILD_ARCH)))))
CONTAINER_BUILD_SECURITY_ARGS ?=

IMAGE_TAG		 ?= $(RELEASE)_$(DATE)
KUBECTL_BIN      ?= bin/kubectl
KUBECTL_VERSION  ?= v1.23.11
YQ_BIN      ?= bin/yq
YQ_VERSION  ?= v4.44.6
NOTEBOOK_REPO_BRANCH_BASE ?= https://raw.githubusercontent.com/opendatahub-io/notebooks/main
REQUIRED_RUNTIME_IMAGE_COMMANDS="curl python3"
REQUIRED_CODE_SERVER_IMAGE_COMMANDS="curl python oc code-server"
REQUIRED_R_STUDIO_IMAGE_COMMANDS="curl python oc /usr/lib/rstudio-server/bin/rserver"

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

	$(eval BUILD_DIR := $(dir $(2)))
	$(eval DOCKERFILE_NAME := $(notdir $(2)))
	$(eval CONF_FILE := $(3))

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

$(eval _DOCKERFILE_USES_PREFETCH := $(shell grep -q 'prefetch-input/' $(2) 2>/dev/null && echo yes))
$(eval PREFETCH_INPUT_DIR := $(or $(wildcard $(BUILD_DIR)prefetch-input),$(if $(_DOCKERFILE_USES_PREFETCH),$(wildcard $(ROOT_DIR)prefetch-input),)))
$(eval CACHI2_VOLUME := $(if $(and $(wildcard cachi2/output),$(PREFETCH_INPUT_DIR)),\
	--volume $(ROOT_DIR)/cachi2/output:/cachi2/output:Z \
	--volume $(ROOT_DIR)/cachi2/output/deps/rpm/$(RPM_ARCH)/repos.d/:/etc/yum.repos.d/:Z,))
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
	$(CONTAINER_ENGINE) push $(IMAGE_NAME)
endef

# Build and push the notebook images:
#   ARG 1: Image tag name.
#   ARG 2: Path of Dockerfile we want to build.
#
# PUSH_IMAGES: allows skipping podman push
define image
	$(eval BUILD_DIRECTORY := $(shell echo $(2) | sed 's/\/Dockerfile.*//'))
	$(eval VARIANT := $(shell echo $(notdir $(2)) | awk -F. '{print $$NF}'))
	# Prefer hermetic Dockerfile.konflux.<variant> when present (codeserver);
	# fall back to the path passed by the target (rstudio and other non-hermetic images).
	$(eval DOCKERFILE := $(or $(wildcard $(BUILD_DIRECTORY)/Dockerfile.konflux.$(VARIANT)),$(2)))
	$(if $(wildcard $(DOCKERFILE)),,$(error Dockerfile not found for variant '$(VARIANT)' in '$(BUILD_DIRECTORY)'))

	$(eval CONF_FILE := $(BUILD_DIRECTORY)/build-args/$(if $(and $(filter rhoai,$(PRODUCT)),$(wildcard $(BUILD_DIRECTORY)/build-args/konflux.$(VARIANT).conf)),konflux.,)$(shell echo $(VARIANT)).conf)
	$(info #*# Image build Dockerfile: <$(DOCKERFILE)> #(MACHINE-PARSED LINE)#*#...)
	$(info #*# Image build directory: <$(BUILD_DIRECTORY)> #(MACHINE-PARSED LINE)#*#...)

	# realpath dereferences symlinks — podman API rejects symlinks with "must be a regular file"
	$(eval DOCKERFILE_BUILD := $(realpath $(DOCKERFILE)))
	$(if $(strip $(DOCKERFILE_BUILD)),,$(error Resolved Dockerfile path is empty for '$(DOCKERFILE)' — file missing or broken symlink))
	$(call build_image,$(1),$(DOCKERFILE_BUILD),$(CONF_FILE))

	$(if $(PUSH_IMAGES:no=),
		$(call push_image,$(1))
	)
endef

#######################################        Build helpers                 #######################################

# https://stackoverflow.com/questions/78899903/how-to-create-a-make-target-which-is-an-implicit-dependency-for-all-other-target
skip-init-for := all-images deploy% undeploy% test% validate% refresh-pipfilelock-files scan-image-vulnerabilities print-release
ifneq (,$(filter-out $(skip-init-for),$(MAKECMDGOALS) $(.DEFAULT_GOAL)))
$(SELF): bin/buildinputs
endif

bin/buildinputs: scripts/buildinputs/buildinputs.go scripts/buildinputs/go.mod scripts/buildinputs/go.sum
	$(info Building a Go helper for Dockerfile dependency analysis...)
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

####################################### Buildchain for Python using rhel9 #######################################

.PHONY: rstudio-rhel9-python-$(RELEASE_PYTHON_VERSION)
rstudio-rhel9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,rstudio/rhel9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.cpu)

.PHONY: cuda-rstudio-rhel9-python-$(RELEASE_PYTHON_VERSION)
cuda-rstudio-rhel9-python-$(RELEASE_PYTHON_VERSION):
	$(call image,$@,rstudio/rhel9-python-$(RELEASE_PYTHON_VERSION)/Dockerfile.cuda)

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
	$(eval NOTEBOOK_PATH := $(subst -,/,$(subst cuda-,,$(TARGET))))
	$(eval NOTEBOOK_PATH := $(subst pytorch/llmcompressor,pytorch+llmcompressor,$(NOTEBOOK_PATH)))
	$(eval NOTEBOOK_DIR := $(NOTEBOOK_PATH)/ubi9-python-$(PYTHON_VERSION)/kustomize/base)
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
	$(eval NOTEBOOK_PATH := $(subst -,/,$(subst cuda-,,$(TARGET))))
	$(eval NOTEBOOK_PATH := $(subst pytorch/llmcompressor,pytorch+llmcompressor,$(NOTEBOOK_PATH)))
	$(eval NOTEBOOK_DIR := $(NOTEBOOK_PATH)/ubi9-python-$(PYTHON_VERSION)/kustomize/base)
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
			if ! $(KUBECTL_BIN) exec runtime-pod -- /bin/sh -c "curl https://raw.githubusercontent.com/opendatahub-io/elyra/refs/heads/main/etc/generic/requirements-elyra.txt --output req.txt && \
					python3 -m pip install -r req.txt > /dev/null && \
					curl https://raw.githubusercontent.com/nteract/papermill/main/papermill/tests/notebooks/simple_execute.ipynb --output simple_execute.ipynb && \
					python3 -m papermill simple_execute.ipynb output.ipynb > /dev/null" ; then
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

.PHONY: validate-rstudio-image
validate-rstudio-image: bin/kubectl
	$(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$(image))))
	$(eval PYTHON_VERSION := $(shell echo $(image) | sed 's/.*-python-//'))
	$(info # Running tests for $(NOTEBOOK_NAME) RStudio Server image...)
	$(KUBECTL_BIN) wait --for=condition=ready pod rstudio-pod --timeout=300s
	@required_commands=$(REQUIRED_R_STUDIO_IMAGE_COMMANDS)
	if [[ $$image == "" ]] ; then
		echo "Usage: make validate-rstudio-image image=<container-image-name>"
		exit 1
	fi
	echo "=> Checking container image $$image for package installation..."
	$(KUBECTL_BIN) exec -it rstudio-pod -- mkdir -p /opt/app-root/src/R/temp-library > /dev/null 2>&1
	if $(KUBECTL_BIN) exec rstudio-pod -- R -e "install.packages('tinytex', lib='/opt/app-root/src/R/temp-library')" > /dev/null 2>&1 ; then
		echo "Tinytex installation successful!"
	else
		echo "Error: Tinytex installation failed."
	fi
	for cmd in $$required_commands ; do
		echo "=> Checking container image $$image for $$cmd..."
		if $(KUBECTL_BIN) exec rstudio-pod which $$cmd > /dev/null 2>&1 ; then
			echo "$$cmd executed successfully!"
		else
			echo "ERROR: Container image $$image  does not meet criteria for command: $$cmd"
			fail=1
			continue
		fi
	done
	echo "=> Fetching R script from URL and executing on the container..."
	curl -sSL -o test_script.R "${NOTEBOOK_REPO_BRANCH_BASE}/rstudio/rhel9-python-$(PYTHON_VERSION)/test/test_script.R" > /dev/null 2>&1
	$(KUBECTL_BIN) cp test_script.R rstudio-pod:/opt/app-root/src/test_script.R > /dev/null 2>&1
	if $(KUBECTL_BIN) exec rstudio-pod -- Rscript /opt/app-root/src/test_script.R > /dev/null 2>&1 ; then
		echo "R script executed successfully!"
		rm test_script.R
	else
		echo "Error: R script failed."
		fail=1
		continue
	fi

# This recipe used mainly from the Pipfile.locks Renewal Action
# Default Python version
PYTHON_VERSION ?= 3.12
ROOT_DIR := $(shell pwd)
ifeq ($(PYTHON_VERSION), 3.11)
	BASE_DIRS := \
		rstudio/rhel9-python-$(PYTHON_VERSION)
else ifeq ($(PYTHON_VERSION), 3.12)
	BASE_DIRS := \
	    jupyter/minimal/ubi9-python-$(PYTHON_VERSION) \
		jupyter/datascience/ubi9-python-$(PYTHON_VERSION) \
		jupyter/pytorch/ubi9-python-$(PYTHON_VERSION) \
		jupyter/tensorflow/ubi9-python-$(PYTHON_VERSION) \
		jupyter/trustyai/ubi9-python-$(PYTHON_VERSION) \
		jupyter/rocm/pytorch/ubi9-python-$(PYTHON_VERSION) \
		jupyter/pytorch+llmcompressor/ubi9-python-$(PYTHON_VERSION) \
		codeserver/ubi9-python-$(PYTHON_VERSION) \
		runtimes/minimal/ubi9-python-$(PYTHON_VERSION) \
		runtimes/datascience/ubi9-python-$(PYTHON_VERSION) \
		runtimes/pytorch/ubi9-python-$(PYTHON_VERSION) \
		runtimes/tensorflow/ubi9-python-$(PYTHON_VERSION) \
		runtimes/rocm-pytorch/ubi9-python-$(PYTHON_VERSION) \
		runtimes/pytorch+llmcompressor/ubi9-python-$(PYTHON_VERSION) \
		runtimes/rocm-tensorflow/ubi9-python-$(PYTHON_VERSION) \
		jupyter/rocm/tensorflow/ubi9-python-$(PYTHON_VERSION)
		# rstudio/rhel9-python-$(PYTHON_VERSION)
else
	$(error Invalid Python version $(PYTHON_VERSION))
endif

# Default value is false, can be overridden
# The below directories are not supported on tier-1
INCLUDE_OPT_DIRS ?= false
OPT_DIRS :=

# This recipe gets args, can be used like
# make refresh-pipfilelock-files PYTHON_VERSION=3.11 INCLUDE_OPT_DIRS=false
.PHONY: refresh-pipfilelock-files
refresh-pipfilelock-files:
	@echo "Updating Pipfile.lock files for Python $(PYTHON_VERSION)"
	@if [ "$(INCLUDE_OPT_DIRS)" = "true" ]; then
		echo "Including optional directories"
		DIRS="$(BASE_DIRS) $(OPT_DIRS)"
	else
		DIRS="$(BASE_DIRS)"
	fi
	for dir in $$DIRS; do
		echo "Processing directory: $$dir"
		cd $(ROOT_DIR)
		if [ -d "$$dir" ]; then
			echo "Updating $(PYTHON_VERSION) uv.lock in $$dir"
			cd $$dir
			if [ -f "pyproject.toml" ]; then
				$(ROOT_DIR)/uv lock && rm uv.lock
			else
				echo "No pyproject.toml found in $$dir, skipping."
			fi
		else
			echo "Skipping $$dir as it does not exist"
		fi
	done

	echo "Regenerating requirements.txt files"
	pushd $(ROOT_DIR)
		bash $(ROOT_DIR)/scripts/sync-python-lockfiles.sh
	popd

# This is only for the workflow action
# For running manually, set the required environment variables
.PHONY: scan-image-vulnerabilities
scan-image-vulnerabilities:
	python ci/security-scan/quay_security_analysis.py

# This is used primarily for gen_gha_matrix_jobs.py to we know the set of all possible images we may want to build
.PHONY: all-images
ifeq ($(RELEASE_PYTHON_VERSION), 3.11)
all-images: \
	rstudio-rhel9-python-$(RELEASE_PYTHON_VERSION) \
	cuda-rstudio-rhel9-python-$(RELEASE_PYTHON_VERSION)
else ifeq ($(RELEASE_PYTHON_VERSION), 3.12)
all-images: \
	jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	jupyter-datascience-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	cuda-jupyter-minimal-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	cuda-jupyter-tensorflow-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	cuda-jupyter-pytorch-ubi9-python-$(RELEASE_PYTHON_VERSION) \
	cuda-jupyter-pytorch-llmcompressor-ubi9-python-$(RELEASE_PYTHON_VERSION) \
 	codeserver-ubi9-python-$(RELEASE_PYTHON_VERSION) \
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
# rstudio-rhel9-python-$(RELEASE_PYTHON_VERSION)
# cuda-rstudio-rhel9-python-$(RELEASE_PYTHON_VERSION)

else
	$(error Invalid Python version $(RELEASE_PYTHON_VERSION))
endif

# This is used primarily for `konflux_generate_component_build_pipelines.py` to we know the build release version
.PHONY: print-release
print-release:
	@echo "$(RELEASE)"

.PHONY: test
test:
	@echo "Running quick static tests"
	./uv run pytest -m 'not buildonlytest'

.PHONY: check-actions
check-actions:
	@echo "Checking GitHub Actions SHA pinning"
	@set +x; GITHUB_TOKEN=$$(gh auth token) pinact run --check --verify
