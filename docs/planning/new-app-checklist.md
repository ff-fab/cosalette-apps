# New App Creation Checklist

Step-by-step guide for adding a new app to the cosalette-apps monorepo.
Use `task app:new -- <name> "<description>"` to automate steps 1–10, or follow
manually below.

## Prerequisites

- The app name follows the `*2mqtt` convention (e.g., `airthings2mqtt`)
- You know the license: **MIT** (default) or **GPL-3.0-or-later**
- The monorepo dev environment is set up (`task sync`)

## Checklist

### 1. App Directory Structure

Create the canonical layout under `apps/<name>/`:

```
apps/<name>/
├── packages/
│   ├── src/
│   │   └── <name>/
│   │       ├── __init__.py      # Version: __version__ = "0.1.0"
│   │       ├── py.typed         # PEP 561 marker (empty file)
│   │       └── main.py          # Entry point stub
│   └── tests/
│       ├── unit/
│       │   ├── __init__.py
│       │   └── conftest.py
│       ├── integration/
│       │   └── __init__.py
│       ├── fixtures/
│       └── conftest.py          # Root test conftest
├── docs/
│   ├── adr/
│   ├── testing/
│   └── index.md
├── README.md
├── LICENSE                      # Full license text (MIT or GPL-3.0)
├── CHANGELOG.md                 # Empty, managed by release-please
├── pyproject.toml               # See step 2
├── Dockerfile                   # See step 9
├── docker-compose.yml           # See step 9
└── zensical.toml                # See step 10
```

### 2. pyproject.toml

Create `apps/<name>/pyproject.toml` with:

- `[project]` — name, version `"0.1.0"`, description, `requires-python = ">=3.14"`,
  license, authors, dependencies (at minimum `cosalette`)
- `[project.scripts]` — entry point: `<name> = "<name>.main:main"`
- `[build-system]` — hatchling
- `[tool.hatch.build.targets.wheel]` — `packages = ["packages/src/<name>"]`
- `[tool.pytest.ini_options]` — testpaths, asyncio_mode, markers
- `[tool.coverage.*]` — source, branch, omit, thresholds (`fail_under = 80`)
- `[tool.ruff.lint.isort]` — `known-first-party = ["<name>"]`
- `[[tool.mypy.overrides]]` — only if the app has third-party deps without stubs

### 3. Root Taskfile.yml

Two edits in `Taskfile.yml`:

1. Add `<name>` to the `APPS` list
2. Add an include block:

```yaml
  <name>:
    taskfile: ./taskfiles/PythonApp.yml
    dir: ./apps/<name>
    vars:
      APP_NAME: <name>
```

### 4. Release Please

**`release-please-config.json`** — add to `packages`:

```json
"apps/<name>": {
  "component": "<name>",
  "release-type": "python"
}
```

**`.release-please-manifest.json`** — add:

```json
"apps/<name>": "0.1.0"
```

### 5. CI Workflow

In `.github/workflows/ci.yml`, add a path filter under `dorny/paths-filter`:

```yaml
<name>:
  - 'apps/<name>/**'
```

### 6. Codecov

In `codecov.yml`, add a flag:

```yaml
  <name>:
    paths:
      - apps/<name>/packages/src/
    carryforward: true
```

### 7. Pyright extraPaths

In root `pyproject.toml` → `[tool.pyright]` → `extraPaths`, append:

```
"apps/<name>/packages/src"
```

### 8. REUSE Licensing

**For MIT apps:** Add `"apps/<name>/**"` to the existing MIT annotation path list
in `REUSE.toml`.

**For GPL apps:** Add a new `[[annotations]]` block:

```toml
[[annotations]]
path = "apps/<name>/**"
SPDX-FileCopyrightText = "2026 Fabian Koerner <mail@fabiankoerner.com>"
SPDX-License-Identifier = "GPL-3.0-or-later"
```

**License file:** Copy the appropriate license text to `apps/<name>/LICENSE`.

### 9. Docker

**`Dockerfile`** — Alpine-based, copies monorepo root + app source, installs via
`uv pip install --system`, runs as non-root user. Use an existing app's Dockerfile
as template.

**`docker-compose.yml`** — service definition with build context `../..`, app-specific
environment variables, depends on mosquitto.

### 10. Documentation Site

**`zensical.toml`** — site_name, site_description, nav structure.

**`docs/index.md`** — landing page.

**`docs/adr/`** — empty directory for future ADRs.

### 11. Post-Creation Verification

After scaffolding, verify all integration points:

```bash
# Dependency sync
task sync

# Lint (should pass with empty/stub code)
task <name>:lint

# Type check
task <name>:typecheck

# Tests (placeholder test should pass)
task <name>:test:unit

# REUSE compliance
task reuse:lint

# Full quality gate
task pre-pr
```

## Notes

- The `task app:new` script automates steps 1–10. See `scripts/scaffold-app.sh`.
- After scaffolding, you still need to implement the actual app logic, write real
  tests, and customize the Docker/docs configuration.
- The scaffold creates a minimal working skeleton — all quality gates should pass
  immediately after creation.
