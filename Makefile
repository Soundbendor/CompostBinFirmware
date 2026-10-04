SHELL := /bin/bash
.DEFAULT_GOAL := help

UV ?= uv
PYTHON ?= .venv/bin/python
IMAGE_TAG ?= compost-bin-firmware:dev
HIL_TEST ?=

.PHONY: help bootstrap check test image hil-list hil

help:
	@echo "Smart Compost Bin firmware tasks"
	@echo ""
	@echo "  make bootstrap  Sync the locked runtime environment"
	@echo "  make check      Validate repository metadata and syntax"
	@echo "  make test       Run workstation unit tests"
	@echo "  make image      Build a local linux/arm64 image without pushing"
	@echo "  make hil-list   List guarded hardware-in-the-loop checks"
	@echo "  make hil        Run one approved HIL check (HIL_APPROVED=1 HIL_TEST=<name>)"

bootstrap:
	@command -v "$(UV)" >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/"; exit 2; }
	$(UV) sync --locked

check:
	@command -v "$(UV)" >/dev/null || { echo "uv is required; run 'make bootstrap' after installing it."; exit 2; }
	@test -x "$(PYTHON)" || { echo "$(PYTHON) is missing; run 'make bootstrap'."; exit 2; }
	$(UV) lock --check
	$(PYTHON) -m compileall -q src
	$(PYTHON) tools/validate_repository.py

test:
	@test -x "$(PYTHON)" || { echo "$(PYTHON) is missing; run 'make bootstrap'."; exit 2; }
	@$(PYTHON) -c 'import pytest' 2>/dev/null || { echo "pytest is not declared in the current project. Add the planned development dependency before treating unit tests as a passing gate."; exit 2; }
	PYTHONPATH=src $(PYTHON) -m pytest -q src/tests/unit

image:
	@command -v docker >/dev/null || { echo "docker with buildx/ARM64 support is required."; exit 2; }
	docker build --platform linux/arm64 --tag "$(IMAGE_TAG)" .

hil-list:
	@echo "Available HIL_TEST values:"
	@echo "  bluetooth  bme  led  lid  load-cell  mlx  realsense  sound  wifi"
	@echo "These scripts require explicit user approval, matching Raspberry Pi hardware, and usually run until interrupted."

hil:
	@test "$${HIL_APPROVED:-0}" = "1" || { echo "Set HIL_APPROVED=1 only after explicit user approval and hardware confirmation."; exit 2; }
	@case "$(HIL_TEST)" in \
		bluetooth) script="src/tests/bluetoothTest.py" ;; \
		bme) script="src/tests/bmeTest.py" ;; \
		led) script="src/tests/ledTest.py" ;; \
		lid) script="src/tests/lidSwitchTest.py" ;; \
		load-cell) script="src/tests/nauTest.py" ;; \
		mlx) script="src/tests/mlxTest.py" ;; \
		realsense) script="src/tests/realsenseTest.py" ;; \
		sound) script="src/tests/soundTest.py" ;; \
		wifi) script="src/tests/wifiTest.py" ;; \
		*) echo "Unknown or missing HIL_TEST='$(HIL_TEST)'. Run 'make hil-list'."; exit 2 ;; \
	esac; \
	PYTHONPATH=src "$(PYTHON)" "$$script"

