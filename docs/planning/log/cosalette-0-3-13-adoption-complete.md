## Epic Complete: Cosalette 0.3.13 Adoption

The workspace now targets cosalette 0.3.13 and has a tracked follow-up plan for using the new framework features. The work separated dependency churn from behavioral refactors, created a jeelink2mqtt refactor epic with ordered child tasks, and audited all other apps for adoption opportunities.

**Phases Completed:** 2 of 2
1. ✅ Phase 1: Framework Bump
2. ✅ Phase 2: App Adoption Audit

**All Files Created/Modified:**
- .beads/issues.jsonl
- .github/instructions/cosalette.instructions.md
- .vscode/mcp.json
- AGENTS.md
- CLAUDE.md
- pyproject.toml
- apps/airthings2mqtt/pyproject.toml
- apps/caldates2mqtt/pyproject.toml
- apps/gas2mqtt/pyproject.toml
- apps/jeelink2mqtt/pyproject.toml
- apps/suncast/pyproject.toml
- apps/velux2mqtt/pyproject.toml
- apps/vito2mqtt/pyproject.toml
- apps/wallpanel-control/pyproject.toml
- uv.lock
- docs/planning/cosalette-0-3-13-app-adoption-audit.md
- docs/planning/log/cosalette-0-3-13-adoption-app-audit-complete.md
- docs/planning/log/cosalette-0-3-13-adoption-framework-bump-complete.md
- docs/planning/log/cosalette-0-3-13-adoption-complete.md

**Key Functions/Classes Added:**
- None; this work intentionally avoided app behavior changes.
- Beads created: cap-lkn, cap-v6y, cap-9rp, cap-e4c, cap-i4l, cap-2t0, cap-5xy, cap-0oc.
- Beads updated or closed: cap-clg, workspace-ds8, workspace-35p, workspace-485, workspace-rpe.

**Test Coverage:**
- Total tests written: 0
- All tests passing: ✅ `task lint` and `task typecheck` passed
- Docs build: ⚠ blocked by pre-existing `.venv/bin/zensical` stale `/workspace/.venv/bin/python` shebang

**Recommendations for Next Steps:**
- Implement cap-clg for airthings2mqtt triggerable telemetry.
- Add a gas2mqtt task for migrating `_gas_lifespan` to `@app.state`.
- Work jeelink2mqtt through cap-v6y child tasks in order: cap-9rp, cap-e4c, cap-i4l, cap-2t0, cap-5xy.
- Resolve workspace-658 before closing the narrowed workspace-485 test task.
