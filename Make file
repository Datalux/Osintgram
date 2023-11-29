# Inspired by https://github.com/jessfraz/dotfiles

.PHONY: all
all: info docker test ## Run all targets.

.PHONY: test
test: info inspec ## Run tests

# if this session isn't interactive, then we don't want to allocate a
# TTY, which would fail, but if it is interactive, we do want to attach
# so that the user can send e.g. ^C through.
INTERACTIVE := $(shell [ -t 0 ] && echo 1 || echo 0)
ifeq ($(INTERACTIVE), 1)
	DOCKER_FLAGS += -t
endif

.PHONY: info
info: ## Gather information about the runtime environment
	echo "whoami: $$(whoami)"; \
	echo "pwd: $$(pwd)"; \
	echo "ls -ahl: $$(ls -ahl)"; \
	docker images; \
	docker ps

.PHONY: help
help: ## Show help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: inspec-check
inspec-check: ## Validate inspec profiles
	docker run $(DOCKER_FLAGS) \
		--rm \
		-v "$(CURDIR)":/workspace \
		-w="/workspace" \
		chef/inspec check \
		--chef-license=accept \
		test/inspec/super-linter

SUPER_LINTER_TEST_CONTAINER_NAME := "super-linter-test"
SUPER_LINTER_TEST_CONTAINER_URL := $(CONTAINER_IMAGE_ID)
DOCKERFILE := ''
IMAGE := $(CONTAINER_IMAGE_TARGET)

# Default to stadard
ifeq ($(IMAGE),)
IMAGE := "standard"
endif

# Default to latest
ifeq ($(SUPER_LINTER_TEST_CONTAINER_URL),)
SUPER_LINTER_TEST_CONTAINER_URL := "ghcr.io/super-linter/super-linter:latest"
endif

.PHONY: inspec
inspec: inspec-check ## Run InSpec tests
	DOCKER_CONTAINER_STATE="$$(docker inspect --format "{{.State.Running}}" $(SUPER_LINTER_TEST_CONTAINER_NAME) 2>/dev/null || echo "")"; \
	if [ "$$DOCKER_CONTAINER_STATE" = "true" ]; then docker kill $(SUPER_LINTER_TEST_CONTAINER_NAME); fi && \
	docker tag $(SUPER_LINTER_TEST_CONTAINER_URL) $(SUPER_LINTER_TEST_CONTAINER_NAME) && \
	SUPER_LINTER_TEST_CONTAINER_ID="$$(docker run -d --name $(SUPER_LINTER_TEST_CONTAINER_NAME) --rm -it --entrypoint /bin/ash $(SUPER_LINTER_TEST_CONTAINER_NAME) -c "while true; do sleep 1; done")" \
	&& docker run $(DOCKER_FLAGS) \
		--rm \
		-v "$(CURDIR)":/workspace \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-e IMAGE=$(IMAGE) \
		-w="/workspace" \
		chef/inspec exec test/inspec/super-linter\
		--chef-license=accept \
		--diagnose \
		--log-level=debug \
		-t "docker://$${SUPER_LINTER_TEST_CONTAINER_ID}" \
	&& docker ps \
	&& docker kill $(SUPER_LINTER_TEST_CONTAINER_NAME)

.phony: docker
docker: ## Build the container image
	@if [ -z "${GITHUB_TOKEN}" ]; then echo "GITHUB_TOKEN environment variable not set. Please set your GitHub Personal Access Token."; exit 1; fi
	DOCKER_BUILDKIT=1 docker buildx build --load \
		--build-arg BUILD_DATE=$(shell date -u +'%Y-%m-%dT%H:%M:%SZ') \
		--build-arg BUILD_REVISION=$(shell git rev-parse --short HEAD) \
		--build-arg BUILD_VERSION=$(shell git rev-parse --short HEAD) \
		--secret id=GITHUB_TOKEN,env=GITHUB_TOKEN \
		-t $(SUPER_LINTER_TEST_CONTAINER_URL) .

.phony: docker-pull
docker-pull: ## Pull the container image from registry
	docker pull $(SUPER_LINTER_TEST_CONTAINER_URL)
