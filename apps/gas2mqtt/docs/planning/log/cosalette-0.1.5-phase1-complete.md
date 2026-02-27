## Epic Adopt cosalette 0.1.5 Complete: Phase 1 — Adapter Lifecycle + Settings DI

Leveraged cosalette 0.1.5's adapter lifecycle protocol and settings-aware DI to remove
the explicit `lifespan()` hook and `_make_magnetometer()` factory from `main.py`.
Adapters now self-manage their lifecycle via `__aenter__`/`__aexit__` and receive
settings automatically through cosalette's unified DI pipeline.

**Files created/changed:**
- packages/src/gas2mqtt/main.py
- packages/src/gas2mqtt/ports.py
- packages/src/gas2mqtt/adapters/qmc5883l.py
- packages/src/gas2mqtt/adapters/fake.py
- packages/tests/integration/test_app_wiring.py
- docs/planning/main-declarativeness-improvements.md
- pyproject.toml
- uv.lock

**Functions created/changed:**
- Removed: `lifespan()`, `_make_magnetometer()` from main.py
- Modified: `Qmc5883lAdapter.__init__` — now accepts `Gas2MqttSettings` via DI
- Added: `__aenter__`/`__aexit__` on `Qmc5883lAdapter`, `FakeMagnetometer`, `MagnetometerPort`

**Tests created/changed:**
- Replaced `TestLifespan` (3 tests) with `TestAdapterLifecycle` (3 tests) in test_app_wiring.py
- All 106 unit tests + 10 integration tests passing

**Review Status:** APPROVED

**Git Commit Message:**
feat: adopt cosalette 0.1.5 adapter lifecycle and settings DI

- Add __aenter__/__aexit__ to Qmc5883lAdapter and FakeMagnetometer
- Change Qmc5883lAdapter to accept Gas2MqttSettings via DI
- Remove lifespan() hook and _make_magnetometer() factory from main.py
- Update MagnetometerPort protocol with lifecycle methods
- Replace lifespan integration tests with adapter lifecycle tests
