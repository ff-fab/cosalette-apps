# ADR-001: Monorepo Structure

## Status

Accepted **Date:** 2026-03-18

## Context

We maintain more than 10 standalone IoT-to-MQTT bridge app repos (gas2mqtt, jeelink2mqtt,
vito2mqtt, etc.) built on the cosalette framework, each scaffolded from the same copier
template. Three repos are actively developed; the rest are planned.

Each repo contains ~90% identical boilerplate (Taskfile, pre-commit, CI workflows,
AGENTS.md, codecov.yml, etc.). This creates concrete pain:

- **Template update friction** — `copier update` creates merge conflicts; easy to skip,
  leading to template drift across repos.
- **No atomic cross-app changes** — updating a cosalette convention requires N separate
  PRs across N repos.
- **Disjoint coding agent context** — an agent working on gas2mqtt has no visibility into
  vito2mqtt's patterns or decisions.
- **N x M maintenance** — N repos x M config files = many places to keep in sync.
- **Cosalette version drift** — each repo pins its own cosalette version; upgrades are
  uncoordinated.

An additional complication: vito2mqtt is GPL-3.0-or-later while all other apps are MIT.
Any consolidation strategy must handle mixed licensing cleanly.

## Decision

Use a **full monorepo** (`cosalette-apps`) with **uv workspaces + Taskfile** for the
build system, **REUSE specification** for licensing, and **Release Please manifest mode**
for per-app versioning — because this combination eliminates template friction entirely,
provides atomic cross-app changes, and builds on the existing toolchain with minimal new
paradigm.

Key choices:

- **cosalette remains an external PyPI dependency**, not a workspace member — it has its
  own release cadence and consumers outside this monorepo.
- **Apps live under `apps/`** — flat namespace, each app is a uv workspace member.
- **vito2mqtt is included** (not kept as a separate repo) — REUSE handles the license
  boundary cleanly, and the benefits of unified tooling outweigh the licensing complexity.

## Decision Drivers

- Eliminate template drift and the N x M maintenance burden
- Enable atomic cross-app changes (cosalette bumps, convention updates)
- Provide unified context for coding agents across all apps
- Stay within GitHub Actions free-tier budget
- Handle mixed MIT/GPL licensing with machine-verifiable compliance
- Preserve full git history (blame, log) for migrated apps

## Considered Options

- **Option A: Full Monorepo (uv Workspaces + Taskfile)** — all apps in one repo,
  shared configuration, path-filtered CI
- **Option B: Enhanced Polyrepo (improved copier template)** — keep separate repos,
  invest in better template automation
- **Option C: Hybrid (MIT monorepo + GPL polyrepo)** — consolidate MIT apps, keep
  vito2mqtt separate to avoid license mixing
- **Option D: Full Monorepo (Bazel)** — all apps in one repo with Bazel as build system

## Decision Matrix

| Criterion                      | A: Monorepo (uv) | B: Polyrepo | C: Hybrid | D: Monorepo (Bazel) |
| ------------------------------ | ----------------- | ----------- | --------- | -------------------- |
| Atomic cross-app changes       | **5**             | 1           | 4         | 5                    |
| Template friction eliminated   | **5**             | 2           | 4         | 5                    |
| Agent context unity            | **5**             | 1           | 4         | 5                    |
| CI cost (free tier)            | **4**             | 5           | 4         | 3                    |
| Setup effort                   | **4**             | 5           | 3         | 1                    |
| Maintainability                | **5**             | 2           | 3         | 2                    |
| Licensing clarity              | 4                 | 5           | **5**     | 4                    |
| Rust/pyO3 readiness            | **4**             | 4           | 4         | 3                    |
| **Total**                      | **36**            | 25          | 31        | 28                   |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Single source of truth for all CI, pre-commit, devcontainer, and agent configuration
- Atomic cross-app changes — update a convention once, apply everywhere
- Unified agent context — full visibility across all apps and their patterns
- Mixed licensing handled cleanly via REUSE.toml + per-app LICENSE files
- Per-app Docker builds, releases, and documentation deployments remain independent
- Migration via `git filter-repo` preserves full commit history per app
- Shared lockfile ensures consistent dependency versions across apps

### Negative

- Larger repository size (all apps' history in one repo)
- Path-filtered CI adds complexity vs. per-repo triggers
- Contributors to a single app must clone the entire monorepo
- Release Please manifest mode is less well-documented than per-repo mode

_2026-03-18_
