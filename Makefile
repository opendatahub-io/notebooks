CONTAINER_ENGINE ?= podman
IMAGE_REGISTRY   ?= quay.io/opendatahub/workbench-images
RELEASE	 		 ?= 2023a
DATE 			 ?= $(shell date +'%Y%m%d')
IMAGE_TAG		 ?= $(RELEASE)_$(DATE)
KUBECTL_BIN      ?= bin/kubectl
KUBECTL_VERSION  ?= v1.23.11

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
	$(CONTAINER_ENGINE) build -t $(IMAGE_NAME) $(BUILD_ARGS) $(2)
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
define image
	$(call build_image,$(1),$(2),$(3))
	$(call push_image,$(1))
endef

# Build and push base-ubi8-python-3.8 image to the registry
.PHONY: base-ubi8-python-3.8
base-ubi8-python-3.8:
	$(call image,$@,base/ubi8-python-3.8)

# Build and push jupyter-minimal-ubi8-python-3.8 image to the registry
.PHONY: jupyter-minimal-ubi8-python-3.8
jupyter-minimal-ubi8-python-3.8: base-ubi8-python-3.8
	$(call image,$@,jupyter/minimal/ubi8-python-3.8,$<)

# Build and push jupyter-datascience-ubi8-python-3.8 image to the registry
.PHONY: jupyter-datascience-ubi8-python-3.8
jupyter-datascience-ubi8-python-3.8: jupyter-minimal-ubi8-python-3.8
	$(call image,$@,jupyter/datascience/ubi8-python-3.8,$<)

# Build and push jupyter-pytorch-ubi8-python-3.8 image to the registry
.PHONY: jupyter-pytorch-ubi8-python-3.8
jupyter-pytorch-ubi8-python-3.8: jupyter-datascience-ubi8-python-3.8
	$(call image,$@,jupyter/pytorch/ubi8-python-3.8,$<)

# Build and push cuda-ubi8-python-3.8 image to the registry
.PHONY: cuda-ubi8-python-3.8
cuda-ubi8-python-3.8: base-ubi8-python-3.8
	$(eval $(call generate_image_tag,IMAGE_TAG))
	$(call image,$@,cuda/ubi8-python-3.8,$<)

# Build and push cuda-jupyter-minimal-ubi8-python-3.8 image to the registry
.PHONY: cuda-jupyter-minimal-ubi8-python-3.8
cuda-jupyter-minimal-ubi8-python-3.8: cuda-ubi8-python-3.8
	$(call image,$@,jupyter/minimal/ubi8-python-3.8,$<)

# Build and push cuda-jupyter-datascience-ubi8-python-3.8 image to the registry
.PHONY: cuda-jupyter-datascience-ubi8-python-3.8
cuda-jupyter-datascience-ubi8-python-3.8: cuda-jupyter-minimal-ubi8-python-3.8
	$(call image,$@,jupyter/datascience/ubi8-python-3.8,$<)

# Build and push cuda-jupyter-tensorflow-ubi8-python-3.8 image to the registry
.PHONY: cuda-jupyter-tensorflow-ubi8-python-3.8
cuda-jupyter-tensorflow-ubi8-python-3.8: cuda-jupyter-datascience-ubi8-python-3.8
	$(call image,$@,jupyter/tensorflow/ubi8-python-3.8,$<)

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

# Build and push jupyter-pytorch-ubi9-python-3.9 image to the registry
.PHONY: jupyter-pytorch-ubi9-python-3.9
jupyter-pytorch-ubi9-python-3.9: jupyter-datascience-ubi9-python-3.9
	$(call image,$@,jupyter/pytorch/ubi9-python-3.9,$<)

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

# Build and push jupyter-trustyai-ubi9-python-3.9 image to the registry
.PHONY: jupyter-trustyai-ubi9-python-3.9
jupyter-trustyai-ubi9-python-3.9: jupyter-datascience-ubi9-python-3.9
	$(call image,$@,jupyter/trustyai/ubi9-python-3.9,$<)

