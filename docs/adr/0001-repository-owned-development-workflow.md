# ADR 0001: Repository-owned development workflow

- Status: Accepted
- Date: 2026-08-16

## Context

Firmware development spans workstation-safe Python, Raspberry Pi hardware, native ARM64 dependencies, cross-repository protocols, and a Balena deployment. Previously, setup and verification commands were distributed across stale README text, shell scripts, source comments, and local knowledge. Unit tests also use a framework that is not declared by the current project, allowing an incorrect `unittest` command to report zero tests without testing behavior.

## Decision

- `AGENTS.md` is the concise operational contract for both people and agents.
- Durable architecture, protocol, and operational details live under `docs/`.
- The root Makefile is the canonical interface for bootstrap, repository checks, unit tests, local image builds, and guarded hardware checks.
- `make test` fails explicitly while the test dependency is undeclared; it must never fall back to a command that collects zero tests.
- Hardware scripts remain manual, require explicit approval, and are exposed one at a time through a guarded target.
- Shared-contract examples are synthetic, version-controlled JSON fixtures.
- Third-party and generated trees are excluded from routine searches but remain available for explicitly scoped work.
- The pull-request template defines the minimum verification and handoff evidence.

## Consequences

Developers and agents have one entry point and a consistent map of repository boundaries. Known quality gaps remain visible rather than being papered over. Documentation and fixtures now require maintenance when contracts change. The Makefile intentionally does not publish images, mutate the fleet, install undeclared development tools, or run hardware automatically.

Dependency cleanup, test repairs, runtime reliability, transport security, and release-promotion changes are separate decisions and are not implemented by this ADR.
