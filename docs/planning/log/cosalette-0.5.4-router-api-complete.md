<!--
SPDX-FileCopyrightText: 2026 Fabian Koerner

SPDX-License-Identifier: GPL-3.0-or-later
-->

## Epic cosalette Upgrade Complete: 0.5.4 Router Introspection API

Upgraded all 8 apps + root to cosalette 0.5.4 and migrated the remaining device-level
`router._commands` test assertions onto the new public `router.commands` API (#335),
closing cap-5cy. Also corrected an `app.registered_names` call broken by 0.5.4's
method→property change.

**Files created/changed:**

- 8 × `apps/*/pyproject.toml` — pin `cosalette>=0.5.4,<0.6`
- `pyproject.toml` — pin `cosalette[mcp]>=0.5.4,<0.6`
- `uv.lock` — cosalette 0.5.3 → 0.5.4
- `apps/wallpanel-control/packages/tests/unit/test_system_action.py` — `router._commands` → `router.commands` (2×)
- `apps/wallpanel-control/packages/tests/unit/test_display.py` — `router._commands` → `router.commands` (4×)
- `apps/jeelink2mqtt/packages/tests/integration/test_app_integration.py` — `app.registered_names()` → `app.registered_names` (0.5.4 property change); carve-out comment retargeted to cap-7cp
- `apps/vito2mqtt/packages/tests/unit/test_main.py` — carve-out comment retargeted to cap-7cp
- `apps/wallpanel-control/packages/tests/unit/test_main.py` — carve-out comment retargeted to cap-7cp

**Public-API changes adopted:**

- `router.commands` — new public accessor (verified equivalent to `router._commands`,
  same objects carrying `name`/`payload_model`/`state_model`/`init`)
- `app.registered_names` — now a `frozenset` **property** in 0.5.4 (was a method in
  0.5.3); the single parenthesized call site was corrected

**Out of scope (no public accessor in 0.5.4) — tracked in cap-7cp:**

- `app._settings_class` (vito2mqtt, wallpanel-control)
- `app._state_factories` (jeelink2mqtt, gas2mqtt)
- typed stream registrations (jeelink2mqtt)

**Tests:** No new tests; 6 assertions migrated in place. Full `task pre-pr` gate green —
all apps' unit/integration suites, lint, typecheck, complexity, similarity, and security
audit pass.

**Review Status:** APPROVED — verified independently: zero `router._commands` remain,
6 `router.commands` present, no `registered_names()` call sites remain, no `cap-5cy` or
`cosalette 0.5.3` residue in tests.

**Git Commit Message:**

```
chore: upgrade cosalette 0.5.4, adopt Router API

- Bump cosalette to >=0.5.4,<0.6 across all 8 apps and root
- Migrate router._commands → router.commands in wallpanel tests
- Fix app.registered_names() → property access (0.5.4 change)
- Retarget residual carve-out comments to cap-7cp
- Close cap-5cy
```
