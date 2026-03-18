# Cosalette Publish Strategies Migration

*2026-02-22T20:25:58Z by Showboat 0.6.0*
<!-- showboat-id: 3923394e-cb78-4d0b-a816-5a16e59c76b5 -->

Upgraded cosalette 0.1.0 → 0.1.2. Migrated temperature and magnetometer from @app.device (manual poll loops) to @app.telemetry with publish strategies. Temperature uses OnChange(threshold=0.05) to suppress duplicate publishes. Adapter factories use settings injection.

```bash
uv run pytest packages/tests/ -q --no-header --tb=line 2>&1 | grep -oP '\d+ passed'
```

```output
103 passed
```

```bash
grep -A2 '@app.telemetry' packages/src/gas2mqtt/main.py | grep -v '^--$'
```

```output
Temperature and magnetometer are registered as ``@app.telemetry``
devices (cosalette 0.1.2) with publish strategies.
"""
    # Temperature: @app.telemetry with OnChange publish strategy.
    # The handler factory returns a closure that captures EWMA filter state,
    # so we lazily initialise it on first call to let cosalette DI provide
    @app.telemetry(
        "temperature",
        interval=temp_interval,
    # Magnetometer: conditional @app.telemetry (debug only).
    # Delegates to make_magnetometer_handler() so the tested factory
    # is the same code path used in production.
        @app.telemetry("magnetometer", interval=poll_interval)
        async def _magnetometer(
            magnetometer: MagnetometerPort,
```
