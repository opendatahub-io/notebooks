VERBOSE ?= FALSE
DOCKER ?= docker
DOCKER_CACHE ?= FALSE
BUILD_OS ?= ubuntu22.04
BUILD_DIR ?= $(CURDIR)/dockerbuild

REPO_SERVER ?= vault.habana.ai
PT_VERSION ?= 2.3.1
RELEASE_VERSION ?= 1.17.1
RELEASE_BUILD_ID ?= 40

BASE_IMAGE_URL ?= base-installer-$(BUILD_OS)
IMAGE_URL = $(IMAGE_NAME):$(RELEASE_VERSION)-$(RELEASE_BUILD_ID)

DOCKER_BUILD_ARGS := --build-arg ARTIFACTORY_URL=$(REPO_SERVER) --build-arg VERSION=$(RELEASE_VERSION) --build-arg REVISION=$(RELEASE_BUILD_ID) --build-arg BASE_NAME=$(BASE_IMAGE_URL)

# Hide or not the calls depending of VERBOSE
ifeq ($(VERBOSE),TRUE)
	HIDE =
else
	HIDE = @
endif

# Use cache for build depending of DOCKER_CACHE
ifeq ($(DOCKER_CACHE),TRUE)
	CACH_FLAG =
else
	CACH_FLAG = --no-cache
endif

.PHONY: help build clean

help: ## Prints this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.DEFAULT_GOAL := help

clean: ## clean the build dir
	$(HIDE)rm -rf $(BUILD_DIR)

build:  ## build docker image
	@echo Building image - $(IMAGE_NAME)
	$(HIDE)$(DOCKER) build --network=host $(CACH_FLAG) --tag $(IMAGE_URL) $(DOCKER_BUILD_ARGS) $(BUILD_DIR)
	@echo -n $(IMAGE_URL) | tee $(BUILD_DIR)/image_name