## Epic Adopt cosalette 0.1.5 Complete: Migrate to cosalette Store

Replaced gas2mqtt's custom storage layer (StateStoragePort, JsonFileStorage, NullStorage,
FakeStorage) with cosalette 0.1.5's built-in Store persistence system (Store protocol,
DeviceStore DI injection, JsonFileStore, NullStore, MemoryStore). The gas_counter device
now receives a framework-managed DeviceStore via dependency injection instead of resolving
a custom adapter.

**Files created/changed:**
- `packages/src/gas2mqtt/main.py` (modified — store= on App constructor, settings before app)
- `packages/src/gas2mqtt/devices/gas_counter.py` (modified — DeviceStore DI, simplified save)
- `packages/src/gas2mqtt/ports.py` (modified — removed StateStoragePort)
- `packages/src/gas2mqtt/adapters/fake.py` (modified — removed NullStorage, FakeStorage)
- `packages/src/gas2mqtt/adapters/__init__.py` (modified — removed storage exports)
- `packages/src/gas2mqtt/adapters/json_storage.py` (deleted)
- `packages/tests/unit/test_storage.py` (deleted — 16 tests; cosalette owns these now)
- `packages/tests/unit/conftest.py` (modified — gas_counter_store fixture added)
- `packages/tests/unit/test_gas_counter.py` (modified — all 27 tests adapted for DeviceStore)
- `packages/tests/integration/test_app_wiring.py` (modified — TestStoreWiring replaces TestStorageAdapterWiring)

**Functions created/changed:**
- `gas_counter(ctx, store)` — now accepts DeviceStore via DI
- `_restore_counter(store, logger)` — reads from DeviceStore instead of dict
- `_restore_consumption(store, settings, logger)` — reads from DeviceStore instead of dict
- `_save_state()` — uses store.update() + store.save() instead of storage.save(name, dict)
- `_make_storage_adapter()` — deleted (replaced by store= constructor parameter)
- `_make_context()` in tests — returns tuple[DeviceContext, DeviceStore]

**Tests created/changed:**
- All 27 gas_counter tests adapted for DeviceStore tuple pattern
- 2 new integration tests (TestStoreWiring) for app store configuration
- 16 storage adapter tests deleted (cosalette's responsibility)

**Review Status:** APPROVED

**Git Commit Message:**
```
refactor: migrate persistence to cosalette Store/DeviceStore

- Replace StateStoragePort with cosalette.Store protocol
- Inject DeviceStore via DI into gas_counter device handler
- Wire store= parameter on App constructor (JsonFileStore/NullStore)
- Delete JsonFileStorage adapter and custom storage tests
- Remove NullStorage/FakeStorage in favour of cosalette equivalents
```
