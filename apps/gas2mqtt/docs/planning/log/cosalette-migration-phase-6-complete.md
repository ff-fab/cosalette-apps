## Epic Cosalette Migration Complete: App Wiring + Integration Tests

Full application wiring in main.py with `create_app()` factory, lifespan for I2C lifecycle, adapter registration, and three device registrations. All device handlers delegate to extracted coroutines for testability.

**Files created/changed:**

- `packages/src/gas2mqtt/main.py` — Full app wiring with `create_app()`, `lifespan`, three `@app.device` registrations
- `packages/src/gas2mqtt/devices/temperature.py` — Added `temperature_device()` coroutine
- `packages/src/gas2mqtt/devices/magnetometer.py` — Added `magnetometer_device()` coroutine
- `packages/src/gas2mqtt/devices/__init__.py` — Updated exports
- `packages/src/gas2mqtt/adapters/qmc5883l.py` — Added default constructor args
- `pyproject.toml` — Added `[project.scripts]` entry point
- `packages/tests/integration/__init__.py` — Package init
- `packages/tests/integration/test_app_wiring.py` — 7 integration tests

**Functions created/changed:**

- `create_app()` — Factory wiring App with adapter + 3 devices
- `lifespan()` — Async context manager for I2C init/cleanup
- `temperature_device()` — Device coroutine with EWMA + calibration
- `magnetometer_device()` — Conditional debug device coroutine

**Tests created/changed:**

- `TestAppCreation` — 1 test (smoke test)
- `TestLifespan` — 3 tests (init, close, error cleanup)
- `TestTemperatureDeviceWiring` — 1 test (end-to-end publish)
- `TestMagnetometerDeviceWiring` — 2 tests (enabled publish, disabled no-op)

**Review Status:** APPROVED after revision (extracted device coroutines, tests exercise real handlers)

**Git Commit Message:**

```
feat: wire app entry point with devices and integration tests

- Add create_app() factory with lifespan, adapter, and device registration
- Extract temperature_device and magnetometer_device coroutines
- Add console script entry point (gas2mqtt = gas2mqtt.main:app.run)
- Add 7 integration tests for wiring, lifespan, and device behavior
```
