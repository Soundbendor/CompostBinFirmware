# Firmware Architecture

## Purpose and runtime

The firmware runs on Raspberry Pi 5 devices inside a privileged ARM64 Balena container. It collects sensor and media data when the lid closes, provides Bluetooth-based setup and local feedback, retains uploads while offline, and sends multipart scans to the Smart Compost Bin server.

The current application is Python 3.14 managed by `uv`. Native components include Intel RealSense, Bosch BSEC/BME68x, Raspberry Pi GPIO/I2C/SPI libraries, and `whisper.cpp`.

## Current process topology

```text
main.py
└── MainController
    ├── WiFiManager (main process)
    ├── DriverManager
    │   ├── LEDDriver process
    │   ├── NAU7802 process
    │   ├── BME688 process
    │   ├── MLX90640 process ──pipe──┐
    │   ├── Realsense process ──pipe┤
    │   ├── SoundController process ─┤
    │   ├── AsyncPublisher process ←─queue
    │   └── BluetoothDriver process
    └── callback loop
```

`DriverManager` wraps each driver in a `multiprocessing.Process`. Sensor values use `multiprocessing.Value`; events use `multiprocessing.Event`; generated filenames return through pipes; complete scan packets enter a queue consumed by `AsyncPublisher`.

The names `ThreadedDriver` and `proccessList` are historical: these workers are processes, not threads.

## Responsibilities

| Component | Current responsibility |
| --- | --- |
| `src/main.py` | Changes to the source directory, starts the controller, and polls callbacks. |
| `MainController` | Creates drivers, performs startup/tare behavior, coordinates a scan, calculates weight delta, and queues the payload. |
| `DriverManager` | Creates shared data/events, starts workers, exposes events, and serializes the nested state into JSON-compatible values. |
| Sensor drivers | Initialize hardware, update shared values, react to capture/control events, and write media under the persistent data directory. |
| `AsyncPublisher` | Transcribes user-triggered audio, caches pending packets in `cachedData.dat`, uploads scans, and deletes acknowledged media. |
| `WiFiManager` and `BluetoothDriver` | Call NetworkManager commands, advertise GATT services, accept setup values, and report connection state. |
| `RequestHandler` | Builds the server URL, reads API credentials, creates the multipart request, and sends heartbeat/upload requests. |
| `BalenaTagReporter` | Publishes the latest device tag value from a worker thread, retries failures with capped backoff, and never blocks the caller. |

## Scan flow

1. A lid-close event reaches the controller.
2. Audio recording and the two camera capture events start.
3. The controller waits for all capture events to clear and receives three filename dictionaries through pipes.
4. After load-cell debounce, the controller snapshots the shared data and queues a packet with a generated UUID.
5. `AsyncPublisher` writes the packet into `../data/cachedData.dat`, transcribes audio when appropriate, and sends the multipart request.
6. On the API's success response, media and the cached entry are removed. Failed packets return to the in-memory queue.

The exact external contract is documented in [the scan upload protocol](protocols/scan-upload.md).

## BME688 calibration tag

The BME688 process publishes one openBalena device tag, `BME688_CALIBRATED_STATE`, with the values `UNHEALTHY`, `CALIBRATING`, and `CALIBRATED`. The value is the latest reported state, not an event history and not a heartbeat.

| Condition | Tag value |
| --- | --- |
| Sensor initialization fails | `UNHEALTHY` |
| Sensor initializes without a valid saved calibration | `UNHEALTHY` |
| Calibration is actively running | `CALIBRATING` |
| Saved calibration loads and initialization completes | `CALIBRATED` |
| Calibration completes and its state is saved | `CALIBRATED` |
| Calibration fails or is stopped | `CALIBRATED` when a valid prior calibration remains, otherwise `UNHEALTHY` |

Reporting runs on its own worker thread inside `BalenaTagReporter`, is created during BME688 `initialize()` rather than in the driver constructor, and never blocks measurement or calibration. Temporary measurement errors and openBalena connection failures leave the tag unchanged. Reporting is disabled with a single warning when configuration is missing. See [ADR 0002](adr/0002-bme688-calibration-device-tag.md).

`MainController` still requests calibration when the driver reports no valid curve, and a run still completes only after at least 24 hours and IAQ accuracy 3.

## Runtime files and configuration

- `/firmware/src` is the container working directory.
- `/firmware/data` is the Balena persistent volume; source-relative code refers to it as `../data`.
- `FASTAPI_KEY`, `ENDPOINT`, and `PORT` configure API access.
- `BALENA_API_URL`, `BALENA_API_KEY`, and `BALENA_DEVICE_UUID` configure calibration tag reporting. All three must be present; otherwise reporting is disabled with one warning. `BALENA_API_KEY` is a secret and must be injected from the fleet, never committed. `BALENA_API_URL` accepts either a full API address or a bare host.
- `CalibrationDetails.json` supplies the NAU7802 calibration factor.
- `/firmware/data/bme688_state.txt` stores BME688/BSEC calibration state. Completed calibrations are written to a temporary file in the same directory and moved into place atomically, so a failed write leaves the previous valid curve readable.
- `/firmware/data/config.json` stores the muted preference.
- `/firmware/data/cachedData.dat` stores the current offline queue.

Bluetooth writes API values to its own process environment. The persistence and propagation of those values to the publisher are not established by the current architecture.

## Packaging and deployment

- `pyproject.toml` and `uv.lock` define the Python environment used by the current Docker build.
- The Dockerfile separately builds the vendored BME68x package and `whisper.cpp`, downloads a speech model, and copies native RealSense artifacts with the application source.
- `.github/workflows/docker-image.yml` cross-builds `linux/arm64` and publishes a Docker image.
- `deploy/docker-compose.yml` runs that image with host networking, DBus, the `balena-api` feature label, persistent storage, device mappings, and privileged access.
- `deploy/balena.yml` contains separate application metadata.

See [the deployment runbook](runbooks/deployment.md) before touching images or the fleet.

## Test boundaries

Files under `src/tests/unit/` are intended to be workstation tests with fake dependencies. The other Python files under `src/tests/` are manual device scripts and may access hardware, NetworkManager, Bluetooth, audio, or a configured API.

The current unit tests use pytest-style functions, and pytest is declared as a development dependency. `make test` runs them with `src` on `PYTHONPATH`.

`src/tests/unit/sensors/bme688_test.py` and `src/tests/unit/drivers/balena_tag_reporter_test.py` replace the native BSEC extension and the balena SDK with recording doubles, so no workstation test imports hardware or contacts a live API.

## Third-party and generated content

The following paths are not first-party firmware architecture:

- `BSEC/`
- `bme68x-python-library-bsec2.6.1.0/`
- `whisper.cpp/`
- `dependencies/`
- committed `.so`, `.a`, `.bin`, and build artifacts

They are excluded from routine `rg` searches by `.rgignore`. Search them with `rg --no-ignore` only when a task explicitly concerns their provenance, build, licensing, or integration.

## Known behavior/documentation mismatch

The module description says scans also run every two hours, and `TimeHelper` contains interval logic, but the current `main.py` loop only dispatches callbacks. Treat periodic capture as an unresolved product requirement rather than current behavior.

