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

IMAGE_REGISTRY   ?= quay.io/opendatahub/workbench-images
RELEASE	 		 ?= 2024b
# additional user-specified caching parameters for $(CONTAINER_ENGINE) build
CONTAINER_BUILD_CACHE_ARGS ?= --no-cache
# whether to build all dependent images or just the one specified
BUILD_DEPENDENT_IMAGES ?= yes
# whether to push the images to a registry as they are built
PUSH_IMAGES ?= yes

# OS dependant: Generate date, select appropriate cmd to locate container engine
ifeq ($(OS), Windows_NT)
	DATE 		?= $(shell powershell -Command "Get-Date -Format 'yyyyMMdd'")
	WHERE_WHICH ?= where
else
	DATE 		?= $(shell date +'%Y%m%d')
	WHERE_WHICH ?= which
endif

# linux/amd64 or darwin/arm64
OS_ARCH=$(shell go env GOOS)/$(shell go env GOARCH)

IMAGE_TAG		 ?= $(RELEASE)_$(DATE)
KUBECTL_BIN      ?= bin/kubectl
KUBECTL_VERSION  ?= v1.23.11
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

# Build function for the notebok image:
#   ARG 1: Image tag name.
#   ARG 2: Path of image context we want to build.
#   ARG 3: Base image tag name (optional).
define build_image
	$(eval IMAGE_NAME := $(IMAGE_REGISTRY):$(1)-$(IMAGE_TAG))
	$(info # Building $(IMAGE_NAME) image...)
	$(if $(3),
		$(eval BASE_IMAGE_NAME := $(IMAGE_REGISTRY):$(3)-$(IMAGE_TAG))
		$(eval BUILD_ARGS := --build-arg BASE_IMAGE=$(BASE_IMAGE_NAME)),
		$(eval BUILD_ARGS :=)
	)
	$(ROOT_DIR)/scripts/sandbox.py --dockerfile '$(2)/Dockerfile' -- \
		$(CONTAINER_ENGINE) build $(CONTAINER_BUILD_CACHE_ARGS) --tag $(IMAGE_NAME) --file '$(2)/Dockerfile' $(BUILD_ARGS) {}\;
endef

# Push function for the notebok image:
# 	ARG 1: Path of image context we want to build.
define push_image
	$(eval IMAGE_NAME := $(IMAGE_REGISTRY):$(subst /,-,$(1))-$(IMAGE_TAG))
	$(info # Pushing $(IMAGE_NAME) image...)
	$(CONTAINER_ENGINE) push $(IMAGE_NAME)
endef

# Build and push the notebook images:
#   ARG 1: Image tag name.
#   ARG 2: Path of image context we want to build.
#   ARG 3: Base image tag name (optional).
#
# BUILD_DEPENDENT_IMAGES: only build images that were explicitly given as a goal on command line
# PUSH_IMAGES: allows skipping podman push
define image
	$(info #*# Image build directory: <$(2)> #(MACHINE-PARSED LINE)#*#...)

	$(if $(or $(BUILD_DEPENDENT_IMAGES:no=), $(filter $@,$(MAKECMDGOALS))),
		$(call build_image,$(1),$(2),$(3))

		$(if $(PUSH_IMAGES:no=),
			$(call push_image,$(1))
		)
	)
endef

#######################################        Build helpers                 #######################################

# https://stackoverflow.com/questions/78899903/how-to-create-a-make-target-which-is-an-implicit-dependency-for-all-other-target
skip-init-for := deploy% undeploy% test% scan-image-vulnerabilities
ifneq (,$(filter-out $(skip-init-for),$(MAKECMDGOALS) $(.DEFAULT_GOAL)))
$(SELF): bin/buildinputs
endif

bin/buildinputs: scripts/buildinputs/buildinputs.go scripts/buildinputs/go.mod scripts/buildinputs/go.sum
	$(info Building a Go helper for Dockerfile dependency analysis...)
	go build -C "scripts/buildinputs" -o "$(ROOT_DIR)/$@" ./...

####################################### Buildchain for Python 3.9 using ubi9 #######################################

# Build and push base-ubi9-python-3.9 image to the registry
.PHONY: base-ubi9-python-3.9
base-ubi9-python-3.9:
	$(call image,$@,base/ubi9-python-3.9)

# Build and push jupyter-minimal-ubi9-python-3.9 image to the registry
.PHONY: jupyter-minimal-ubi9-python-3.9
jupyter-minimal-ubi9-python-3.9: base-ubi9-python-3.9
	$(call image,$@,jupyter/minimal/ubi9-python-3.9,$<)

# Build and push jupyter-datascience-ubi9-python-3.9 image to the registry
.PHONY: jupyter-datascience-ubi9-python-3.9
jupyter-datascience-ubi9-python-3.9: jupyter-minimal-ubi9-python-3.9
	$(call image,$@,jupyter/datascience/ubi9-python-3.9,$<)

# Build and push cuda-ubi9-python-3.9 image to the registry
.PHONY: cuda-ubi9-python-3.9
cuda-ubi9-python-3.9: base-ubi9-python-3.9
	$(call image,$@,cuda/ubi9-python-3.9,$<)

# Build and push cuda-jupyter-minimal-ubi9-python-3.9 image to the registry
.PHONY: cuda-jupyter-minimal-ubi9-python-3.9
cuda-jupyter-minimal-ubi9-python-3.9: cuda-ubi9-python-3.9
	$(call image,$@,jupyter/minimal/ubi9-python-3.9,$<)

# Build and push cuda-jupyter-datascience-ubi9-python-3.9 image to the registry
.PHONY: cuda-jupyter-datascience-ubi9-python-3.9
cuda-jupyter-datascience-ubi9-python-3.9: cuda-jupyter-minimal-ubi9-python-3.9
	$(call image,$@,jupyter/datascience/ubi9-python-3.9,$<)

# Build and push cuda-jupyter-tensorflow-ubi9-python-3.9 image to the registry
.PHONY: cuda-jupyter-tensorflow-ubi9-python-3.9
cuda-jupyter-tensorflow-ubi9-python-3.9: cuda-jupyter-datascience-ubi9-python-3.9
	$(call image,$@,jupyter/tensorflow/ubi9-python-3.9,$<)

# Build and push jupyter-pytorch-ubi9-python-3.9 image to the registry
.PHONY: jupyter-pytorch-ubi9-python-3.9
jupyter-pytorch-ubi9-python-3.9: cuda-jupyter-datascience-ubi9-python-3.9
	$(call image,$@,jupyter/pytorch/ubi9-python-3.9,$<)

# Build and push jupyter-trustyai-ubi9-python-3.9 image to the registry
.PHONY: jupyter-trustyai-ubi9-python-3.9
jupyter-trustyai-ubi9-python-3.9: jupyter-datascience-ubi9-python-3.9
	$(call image,$@,jupyter/trustyai/ubi9-python-3.9,$<)

# Build and push runtime-minimal-ubi9-python-3.9 image to the registry
.PHONY: runtime-minimal-ubi9-python-3.9
runtime-minimal-ubi9-python-3.9: base-ubi9-python-3.9
	$(call image,$@,runtimes/minimal/ubi9-python-3.9,$<)

# Build and push runtime-datascience-ubi9-python-3.9 image to the registry
.PHONY: runtime-datascience-ubi9-python-3.9
runtime-datascience-ubi9-python-3.9: base-ubi9-python-3.9
	$(call image,$@,runtimes/datascience/ubi9-python-3.9,$<)

# Build and push runtime-pytorch-ubi9-python-3.9 image to the registry
.PHONY: runtime-pytorch-ubi9-python-3.9
runtime-pytorch-ubi9-python-3.9: base-ubi9-python-3.9
	$(call image,$@,runtimes/pytorch/ubi9-python-3.9,$<)

# Build and push runtime-cuda-tensorflow-ubi9-python-3.9 image to the registry
.PHONY: runtime-cuda-tensorflow-ubi9-python-3.9
runtime-cuda-tensorflow-ubi9-python-3.9: cuda-ubi9-python-3.9
	$(call image,$@,runtimes/tensorflow/ubi9-python-3.9,$<)

.PHONY: codeserver-ubi9-python-3.9
codeserver-ubi9-python-3.9: base-ubi9-python-3.9
	$(call image,$@,codeserver/ubi9-python-3.9,$<)

# Build and push base-anaconda-python-3.9-intel-gpu image to the registry
.PHONY: intel-base-gpu-ubi9-python-3.9
intel-base-gpu-ubi9-python-3.9: base-ubi9-python-3.9
	$(call image,$@,intel/base/gpu/ubi9-python-3.9,$<)

# Build and push intel-runtime-tensorflow-ubi9-python-3.9 image to the registry
.PHONY: intel-runtime-tensorflow-ubi9-python-3.9
intel-runtime-tensorflow-ubi9-python-3.9: intel-base-gpu-ubi9-python-3.9
	$(call image,$@,intel/runtimes/tensorflow/ubi9-python-3.9,$<)

# Build and push jupyter-intel-tensorflow-ubi9-python-3.9 image to the registry
.PHONY: jupyter-intel-tensorflow-ubi9-python-3.9
jupyter-intel-tensorflow-ubi9-python-3.9: intel-base-gpu-ubi9-python-3.9
	$(call image,$@,jupyter/intel/tensorflow/ubi9-python-3.9,$<)

# Build and push intel-runtime-pytorch-ubi9-python-3.9 image to the registry
.PHONY: intel-runtime-pytorch-ubi9-python-3.9
intel-runtime-pytorch-ubi9-python-3.9: intel-base-gpu-ubi9-python-3.9
	$(call image,$@,intel/runtimes/pytorch/ubi9-python-3.9,$<)

# Build and push jupyter-intel-pytorch-ubi9-python-3.9 image to the registry
.PHONY: jupyter-intel-pytorch-ubi9-python-3.9
jupyter-intel-pytorch-ubi9-python-3.9: intel-base-gpu-ubi9-python-3.9
	$(call image,$@,jupyter/intel/pytorch/ubi9-python-3.9,$<)

# Build and push intel-runtime-ml-ubi9-python-3.9 image to the registry
.PHONY: intel-runtime-ml-ubi9-python-3.9
intel-runtime-ml-ubi9-python-3.9: base-ubi9-python-3.9
	$(call image,$@,intel/runtimes/ml/ubi9-python-3.9,$<)

# Build and push jupyter-intel-ml-ubi9-python-3.9 image to the registry
.PHONY: jupyter-intel-ml-ubi9-python-3.9
jupyter-intel-ml-ubi9-python-3.9: base-ubi9-python-3.9
	$(call image,$@,jupyter/intel/ml/ubi9-python-3.9,$<)

####################################### Buildchain for Python 3.11 using ubi9 #####################################

# Build and push base-ubi9-python-3.11 image to the registry
.PHONY: base-ubi9-python-3.11
base-ubi9-python-3.11:
	$(call image,$@,base/ubi9-python-3.11)

# Build and push jupyter-minimal-ubi9-python-3.11 image to the registry
.PHONY: jupyter-minimal-ubi9-python-3.11
jupyter-minimal-ubi9-python-3.11: base-ubi9-python-3.11
	$(call image,$@,jupyter/minimal/ubi9-python-3.11,$<)

# Build and push jupyter-datascience-ubi9-python-3.11 image to the registry
.PHONY: jupyter-datascience-ubi9-python-3.11
jupyter-datascience-ubi9-python-3.11: jupyter-minimal-ubi9-python-3.11
	$(call image,$@,jupyter/datascience/ubi9-python-3.11,$<)

# Build and push cuda-ubi9-python-3.11 image to the registry
.PHONY: cuda-ubi9-python-3.11
cuda-ubi9-python-3.11: base-ubi9-python-3.11
	$(call image,$@,cuda/ubi9-python-3.11,$<)

# Build and push cuda-jupyter-minimal-ubi9-python-3.11 image to the registry
.PHONY: cuda-jupyter-minimal-ubi9-python-3.11
cuda-jupyter-minimal-ubi9-python-3.11: cuda-ubi9-python-3.11
	$(call image,$@,jupyter/minimal/ubi9-python-3.11,$<)

# Build and push cuda-jupyter-datascience-ubi9-python-3.11 image to the registry
.PHONY: cuda-jupyter-datascience-ubi9-python-3.11
cuda-jupyter-datascience-ubi9-python-3.11: cuda-jupyter-minimal-ubi9-python-3.11
	$(call image,$@,jupyter/datascience/ubi9-python-3.11,$<)

# Build and push cuda-jupyter-tensorflow-ubi9-python-3.11 image to the registry
.PHONY: cuda-jupyter-tensorflow-ubi9-python-3.11
cuda-jupyter-tensorflow-ubi9-python-3.11: cuda-jupyter-datascience-ubi9-python-3.11
	$(call image,$@,jupyter/tensorflow/ubi9-python-3.11,$<)

# Build and push jupyter-pytorch-ubi9-python-3.11 image to the registry
.PHONY: jupyter-pytorch-ubi9-python-3.11
jupyter-pytorch-ubi9-python-3.11: cuda-jupyter-datascience-ubi9-python-3.11
	$(call image,$@,jupyter/pytorch/ubi9-python-3.11,$<)

# Build and push jupyter-trustyai-ubi9-python-3.11 image to the registry
.PHONY: jupyter-trustyai-ubi9-python-3.11
jupyter-trustyai-ubi9-python-3.11: jupyter-datascience-ubi9-python-3.11
	$(call image,$@,jupyter/trustyai/ubi9-python-3.11,$<)

# Build and push runtime-minimal-ubi9-python-3.11 image to the registry
.PHONY: runtime-minimal-ubi9-python-3.11
runtime-minimal-ubi9-python-3.11: base-ubi9-python-3.11
	$(call image,$@,runtimes/minimal/ubi9-python-3.11,$<)

# Build and push runtime-datascience-ubi9-python-3.11 image to the registry
.PHONY: runtime-datascience-ubi9-python-3.11
runtime-datascience-ubi9-python-3.11: base-ubi9-python-3.11
	$(call image,$@,runtimes/datascience/ubi9-python-3.11,$<)

# Build and push runtime-pytorch-ubi9-python-3.11 image to the registry
.PHONY: runtime-pytorch-ubi9-python-3.11
runtime-pytorch-ubi9-python-3.11: base-ubi9-python-3.11
	$(call image,$@,runtimes/pytorch/ubi9-python-3.11,$<)

# Build and push runtime-cuda-tensorflow-ubi9-python-3.11 image to the registry
.PHONY: runtime-cuda-tensorflow-ubi9-python-3.11
runtime-cuda-tensorflow-ubi9-python-3.11: cuda-ubi9-python-3.11
	$(call image,$@,runtimes/tensorflow/ubi9-python-3.11,$<)

.PHONY: codeserver-ubi9-python-3.11
codeserver-ubi9-python-3.11: base-ubi9-python-3.11
	$(call image,$@,codeserver/ubi9-python-3.11,$<)

# Build and push base-anaconda-python-3.11-intel-gpu image to the registry
.PHONY: intel-base-gpu-ubi9-python-3.11
intel-base-gpu-ubi9-python-3.11: base-ubi9-python-3.11
	$(call image,$@,intel/base/gpu/ubi9-python-3.11,$<)

# Build and push intel-runtime-tensorflow-ubi9-python-3.11 image to the registry
.PHONY: intel-runtime-tensorflow-ubi9-python-3.11
intel-runtime-tensorflow-ubi9-python-3.11: intel-base-gpu-ubi9-python-3.11
	$(call image,$@,intel/runtimes/tensorflow/ubi9-python-3.11,$<)

# Build and push jupyter-intel-tensorflow-ubi9-python-3.11 image to the registry
.PHONY: jupyter-intel-tensorflow-ubi9-python-3.11
jupyter-intel-tensorflow-ubi9-python-3.11: intel-base-gpu-ubi9-python-3.11
	$(call image,$@,jupyter/intel/tensorflow/ubi9-python-3.11,$<)

# Build and push intel-runtime-pytorch-ubi9-python-3.11 image to the registry
.PHONY: intel-runtime-pytorch-ubi9-python-3.11
intel-runtime-pytorch-ubi9-python-3.11: intel-base-gpu-ubi9-python-3.11
	$(call image,$@,intel/runtimes/pytorch/ubi9-python-3.11,$<)

# Build and push jupyter-intel-pytorch-ubi9-python-3.11 image to the registry
.PHONY: jupyter-intel-pytorch-ubi9-python-3.11
jupyter-intel-pytorch-ubi9-python-3.11: intel-base-gpu-ubi9-python-3.11
	$(call image,$@,jupyter/intel/pytorch/ubi9-python-3.11,$<)

# Build and push intel-runtime-ml-ubi9-python-3.11 image to the registry
.PHONY: intel-runtime-ml-ubi9-python-3.11
intel-runtime-ml-ubi9-python-3.11: base-ubi9-python-3.11
	$(call image,$@,intel/runtimes/ml/ubi9-python-3.11,$<)

# Build and push jupyter-intel-ml-ubi9-python-3.11 image to the registry
.PHONY: jupyter-intel-ml-ubi9-python-3.11
jupyter-intel-ml-ubi9-python-3.11: base-ubi9-python-3.11
	$(call image,$@,jupyter/intel/ml/ubi9-python-3.11,$<)

####################################### Buildchain for Python 3.9 using C9S #######################################

# Build and push base-c9s-python-3.9 image to the registry
.PHONY: base-c9s-python-3.9
base-c9s-python-3.9:
	$(call image,$@,base/c9s-python-3.9)

.PHONY: cuda-c9s-python-3.9
cuda-c9s-python-3.9: base-c9s-python-3.9
	$(call image,$@,cuda/c9s-python-3.9,$<)

.PHONY: rstudio-c9s-python-3.9
rstudio-c9s-python-3.9: base-c9s-python-3.9
	$(call image,$@,rstudio/c9s-python-3.9,$<)

.PHONY: cuda-rstudio-c9s-python-3.9
cuda-rstudio-c9s-python-3.9: cuda-c9s-python-3.9
	$(call image,$@,rstudio/c9s-python-3.9,$<)

####################################### Buildchain for Python 3.11 using C9S #######################################

# Build and push base-c9s-python-3.11 image to the registry
.PHONY: base-c9s-python-3.11
base-c9s-python-3.11:
	$(call image,$@,base/c9s-python-3.11)

.PHONY: cuda-c9s-python-3.11
cuda-c9s-python-3.11: base-c9s-python-3.11
	$(call image,$@,cuda/c9s-python-3.11,$<)

.PHONY: rstudio-c9s-python-3.11
rstudio-c9s-python-3.11: base-c9s-python-3.11
	$(call image,$@,rstudio/c9s-python-3.11,$<)

.PHONY: cuda-rstudio-c9s-python-3.11
cuda-rstudio-c9s-python-3.11: cuda-c9s-python-3.11
	$(call image,$@,rstudio/c9s-python-3.11,$<)

####################################### Buildchain for AMD Python 3.9 using UBI9 #######################################
.PHONY: rocm-ubi9-python-3.9
rocm-ubi9-python-3.9: base-ubi9-python-3.9
	$(call image,$@,rocm/ubi9-python-3.9,$<)

# We are only using rocm-ubi9 base image here onwards
.PHONY: rocm-jupyter-minimal-ubi9-python-3.9
rocm-jupyter-minimal-ubi9-python-3.9: rocm-ubi9-python-3.9
	$(call image,$@,jupyter/minimal/ubi9-python-3.9,$<)

# Build and push rocm-jupyter-datascience-ubi9-python-3.9 image to the registry
.PHONY: rocm-jupyter-datascience-ubi9-python-3.9
rocm-jupyter-datascience-ubi9-python-3.9: rocm-jupyter-minimal-ubi9-python-3.9
	$(call image,$@,jupyter/datascience/ubi9-python-3.9,$<)

# Build and push rocm-jupyter-tensorflow-ubi9-python-3.9 image to the registry
.PHONY: rocm-jupyter-tensorflow-ubi9-python-3.9
rocm-jupyter-tensorflow-ubi9-python-3.9: rocm-jupyter-datascience-ubi9-python-3.9
	$(call image,$@,jupyter/rocm/tensorflow/ubi9-python-3.9,$<)

# Build and push rocm-jupyter-pytorch-ubi9-python-3.9 image to the registry
.PHONY: rocm-jupyter-pytorch-ubi9-python-3.9
rocm-jupyter-pytorch-ubi9-python-3.9: rocm-jupyter-datascience-ubi9-python-3.9
	$(call image,$@,jupyter/rocm/pytorch/ubi9-python-3.9,$<)

# Build and push rocm-jupyter-runtime-pytorch-ubi9-python-3.9 image to the registry
.PHONY: rocm-runtime-pytorch-ubi9-python-3.9
rocm-runtime-pytorch-ubi9-python-3.9: rocm-ubi9-python-3.9
	$(call image,$@,runtimes/rocm-pytorch/ubi9-python-3.9,$<)

# Build and push rocm-jupyter-runtime-tensorflow-ubi9-python-3.9 image to the registry
.PHONY: rocm-runtime-tensorflow-ubi9-python-3.9
rocm-runtime-tensorflow-ubi9-python-3.9: rocm-ubi9-python-3.9
	$(call image,$@,runtimes/rocm-tensorflow/ubi9-python-3.9,$<)

####################################### Buildchain for AMD Python 3.11 using UBI9 #######################################
.PHONY: rocm-ubi9-python-3.11
rocm-ubi9-python-3.11: base-ubi9-python-3.11
	$(call image,$@,rocm/ubi9-python-3.11,$<)

# We are only using rocm-ubi9 base image here onwards
.PHONY: rocm-jupyter-minimal-ubi9-python-3.11
rocm-jupyter-minimal-ubi9-python-3.11: rocm-ubi9-python-3.11
	$(call image,$@,jupyter/minimal/ubi9-python-3.11,$<)

# Build and push rocm-jupyter-datascience-ubi9-python-3.11 image to the registry
.PHONY: rocm-jupyter-datascience-ubi9-python-3.11
rocm-jupyter-datascience-ubi9-python-3.11: rocm-jupyter-minimal-ubi9-python-3.11
	$(call image,$@,jupyter/datascience/ubi9-python-3.11,$<)

# Build and push rocm-jupyter-tensorflow-ubi9-python-3.11 image to the registry
.PHONY: rocm-jupyter-tensorflow-ubi9-python-3.11
rocm-jupyter-tensorflow-ubi9-python-3.11: rocm-jupyter-datascience-ubi9-python-3.11
	$(call image,$@,jupyter/rocm/tensorflow/ubi9-python-3.11,$<)

# Build and push rocm-jupyter-pytorch-ubi9-python-3.11 image to the registry
.PHONY: rocm-jupyter-pytorch-ubi9-python-3.11
rocm-jupyter-pytorch-ubi9-python-3.11: rocm-jupyter-datascience-ubi9-python-3.11
	$(call image,$@,jupyter/rocm/pytorch/ubi9-python-3.11,$<)

# Build and push rocm-jupyter-runtime-pytorch-ubi9-python-3.11 image to the registry
.PHONY: rocm-runtime-pytorch-ubi9-python-3.11
rocm-runtime-pytorch-ubi9-python-3.11: rocm-ubi9-python-3.11
	$(call image,$@,runtimes/rocm-pytorch/ubi9-python-3.11,$<)

# Build and push rocm-jupyter-runtime-tensorflow-ubi9-python-3.11 image to the registry
.PHONY: rocm-runtime-tensorflow-ubi9-python-3.11
rocm-runtime-tensorflow-ubi9-python-3.11: rocm-ubi9-python-3.11
	$(call image,$@,runtimes/rocm-tensorflow/ubi9-python-3.11,$<)

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

.PHONY: deploy9
deploy9-%: bin/kubectl
	$(eval TARGET := $(shell echo $* | sed 's/-ubi9-python.*//'))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$(TARGET)))/ubi9-python-$(PYTHON_VERSION)/kustomize/base)
