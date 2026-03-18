## Epic Cosalette Publish Strategies: Telemetry Migration

Migrated temperature and magnetometer devices from `@app.device` (manual poll loops) to `@app.telemetry` (framework-managed polling). Temperature uses `OnChange(threshold={"temperature": 0.05})` to suppress redundant publishes. Magnetometer conditionally registered only when `enable_debug_device=True`. Adapter factory updated to use cosalette 0.1.1 settings injection.

**Files created/changed:**

- `packages/src/gas2mqtt/main.py` — Telemetry registration with OnChange strategy, settings injection for adapter factory
- `packages/src/gas2mqtt/devices/temperature.py` — Removed `temperature_device()` coroutine, kept `make_temperature_handler()` factory
- `packages/src/gas2mqtt/devices/magnetometer.py` — Removed `magnetometer_device()` coroutine, kept `make_magnetometer_handler()` factory
- `packages/src/gas2mqtt/devices/__init__.py` — Updated exports
- `packages/tests/integration/test_app_wiring.py` — Updated tests for new registration pattern
- `uv.lock` — cosalette 0.1.0 → 0.1.2

**Functions created/changed:**

- `create_app()` — Replaced `@app.device` with `@app.telemetry` for temperature + magnetometer, lazy handler init for EWMA state persistence
- `_make_magnetometer()` — Now uses settings injection parameter
- Removed: `temperature_device()`, `magnetometer_device()`

**Tests created/changed:**

- `test_handler_produces_calibrated_state` — Integration test for temperature handler pipeline
- `test_temperature_registered_as_telemetry` — Verifies app registration
- `test_handler_returns_raw_values` — Integration test for magnetometer handler
- `test_registered_when_enabled` — Verifies conditional registration (True branch)
- `test_noop_when_disabled` — Verifies conditional registration (False branch)

**Review Status:** APPROVED after revision (used `make_magnetometer_handler` factory in production path, removed unused loggers, added missing True-branch test)

**Git Commit Message:**

```
feat: migrate temperature + magnetometer to @app.telemetry

- Upgrade cosalette 0.1.0 → 0.1.2 for publish strategies
- Temperature uses OnChange(threshold=0.05) to suppress duplicates
- Magnetometer conditionally registered as telemetry (debug only)
- Adapter factory uses settings injection (cosalette 0.1.1)
- Lazy handler init preserves EWMA filter state across calls
```
