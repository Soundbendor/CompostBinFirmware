---
name: openbalena-local-dev
description: Set up balenaOS devices managed by openBalena for local development with Livepush, inspect local device logs and state, and diagnose deployment or application failures. Use for local device work, not fleet-wide production deployment.
---

# openBalena local development

Use one verified development device. Resolve its UUID, LAN address, service name, and source directory from the current session. Never reuse an address or container ID from an earlier session without checking it. Below, `DEVICE_ADDR`, `DEVICE_UUID`, `SERVICE`, and `SOURCE_DIR` are shell variables populated with those verified values.

## Set up

1. Inspect repository instructions, Git status, Dockerfiles, Compose files, and installed `balena --version` / command help. Keep existing production manifests and unrelated edits intact. Keep the CLI connected to the intended openBalena server.
2. Confirm balenaOS development mode is enabled. This exposes debugging access, including the Engine API on port 2375 and SSH on port 22222; use a trusted LAN. Development mode and Supervisor Local Mode are separate settings. Entering Local Mode interrupts the device's fleet application.
3. For an authorized local-development session:

   ```bash
   balena device local-mode "$DEVICE_UUID" --enable
   balena device local-mode "$DEVICE_UUID" --status
   ```

4. Use a development Compose file at the source root, with `build.context: .` and `build.dockerfile: Dockerfile.dev`. An `image:`-only service does not incorporate source edits. Preserve required device mappings, privileges, networking, D-Bus labels, and data volumes.
5. For heavy dependencies, derive `Dockerfile.dev` from a compatible, preferably digest-pinned ARM image and copy only application source/assets over it. Remove obsolete inherited application files before copying; retain installed dependencies and models. Check builder compatibility before reusing BuildKit-specific instructions.
6. Inspect `.dockerignore`: exclude workstation `.venv` as well as `venv`, caches, and unnecessary artifacts. Balena does not use `.gitignore` to filter its build context. A pause after “Starting build on device” can be source packaging/upload; measure context size before blaming the Pi.
7. Put non-secret runtime settings in development Compose. Supply secrets without displaying their values or committing them. Fleet application environment variables do not automatically carry into Local Mode. Keep machine-specific Compose files out of Git when local-only configuration is requested.

   ```bash
   balena push "$DEVICE_ADDR" --source "$SOURCE_DIR"
   ```

   Supply required `--env "NAME=$VALUE"` arguments from privately populated shell variables. Target a LAN address or `.local` hostname. Leave the session open for Livepush; avoid `--nocache` and `--nolive` during iteration. The first base-image pull can be slow. Dependency changes still require a suitable base rebuild.

## Inspect before changing state

```bash
balena device logs "$DEVICE_ADDR" --service "$SERVICE"
balena device logs "$DEVICE_ADDR" --system
balena device ssh "$DEVICE_ADDR"
```

On the host, use `balena-engine ps -a`, bounded `balena-engine logs --tail 100 <container-id>`, and selected `inspect --format` fields. Check status, exit code, `OOMKilled`, restart count, timestamps, and mounts. Exit 137 alone does not prove OOM. Service log filtering removes Supervisor chatter, not native-library output from the same container.

For direct read-only HTTP diagnostics, use short curl connection/overall timeouts:

- Engine: `http://$DEVICE_ADDR:2375/_ping` and `/containers/json?all=true`.
- Supervisor: `http://$DEVICE_ADDR:48484/ping`, `/v2/state/status`, and `/v2/local/target-state`.

Read installed CLI source or current documentation when response shapes differ. Target state may be nested under `state`. Engine log responses may use Docker stream framing. Never dump full inspect/target-state payloads: filter before returning tool output. Show only needed non-secret settings and secret-presence booleans. Scrub credentials from logs; avoid debug output that prints target environments.

Compare intended Supervisor settings with the actual container environment. A correct CLI command can coexist with a stale container while the Supervisor is stuck applying an update. Distinguish build, deployment, and Python runtime failures using evidence from each layer.

## Recovery and logging

- Repeated “Starting service” messages do not prove a Python crash. Check Supervisor errors. An HTTP 409 name conflict can come from a stopped container still reserving the name.
- If recovery is authorized, identify the exact stale application container and verify its mounts. Stop it if running, then remove only that container without volume-removal flags and re-push. Named volumes remain; writable-layer files do not. Reinspect after one recovery attempt; stop and investigate if the conflict returns. Do not prune containers/images/volumes or toggle Local Mode as a blanket fix.
- Route Python logging to stdout/stderr and enable unbuffered output. Configure logging at the application entry point and inside actual multiprocessing workers, especially with `spawn` or `forkserver`. `basicConfig(force=True)` can replace earlier handlers; avoid resetting the caller's handlers during in-process tests. Include process identity and support a runtime log level. Native C output bypasses Python logging levels.
- Treat requests to inspect as read-only. Apply existing authorization to recovery actions; when interruption or data loss is outside that scope, describe the exact proposed action and obtain approval. Never print or request a real API key in chat.
- `Ctrl+C` ends Livepush but leaves services running. Disabling Local Mode resumes the assigned fleet release and deletes local-mode containers and volumes. Export needed test data first.

Report observed state, changes made, validation, and unresolved causes separately. Do not claim a fix reached the Pi until its running state and logs confirm it.

## References

- [openBalena setup](https://open-balena-docs.balena.io/getting-started/)
- [Local Mode, Livepush, and data lifecycle](https://docs.balena.io/learn/develop/local-mode)
- [balenaOS development mode](https://docs.balena.io/reference/os/overview)