ifndef NOTEBOOK_TAG
	$(eval NOTEBOOK_TAG := $*-$(IMAGE_TAG))
endif
	$(info # Deploying notebook from $(NOTEBOOK_DIR) directory...)
	@sed -i 's,newName: .*,newName: $(IMAGE_REGISTRY),g' $(NOTEBOOK_DIR)/kustomization.yaml
	@sed -i 's,newTag: .*,newTag: $(NOTEBOOK_TAG),g' $(NOTEBOOK_DIR)/kustomization.yaml
	$(KUBECTL_BIN) apply -k $(NOTEBOOK_DIR)

.PHONY: undeploy9
undeploy9-%: bin/kubectl
	$(eval TARGET := $(shell echo $* | sed 's/-ubi9-python.*//'))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$(TARGET)))/ubi9-python-$(PYTHON_VERSION)/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

.PHONY: deploy-c9s
deploy-c9s-%: bin/kubectl
	$(eval TARGET := $(shell echo $* | sed 's/-c9s-python.*//'))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$(TARGET)))/c9s-python-$(PYTHON_VERSION)/kustomize/base)
ifndef NOTEBOOK_TAG
	$(eval NOTEBOOK_TAG := $*-$(IMAGE_TAG))
endif
	$(info # Deploying notebook from $(NOTEBOOK_DIR) directory...)
	@sed -i 's,newName: .*,newName: $(IMAGE_REGISTRY),g' $(NOTEBOOK_DIR)/kustomization.yaml
	@sed -i 's,newTag: .*,newTag: $(NOTEBOOK_TAG),g' $(NOTEBOOK_DIR)/kustomization.yaml
	$(KUBECTL_BIN) apply -k $(NOTEBOOK_DIR)

.PHONY: undeploy-c9s
undeploy-c9s-%: bin/kubectl
	$(eval TARGET := $(shell echo $* | sed 's/-c9s-python.*//'))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$(TARGET)))/c9s-python-$(PYTHON_VERSION)/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

