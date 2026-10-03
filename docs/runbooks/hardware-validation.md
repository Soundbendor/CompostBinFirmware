# Hardware Validation Runbook

The scripts under `src/tests/` are interactive component checks, not an automated unit suite. Several loop until interrupted and may operate GPIO, LEDs, audio, cameras, Bluetooth, Wi-Fi, or load-cell hardware.

## Safety gate

Run a hardware check only when all of the following are true:

- the user explicitly approved the specific check;
- the target is a Raspberry Pi 5 with the expected component connected;
- no production capture or upload process is using that component;
- the operator understands whether the script loops, records media, changes connectivity, or requires physical interaction;
- generated media and logs will remain in an approved local data directory.

Setting `HIL_APPROVED=1` records operator intent for the Make target but does not replace user authorization.

## Inventory

```bash
make hil-list
```

The guarded component names map to existing scripts:

| `HIL_TEST` | Component | Interaction |
| --- | --- | --- |
| `bluetooth` | BlueZ/DBus service | Advertises a Bluetooth service; may require a phone. |
| `bme` | BME688/BSEC | Reads I2C sensor data and may run continuously. |
| `led` | NeoPixel SPI strip | Changes visible LED output and runs continuously. |
| `lid` | Hall-effect GPIO | Waits for physical lid transitions. |
| `load-cell` | NAU7802 | Reads scale values and may require physical weights. |
| `mlx` | MLX90640 | Captures thermal data and writes media. |
| `realsense` | Intel RealSense | Captures color/depth/topology files. |
| `sound` | Microphone and speaker | Plays prompts and records audio. |
| `wifi` | NetworkManager | Scans local wireless networks. |

Calibration, forced LED, and live request scripts are intentionally not exposed through `make hil`; run them only under a separately reviewed procedure.

## Execute one check

```bash
HIL_APPROVED=1 HIL_TEST=lid make hil
```

Use `Ctrl-C` to stop scripts that loop. Afterward, verify that no child process still owns the device and that the production service can reacquire it before restarting the service.

## Evidence to record

- Raspberry Pi model and OS/Balena version
- firmware Git revision and image digest, when available
- connected sensor model/revision
- exact Make command
- start/end time and whether interruption was expected
- observed output and generated artifact paths
- cleanup performed
- pass, fail, or inconclusive result with the failure message

Never commit captured household media, Wi-Fi scan results, serial numbers, API responses, or credentials as evidence.

