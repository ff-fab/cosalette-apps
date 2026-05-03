## Epic Cosalette 0.3.13 Adoption Complete: Framework Bump

The workspace now targets cosalette 0.3.13 as the baseline for later app refactors. This phase also refreshed generated framework guidance and created the beads plan for jeelink2mqtt refactoring plus cross-app adoption analysis.

**Files created/changed:**
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
- docs/planning/log/cosalette-0-3-13-adoption-framework-bump-complete.md

**Functions created/changed:**
- None; this phase intentionally avoided app behavior changes.

**Tests created/changed:**
- None; verification used existing lint and typecheck gates.
- `task lint` passed.
- `task typecheck` passed.

**Review Status:** APPROVED

**Git Commit Message:**
chore: bump cosalette to 0.3.13

- Update workspace cosalette constraints and lockfile
- Refresh generated cosalette AI guidance
- Add beads plan for 0.3.13 adoption work
