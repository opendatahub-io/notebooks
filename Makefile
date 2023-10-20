CONTAINER_ENGINE ?= podman
IMAGE_REGISTRY   ?= quay.io/opendatahub/workbench-images
RELEASE	 		 ?= 2023a
DATE 			 ?= $(shell date +'%Y%m%d')
IMAGE_TAG		 ?= $(RELEASE)_$(DATE)
KUBECTL_BIN      ?= bin/kubectl
KUBECTL_VERSION  ?= v1.23.11
NOTEBOOK_REPO_BRANCH_BASE ?= https://raw.githubusercontent.com/opendatahub-io/notebooks/main
REQUIRED_RUNTIME_IMAGE_COMMANDS="curl python3"
REQUIRED_CODE_SERVER_IMAGE_COMMANDS="curl python oc code-server"
REQUIRED_R_STUDIO_IMAGE_COMMANDS="curl python oc /usr/lib/rstudio-server/bin/rserver"


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
	$(CONTAINER_ENGINE) build --no-cache  -t $(IMAGE_NAME) $(BUILD_ARGS) $(2)
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

####################################### Buildchain for Python 3.8 using ubi8 #######################################

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

# Build and push jupyter-trustyai-ubi8-python-3.8 image to the registry
.PHONY: jupyter-trustyai-ubi8-python-3.8
jupyter-trustyai-ubi8-python-3.8: jupyter-datascience-ubi8-python-3.8
	$(call image,$@,jupyter/trustyai/ubi8-python-3.8,$<)

# Build and push habana-jupyter-1.9.0-ubi8-python-3.8 image to the registry
.PHONY: habana-jupyter-1.9.0-ubi8-python-3.8
habana-jupyter-1.9.0-ubi8-python-3.8: jupyter-datascience-ubi8-python-3.8
	$(call image,$@,habana/1.9.0/ubi8-python-3.8,$<)

# Build and push habana-jupyter-1.10.0-ubi8-python-3.8 image to the registry
.PHONY: habana-jupyter-1.10.0-ubi8-python-3.8
habana-jupyter-1.10.0-ubi8-python-3.8: jupyter-datascience-ubi8-python-3.8
	$(call image,$@,habana/1.10.0/ubi8-python-3.8,$<)

# Build and push habana-jupyter-1.11.0-ubi8-python-3.8 image to the registry
.PHONY: habana-jupyter-1.11.0-ubi8-python-3.8
habana-jupyter-1.11.0-ubi8-python-3.8: jupyter-datascience-ubi8-python-3.8
	$(call image,$@,habana/1.11.0/ubi8-python-3.8,$<)

# Build and push runtime-minimal-ubi8-python-3.8 image to the registry
.PHONY: runtime-minimal-ubi8-python-3.8
runtime-minimal-ubi8-python-3.8: base-ubi8-python-3.8
	$(call image,$@,runtimes/minimal/ubi8-python-3.8,$<)

# Build and push runtime-datascience-ubi8-python-3.8 image to the registry
.PHONY: runtime-datascience-ubi8-python-3.8
runtime-datascience-ubi8-python-3.8: base-ubi8-python-3.8
	$(call image,$@,runtimes/datascience/ubi8-python-3.8,$<)

# Build and push runtime-pytorch-ubi8-python-3.8 image to the registry
.PHONY: runtime-pytorch-ubi8-python-3.8
runtime-pytorch-ubi8-python-3.8: base-ubi8-python-3.8
	$(call image,$@,runtimes/pytorch/ubi8-python-3.8,$<)

# Build and push runtime-cuda-tensorflow-ubi8-python-3.8 image to the registry
.PHONY: runtime-cuda-tensorflow-ubi8-python-3.8
runtime-cuda-tensorflow-ubi8-python-3.8: cuda-ubi8-python-3.8
	$(call image,$@,runtimes/tensorflow/ubi8-python-3.8,$<)

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

####################################### Buildchain for Python 3.9 using C9S #######################################

# Build and push base-c9s-python-3.9 image to the registry
.PHONY: base-c9s-python-3.9
base-c9s-python-3.9:
	$(call image,$@,base/c9s-python-3.9)

.PHONY: cuda-c9s-python-3.9
cuda-c9s-python-3.9: base-c9s-python-3.9
	$(call image,$@,cuda/c9s-python-3.9,$<)