# Function for testing a notebook with papermill
#   ARG 1: Notebook name
#   ARG 1: UBI flavor
#   ARG 1: Python kernel
define test_with_papermill
	$(eval PREFIX_NAME := $(subst /,-,$(1)_$(2)))
	$(KUBECTL_BIN) exec $(FULL_NOTEBOOK_NAME) -- /bin/sh -c "python3 -m pip install papermill"
	if ! $(KUBECTL_BIN) exec $(FULL_NOTEBOOK_NAME) -- /bin/sh -c "wget ${NOTEBOOK_REPO_BRANCH_BASE}/jupyter/$(1)/$(2)-$(3)/test/test_notebook.ipynb -O test_notebook.ipynb && python3 -m papermill test_notebook.ipynb $(PREFIX_NAME)_output.ipynb --kernel python3 --stderr-file $(PREFIX_NAME)_error.txt" ; then
		echo "ERROR: The $(1) $(2) notebook encountered a failure. To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-$(1)-$(2)-$(3)-test-e2e' directory or run 'cat $(PREFIX_NAME)_error.txt' within your container. The make process has been aborted."
		exit 1
	fi
	if $(KUBECTL_BIN) exec $(FULL_NOTEBOOK_NAME) -- /bin/sh -c "cat $(PREFIX_NAME)_error.txt | grep --quiet FAILED" ; then
		echo "ERROR: The $(1) $(2) notebook encountered a failure. The make process has been aborted."
		$(KUBECTL_BIN) exec $(FULL_NOTEBOOK_NAME) -- /bin/sh -c "cat $(PREFIX_NAME)_error.txt"
		exit 1
	fi
