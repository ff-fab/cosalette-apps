## Epic State Persistence Complete: Device Integration

Modified the gas counter device to load state on startup and save state after
every meaningful event (tick, command, shutdown). Extracted `_restore_counter()`
and `_restore_consumption()` helper functions to keep cyclomatic complexity
at rank A.

**Files created/changed:**

- [packages/src/gas2mqtt/devices/gas_counter.py](packages/src/gas2mqtt/devices/gas_counter.py)
- [packages/tests/unit/conftest.py](packages/tests/unit/conftest.py)
- [packages/tests/unit/test_gas_counter.py](packages/tests/unit/test_gas_counter.py)

**Functions created/changed:**

- `_restore_counter(saved, logger)` — extract counter value from saved state
  with type-safe narrowing
- `_restore_consumption(saved, settings, logger)` — rebuild
  `ConsumptionTracker` from saved state
- `gas_counter()` — now resolves `StateStoragePort`, loads/saves state

**Tests created/changed:**

- `TestGasCounterStatePersistence::test_restores_counter_from_saved_state`
- `TestGasCounterStatePersistence::test_restores_consumption_from_saved_state`
- `TestGasCounterStatePersistence::test_saves_state_on_shutdown`
- `TestGasCounterStatePersistence::test_saves_state_after_tick`
- `TestGasCounterStatePersistence::test_saves_state_after_command`
- `TestGasCounterStatePersistence::test_null_storage_starts_fresh`
- `TestGasCounterStatePersistence::test_full_roundtrip_restart`

**Review Status:** APPROVED

**Git Commit Message:**

```text
feat: persist gas counter state between restarts

- Load/save counter and consumption state via StateStoragePort
- Extract _restore_counter() and _restore_consumption() helpers
- Save state after tick events, commands, and on shutdown
- Add 7 unit tests for state persistence scenarios
```
