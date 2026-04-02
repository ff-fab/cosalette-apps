---
name: docs-pipeline-architecture
description:
  How root vs per-app docs are built, where outputs go, and the cache/overlay mechanism
  for GitHub Pages deployment
type: project
---

The docs pipeline uses two workflows: `docs.yml` (orchestrator) and `docs-app.yml`
(reusable per-app).

**Build paths:**

- Root docs: `task docs:build` → `uv run --group docs zensical build --clean` run from
  `/workspace` → outputs to `/workspace/site/`
- Per-app docs: `task <app>:docs:build` →
  `uv run --project {{ROOT_DIR}} --group docs zensical build --clean` run from
  `/workspace/apps/<app>/` → outputs to `/workspace/apps/<app>/site/`

**Artifact upload paths (in CI):**

- Root: `actions/upload-artifact` with `path: site` (relative to workspace root) →
  artifact named `docs-root`
- Per-app: `actions/upload-artifact` with `path: apps/${{ inputs.app }}/site` → artifact
  named `docs-<appname>`

**Deploy job (cache overlay):**

- Restores `merged/` from `actions/cache` using key prefix `pages-site-`
- Downloads all `docs-*` artifacts into `artifacts/`
- For root artifact (`docs-root`): rsync with `--delete` onto `merged/`, dynamically
  excluding existing app subdirs
- For app artifacts: `rm -rf merged/<app>` then rsync into `merged/<app>/`
- Saves new cache as `pages-site-${{ github.run_id }}`
- Deploys `merged/` via `actions/upload-pages-artifact` + `actions/deploy-pages`

**Key constraint:** On `push` events, only changed docs are rebuilt. The cache MUST
exist or the deploy fails. On `workflow_dispatch`, everything is rebuilt and the cache
is seeded/refreshed.

**Why:** The cache is the single source of truth for the full merged site between
incremental builds.

---

## zensical.toml configuration conventions

All apps use `zensical.toml` (not `mkdocs.yml`) at the app root. The root site also has
one at `/workspace/zensical.toml`.

**Two nav tiers exist in the repo:**

1. **Minimal nav** (airthings2mqtt, velux2mqtt): `[project]` only — no
   `[project.theme]`, no plugin config, no markdown_extensions. Nav is flat: Home,
   Getting Started, Configuration, MQTT Topics, ADRs. Used for newer/simpler apps.

2. **Full nav** (gas2mqtt, jeelink2mqtt, vito2mqtt): Full config with `[project.theme]`,
   plugins (mkdocstrings), markdown_extensions, palette toggles. Nav has nested sections
   (Reference, Architecture, Guides etc.).

**Homepage content tiers:**

- airthings2mqtt / velux2mqtt: Bare — just `# Title\n\nOne-line description.` (3–4 lines
  total)
- gas2mqtt: Badges + bold tagline + Features list + hardware table + grid cards with
  icon links
- jeelink2mqtt: Bold tagline + prose description + horizontal rules + Key Features
  (definition list) + Mermaid architecture diagram + Quick Start code blocks +
  Documentation Map table
- vito2mqtt: YAML frontmatter (`title: Home`) + bold tagline + prose + grid cards with
  Material icons + Quick Start code blocks + Documentation table + License section

**Root site** (`/workspace/zensical.toml`): amber/orange palette (vs teal/cyan for
apps), no `navigation.tabs` or `navigation.sections` in features, no mkdocstrings plugin
(root has no Python API), nav is just `[{ "Home" = "index.md" }]`.
