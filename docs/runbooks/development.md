# Development Runbook

## Prerequisites

- Linux workstation or Raspberry Pi
- Python version from `.python-version`
- `uv`
- GNU Make
- Docker with ARM64/buildx support only when building the image

Hardware is not required for repository checks. Never connect workstation tests to a live production API.

## Bootstrap and inspect

```bash
git status --short
make bootstrap
make check
```

`make bootstrap` synchronizes `uv.lock`. It installs both the runtime environment and the `dev` dependency group, which declares pytest, so `make test` runs the suite once the environment is synchronized. If `make test` stops with its pytest dependency message, the environment is out of date; run `make bootstrap` rather than installing untracked tools or reporting zero collected tests as success.

Use `make help` as the task index. Override `PYTHON` only when intentionally using an equivalent synchronized environment:

```bash
make PYTHON=/absolute/path/to/python check
```

## Workstation verification

`make check` performs only deterministic, non-hardware checks:

- `uv.lock` consistency;
- Python byte-compilation;
- syntax validation for first-party shell scripts;
- required workflow/documentation file checks;
- JSON parsing and contract-field checks for sanitized fixtures.

`make test` is the sole test entry point. It runs the pytest suite under `src/tests/unit` with `src` on `PYTHONPATH`.

`src/tests/unit/sensors/bme688_test.py` and `src/tests/unit/drivers/balena_tag_reporter_test.py` stub the vendored BSEC extension and the balena SDK with recording doubles. They must stay offline: never point a workstation test at a live API, and never add a real API key to a test.

## Search boundaries

Routine `rg` searches exclude native artifacts and the BSEC/BME68x/Whisper vendor trees through `.rgignore`. For a deliberately scoped dependency task, use a path or `--no-ignore`, for example:

```bash
rg --no-ignore 'specific symbol' whisper.cpp
```

Do not mix incidental vendor formatting or generated output into application changes.

## Local image build

```bash
make image
```

Override the local-only tag with `IMAGE_TAG=name:tag`. The target does not log in or push. Building may require network downloads and ARM64 emulation; obtain approval before network access when the execution environment requires it.

## Refresh the local development base image

For an authorized push to a verified local-mode device, set `DEVICE_ADDR` to its LAN address or `.local` hostname and `SOURCE_DIR` to the firmware source root, then run:

```bash
balena push "$DEVICE_ADDR" --source "$SOURCE_DIR" --pull
```

Keep any required `--env` and `--registry-secrets` arguments, supplying credentials privately. This command builds and deploys the development service; it is not a read-only freshness check. Follow the [openBalena local development skill](../../.agents/skills/openbalena-local-dev/SKILL.md) for device setup and inspection.

For local pushes, [`--pull`](https://docs.balena.io/reference/balena-cli/latest/#push) asks the device's build engine to pull the base image from the registry even when it is cached locally. The engine resolves the tag and reuses existing layers. Keep build caching and Livepush enabled; do not add `--nocache` or `--nolive` for this refresh. Base-image selection happens before Dockerfile instructions execute, so neither Dockerfile needs a refresh instruction.

Freshness is established at push time. Livepush does not continuously watch the registry; start another push with `--pull` to refresh again. A digest-pinned `FIRMWARE_BASE` still selects that exact image. A successful refresh does not prove compatibility with the current source: the registry's `latest` must already contain the required dependencies and transcription model. This workflow adds no compatibility guard or automatic repair.

`Dockerfile.dev` inherits its Python environment from `FIRMWARE_BASE` and never runs `uv sync`, so a new runtime dependency is only present on the device after the base image that carries it is published and selected. Dependency changes therefore require a base-image rebuild before a local push can import them.

During an authorized device validation:

- Record the selected base image's ID and repository digest before and after the push, retaining the previous digest for rollback.
- Confirm a stale tag updates, an unchanged tag reuses existing layers, and the resulting development image derives from the refreshed base.
- Check pull errors when the registry is unavailable; report freshness as unverified if the pull fails.
- Preserve the existing data volume. If rollback is needed, select the recorded previous base digest and rebuild/redeploy through the authorized local workflow; do not disable Local Mode or prune volumes.

## Fixtures

Contract fixtures live in `src/tests/fixtures/`. They must:

- be synthetic and contain no captured production data;
- use `example.invalid` for hostnames;
- use identifiers beginning with `fixture-` where practical;
- preserve exact field names and types from the documented contract;
- be updated alongside both documentation and tests when a contract changes.

## Handoff

Before handing work back:

1. Run the narrowest affected checks, then `make check` and `make test` when available.
2. Review `git diff --check` and `git status --short`.
3. Report failures and skipped checks accurately.
4. Name any affected external consumer, persistent file, hardware device, image, or fleet behavior.
5. State rollout and rollback considerations for shared contracts or persisted data.
