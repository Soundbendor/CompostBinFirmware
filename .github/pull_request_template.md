## Summary

<!-- Describe the behavior and why this change is needed. -->

## Boundaries affected

- [ ] Runtime orchestration or process lifecycle
- [ ] Sensor or Raspberry Pi hardware
- [ ] Scan/API contract
- [ ] Bluetooth contract
- [ ] Persistent files, calibration, or offline queue
- [ ] Container, native dependency, or ARM64 build
- [ ] Image publication, Balena, or fleet behavior
- [ ] Third-party, generated, or model artifacts
- [ ] Documentation/workflow only

External producers/consumers and deployed-version compatibility:

<!-- Name the server, mobile app, fleet, or other consumer, or write "None". -->

## Verification

- [ ] `make check`
- [ ] `make test`
- [ ] Relevant focused tests
- [ ] ARM64 image build, when applicable
- [ ] Explicitly approved hardware validation, when applicable

Commands and results:

```text
Paste concise results here. Do not include credentials, device identifiers, Wi-Fi details, or captured user data.
```

Skipped checks and reason:

<!-- Hardware, credentials, network access, and unavailable ARM64 builders must be stated. -->

## Persistence, rollout, and rollback

Persistent-data/schema impact:

<!-- Include migration/recovery behavior or write "None". -->

Rollout order and compatibility window:

<!-- Required for a shared protocol or deployment change; otherwise write "None". -->

Rollback behavior:

<!-- State what is restored and whether new data remains readable. -->

## Safety checklist

- [ ] Fixtures and logs are synthetic/redacted.
- [ ] No secrets or production data were added.
- [ ] The change preserves queued media until server acknowledgement, or documents an approved migration.
- [ ] Documentation and fixtures match any changed contract.
- [ ] Unrelated user and vendor/generated changes were preserved.

