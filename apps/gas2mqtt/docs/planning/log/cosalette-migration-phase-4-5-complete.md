## Epic Cosalette Migration Complete: Temperature + Debug Magnetometer Devices

Phases 4 and 5 implemented together as both are simple `@app.telemetry` handlers using a factory+closure pattern. Temperature reads raw sensor data, applies linear calibration and EWMA filtering. Debug magnetometer passes through raw bx/by/bz values.

**Files created/changed:**

- `packages/src/gas2mqtt/devices/temperature.py`
- `packages/src/gas2mqtt/devices/magnetometer.py`
- `packages/src/gas2mqtt/devices/__init__.py`
- `packages/tests/unit/test_temperature.py`
- `packages/tests/unit/test_magnetometer.py`

**Functions created/changed:**

- `make_temperature_handler(magnetometer, settings)` — factory returning zero-param async closure
- `make_magnetometer_handler(magnetometer)` — factory returning zero-param async closure

**Tests created/changed:**

- `TestTemperatureHandler` — 6 tests (calibration, EWMA smoothing, custom coefficients, rounding, alpha boundary, filter isolation)
- `TestMagnetometerHandler` — 4 tests (output contract, defaults, value updates, no temperature leakage)

**Review Status:** APPROVED (2 LOW-severity items: unused loggers — intentional scaffolding)

**Git Commit Message:**

```
feat: add temperature and debug magnetometer devices

- Add make_temperature_handler factory with calibration + EWMA filter
- Add make_magnetometer_handler factory for raw bx/by/bz debug output
- Add 6 temperature tests and 4 magnetometer tests (94 total passing)
```
