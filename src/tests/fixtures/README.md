# Contract Fixtures

These files are synthetic examples of cross-component wire formats. They support documentation, review, and future contract tests without requiring hardware or a live service.

- `contracts/scan_payload.json` mirrors the JSON string sent in multipart form field `data`.
- `bluetooth/` contains representative GATT request and response JSON.

Rules:

- Never replace these examples with captured device, household, Wi-Fi, log, image, audio, or API data.
- Use `example.invalid` for endpoints and `fixture-` identifiers/credentials.
- Preserve exact field names and JSON types.
- Update the relevant protocol document and tests in the same change.
- Run `make check` to validate structure and required fields.

