# 0002 — Publish BME688 calibration state as a balena device tag

- Status: accepted
- Date: 2026-10-03

## Context and constraints

Bin calibration status is only observable in three ways today: the `BME688.CALIBRATE` event and its log line, the `calibrated` flag inside the shared sensor dictionary, and the presence of `/firmware/data/bme688_state.txt`. None of them survives outside the container, so a fleet dashboard or an automated check cannot tell a device that never had a valid calibration curve from one that is mid burn-in.

The fleet already runs on openBalena, which exposes device tags through the balena API. Reaching that API needs three service environment variables and the `io.balena.features.balena-api` label, and it needs an SDK dependency in the image.

Constraints that shaped the decision:

- Sensor initialization, measurement, and calibration must not block on or fail because of reporting.
- The shared sensor dictionary is serialized into every scan payload, so it cannot carry reporting state.
- The BSEC extension returns integer status codes that the current driver discards, so a rejected calibration curve is currently indistinguishable from an accepted one.
- Calibration writes go to the persistent volume, so a partial write is visible on the next boot.
- Workstation tests must not import the SDK or the native BSEC extension, and must not contact a live API.

## Decision

The BME688 driver publishes a single device tag, `BME688_CALIBRATED_STATE`, through a small reporter that owns one worker thread.

| Condition | Tag value |
| --- | --- |
| Sensor initialization fails | `UNHEALTHY` |
| Sensor initializes without a valid saved calibration | `UNHEALTHY` |
| Calibration is actively running | `CALIBRATING` |
| Saved calibration loads and initialization completes | `CALIBRATED` |
| Calibration completes and its state is saved | `CALIBRATED` |
| Calibration fails or is stopped | `CALIBRATED` when a valid prior calibration remains, otherwise `UNHEALTHY` |

`src/drivers/BalenaTagReporter.py` owns the SDK client and the worker thread. It is constructed inside the BME688 process during `initialize()`, never in the driver constructor, because it holds a thread and a network client. The driver only calls `set_state()`, which never contacts openBalena.

The reporter keeps one desired value, drops acknowledged duplicates, and republishes on every process start so a tag that drifted while the device was offline converges. Newer values replace older pending ones, and a response to an in-flight request never discards a newer update. Failures retry after five seconds, doubling to five minutes, with logs throttled to one line per minute that record only the exception type. Missing configuration disables reporting with a single warning; it never raises into the driver.

`src/drivers/sensors/BME688.py` now checks the native return codes from `set_bsec_state()` and `set_sample_rate()`, and validates a saved curve for integer byte values and for the 238-byte length of the `bsec_IAQ_Sel` blob the vendored ARM64 build uses. A rejected curve is preserved on disk for diagnosis. Completed calibrations are written to a temporary file and moved into place atomically, keeping the previous valid curve if the write fails. Calibration cannot start after a failed initialization, duplicate start requests are ignored while a worker is alive, cancellation is effective while the worker waits for sensor data, and an exiting worker cannot overwrite a newer run's state.

The existing trigger and completion rule are unchanged: `MainController` still requests calibration when the driver reports no valid curve, and a run still completes only after at least 24 hours and IAQ accuracy 3.

## Consequences

- Dashboards and fleet queries can read one tag per device instead of inferring health from logs.
- The tag is the latest reported state, not an event history and not a heartbeat. A device with no configuration, a failing API, or a stopped application leaves whatever value was last written in place.
- Pending reports live in memory only. After a restart the state is derived again from initialization and the saved curve.
- Calibration-file writes became atomic. There is no format migration, and existing files remain readable.
- The balena SDK declares a `timeout` setting in milliseconds but 17.3.0 does not apply it to its HTTP layer. The configured five-second value is therefore advisory; what actually bounds reporting work is the single worker thread and the retry cap.
- Fleet, app, and firmware versions still do not deploy atomically. Deploy the image and the `io.balena.features.balena-api` label together.

## Rejected alternatives

- *Publish from the main process.* MainController owns scan coordination and the Wi-Fi manager; adding an SDK client there would put fleet reporting on the critical path of every scan.
- *Put the tag in the shared sensor dictionary.* It would change the scan payload contract for every upload and every server consumer to carry a field no consumer reads.
- *Write the tag directly from the calibration thread.* That couples a 24-hour background run to the network and lets a slow API stall sensor polling.
- *Poll the API for state instead of publishing.* Polling needs the same credentials and label, costs a request per interval per device, and still cannot distinguish mid-run from complete.
- *Queue pending states on the persistent volume.* Reporting is a best-effort hint that initialization can always recompute, so durable queueing adds recovery code and data migration for no additional information.

## Compatibility, rollout, and rollback

This adds one device-metadata contract. Bluetooth UUIDs, characteristic payloads, scan field names, multipart layout, filename conventions, queued media, and calibration timing are unchanged.

Before deployment, verify the pinned SDK against the installed openBalena API version and validate on one authorized device. Deploy the updated image and the service label together.

Rollback restores the previous image and manifest. Calibration files stay readable across the change. The last reported tag remains in openBalena until it is explicitly updated or removed, so treat any tag on a rolled-back device as stale.
