# Smart Compost Bin Firmware Agent Guide

## Scope and source of truth

This repository contains the Raspberry Pi 5 firmware for the Smart Compost Bin. It runs as a privileged ARM64 Balena container and coordinates local sensors, audio, Bluetooth provisioning, persistent retry data, and uploads to the server API.

The running Python code and deployment manifests are authoritative. The README and manual scripts contain legacy Jetson Nano and pre-Balena instructions; do not copy those assumptions into new work.

Before changing anything:

1. Run `git status --short` and preserve unrelated or untracked user work.
2. Read [the architecture map](docs/architecture.md) and the relevant protocol or runbook.
3. State whether the change affects hardware, persistent data, Bluetooth, the server contract, the container, or fleet deployment.
4. Use the narrowest relevant verification command from `make help`.

## Canonical commands

- `make bootstrap` — synchronize the locked runtime environment.
- `make check` — validate the lock, Python syntax, shell syntax, repository metadata, and fixtures.
- `make test` — run workstation unit tests. This currently reports the known missing pytest development dependency instead of silently collecting zero tests.
- `make image` — build a local ARM64 image; it never pushes.
- `make hw-list` — list manual hardware checks.
- `hw_APPROVED=1 hw_TEST=<name> make hw` — run one approved hardware script. User approval and the matching hardware are still required.

Do not run hardware scripts, publish an image, mutate Balena, change production credentials, or call a live API unless the user explicitly authorizes that action.

## Runtime environment variables

- `BME688_DEBUG_MODE` — set to `1` only to reproduce BSEC library diagnostics. 
- `WHISPER_MODEL_PATH` — packaged model snapshot; runtime transcription never downloads.
- `WHISPER_CPU_THREADS` — see the development runbook before changing it.

## Repository boundaries

- `src/main.py` and `src/drivers/MainController.py` own orchestration.
- `src/drivers/` owns process management, networking, Bluetooth, and hardware adapters.
- `src/helpers/__init__.py` owns current HTTP, logging, timing, and calibration helpers.
- `src/tests/unit/` contains workstation tests; other files under `src/tests/` are manual hardware scripts.
- `deploy/`, `Dockerfile`, and `.github/workflows/` jointly define packaging and delivery.
- `media/` contains runtime audio prompts.
- `BSEC/`, `bme68x-python-library-bsec2.6.1.0/`, `whisper.cpp/`, `dependencies/`, and committed native/model artifacts are third-party or generated inputs. Avoid broad edits and searches there unless the task targets that dependency. Use `rg --no-ignore` when an explicit vendor search is required.

## Non-negotiable invariants

- Preserve offline capture data until the server has acknowledged it. Never delete queued media merely because an attempt was made.
- Treat scan field names, multipart layout, filename conventions, Bluetooth UUIDs, and characteristic payloads as cross-repository contracts. Review the server and mobile consumers before making incompatible changes.
- Treat API keys, Wi-Fi credentials, device identifiers, images, audio, annotations, logs, and household behavior as sensitive. Fixtures must be synthetic and clearly marked.
- Hardware and native-library imports must remain mockable for workstation tests. Do not make tests depend on GPIO, I2C, SPI, DBus, RealSense, audio devices, or live services.
- Do not assume firmware, server, app, and fleet versions deploy atomically. Prefer additive changes and staged rollouts for shared contracts.
- Do not infer production authority from a code task. Fleet releases, credential rotation, destructive cache operations, and infrastructure changes require explicit approval and a rollback plan.

## Change and review expectations

- Keep application changes separate from generated or third-party changes.
- Add or update sanitized fixtures and tests for every protocol or persistence change.
- In the handoff, report commands run, failures, skipped hardware checks, affected contracts, persistent-data impact, and rollback behavior.
- Use the pull-request checklist in `.github/pull_request_template.md`, even when no pull request is created, as the definition of a complete change.
- Record durable architectural decisions under `docs/adr/`; keep this file short and operational.

## Task-specific skills

For local openBalena setup, Livepush, or debugging a locally connected
balenaOS device, read
[openbalena-local-dev](.agents/skills/openbalena-local-dev/SKILL.md).
Load it only when relevant; keep detailed procedures in the skill.

## Reference documentation

- [Architecture](docs/architecture.md)
- [Scan upload protocol](docs/protocols/scan-upload.md)
- [Bluetooth protocol](docs/protocols/bluetooth.md)
- [Development runbook](docs/runbooks/development.md)
- [Hardware validation runbook](docs/runbooks/hardware-validation.md)
- [Deployment runbook](docs/runbooks/deployment.md)
- [Architecture decisions](docs/adr/README.md)

