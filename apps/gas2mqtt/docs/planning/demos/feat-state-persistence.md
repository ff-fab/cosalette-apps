# State persistence for gas counter

*2026-02-22T18:57:01Z by Showboat 0.6.0*
<!-- showboat-id: e6492839-3a47-40f2-80b1-3152033c2082 -->

Added state persistence for gas2mqtt so cumulative gas consumption and tick counter survive app restarts. Implements StateStoragePort (Protocol) with three adapters: JsonFileStorage (atomic write via temp+replace), NullStorage (no-op when disabled), and FakeStorage (test double). The gas_counter device loads state on startup, saves after each trigger event and command, and saves on shutdown via try/finally. Opt-in via state_file setting (default: None = disabled).

```bash
uv run pytest packages/tests/unit/test_storage.py packages/tests/unit/test_gas_counter.py -q --tb=line --no-header 2>&1 | tail -1
```

```output
============================== 37 passed in 0.26s ==============================
```
