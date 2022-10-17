CONTAINER_ENGINE ?= podman
IMAGE_REGISTRY   ?= quay.io/opendatahub/notebooks
IMAGE_TAG        ?= $(shell git describe --tags --always --dirty || echo 'dev')
KUBECTL_BIN      ?= bin/kubectl
KUBECTL_VERSION  ?= v1.23.11

# Build function for the notebok image:
# 	ARG 1: Path of image context we want to build.
#	ARG 2: Path of the base image directory.
define build_image
	$(eval IMAGE_NAME := $(IMAGE_REGISTRY):$(subst /,-,$(1))-$(IMAGE_TAG))
	$(info ## Building $(IMAGE_NAME) image...)
	$(if $(2),
		$(eval BASE_IMAGE_NAME := $(IMAGE_REGISTRY):$(subst /,-,$(2))-$(IMAGE_TAG))
		$(eval BUILD_ARGS := --build-arg BASE_IMAGE=$(BASE_IMAGE_NAME)),
		$(eval BUILD_ARGS :=)
	)
	$(CONTAINER_ENGINE) build -t $(IMAGE_NAME) $(BUILD_ARGS) $(1)
endef

# Push function for the notebok image:
# 	ARG 1: Path of image context we want to build.
define push_image
	$(eval IMAGE_NAME := $(IMAGE_REGISTRY):$(subst /,-,$(1))-$(IMAGE_TAG))
	$(info ## Pushing $(IMAGE_NAME) image...)
	$(CONTAINER_ENGINE) push $(IMAGE_NAME)
endef

# Build and push the notebook images:
#   ARG 1: Path of image context we want to build.
#   ARG 2: Path of the base image directory.
define image
	$(call build_image,$(1),$(2))
	$(call push_image,$(1))
endef

# Generate requirements.txt using a containerized Python virtual environment:
#   ARG 1: Name of the container image with pip-compile tool installed.
#   ARG 2: Path of requirements.in input files.
#   ARG 3: Path of requirements.txt output file.
define pip_compile
	$(info # Locking $(3) file..)
	$(eval PY_BUILDER_IMAGE := $(IMAGE_REGISTRY):$(subst /,-,$(1))-$(IMAGE_TAG))
	$(CONTAINER_ENGINE) run -q --rm -i --entrypoint="" $(PY_BUILDER_IMAGE) \
		pip-compile -q --generate-hashes --allow-unsafe --output-file=- - <<< $$(cat $(2)) > $(3)
endef

# Build bootstrap/ubi8-python-3.8 image, used to generate the corresponding
# requirements.txt file for the notebooks images
.PHONY: bootstrap-ubi8-python-3.8
bootstrap-ubi8-python-3.8:
	$(call build_image,bootstrap/ubi8-python-3.8)

# Build and push base/ubi8-python-3.8 image to the registry
.PHONY: base-ubi8-python-3.8
base-ubi8-python-3.8: bootstrap-ubi8-python-3.8
	$(call pip_compile,bootstrap/ubi8-python-3.8,\
		base/ubi8-python-3.8/requirements.in,\
		base/ubi8-python-3.8/requirements.txt)
	$(call image,base/ubi8-python-3.8)

# Build and push jupyter/minimal-ubi8-python-3.8 image to the registry
.PHONY: jupyter-minimal-ubi8-python-3.8
jupyter-minimal-ubi8-python-3.8: base-ubi8-python-3.8
	$(call pip_compile,bootstrap/ubi8-python-3.8,\
		base/ubi8-python-3.8/requirements.in jupyter/minimal/ubi8-python-3.8/requirements.in,\
		jupyter/minimal/ubi8-python-3.8/requirements.txt)
	$(call image,jupyter/minimal/ubi8-python-3.8,base/ubi8-python-3.8)

# Build and push jupyter-datascience-ubi8-python-3.8 image to the registry
.PHONY: jupyter-datascience-ubi8-python-3.8
jupyter-datascience-ubi8-python-3.8: jupyter-minimal-ubi8-python-3.8
	$(call pip_compile,bootstrap/ubi8-python-3.8,\
		base/ubi8-python-3.8/requirements.in jupyter/minimal/ubi8-python-3.8/requirements.in jupyter/datascience/ubi8-python-3.8/requirements.in,\
		jupyter/datascience/ubi8-python-3.8/requirements.txt)
	$(call image,jupyter/datascience/ubi8-python-3.8,jupyter/minimal/ubi8-python-3.8)

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
.PHONY: deploy
deploy-%-ubi8-python-3.8: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$*)/ubi8-python-3.8/kustomize/base)
ifndef NOTEBOOK_TAG
	$(eval NOTEBOOK_TAG := $*-ubi8-python-3.8-$(IMAGE_TAG))
endif
	$(info # Deploying notebook from $(NOTEBOOK_DIR) directory...)
	@sed -i 's,newName: .*,newName: $(IMAGE_REGISTRY),g' $(NOTEBOOK_DIR)/kustomization.yaml
	@sed -i 's,newTag: .*,newTag: $(NOTEBOOK_TAG),g' $(NOTEBOOK_DIR)/kustomization.yaml
	$(KUBECTL_BIN) apply -k $(NOTEBOOK_DIR)

# Undeploy a notebook image using kustomize
.PHONY: undeploy
undeploy-%-ubi8-python-3.8: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$*)/ubi8-python-3.8/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

# Check if the notebook is ready by pinging the /api endpoint
.PHONY: test
test-%: bin/kubectl
	$(eval NOTEBOOK_NAME := $(subst .,-,$*))
	$(info # Running tests for $(NOTEBOOK_NAME) notebook...)
	$(KUBECTL_BIN) wait --for=condition=ready pod -l app=$(NOTEBOOK_NAME) --timeout=60s
	$(KUBECTL_BIN) port-forward svc/$(NOTEBOOK_NAME)-notebook 8888:8888 &
	curl --retry 5 --retry-delay 5 --retry-connrefused \
		http://localhost:8888/notebook/opendatahub/jovyan/api; EXIT_CODE=$$?; echo && \
	pkill --full "^$(KUBECTL_BIN).*port-forward.*"; \
	exit $${EXIT_CODE}
