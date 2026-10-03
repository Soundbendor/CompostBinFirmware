# Deployment Runbook

This runbook documents the checked-in delivery path. It does not authorize publishing an image or changing the fleet.

## Current path

1. `.github/workflows/docker-image.yml` runs on pushes to `main` and `env_modernization`.
2. GitHub Actions cross-builds the Dockerfile for `linux/arm64`.
3. The workflow publishes `aidanb1409/compostsense_firmware:latest`.
4. `deploy/docker-compose.yml` configures Balena to consume that mutable tag.
5. `deploy/balena.yml` records the application name and an independent version string.

These identifiers are not currently connected into an immutable promotion or rollback record. Treat the running fleet and image registry as external state that must be inspected before a deployment change.

## Read-only preflight

Before proposing a deployment change:

```bash
git status --short
make check
make test
```

Then review together:

- `Dockerfile`
- `pyproject.toml` and `uv.lock`
- `.github/workflows/docker-image.yml`
- `deploy/docker-compose.yml`
- `deploy/balena.yml`

Record the intended Git revision, target fleet/application, current deployed image or digest, required configuration names, persistent-volume expectations, hardware compatibility, and rollback target.

## Local-only build

```bash
make IMAGE_TAG=compost-bin-firmware:review image
```

This command does not push. Report when the build is skipped because ARM64 emulation, network access, or native dependencies are unavailable.

## Production boundary

The following require explicit user authorization and a stated rollback path:

- registry login or image push;
- changing or triggering the publishing workflow;
- Balena release creation, promotion, restart, or rollback;
- device environment or secret changes;
- persistent-volume deletion or migration;
- modification of host networking, DBus, device access, or privileges.

After an authorized release, record the deployed digest, affected devices, canary result if used, health/queue status, and the exact rollback release. The current repository does not provide an automated fleet-inspection or rollback command.

