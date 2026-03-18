## Epic gas2mqtt Migration Complete: Phase 1 — Project Setup + Settings + Adapters

Established the cosalette framework foundation: added dependencies, replaced scaffolded config with `Gas2MqttSettings`, defined `MagnetometerPort` protocol and `MagneticReading` dataclass, implemented production `Qmc5883lAdapter` and `FakeMagnetometer` test double, updated test fixtures, and wrote 34 unit tests covering defaults, validation boundaries, port behavior, and adapter lifecycle.

**Files created/changed:**
- `packages/src/gas2mqtt/settings.py` — `Gas2MqttSettings` extending `cosalette.Settings`
- `packages/src/gas2mqtt/ports.py` — `MagneticReading` dataclass + `MagnetometerPort` protocol
- `packages/src/gas2mqtt/adapters/__init__.py` — adapter package re-exports
- `packages/src/gas2mqtt/adapters/qmc5883l.py` — production I2C adapter (QMC5883L)
- `packages/src/gas2mqtt/adapters/fake.py` — `FakeMagnetometer` test double
- `packages/src/gas2mqtt/domain/__init__.py` — domain logic stub
- `packages/src/gas2mqtt/devices/__init__.py` — device handlers stub
- `packages/tests/conftest.py` — updated (removed template artifacts)
- `packages/tests/fixtures/config.py` — replaced with cosalette-based settings factory
- `packages/tests/fixtures/magnetometer.py` — `fake_magnetometer` fixture
- `packages/tests/unit/__init__.py` — unit test package
- `packages/tests/unit/test_settings.py` — 24 tests (defaults + BVA validation)
- `packages/tests/unit/test_ports.py` — 4 tests (MagneticReading)
- `packages/tests/unit/test_adapters.py` — 6 tests (FakeMagnetometer)
- `.env.example` — all settings documented
- `pyproject.toml` — dependencies updated (cosalette, smbus2)
- `packages/src/gas2mqtt/config.py` — deleted (replaced by settings.py)

**Functions created/changed:**
- `Gas2MqttSettings` — settings class with I2C, trigger, temperature, consumption fields
- `MagneticReading` — frozen dataclass (bx, by, bz, temperature_raw)
- `MagnetometerPort` — Protocol with `read()`, `initialize()`, `close()`
- `Qmc5883lAdapter` — production I2C adapter with `_to_signed_16()` helper
- `FakeMagnetometer` — configurable test double
- `make_gas2mqtt_settings()` — isolated test settings factory
- `_IsolatedGas2MqttSettings` — env-isolated settings subclass for tests

**Tests created/changed:**
- `TestGas2MqttSettingsDefaults` — 12 tests verifying legacy-matching defaults
- `TestGas2MqttSettingsValidation` — 12 tests (BVA boundaries, both rejection + acceptance)
- `TestMagneticReading` — 4 tests (creation, immutability, equality)
- `TestFakeMagnetometer` — 6 tests (defaults, config, lifecycle, protocol)

**Review Status:** APPROVED (after revision — lint fixed, ValidationError, BVA boundaries added)

**Git Commit Message:**
```
feat: add cosalette framework setup with settings and adapters

- Replace scaffolded config.py with Gas2MqttSettings (cosalette Settings subclass)
- Define MagnetometerPort protocol and MagneticReading dataclass
- Implement Qmc5883lAdapter (production I2C) and FakeMagnetometer (test double)
- Add 34 unit tests covering settings validation, ports, and adapters
- Create .env.example with all configurable settings documented
- Update dependencies: cosalette>=0.1.0, smbus2>=0.6.0
```
