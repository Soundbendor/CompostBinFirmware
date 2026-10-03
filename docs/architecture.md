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

## Scan flow

1. A lid-close event reaches the controller.
2. Audio recording and the two camera capture events start.
3. The controller waits for all capture events to clear and receives three filename dictionaries through pipes.
4. After load-cell debounce, the controller snapshots the shared data and queues a packet with a generated UUID.
5. `AsyncPublisher` writes the packet into `../data/cachedData.dat`, transcribes audio when appropriate, and sends the multipart request.
6. On the API's success response, media and the cached entry are removed. Failed packets return to the in-memory queue.

The exact external contract is documented in [the scan upload protocol](protocols/scan-upload.md).

## Runtime files and configuration

- `/firmware/src` is the container working directory.
- `/firmware/data` is the Balena persistent volume; source-relative code refers to it as `../data`.
- `FASTAPI_KEY`, `ENDPOINT`, and `PORT` configure API access.
- `CalibrationDetails.json` supplies the NAU7802 calibration factor.
- `/firmware/data/bme688_state.txt` stores BME688/BSEC calibration state.
- `/firmware/data/config.json` stores the muted preference.
- `/firmware/data/cachedData.dat` stores the current offline queue.

Bluetooth writes API values to its own process environment. The persistence and propagation of those values to the publisher are not established by the current architecture.

## Packaging and deployment

- `pyproject.toml` and `uv.lock` define the Python environment used by the current Docker build.
- The Dockerfile separately builds the vendored BME68x package and `whisper.cpp`, downloads a speech model, and copies native RealSense artifacts with the application source.
- `.github/workflows/docker-image.yml` cross-builds `linux/arm64` and publishes a Docker image.
- `deploy/docker-compose.yml` runs that image with host networking, DBus, persistent storage, device mappings, and privileged access.
- `deploy/balena.yml` contains separate application metadata.

See [the deployment runbook](runbooks/deployment.md) before touching images or the fleet.

## Test boundaries

Files under `src/tests/unit/` are intended to be workstation tests with fake dependencies. The other Python files under `src/tests/` are manual device scripts and may access hardware, NetworkManager, Bluetooth, audio, or a configured API.

The current unit tests use pytest-style functions, but pytest is not declared in project dependencies. This is a known baseline limitation exposed by `make test`; it should not be hidden by using a test command that collects zero tests.

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

