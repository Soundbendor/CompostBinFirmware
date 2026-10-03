# Bluetooth Protocol

This document records the GATT surface implemented by `src/drivers/NetworkDriver.py`. UUID strings and JSON shapes are shared with the mobile application and must not change in isolation.

## Advertisement

- Device alias: `Binsight Compost Bin`
- Advertised services: Wi-Fi setup service and API setup service
- Agent type: BlueZ `NoIoAgent`

## Wi-Fi setup service

Service UUID: `31415924535897932384626433832790`

| Characteristic UUID | Flags | Current behavior |
| --- | --- | --- |
| `31415924535897932384626433832791` | read | Returns connection status JSON. |
| `31415924535897932384626433832792` | read/write/write-without-response | Accepts `ssid` and `password`; reads the last connection result. |
| `31415924535897932384626433832793` | read/notify | Returns the last Wi-Fi scan as an SSID-keyed JSON object. |
| `31415924535897932384626433832794` | write/write-without-response | Accepts an `ssid` to delete a NetworkManager connection. |

Sanitized request and response examples live under `src/tests/fixtures/bluetooth/`.

## API setup service

Service UUID: `ABC0`

| Characteristic UUID | Flags | Current behavior |
| --- | --- | --- |
| `ABC1` | read/write/write-without-response | Accepts `apiKey`, `endpoint`, and `port`; a read returns whether the secure heartbeat succeeds. |
| `ABC2` | read | Returns `apiKey` and Raspberry Pi `deviceID`. |

The setter updates environment variables only within the Bluetooth worker and refreshes that service's `RequestHandler`. The current implementation does not establish durable credential storage or propagation to the publisher process.

## Debug service

Service UUID: `BEEF`

| Characteristic UUID | Flags | Current behavior |
| --- | --- | --- |
| `BEF0` | read/write/write-without-response | Reads or changes muted state. |
| `BEF1` | write/write-without-response | A `True` string requests deletion of regular files under `../data`. |

Treat API-key retrieval and cache deletion as sensitive behavior. Documenting them here does not authorize calling them or expanding them.

## Payload conventions

- Values are UTF-8.
- Structured values are JSON unless the table explicitly describes a plain string.
- Fixture credentials use reserved example domains and clearly synthetic values.
- Do not log Wi-Fi passwords, API keys, full provisioning payloads, or unredacted device identifiers.

## Compatibility procedure

Bluetooth changes require review of the mobile setup implementation and deployed firmware compatibility. Prefer a new service/characteristic version for incompatible behavior, deploy readers before writers, and keep a documented retirement window for the previous version.
