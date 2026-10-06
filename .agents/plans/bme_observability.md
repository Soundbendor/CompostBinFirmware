# Publish BME688 calibration status through balena-sdk

## Summary

Add the device tag `BME688_CALIBRATED_STATE`, updated automatically from the BME688 driver through `balena-sdk`. Reporting runs independently of sensor operations and retries failed requests without blocking initialization, measurements, or calibration.

The tag represents the latest reported state, not an event history or a device heartbeat.

## State behavior

| Condition | Tag value |
|---|---|
| Sensor initialization fails | `UNHEALTHY` |
| Sensor initializes without valid saved calibration | `UNHEALTHY` |
| Calibration is actively running | `CALIBRATING` |
| Saved calibration loads successfully and initialization completes | `CALIBRATED` |
| Calibration completes successfully and its state is saved | `CALIBRATED` |
| Calibration fails or stops | `CALIBRATED` if a valid prior calibration remains; otherwise `UNHEALTHY` |

Preserve the existing automatic calibration trigger and completion requirement: at least 24 hours elapsed and IAQ accuracy of 3. Temporary measurement errors and openBalena connection failures do not change the calibration tag.

## Implementation

### Sensor lifecycle

- Integrate state transitions into `src/drivers/sensors/BME688.py`, keeping tag state outside the shared sensor-data dictionary so scan payloads remain unchanged.
- Check native return codes for calibration restoration and sample-rate configuration. Only report successful initialization after those operations succeed.
- Validate saved state before passing it to the native extension, including integer byte values and the active vendored BSEC blob length of 238 bytes. Invalid or rejected state produces `UNHEALTHY`; preserve the file for diagnosis.
- Prevent calibration from starting after failed initialization. Ignore duplicate start requests while a calibration worker remains active.
- Make cancellation effective while waiting for sensor data, and prevent an exiting worker from overwriting a newer run's state.
- Save completed calibration through a temporary file and atomic replacement. Preserve the existing filename and text format, and retain the previous valid file if saving fails.

### SDK reporter

- Add a small reporter in `src/drivers/BalenaTagReporter.py` with a nonblocking `set_state()` interface and shutdown handling.
- Create its worker thread and SDK instance inside the BME688 child process during initialization, not in the driver constructor.
- Configure the SDK from `BALENA_API_URL`, authenticate with `BALENA_API_KEY`, and target `BALENA_DEVICE_UUID`. Keep SDK settings in memory with `data_directory=False`; retain TLS verification.
- Use one worker to serialize calls to `models.device.tags.set()`. Keep only the latest desired state, suppress successfully acknowledged duplicates, and publish again on every process startup.
- Set a five-second SDK request timeout. Retry failures after 5 seconds, doubling to a five-minute maximum. New state replaces pending older state; an older in-flight response must not discard a newer update.
- Missing configuration disables reporting with one warning. SDK failures remain isolated from sensor initialization and calibration, with throttled logs that exclude credentials and raw request details.
- Keep pending reports in memory. After restart, derive the current state again from initialization and saved calibration.

### Packaging and documentation

- Add and lock `balena-sdk==17.3.0` as a runtime dependency and pytest as a development dependency. Constrain Python to `>=3.14,<4` to match the SDK's supported range.
- Add `io.balena.features.balena-api: '1'` to the existing service labels in `deploy/docker-compose.yml`.
- Document the tag contract, credential injection, offline behavior, and the requirement that the development base image contain the new SDK dependency.
- Update the architecture/runbook documentation and record the reporting design in an ADR. Preserve the ignored local Compose configuration.

## Verification

Use mocked SDK/native libraries, synthetic calibration fixtures, temporary directories, and controllable clocks.

Cover:

- Initialization exceptions, rejected calibration state, and sample-rate failures.
- Startup with valid, absent, malformed, and incorrectly sized calibration files.
- Calibration start, successful completion, cancellation, exceptions, and save failures.
- Recovery to prior valid calibration, duplicate starts, and cancellation while no readings arrive.
- SDK authentication/configuration, exact tag name and values, missing credentials, retry backoff, duplicate suppression, and state changes during an in-flight request.
- Continued sensor operation during reporting failures and preservation of the old calibration file after unsuccessful writes.

Run `make check`, `make test`, and `git diff --check`. The current `make test` baseline fails because pytest is undeclared; the planned development dependency resolves that prerequisite. Report any unrelated failures separately.

Build the ARM64 image locally with `make image` and verify SDK import without contacting openBalena. Live API and hardware validation require separate authorization.

## Rollout and rollback

The change adds one device-metadata contract and changes calibration-file writes to atomic replacement without a format migration. Bluetooth, scan uploads, queued media, and calibration timing remain unchanged.

Before deployment, verify SDK compatibility with the installed openBalena API and validate on one authorized device. Deploy the updated image and service label together.

Rollback restores the previous image and manifest; calibration files remain readable. The last reported tag remains in openBalena until explicitly updated or removed, so rollback documentation must identify it as stale.