# Download kubectl binary
.PHONY: bin/kubectl
bin/kubectl:
ifeq (,$(wildcard $(KUBECTL_BIN)))
	@mkdir -p bin
	@curl -sSL https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/linux/amd64/kubectl > \
		$(KUBECTL_BIN)
	@chmod +x $(KUBECTL_BIN)
endif

# Deploy a notebook image using kustomize
.PHONY: deploy8
deploy8-%-ubi8-python-3.8: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$*))/ubi8-python-3.8/kustomize/base)
ifndef NOTEBOOK_TAG
	$(eval NOTEBOOK_TAG := $*-ubi8-python-3.8-$(IMAGE_TAG))
endif
	$(info # Deploying notebook from $(NOTEBOOK_DIR) directory...)
	@sed -i 's,newName: .*,newName: $(IMAGE_REGISTRY),g' $(NOTEBOOK_DIR)/kustomization.yaml
	@sed -i 's,newTag: .*,newTag: $(NOTEBOOK_TAG),g' $(NOTEBOOK_DIR)/kustomization.yaml
	$(KUBECTL_BIN) apply -k $(NOTEBOOK_DIR)

.PHONY: deploy9
deploy9-%-ubi9-python-3.9: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$*))/ubi9-python-3.9/kustomize/base)
ifndef NOTEBOOK_TAG
	$(eval NOTEBOOK_TAG := $*-ubi9-python-3.9-$(IMAGE_TAG))
endif
	$(info # Deploying notebook from $(NOTEBOOK_DIR) directory...)
	@sed -i 's,newName: .*,newName: $(IMAGE_REGISTRY),g' $(NOTEBOOK_DIR)/kustomization.yaml
	@sed -i 's,newTag: .*,newTag: $(NOTEBOOK_TAG),g' $(NOTEBOOK_DIR)/kustomization.yaml
	$(KUBECTL_BIN) apply -k $(NOTEBOOK_DIR)

# Undeploy a notebook image using kustomize
.PHONY: undeploy8
undeploy8-%-ubi8-python-3.8: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$*))/ubi8-python-3.8/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

.PHONY: undeploy9
undeploy9-%-ubi9-python-3.9: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$*))/ubi9-python-3.9/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

# Check if the notebook is ready by pinging the /api endpoint
.PHONY: test
test-%: bin/kubectl
	$(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$*)))
	$(info # Running tests for $(NOTEBOOK_NAME) notebook...)
	$(KUBECTL_BIN) wait --for=condition=ready pod -l app=$(NOTEBOOK_NAME) --timeout=300s
	$(KUBECTL_BIN) port-forward svc/$(NOTEBOOK_NAME)-notebook 8888:8888 &
	curl --retry 5 --retry-delay 5 --retry-connrefused \
		http://localhost:8888/notebook/opendatahub/jovyan/api; EXIT_CODE=$$?; echo && \
	pkill --full "^$(KUBECTL_BIN).*port-forward.*"; \
	exit $${EXIT_CODE}

# This is only for the workflow action
.PHONY: refresh-pipfilelock-files
refresh-pipfilelock-files:
	cd base/ubi8-python-3.8 && pipenv lock
	cd base/ubi9-python-3.9 && pipenv lock
	cd jupyter/minimal/ubi8-python-3.8 && pipenv lock
	cd jupyter/minimal/ubi9-python-3.9 && pipenv lock
	cd jupyter/datascience/ubi8-python-3.8 && pipenv lock
	cd jupyter/datascience/ubi9-python-3.9 && pipenv lock
	cd jupyter/pytorch/ubi9-python-3.9 && pipenv lock
	cd jupyter/pytorch/ubi8-python-3.8 && pipenv lock
	cd jupyter/tensorflow/ubi8-python-3.8 && pipenv lock
	cd jupyter/tensorflow/ubi9-python-3.9 && pipenv lock
	cd jupyter/trustyai/ubi9-python-3.9 && pipenv lock

