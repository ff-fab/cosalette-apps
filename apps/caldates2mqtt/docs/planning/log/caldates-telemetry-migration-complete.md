## Epic Complete: caldates2mqtt Telemetry Migration

Converted caldates2mqtt from `@app.device()` / `app.add_device()` to `app.add_telemetry()` with `triggerable=True` and `TriggerPayload`. Consolidated all handler code into a single `main.py`, removed the `devices/` directory, added input clamping for trigger overrides, and updated all tests and documentation.

**Phases Completed:** 4 of 4
1. ✅ Phase 1: Rewrite main.py with factory + on_configure pattern
2. ✅ Phase 2: Rewrite unit tests for TriggerPayload API
3. ✅ Phase 3: Update integration tests (conftest import + add_telemetry)
4. ✅ Phase 4: Update ADR-001 documentation

**All Files Created/Modified:**
- apps/caldates2mqtt/packages/src/caldates2mqtt/main.py
- apps/caldates2mqtt/packages/src/caldates2mqtt/devices/ (deleted)
- apps/caldates2mqtt/packages/tests/unit/test_calendar_device.py
- apps/caldates2mqtt/packages/tests/integration/conftest.py
- apps/caldates2mqtt/docs/adr/ADR-001-cosalette-migration.md

**Key Functions/Classes Added:**
- `make_calendar_handler(cal)` — factory producing async telemetry handlers with TriggerPayload
- `setup_calendars(settings)` — @app.on_configure hook for dynamic registration
- `_ENTRIES_MAX`, `_DAYS_MAX` — bounds constants for trigger override clamping

**Test Coverage:**
- Total tests: 67 (51 unit + 16 integration)
- All tests passing: ✅

**Recommendations for Next Steps:**
- NameSpec + triggerable bug in cosalette: callable `name=` with `triggerable=True` raises ValueError. Worth filing upstream for future simplification.