endef

# Verify the notebook's readiness by pinging the /api endpoint and executing the corresponding test_notebook.ipynb file in accordance with the build chain logic.
.PHONY: test
test-%: bin/kubectl
	# Verify the notebook's readiness by pinging the /api endpoint
	$(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$*)))
	$(eval PYTHON_VERSION := $(shell echo $* | sed 's/.*-python-//'))
	$(info # Running tests for $(NOTEBOOK_NAME) notebook...)
	$(KUBECTL_BIN) wait --for=condition=ready pod -l app=$(NOTEBOOK_NAME) --timeout=600s
	$(KUBECTL_BIN) port-forward svc/$(NOTEBOOK_NAME)-notebook 8888:8888 & curl --retry 5 --retry-delay 5 --retry-connrefused http://localhost:8888/notebook/opendatahub/jovyan/api ; EXIT_CODE=$$?; echo && pkill --full "^$(KUBECTL_BIN).*port-forward.*"
	$(eval FULL_NOTEBOOK_NAME = $(shell ($(KUBECTL_BIN) get pods -l app=$(NOTEBOOK_NAME) -o custom-columns=":metadata.name" | tr -d '\n')))

	# Tests notebook's functionalities
	if echo "$(FULL_NOTEBOOK_NAME)" | grep -q "minimal-ubi9"; then
		$(call test_with_papermill,minimal,ubi9,python-$(PYTHON_VERSION))
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "intel-tensorflow-ubi9"; then
		$(call test_with_papermill,intel/tensorflow,ubi9,python-$(PYTHON_VERSION))
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "intel-pytorch-ubi9"; then
		$(call test_with_papermill,intel/pytorch,ubi9,python-$(PYTHON_VERSION))
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "datascience-ubi9"; then
		$(MAKE) validate-ubi9-datascience PYTHON_VERSION=$(PYTHON_VERSION) -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME)
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "pytorch-ubi9"; then
		$(MAKE) validate-ubi9-datascience PYTHON_VERSION=$(PYTHON_VERSION) -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME)
		$(call test_with_papermill,pytorch,ubi9,python-$(PYTHON_VERSION))
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "tensorflow-ubi9"; then
		$(MAKE) validate-ubi9-datascience PYTHON_VERSION=$(PYTHON_VERSION) -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME)
		$(call test_with_papermill,tensorflow,ubi9,python-$(PYTHON_VERSION))
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "intel-ml-ubi9"; then
		$(call test_with_papermill,intel/ml,ubi9,python-$(PYTHON_VERSION))
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "trustyai-ubi9"; then
		$(call test_with_papermill,trustyai,ubi9,python-$(PYTHON_VERSION))
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "anaconda"; then
		echo "There is no test notebook implemented yet for Anaconda Notebook...."
	else
		echo "No matching condition found for $(FULL_NOTEBOOK_NAME)."
	fi

