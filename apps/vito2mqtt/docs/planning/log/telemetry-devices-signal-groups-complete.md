## Epic Telemetry Devices Complete: Signal Groups & Serialization

Added the `SIGNAL_GROUPS` registry mapping 7 ADR-002 domains to 46 READ-able
signals, and a `serialize_value()` dispatch-table converter that transforms codec
return types to JSON-serializable forms for MQTT publishing. Review
recommendations addressed: tighter types, `__all__` export, `cast()` for
heterogeneous list, removed redundant test.

**Files created/changed:**

- `packages/src/vito2mqtt/devices/__init__.py`
- `packages/src/vito2mqtt/devices/_serialization.py`
- `packages/tests/unit/devices/__init__.py`
- `packages/tests/unit/devices/test_signal_groups.py`
- `packages/tests/unit/devices/test_serialization.py`

**Functions created/changed:**

- `SIGNAL_GROUPS` — dict mapping 7 domain groups to signal name tuples
- `serialize_value(value, type_code)` — dispatch-table MQTT serializer
- `_passthrough`, `_convert_return_status`, `_convert_error_history`,
  `_convert_system_time` — internal converter helpers

**Tests created/changed:**

- `TestSignalGroupsIntegrity` — 5 test methods (3 parametrized over 46 signals)
- `TestSerializePassthrough` — 8 parametrized passthrough cases
- `TestSerializeReturnStatus` — 4 parametrized ReturnStatus members
- `TestSerializeErrorHistory` — ES pair to dict conversion
- `TestSerializeSystemTime` — datetime to ISO string
- `TestSerializeUnknownTypeCode` — defensive fallback

**Review Status:** APPROVED with recommendations addressed

**Git Commit Message:**

```text
feat: add signal group registry and value serialization

- Define SIGNAL_GROUPS mapping 7 domains to 46 READ-able signals
- Add serialize_value() dispatch-table converter for MQTT publishing
- RT→name, ES→{error,timestamp}, TI→isoformat, rest→passthrough
- Comprehensive tests for registry integrity and serialization
```