.PHONY: codeserver-c9s-python-3.9
codeserver-c9s-python-3.9: base-c9s-python-3.9
	$(call image,$@,codeserver/c9s-python-3.9,$<)

.PHONY: rstudio-c9s-python-3.9
rstudio-c9s-python-3.9: base-c9s-python-3.9
	$(call image,$@,rstudio/c9s-python-3.9,$<)

.PHONY: cuda-rstudio-c9s-python-3.9
cuda-rstudio-c9s-python-3.9: cuda-c9s-python-3.9
	$(call image,$@,rstudio/c9s-python-3.9,$<)

####################################### Buildchain for Anaconda Python #######################################

# Build and push base-anaconda-python-3.8 image to the registry
.PHONY: base-anaconda-python-3.8
base-anaconda-python-3.8:
	$(call image,$@,base/anaconda-python-3.8)

# Build and push jupyter-datascience-anaconda-python-3.8 image to the registry
.PHONY: jupyter-datascience-anaconda-python-3.8
jupyter-datascience-anaconda-python-3.8: base-anaconda-python-3.8
	$(call image,$@,jupyter/datascience/anaconda-python-3.8,$<)


####################################### Deployments #######################################

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

# Deploy a notebook image using kustomize
.PHONY: deploy-anaconda8
deploy8-%-anaconda-python-3.8: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$*))/anaconda-python-3.8/kustomize/base)
ifndef NOTEBOOK_TAG
	$(eval NOTEBOOK_TAG := $*-anaconda-python-3.8-$(IMAGE_TAG))
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

.PHONY: undeploy-anaconda8
undeploy8-%-anaconda-python-3.8: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$*))/anaconda-python-3.8/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

.PHONY: undeploy9
undeploy9-%-ubi9-python-3.9: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$*))/ubi9-python-3.9/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

.PHONY: deploy-c9s
deploy-c9s-%-c9s-python-3.9: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$*))/c9s-python-3.9/kustomize/base)
ifndef NOTEBOOK_TAG
	$(eval NOTEBOOK_TAG := $*-c9s-python-3.9-$(IMAGE_TAG))
