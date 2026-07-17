<!--
SPDX-FileCopyrightText: 2026 Fabian Koerner

SPDX-License-Identifier: GPL-3.0-or-later
-->

## Epic cosalette Upgrade Complete: 0.5.3 Public Introspection API

Upgraded all 8 apps + root to cosalette 0.5.3 and migrated every test assertion off
cosalette's private App attributes onto the new public introspection API (#332),
closing cap-b7b and cap-951 in a single coherent change.

**Files created/changed:**

- `apps/airthings2mqtt/pyproject.toml` — pin `cosalette>=0.5.3,<0.6`
- `apps/caldates2mqtt/pyproject.toml` — pin `cosalette>=0.5.3,<0.6`
- `apps/gas2mqtt/pyproject.toml` — pin `cosalette>=0.5.3,<0.6`
- `apps/jeelink2mqtt/pyproject.toml` — pin `cosalette>=0.5.3,<0.6`
- `apps/suncast/pyproject.toml` — pin `cosalette>=0.5.3,<0.6`
- `apps/velux2mqtt/pyproject.toml` — pin `cosalette>=0.5.3,<0.6`
- `apps/vito2mqtt/pyproject.toml` — pin `cosalette>=0.5.3,<0.6`
- `apps/wallpanel-control/pyproject.toml` — pin `cosalette>=0.5.3,<0.6`
- `pyproject.toml` — pin `cosalette[mcp]>=0.5.3,<0.6`
- `uv.lock` — cosalette 0.5.2 → 0.5.3; mcp 1.27.0 → 1.28.1 (CVE fix)
- `apps/airthings2mqtt/packages/tests/unit/test_main.py`
- `apps/caldates2mqtt/packages/tests/unit/test_main.py`
- `apps/gas2mqtt/packages/tests/unit/test_main.py`
- `apps/jeelink2mqtt/packages/tests/integration/test_app_integration.py`
- `apps/suncast/packages/tests/unit/test_app.py`
- `apps/velux2mqtt/packages/tests/unit/test_main.py`
- `apps/vito2mqtt/packages/tests/unit/test_main.py`
- `apps/wallpanel-control/packages/tests/unit/test_main.py`

**Public-API renames applied (pure rename; equivalence proven via introspection):**

- `app._telemetry` → `app.telemetry_registrations`
- `app._commands` → `app.commands`
- `app._devices` → `app.devices`
- `app._adapters` → `app.adapters` (read-only `mappingproxy`)
- `app._store` → `app.store`
- `app._has_dynamic_entity_set()` → `app.has_dynamic_entities` (method → property)

**Explicitly out of scope (no public accessor in 0.5.3):**

- 6× `router._commands` in wallpanel-control `test_system_action.py` (2) and
  `test_display.py` (4) — `Router` singleton, tracked in follow-up **cap-5cy**.

**Tests:** No new tests; existing suites migrated in place. Full gate green —
1638 unit/integration tests pass across all 8 apps, plus lint, typecheck,
complexity, similarity, and security audit.

**Review Status:** APPROVED — the 6 targeted private attrs (_telemetry/_commands/_devices/_adapters/_store/_has_dynamic_entity_set) are fully migrated. Known remaining exceptions with no public accessor in 0.5.3: `app._streams` and `app._state_factories` in jeelink2mqtt (tracked in cap-5cy follow-up family), and `app._settings_class` in vito2mqtt/wallpanel-control (to be filed). The 6 `router._commands` carve-outs are documented in PR #172 / cap-5cy.

**Git Commit Message:**

```
chore: upgrade cosalette 0.5.3, adopt public API

- Bump cosalette to >=0.5.3,<0.6 across all 8 apps and root
- Migrate test assertions from private App attrs to public accessors
- app._telemetry/_commands/_devices/_adapters -> public registration API
- app._store -> app.store; _has_dynamic_entity_set() -> has_dynamic_entities
- Bump mcp transitive to 1.28.1 (CVE-2026-52869/52870/59950)
- Close cap-b7b and cap-951
```
