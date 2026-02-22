## Epic State Persistence Complete: Port + Adapters + Tests

Defined `StateStoragePort` protocol and implemented three adapters (`JsonFileStorage`,
`NullStorage`, `FakeStorage`) following the existing hexagonal architecture pattern.
All 16 unit tests pass, including mutation isolation tests for `FakeStorage`.

**Files created/changed:**

- `packages/src/gas2mqtt/ports.py` (modified — added `StateStoragePort`)
- `packages/src/gas2mqtt/adapters/json_storage.py` (new — `JsonFileStorage`)
- `packages/src/gas2mqtt/adapters/fake.py` (modified — added `NullStorage`, `FakeStorage`)
- `packages/src/gas2mqtt/adapters/__init__.py` (modified — re-exports)
- `packages/tests/unit/test_storage.py` (new — 16 tests)

**Functions created/changed:**

- `StateStoragePort.load()`, `StateStoragePort.save()` — protocol contract
- `JsonFileStorage.__init__()`, `.load()`, `.save()` — atomic file persistence
- `NullStorage.load()`, `.save()` — no-op adapter
- `FakeStorage.__init__()`, `.load()`, `.save()` — in-memory test double with
  deep-copy isolation

**Tests created/changed:**

- `TestJsonFileStorage` — 8 tests (missing file, roundtrip, corruption, atomic write)
- `TestNullStorage` — 2 tests (no-op contract)
- `TestFakeStorage` — 6 tests (roundtrip, independence, mutation isolation)

**Review Status:** APPROVED (mutation leakage issue addressed with `copy.deepcopy`)

**Git Commit Message:**

```text
feat: add StateStoragePort and storage adapters

- Define StateStoragePort protocol in ports.py
- Implement JsonFileStorage with atomic write (temp + replace)
- Add NullStorage (no-op) and FakeStorage (test double)
- 16 unit tests covering roundtrip, corruption, and mutation isolation
```
