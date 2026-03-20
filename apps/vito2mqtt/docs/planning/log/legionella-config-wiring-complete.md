## Epic Legionella Treatment Complete: Config & Composition Root Wiring

Added three legionella-specific settings to `Vito2MqttSettings` (temperature, duration,
safety margin), wired `JsonFileStore` and `register_legionella()` into the composition
root, and added 12 new tests covering defaults, overrides, and validation boundaries.

**Files created/changed:**

- `packages/src/vito2mqtt/config.py`
- `packages/src/vito2mqtt/main.py`
- `packages/tests/unit/test_config.py`
- `packages/tests/unit/test_main.py`

**Functions created/changed:**

- `Vito2MqttSettings.legionella_temperature` (new field, default 68, gt=0)
- `Vito2MqttSettings.legionella_duration_minutes` (new field, default 40, gt=0)
- `Vito2MqttSettings.legionella_safety_margin_minutes` (new field, default 30, ge=0)
- `app` in main.py — added `store=JsonFileStore(...)` and `register_legionella(app)`

**Tests created/changed:**

- `TestDefaults.test_config_legionella_temperature_default`
- `TestDefaults.test_config_legionella_duration_minutes_default`
- `TestDefaults.test_config_legionella_safety_margin_minutes_default`
- `TestCustomValues.test_config_custom_legionella_values`
- `TestLegionellaValidation.test_config_zero_legionella_temperature_raises`
- `TestLegionellaValidation.test_config_zero_legionella_duration_raises`
- `TestLegionellaValidation.test_config_negative_legionella_temperature_raises`
- `TestLegionellaValidation.test_config_negative_legionella_duration_raises`
- `TestLegionellaValidation.test_config_negative_legionella_safety_margin_raises`
- `TestLegionellaValidation.test_config_zero_legionella_safety_margin_valid`
- `TestDeviceRegistration.test_legionella_device_registered`
- `TestStoreConfiguration.test_app_has_store`

**Review Status:** APPROVED

**Git Commit Message:**

```
feat: add legionella settings and wire into composition root

- Add legionella_temperature, legionella_duration_minutes,
  legionella_safety_margin_minutes to Vito2MqttSettings
- Wire JsonFileStore and register_legionella into App constructor
- Add 12 tests for defaults, overrides, and validation boundaries
```
