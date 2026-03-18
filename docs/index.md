# cosalette-apps

A monorepo collection for various cosalette-based smart home apps.

## Apps

Apps will be listed here as they are migrated:

<!-- Add links as apps are migrated in Phases 2-4 -->

## Architecture

- **Build system:** uv workspaces + Taskfile
- **Licensing:** REUSE-compliant (MIT default, GPL-3.0 for vito2mqtt)
- **CI:** Per-app change detection with reusable workflows
- **Releases:** Release Please manifest mode (per-app versioning)

See [ADR-001](adr/ADR-001-monorepo-structure.md) for the full decision record.
