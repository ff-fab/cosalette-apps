## Epic Complete: CLI --help/--version without env vars

Upgraded to cosalette 0.1.8 and adopted deferred interval resolution so that
`vito2mqtt --help` and `--version` work without `VITO2MQTT_SERIAL_PORT` being set.
The root cause was a chicken-and-egg problem: `register_telemetry()` eagerly accessed
`app.settings` at module-import time, but settings aren't available until the CLI
callback runs. cosalette 0.1.8's `IntervalSpec = float | Callable[[Settings], float]`
breaks the cycle.

**Files created/changed:**

- packages/src/vito2mqtt/devices/telemetry.py
- packages/src/vito2mqtt/devices/commands.py
- packages/tests/unit/devices/test_telemetry.py
- packages/tests/unit/devices/test_commands.py
- packages/tests/unit/test_main.py
- pyproject.toml (cosalette>=0.1.8)
- uv.lock
- .pre-commit-config.yaml (cosalette>=0.1.8 in mypy hook)

**Functions created/changed:**

- `_make_interval(group)` — NEW, factory returning `Callable[[Settings], float]`
- `_get_interval(settings, group)` — REMOVED (replaced by `_make_interval`)
- `register_telemetry(app)` — no longer accesses `app.settings` eagerly
- `register_commands(app)` — no longer accesses `app.settings` eagerly

**Tests created/changed:**

- `TestMakeInterval` — NEW, 3 tests for the interval factory
- `test_uses_deferred_polling_intervals` — NEW, verifies intervals are callables
- `test_rejects_wrong_settings_type` — REMOVED from both telemetry + commands
- `test_app_settings_type` — updated to check `_settings_class` attribute
- `_ensure_serial_port_env` fixture — REMOVED (no longer needed)

**Review Status:** APPROVED

**Git Commit Message:**

```
fix: allow --help/--version without env vars

- Upgrade cosalette to 0.1.8 for deferred interval resolution
- Replace _get_interval with _make_interval factory pattern
- Remove eager app.settings access from registration functions
- Remove _ensure_serial_port_env test workaround
```
