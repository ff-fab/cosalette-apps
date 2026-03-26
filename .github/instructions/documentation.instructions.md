---
description: 'Documentation - Markdown and Zensical conventions'
applyTo: '**/*.md'
---

# Documentation Instructions

## Documentation System

| Component      | Choice                                                         |
| -------------- | -------------------------------------------------------------- |
| Site Generator | Zensical (`zensical.toml`)                                     |
| Theme          | Zensical (modern theme)                                        |
| Structure      | User Journey (guided flow through tasks along lifecycle)       |

### Documentation Sites

This monorepo has **multiple independent documentation sites**:

| Site           | Config                                | Serve command                    | Build command                    |
| -------------- | ------------------------------------- | -------------------------------- | -------------------------------- |
| Root (monorepo)| `zensical.toml`                       | `task docs:serve`                | `task docs:build`                |
| Per-app        | `apps/<name>/zensical.toml`           | `task <app>:docs:serve`          | `task <app>:docs:build`          |

## App Documentation Conventions

### Navigation

All app documentation sites use **top-bar tab navigation** (`navigation.tabs`), not
sidebar navigation. The `zensical.toml` for every app must include a full
`[project.theme]` section with `navigation.tabs`, `navigation.tabs.sticky`, palette
toggles, and all standard markdown extensions. See any existing app (e.g.
`apps/gas2mqtt/zensical.toml`) as reference. The `task app:new` scaffold generates this
automatically.

### Homepage (`docs/index.md`)

Every app homepage must include:

1. **Badges** — License, Python version, cosalette framework
2. **Bold tagline** — one-sentence description of what the app does
3. **Quick Links** — grid cards (Material `grid cards` syntax) linking to each
   documentation page (Getting Started, Configuration, MQTT Topics, etc.)

The scaffold generates these three automatically. Additionally, each homepage should
include (expand after scaffolding):

4. **Prose paragraph** — brief explanation of how the app works
5. **Features section** — bullet list of key capabilities
6. **Hardware table** (if applicable) — sensor/interface/platform

Do not leave the homepage as just a title and one-liner.

## ADR Format

Architecture Decision Records follow this structure. ADRs live in two places:

| Scope              | Location                          | Examples                            |
| ------------------ | --------------------------------- | ----------------------------------- |
| Monorepo-wide      | `docs/adr/ADR-NNN-title.md`      | Monorepo structure, shared tooling  |
| App-specific       | `apps/<name>/docs/adr/ADR-NNN-title.md` | Framework choice, domain design     |

When creating an ADR, choose the right scope:
- Decisions affecting the monorepo or multiple apps → root `docs/adr/`
- Decisions scoped to a single app's architecture → `apps/<name>/docs/adr/`

ADR template:

```markdown
# ADR-<number>: <title>

## Status

Proposed | Accepted | Deprecated | Superseded **Date:** YYYY-MM-DD

## Context

The issue and context for the decision.

## Decision

Use <solution> for <problem> because <rationale>.

## Decision Drivers

- Driver 1...

## Considered Options

- Option 1...

## Decision Matrix

| Criterion | Option 1 | Option 2 |
| --------- | -------- | -------- |
| Driver 1  | 3        | 5        |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- ...

### Negative

- ...

_<Date>_
```

## File Locations

| Content              | Location                              |
| -------------------- | ------------------------------------- |
| Root documentation   | `docs/`                               |
| Root ADRs            | `docs/adr/`                           |
| App documentation    | `apps/<name>/docs/`                   |
| App ADRs             | `apps/<name>/docs/adr/`               |

ADRs are included in their respective documentation site (root or per-app).
