# Scan Upload Protocol

This document records the firmware's current wire format. It is descriptive, not approval to change the server contract.

## Request

- Method and path: `POST /api/scan`
- Authentication header: `token: <device API key>`
- Content type: `multipart/form-data`
- Form field `files`: repeated five times, in the order shown below
- Form field `data`: a JSON document encoded as a string

The five required file kinds are:

1. `colorImage`
2. `depthImage`
3. `heatmapImage`
4. `topologyMap`
5. `voiceRecording`

The JSON object currently contains:

| Field | Type | Source |
| --- | --- | --- |
| `colorImage` | string | Basename of the color image |
| `depthImage` | string | Basename of the colorized depth image |
| `heatmapImage` | string | Basename of the thermal image |
| `topologyMap` | string | Basename of the PLY topology file |
| `voiceRecording` | string | Basename of the WAV recording |
| `total_weight` | number | NAU7802 current weight |
| `weight_delta` | number | Current weight minus the pre-scan baseline |
| `temperature` | number | BME688 temperature in Celsius |
| `pressure` | number | BME688 pressure in kPa |
| `humidity` | number | BME688 relative humidity |
| `iaq` | number | BSEC indoor-air-quality value |
| `co2_eq` | number | BSEC equivalent CO2 value |
| `tvoc` | number | BSEC breath-VOC-equivalent value |
| `transcription` | string | Local speech transcription |
| `userTrigger` | boolean | Whether collection was lid/user triggered |
| `deviceID` | string | Raspberry Pi serial number |
| `commitID` | null/string | Currently always `null` in this branch |

A sanitized representative payload is stored at `src/tests/fixtures/contracts/scan_payload.json`.

## Filenames and time

Media filenames use UTC and generally follow:

```text
<kind>_YYYY-MM-DD--HH-MM-SS.<extension>
```

The filename is currently consumed outside this repository as a timestamp convention. Changes require coordinated server and mobile review.

## Current response handling

The uploader parses the response as JSON and considers it acknowledged when the JSON contains `"status": true`. It then deletes all uploaded local files and removes the cached entry. Other responses are retried after a heartbeat check.

The locally generated queue UUID is not currently included in the HTTP payload, so it does not provide server-side idempotency.

## Compatibility procedure

For any field, filename, file count, authentication, or response change:

1. Identify the firmware producer, server validator/storage, mobile/operations consumers, and persisted database representation.
2. Add a sanitized fixture representing both the old and new shapes.
3. Deploy a tolerant server first.
4. Deploy firmware and other consumers during a defined compatibility window.
5. Remove legacy behavior only after deployed versions have been verified.
6. Document rollback when a new client sends data an old server cannot understand.

Never use production media, identifiers, tokens, or household data as fixtures.

