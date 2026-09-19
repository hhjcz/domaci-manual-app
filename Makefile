# Local development for the Domácí manuál Home Assistant app.
# `make help` lists everything.

ADDON_DIR  := domaci_manual
IMAGE      := domaci-manual:dev
DEV_DIR    := .dev
VENV       := .venv
PY         := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
HOST_PORT  ?= 8099

# Read from build.yaml so there is one source of truth for the base image.
BUILD_FROM ?= $(shell sed -n 's/^  amd64: *//p' $(ADDON_DIR)/build.yaml)

# Git inside the container reads the bind-mounted fixture, which is owned by the
# host user; without this git refuses it as "dubious ownership".
DEV_GIT_ENV := -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=*

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV): requirements-dev.txt domaci_manual/requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements-dev.txt
	@touch $(VENV)

.PHONY: venv
venv: $(VENV) ## Create the development virtualenv

.PHONY: fixture
fixture: ## Recreate the local Git documentation fixture in .dev/
	./scripts/dev_fixture.sh

$(DEV_DIR)/data/options.json:
	./scripts/dev_fixture.sh

.PHONY: change
change: ## Push a documentation change to the fixture repository
	./scripts/dev_change.sh

.PHONY: test
test: $(VENV) ## Run the automated test suite (no network needed)
	$(VENV)/bin/pytest -q

.PHONY: e2e-github
e2e-github: $(VENV) ## Run the opt-in GitHub end-to-end test (see tests/test_github_e2e.py)
	$(VENV)/bin/pytest -q -m github

.PHONY: run
run: $(VENV) $(DEV_DIR)/data/options.json ## Run the app on the host against the fixture (fastest loop)
	DOMACI_MANUAL_DATA=$(CURDIR)/$(DEV_DIR)/data \
	DOMACI_MANUAL_ADDON_CONFIG=$(CURDIR)/$(DEV_DIR)/addon_config \
	DOMACI_MANUAL_KNOWN_HOSTS=$(CURDIR)/$(ADDON_DIR)/rootfs/usr/share/domaci-manual/known_hosts \
	PYTHONPATH=$(CURDIR)/$(ADDON_DIR)/src \
	$(PY) -m domaci_manual

.PHONY: build
build: ## Build the add-on container image
	docker build --build-arg BUILD_FROM=$(BUILD_FROM) -t $(IMAGE) $(ADDON_DIR)

.PHONY: up
up: build $(DEV_DIR)/data/options.json ## Build and run the container against the fixture repository
	docker run --rm --name domaci-manual-dev \
		-p $(HOST_PORT):8099 \
		-v $(CURDIR)/$(DEV_DIR)/data:/data \
		-v $(CURDIR)/$(DEV_DIR)/docs.git:$(CURDIR)/$(DEV_DIR)/docs.git:ro \
		$(DEV_GIT_ENV) \
		$(IMAGE)

.PHONY: lint
lint: $(VENV) ## Lint Python, YAML and shell scripts
	$(VENV)/bin/ruff check .
	$(VENV)/bin/yamllint -c .yamllint .
	docker run --rm -v $(CURDIR):/mnt -w /mnt koalaman/shellcheck:stable \
		-s bash -e SC1008 -x \
		scripts/*.sh .devcontainer/post_create.sh \
		$(ADDON_DIR)/rootfs/etc/s6-overlay/s6-rc.d/domaci-manual/run \
		$(ADDON_DIR)/rootfs/etc/s6-overlay/s6-rc.d/domaci-manual/finish

# `make up` runs as root inside the container, so .dev/data ends up root-owned
# on the host; delete it from a container that can.
.PHONY: clean
clean: ## Remove development state
	@if [ -d "$(DEV_DIR)/data" ]; then \
		docker run --rm --entrypoint /bin/rm \
			-v $(CURDIR)/$(DEV_DIR):/devdir $(BUILD_FROM) -rf /devdir/data; \
	fi
	rm -rf $(DEV_DIR) $(VENV) .pytest_cache .ruff_cache
