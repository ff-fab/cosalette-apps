## Epic Jeelink2mqtt Runtime Adoption Complete: Periodic Handlers

Timing concerns for jeelink2mqtt now live in named app-level handlers, while the receiver loop focuses on incoming JeeLink readings. Because cosalette 0.3.13 does not expose `@app.periodic`, this slice uses compact `@app.device` loops with `ctx.sleep` as the framework-supported periodic primitive.

**Files created/changed:**
- apps/jeelink2mqtt/packages/src/jeelink2mqtt/main.py
- apps/jeelink2mqtt/packages/src/jeelink2mqtt/receiver.py
- apps/jeelink2mqtt/packages/src/jeelink2mqtt/state.py
- apps/jeelink2mqtt/packages/tests/fixtures/doubles.py
- apps/jeelink2mqtt/packages/tests/integration/test_app_integration.py
- apps/jeelink2mqtt/packages/tests/unit/test_receiver.py
- docs/planning/log/jeelink2mqtt-runtime-periodic-handlers-complete.md

**Functions created/changed:**
- `receiver`
- `staleness`
- `heartbeat`
- `SharedState.record_published_reading`
- `_check_staleness`
- `_maybe_heartbeat`
- `FakeDeviceContext.sleep`

**Tests created/changed:**
- `TestApp.test_app_registers_periodic_handlers`
- `TestApp.test_shared_state_has_heartbeat_state`
- `TestMaybeHeartbeat` state-backed heartbeat cases
- `TestCheckStaleness` dedup and TOCTOU guard cases
- `TestRecordPublishedReading` availability side-effect cases

**Git Commit Message:**
refactor(jeelink2mqtt): split timing handlers

- Move heartbeat state into SharedState
- Add named staleness and heartbeat devices
- Keep receiver timing timeout for shutdown only
