## Epic Complete: State Persistence

Added durable state persistence to gas2mqtt so cumulative gas consumption
and counter values survive application restarts. Implemented using the
hexagonal architecture pattern with a `StateStoragePort` protocol, a
production `JsonFileStorage` adapter (atomic writes via rename), and test
doubles (`FakeStorage`, `NullStorage`). Configured via the existing
`GAS2MQTT_STATE_FILE` environment variable / `state_file` setting.

**Phases Completed:** 3 of 3

1. ✅ Phase 1: Port + Adapters + Tests
2. ✅ Phase 2: Settings + Wiring
3. ✅ Phase 3: Device Integration + Tests

**All Files Created/Modified:**

- packages/src/gas2mqtt/ports.py
- packages/src/gas2mqtt/settings.py
- packages/src/gas2mqtt/main.py
- packages/src/gas2mqtt/adapters/\_\_init\_\_.py
- packages/src/gas2mqtt/adapters/json\_storage.py (new)
- packages/src/gas2mqtt/adapters/fake.py
- packages/src/gas2mqtt/devices/gas\_counter.py
- packages/tests/unit/conftest.py
- packages/tests/unit/test\_storage.py (new)
- packages/tests/unit/test\_gas\_counter.py
- packages/tests/integration/test\_app\_wiring.py

**Key Functions/Classes Added:**

- `StateStoragePort` protocol (load/save)
- `JsonFileStorage` adapter (atomic file writes, corruption recovery)
- `NullStorage` adapter (no-op for stateless mode)
- `FakeStorage` test double (in-memory, deepcopy isolation)
- `_restore_counter()` helper (type-safe state extraction)
- `_restore_consumption()` helper (rebuild ConsumptionTracker)
- `_make_storage_adapter()` factory (settings-driven adapter selection)

**Test Coverage:**

- Total tests written: 26 (16 storage + 7 gas counter persistence + 3
  integration wiring)
- All tests passing: ✅ (127 total suite)
- Coverage: 88.1% lines, 81.2% branches (threshold 80%)

**Recommendations for Next Steps:**

- Gate task `workspace-5wl` remains open: evaluate extracting StoragePort
  to the cosalette framework when a second project needs persistence
- Consider adding state migration/versioning if the persisted schema
  evolves
