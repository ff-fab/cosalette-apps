## Epic Adapter Layer Complete: Settings + Error Types + OptolinkPort Protocol

Implemented the three foundational modules for the adapter layer: `Vito2MqttSettings`
(replacing the placeholder config), domain error types with `error_type_map`, and the
`OptolinkPort` PEP 544 Protocol. All 245 tests pass (29 new + 216 existing).

**Files created/changed:**

- packages/src/vito2mqtt/config.py (replaced: `Vito2MqttSettings` extends `cosalette.Settings`)
- packages/src/vito2mqtt/errors.py (new: 5 domain error types + `error_type_map`)
- packages/src/vito2mqtt/ports.py (new: `OptolinkPort` runtime-checkable Protocol)
- packages/tests/unit/test_config.py (new: 7 tests)
- packages/tests/unit/test_errors.py (new: 16 tests)
- packages/tests/unit/test_ports.py (new: 6 tests)
- packages/tests/fixtures/config.py (updated: uses `Vito2MqttSettings`)

**Functions created/changed:**

- `Vito2MqttSettings` — cosalette.Settings subclass with serial_port, baud_rate, device_id, signal_language
- `VitoBridgeError` — root domain exception
- `OptolinkConnectionError`, `OptolinkTimeoutError`, `InvalidSignalError`, `CommandNotWritableError`
- `error_type_map` — dict mapping error types to string keys for cosalette ErrorPublisher
- `OptolinkPort` — PEP 544 Protocol with read_signal, write_signal, read_signals

**Tests created/changed:**

- test_config.py: inheritance, required field, 3 defaults, custom values, validation, env prefix (7)
- test_errors.py: hierarchy, catch-by-parent, messages, map completeness/values/uniqueness (16)
- test_ports.py: runtime_checkable, isinstance positive/negative, method signatures (6)

**Review Status:** APPROVED with minor suggestions (type: ignore in test code, shared fixture wiring — both deferred)

**Git Commit Message:**

```
feat: add settings, error types, and OptolinkPort protocol

- Replace placeholder config with Vito2MqttSettings(cosalette.Settings)
- Add domain error hierarchy under VitoBridgeError with error_type_map
- Define OptolinkPort PEP 544 Protocol (read_signal/write_signal/read_signals)
- Add 29 tests covering all three modules (245 total)
```