.PHONY: validate-ubi9-datascience
validate-ubi9-datascience:
	$(call test_with_papermill,minimal,ubi9,python-$(PYTHON_VERSION))
	$(call test_with_papermill,datascience,ubi9,python-$(PYTHON_VERSION))

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
	curl -sSL -o test_script.R "${NOTEBOOK_REPO_BRANCH_BASE}/rstudio/c9s-python-$(PYTHON_VERSION)/test/test_script.R" > /dev/null 2>&1
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
PYTHON_VERSION ?= 3.11
ROOT_DIR := $(shell pwd)
BASE_DIRS := base/c9s-python-$(PYTHON_VERSION) \
		base/ubi9-python-$(PYTHON_VERSION) \
		jupyter/minimal/ubi9-python-$(PYTHON_VERSION) \
		jupyter/datascience/ubi9-python-$(PYTHON_VERSION) \
		jupyter/pytorch/ubi9-python-$(PYTHON_VERSION) \
		jupyter/tensorflow/ubi9-python-$(PYTHON_VERSION) \
		jupyter/trustyai/ubi9-python-$(PYTHON_VERSION) \
		jupyter/rocm/tensorflow/ubi9-python-$(PYTHON_VERSION) \
		jupyter/rocm/pytorch/ubi9-python-$(PYTHON_VERSION) \
		codeserver/ubi9-python-$(PYTHON_VERSION) \
		runtimes/minimal/ubi9-python-$(PYTHON_VERSION) \
		runtimes/datascience/ubi9-python-$(PYTHON_VERSION) \
		runtimes/pytorch/ubi9-python-$(PYTHON_VERSION) \
		runtimes/tensorflow/ubi9-python-$(PYTHON_VERSION) \
		runtimes/rocm-tensorflow/ubi9-python-$(PYTHON_VERSION) \
		runtimes/rocm-pytorch/ubi9-python-$(PYTHON_VERSION)

# Default value is false, can be overiden
# The below directories are not supported on tier-1
INCLUDE_OPT_DIRS ?= false
OPT_DIRS := jupyter/intel/ml/ubi9-python-$(PYTHON_VERSION) \
		jupyter/intel/pytorch/ubi9-python-$(PYTHON_VERSION) \
		jupyter/intel/tensorflow/ubi9-python-$(PYTHON_VERSION) \
		intel/runtimes/ml/ubi9-python-$(PYTHON_VERSION) \
		intel/runtimes/pytorch/ubi9-python-$(PYTHON_VERSION) \
		intel/runtimes/tensorflow/ubi9-python-$(PYTHON_VERSION)

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
			echo "Updating $(PYTHON_VERSION) Pipfile.lock in $$dir"
			cd $$dir
			if [ -f "Pipfile" ]; then
				pipenv lock
			else
				echo "No Pipfile found in $$dir, skipping."
			fi
		else
			echo "Skipping $$dir as it does not exist"
		fi
	done

# This is only for the workflow action
# For running manually, set the required environment variables
.PHONY: scan-image-vulnerabilities
scan-image-vulnerabilities:
	python ci/security-scan/quay_security_analysis.py