endif
	$(info # Deploying notebook from $(NOTEBOOK_DIR) directory...)
	@sed -i 's,newName: .*,newName: $(IMAGE_REGISTRY),g' $(NOTEBOOK_DIR)/kustomization.yaml
	@sed -i 's,newTag: .*,newTag: $(NOTEBOOK_TAG),g' $(NOTEBOOK_DIR)/kustomization.yaml
	$(KUBECTL_BIN) apply -k $(NOTEBOOK_DIR)

.PHONY: undeploy-c9s
undeploy-c9s-%-c9s-python-3.9: bin/kubectl
	$(eval NOTEBOOK_DIR := $(subst -,/,$(subst cuda-,,$*))/c9s-python-3.9/kustomize/base)
	$(info # Undeploying notebook from $(NOTEBOOK_DIR) directory...)
	$(KUBECTL_BIN) delete -k $(NOTEBOOK_DIR)

# Function for testing a notebook with papermill
#   ARG 1: Notebook name
#   ARG 1: UBI flavor
#   ARG 1: Python kernel
define test_with_papermill
	$(KUBECTL_BIN) exec $(FULL_NOTEBOOK_NAME) -- /bin/sh -c "python3 -m pip install papermill" ; \
	$(KUBECTL_BIN) exec $(FULL_NOTEBOOK_NAME) -- /bin/sh -c "wget ${NOTEBOOK_REPO_BRANCH_BASE}/jupyter/$(1)/$(2)-$(3)/test/test_notebook.ipynb -O test_notebook.ipynb && python3 -m papermill test_notebook.ipynb $(1)_$(2)_output.ipynb --kernel python3 --stderr-file $(1)_$(2)_error.txt" ; \
    if [ $$? -ne 0 ]; then \
		echo "ERROR: The $(1) $(2) notebook encountered a failure. To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-$(1)-$(2)-$(3)-test-e2e' directory or run 'cat $(1)_$(2)_error.txt' within your container. The make process has been aborted." ; \
		exit 1 ; \
	fi ; \
	$(KUBECTL_BIN) exec $(FULL_NOTEBOOK_NAME) -- /bin/sh -c "cat $(1)_$(2)_error.txt | grep --quiet FAILED" ; \
	if [ $$? -eq 0 ]; then \
		echo "ERROR: The $(1) $(2) notebook encountered a failure. The make process has been aborted." ; \
		$(KUBECTL_BIN) exec $(FULL_NOTEBOOK_NAME) -- /bin/sh -c "cat $(1)_$(2)_error.txt" ; \
		exit 1 ; \
	fi
endef

# Verify the notebook's readiness by pinging the /api endpoint and executing the corresponding test_notebook.ipynb file in accordance with the build chain logic.
.PHONY: test
test-%: bin/kubectl

	# Verify the notebook's readiness by pinging the /api endpoint
	$(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$*)))
	$(info # Running tests for $(NOTEBOOK_NAME) notebook...)
	$(KUBECTL_BIN) wait --for=condition=ready pod -l app=$(NOTEBOOK_NAME) --timeout=600s
	$(KUBECTL_BIN) port-forward svc/$(NOTEBOOK_NAME)-notebook 8888:8888 & curl --retry 5 --retry-delay 5 --retry-connrefused http://localhost:8888/notebook/opendatahub/jovyan/api ; EXIT_CODE=$$?; echo && pkill --full "^$(KUBECTL_BIN).*port-forward.*"; \
	$(eval FULL_NOTEBOOK_NAME = $(shell ($(KUBECTL_BIN) get pods -l app=$(NOTEBOOK_NAME) -o custom-columns=":metadata.name" | tr -d '\n')))
	
	# Tests notebook's functionalities 
	if echo "$(FULL_NOTEBOOK_NAME)" | grep -q "minimal-ubi9"; then \
		$(call test_with_papermill,minimal,ubi9,python-3.9) \
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "datascience-ubi9"; then \
		$(MAKE) validate-ubi9-datascience -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME); \
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "pytorch-ubi9"; then \
		$(MAKE) validate-ubi9-datascience -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME); \
		$(call test_with_papermill,pytorch,ubi9,python-3.9) \
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "tensorflow-ubi9"; then \
		$(MAKE) validate-ubi9-datascience -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME); \
		$(call test_with_papermill,tensorflow,ubi9,python-3.9) \
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "trustyai-ubi9"; then \
		$(MAKE) validate-ubi9-datascience -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME); \
		$(call test_with_papermill,trustyai,ubi9,python-3.9) \
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "minimal-ubi8"; then \
		$(call test_with_papermill,minimal,ubi8,python-3.8) \
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "datascience-ubi8"; then \
		$(MAKE) validate-ubi8-datascience -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME); \
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "pytorch-ubi8"; then \
		$(MAKE) validate-ubi8-datascience -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME); \
		$(call test_with_papermill,pytorch,ubi8,python-3.8) \
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "tensorflow-ubi8"; then \
		$(MAKE) validate-ubi8-datascience -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME); \
		$(call test_with_papermill,tensorflow,ubi8,python-3.8) \
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "trustyai-ubi8"; then \
		$(MAKE) validate-ubi8-datascience -e FULL_NOTEBOOK_NAME=$(FULL_NOTEBOOK_NAME); \
		$(call test_with_papermill,trustyai,ubi8,python-3.8) \
	elif echo "$(FULL_NOTEBOOK_NAME)" | grep -q "anaconda"; then \
		echo "There is no test notebook implemented yet for Anaconda Notebook...." \
	else \
		echo "No matching condition found for $(FULL_NOTEBOOK_NAME)." ; \
	fi

.PHONY: validate-ubi9-datascience
validate-ubi9-datascience:
	$(call test_with_papermill,minimal,ubi9,python-3.9)
	$(call test_with_papermill,datascience,ubi9,python-3.9)

.PHONY: validate-ubi8-datascience
validate-ubi8-datascience:
	$(call test_with_papermill,minimal,ubi8,python-3.8)
	$(call test_with_papermill,datascience,ubi8,python-3.8)

