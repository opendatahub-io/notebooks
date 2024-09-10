
include ../common.mk

IMAGE_NAME = base-installer-${BUILD_OS}

ifdef REPO_NAME
	DOCKER_BUILD_ARGS := $(DOCKER_BUILD_ARGS) --build-arg REPO_NAME=$(REPO_NAME)
endif

init:
	$(HIDE)mkdir -p $(BUILD_DIR)
	$(HIDE)cp $(CURDIR)/LICENSE $(BUILD_DIR)/
	$(HIDE)cp $(CURDIR)/*.sh $(BUILD_DIR)/
	$(HIDE)cp $(CURDIR)/tencentos_efa_patch.txt $(BUILD_DIR)/
	$(HIDE)cp $(CURDIR)/Dockerfile.$(BUILD_OS) $(BUILD_DIR)/Dockerfile

build: init
