CONTAINER_ENGINE ?= podman
IMAGE_REGISTRY   ?= quay.io/opendatahub/notebooks
IMAGE_TAG        ?= $(shell git describe --tags --always --dirty || echo 'dev')

# Build and push notebook images
.PHONY: build-image
build-image:
	$(eval IMAGE_NAME := $(subst /,-,$(IMAGE_CONTEXT))-$(IMAGE_TAG))
	$(info Building $(IMAGE_NAME) image...)
	$(CONTAINER_ENGINE) build -t $(IMAGE_REGISTRY):$(IMAGE_NAME) $(IMAGE_CONTEXT)

.PHONY: push-image
push-image:
	$(eval IMAGE_NAME := $(subst /,-,$(IMAGE_CONTEXT))-$(IMAGE_TAG))
	$(info Pushing $(IMAGE_NAME) image...)
	$(CONTAINER_ENGINE) push $(IMAGE_REGISTRY):$(IMAGE_NAME)

.PHONY: image
image: build-image push-image

# Build and push base/ubi8-python-3.8 image
.PHONY: base-ubi8-python-3.8
base-ubi8-python-3.8: IMAGE_CONTEXT=base/ubi8-python-3.8
base-ubi8-python-3.8: image