# Validate that runtime image meets minimum criteria
# This validation is created from subset of https://github.com/elyra-ai/elyra/blob/9c417d2adc9d9f972de5f98fd37f6945e0357ab9/Makefile#L325
.PHONY: validate-runtime-image
validate-runtime-image: bin/kubectl
	$(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$*)))
	$(info # Running tests for $(NOTEBOOK_NAME) runtime...)
	$(KUBECTL_BIN) wait --for=condition=ready pod runtime-pod --timeout=300s
	@required_commands=$(REQUIRED_RUNTIME_IMAGE_COMMANDS) ; \
	if [[ $$image == "" ]] ; then \
		echo "Usage: make validate-runtime-image image=<container-image-name>" ; \
		exit 1 ; \
	fi ; \
	for cmd in $$required_commands ; do \
		echo "=> Checking container image $$image for $$cmd..." ; \
		$(KUBECTL_BIN) exec runtime-pod which $$cmd > /dev/null 2>&1 ; \
		if [ $$? -ne 0 ]; then \
			echo "ERROR: Container image $$image  does not meet criteria for command: $$cmd" ; \
			fail=1; \
			continue; \
		fi; \
		if [ $$cmd == "python3" ]; then \
			echo "=> Checking notebook execution..." ; \
			$(KUBECTL_BIN) exec runtime-pod -- /bin/sh -c "python3 -m pip install -r /opt/app-root/elyra/requirements-elyra.txt && \
				curl https://raw.githubusercontent.com/nteract/papermill/main/papermill/tests/notebooks/simple_execute.ipynb --output simple_execute.ipynb && \
				python3 -m papermill simple_execute.ipynb output.ipynb > /dev/null" ; \
			if [ $$? -ne 0 ]; then \
				echo "ERROR: Image does not meet Python requirements criteria in requirements-elyra.txt" ; \
				fail=1; \
			fi; \
		fi; \
	done ; \
	if [ $$fail -eq 1 ]; then \
		echo "=> ERROR: Container image $$image is not a suitable Elyra runtime image" ; \
		exit 1 ; \
	else \
		echo "=> Container image $$image is a suitable Elyra runtime image" ; \
	fi;

.PHONY: validate-codeserver-image
validate-codeserver-image: bin/kubectl
	$(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$*)))
	$(info # Running tests for $(NOTEBOOK_NAME) Code Server image...)
	$(KUBECTL_BIN) wait --for=condition=ready pod codeserver-pod --timeout=300s
	@required_commands=$(REQUIRED_CODE_SERVER_IMAGE_COMMANDS) ; \
	if [[ $$image == "" ]] ; then \
		echo "Usage: make validate-codeserver-image image=<container-image-name>" ; \
		exit 1 ; \
	fi ; \
	for cmd in $$required_commands ; do \
		echo "=> Checking container image $$image for $$cmd..." ; \
		$(KUBECTL_BIN) exec codeserver-pod which $$cmd > /dev/null 2>&1 ; \
		if [ $$? -ne 0 ]; then \
			echo "ERROR: Container image $$image  does not meet criteria for command: $$cmd" ; \
			fail=1; \
			continue; \
		fi; \
	done ; \

.PHONY: validate-rstudio-image
validate-rstudio-image: bin/kubectl
	$(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$*)))
	$(info # Running tests for $(NOTEBOOK_NAME) Code Server image...)
	$(KUBECTL_BIN) wait --for=condition=ready pod rstudio-pod --timeout=300s
	@required_commands=$(REQUIRED_R_STUDIO_IMAGE_COMMANDS) ; \
	if [[ $$image == "" ]] ; then \
		echo "Usage: make validate-rstudio-image image=<container-image-name>" ; \
		exit 1 ; \
	fi ; \
	for cmd in $$required_commands ; do \
		echo "=> Checking container image $$image for $$cmd..." ; \
		$(KUBECTL_BIN) exec rstudio-pod which $$cmd > /dev/null 2>&1 ; \
		if [ $$? -ne 0 ]; then \
			echo "ERROR: Container image $$image  does not meet criteria for command: $$cmd" ; \
			fail=1; \
			continue; \
		fi; \
	done ; \

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
	cd jupyter/tensorflow/ubi9-python-3.9 && pipenv lock
	cd jupyter/trustyai/ubi8-python-3.8 && pipenv lock
	cd jupyter/trustyai/ubi9-python-3.9 && pipenv lock
	cd runtimes/datascience/ubi8-python-3.8 && pipenv lock
	cd runtimes/datascience/ubi9-python-3.9 && pipenv lock
	cd runtimes/pytorch/ubi9-python-3.9 && pipenv lock
	cd runtimes/pytorch/ubi8-python-3.8 && pipenv lock
	cd runtimes/tensorflow/ubi8-python-3.8 && pipenv lock
	cd runtimes/tensorflow/ubi9-python-3.9 && pipenv lock
	cd base/c9s-python-3.9 && pipenv lock
	