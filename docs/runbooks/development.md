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

`make bootstrap` synchronizes `uv.lock`; it does not install an undeclared test framework. The current project therefore expects `make test` to stop with a clear pytest dependency message. This is a known baseline condition, not permission to install untracked tools or report zero collected tests as success.

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

`make test` is the sole test entry point. Once the development test dependencies are declared, it runs the pytest suite under `src/tests/unit` with `src` on `PYTHONPATH`.

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

