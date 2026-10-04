# Contributing

This repository targets Raspberry Pi 5 hardware in a privileged ARM64 Balena container. Most development should still be possible on a normal workstation by keeping hardware access behind drivers and using synthetic fixtures.

## Start here

1. Read `AGENTS.md` and `docs/architecture.md`.
2. Run `git status --short` and preserve unrelated work.
3. Run `make bootstrap`, then `make check`.
4. Identify any affected API, Bluetooth, persistence, hardware, container, or fleet boundary before editing.

`make test` is the canonical unit-test command. It currently stops with an actionable message because pytest is not yet declared as a development dependency; do not substitute `unittest discover`, which silently collects none of the pytest-style tests.

## Change shape

- Keep commits focused and separate application changes from vendor/generated updates.
- Add a regression test for bug fixes and sanitized fixtures for protocol changes.
- Avoid live services in automated tests. Use fake hardware and mocked HTTP/DBus boundaries.
- Use additive, backward-compatible changes for deployed protocols. Document producer, consumer, stored representation, rollout order, and rollback.
- Do not include real keys, Wi-Fi details, device data, household images/audio, logs, or captured production payloads.

## Verification

- `make check` validates lock consistency, Python syntax, shell syntax, documentation structure, and JSON fixtures.
- `make test` runs workstation unit tests once the declared development test environment exists.
- `make image` builds locally and never pushes an image.
- `make hil-list` shows manual hardware checks. A HIL script requires both explicit user approval and `HIL_APPROVED=1`; see the hardware runbook first.

Report every command run and every skipped check. Hardware, credentials, network access, or an unavailable ARM64 builder are valid reasons to skip a check, but must be stated.

## Pull requests and handoff

Use `.github/pull_request_template.md` as the completion checklist. The handoff must include:

- user-visible and device-visible behavior;
- affected contracts and persistent state;
- verification evidence and skipped checks;
- deployment order and compatibility window, if applicable;
- rollback behavior;
- whether third-party or generated files changed.

Durable architectural decisions belong in `docs/adr/`. Operational instructions belong in `docs/runbooks/`; protocol wire shapes belong in `docs/protocols/`.
