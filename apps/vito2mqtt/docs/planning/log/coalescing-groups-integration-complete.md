## Epic Coalescing Groups Complete: vito2mqtt Integration

All 7 telemetry handlers now register with `group="optolink"`, enabling
cosalette 0.1.6's tick-aligned coalescing. Phases 1–3 (framework work) were
implemented upstream in cosalette; only Phase 4 (application integration)
required changes in vito2mqtt.

**Files created/changed:**

- packages/src/vito2mqtt/devices/telemetry.py
- packages/tests/unit/devices/test_telemetry.py
- pyproject.toml
- .pre-commit-config.yaml
- docs/adr/ADR-007-telemetry-coalescing-groups.md
- uv.lock

**Functions created/changed:**

- `register_telemetry()` — added `group="optolink"` to `app.add_telemetry()`

**Tests created/changed:**

- `test_uses_optolink_coalescing_group` — verifies all 7 handlers use group="optolink"
- `test_rejects_wrong_settings_type` — verifies TypeError guard on misconfigured app

**Review Status:** APPROVED

**Git Commit Message:**

```
feat: integrate coalescing groups for telemetry handlers

- Add group="optolink" to all 7 telemetry handler registrations
- Bump cosalette dependency to >=0.1.6 (coalescing groups support)
- Update pre-commit mypy hook to use cosalette >=0.1.6
- Add test verifying all handlers use the optolink coalescing group
- Add test for TypeError guard on wrong settings type
- Update ADR-007 status from Proposed to Accepted
```
