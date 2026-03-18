# Monorepo Implementation Plan

> **Status:** Ready for implementation
> **Prerequisite:** [monorepo-analysis.md](monorepo-analysis.md) — decisions recorded
> **Approach:** Full monorepo, uv workspaces + Taskfile, REUSE licensing,
> incremental migration via `git filter-repo`

---

## Overview

Six phases, executed sequentially. Each phase ends with a working, testable state.

| Phase | Goal                                   | Branch                        |
| ----- | -------------------------------------- | ----------------------------- |
| 1     | Monorepo skeleton (workspace, CI, Taskfile) | `feat/monorepo-skeleton` |
| 2     | Migrate gas2mqtt                       | `feat/migrate-gas2mqtt`       |
| 3     | Migrate jeelink2mqtt                   | `feat/migrate-jeelink2mqtt`   |
| 4     | Migrate vito2mqtt (GPL)                | `feat/migrate-vito2mqtt`      |
| 5     | New app workflow validation            | (done as part of next new app)|
| 6     | Cleanup (archive old repos, remove tmp)| `chore/migration-cleanup`     |

---

## Phase 1: Monorepo Skeleton

**Goal:** Transform the copier-template scaffold into a workspace-aware monorepo with
reusable Taskfile, CI, documentation, and licensing infrastructure. No app code yet.

### 1.1 — Directory Structure

Create the target layout:

```
cosalette-apps/
├── apps/                          # NEW — app directories go here
│   └── .gitkeep
├── taskfiles/
│   └── PythonApp.yml              # NEW — reusable per-app Taskfile template
├── LICENSES/
│   ├── MIT.txt                    # NEW — full MIT license text
│   └── GPL-3.0-or-later.txt      # NEW — full GPL license text
├── REUSE.toml                     # NEW — license annotations
├── docs/
│   ├── index.md                   # NEW — root landing page
│   ├── planning/                  # EXISTS — keep as-is
│   └── adr/
│       └── ADR-001-monorepo-structure.md  # NEW
└── ...
```

**Tasks:**

- [ ] Create `apps/` directory with `.gitkeep`
- [ ] Create `taskfiles/` directory
- [ ] Create `LICENSES/MIT.txt` (full MIT text)
- [ ] Create `LICENSES/GPL-3.0-or-later.txt` (full GPL-3.0 text)
- [ ] Create `docs/index.md` (root landing page — links to future app docs)
- [ ] Create `docs/adr/ADR-001-monorepo-structure.md` documenting the decision

### 1.2 — Root `pyproject.toml` (Workspace Configuration)

Transform the existing `pyproject.toml` from a single-package config to a workspace root.

**Changes to `pyproject.toml`:**

```toml
[project]
name = "cosalette-apps"
version = "0.1.0"
description = "A monorepo collection for various cosalette based smart home apps."
readme = "README.md"
requires-python = ">=3.14"
license = "MIT"
authors = [
    { name = "Fabian Koerner", email = "mail@fabiankoerner.com" }
]
# Root package has no runtime dependencies — each app declares its own
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# ── uv workspace ──────────────────────────────────────────────
[tool.uv.workspace]
members = ["apps/*"]

# ── Shared tool configuration ────────────────────────────────
# Per-app overrides live in apps/<name>/pyproject.toml.
# Ruff, mypy, and pytest pick up the closest pyproject.toml when
# run from the app directory via Taskfile's `dir:` setting.

[tool.ruff]
target-version = "py314"
line-length = 88

[tool.ruff.lint]
select = ["E", "W", "F", "B", "I", "C4", "UP", "SIM", "ARG"]

[tool.ruff.lint.per-file-ignores]
"**/tests/**" = ["ARG", "F841"]
"**/adapters/protocol.py" = ["ARG001"]
"**/__init__.py" = ["F401", "E402"]

[tool.mypy]
python_version = "3.14"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true

[tool.pyright]
pythonVersion = "3.14"
venvPath = "."
venv = ".venv"
# Updated dynamically as apps are added:
extraPaths = ["apps/gas2mqtt/packages/src"]

[dependency-groups]
docs = [
    "mkdocs-autorefs>=1.4.4",
    "mkdocstrings[python]>=0.29",
    "zensical>=0.0.23",
]
dev = [
    "coverage>=7.13.2",
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "pytest-cov>=7.0.0",
    "pytest-httpx>=0.35.0",
    "mypy>=1.8.0",
    "ruff>=0.1.0",
    "flake8>=7.3.0",
    "flake8-cognitive-complexity>=0.1.0",
    "pylint>=3.0.0",
    "radon>=6.0.1",
    "xenon>=0.9.3",
    "types-PyYAML>=6.0.0",
    "pre-commit>=4.5.0",
    "setuptools-scm[toml]>=8.0.0",
    "reuse>=5.0.2",
]
```

**Key changes from current:**

| What                            | Before                     | After                       |
| ------------------------------- | -------------------------- | --------------------------- |
| `dependencies`                  | pydantic, pydantic-settings| `[]` (empty — apps own deps)|
| `[tool.uv.workspace]`          | absent                     | `members = ["apps/*"]`      |
| `[tool.hatch.build]`           | `packages/src/cosalette-apps` | removed (root is not a package) |
| `[tool.setuptools_scm]`        | present                    | removed (per-app versioning)|
| `[tool.pytest.ini_options]`    | present                    | removed (per-app config)    |
| `[tool.coverage.*]`            | present                    | removed (per-app config)    |
| `[tool.ruff.lint.isort]`       | `cosalette-apps`           | removed (per-app config)    |
| `[tool.mypy] overrides`        | `cosalette-apps._version`  | removed (per-app config)    |
| dev dependencies                | kept                       | add `reuse>=5.0.2`          |

**Tasks:**

- [ ] Rewrite `pyproject.toml` as workspace root
- [ ] Remove `packages/src/cosalette-apps/` (copier template skeleton — no longer needed)
- [ ] Remove `packages/tests/` (copier template skeleton)
- [ ] Run `uv lock` to regenerate lockfile
- [ ] Run `uv sync --group dev` to validate

### 1.3 — REUSE Licensing

**Create `REUSE.toml`:**

```toml
version = 1

[[annotations]]
path = ["apps/gas2mqtt/**", "apps/jeelink2mqtt/**"]
SPDX-FileCopyrightText = "2026 Fabian Koerner <mail@fabiankoerner.com>"
SPDX-License-Identifier = "MIT"

[[annotations]]
path = "apps/vito2mqtt/**"
SPDX-FileCopyrightText = "2026 Fabian Koerner <mail@fabiankoerner.com>"
SPDX-License-Identifier = "GPL-3.0-or-later"

[[annotations]]
path = [
    "*.toml",
    "*.yml",
    "*.yaml",
    "*.md",
    "*.json",
    "*.cfg",
    "*.txt",
    "*.lock",
    "Taskfile.yml",
    "taskfiles/**",
    "docs/**",
    "scripts/**",
    ".github/**",
    ".devcontainer/**",
    ".pre-commit-config.yaml",
    ".editorconfig",
    ".gitignore",
    "LICENSE",
    "LICENSES/**",
]
SPDX-FileCopyrightText = "2026 Fabian Koerner <mail@fabiankoerner.com>"
SPDX-License-Identifier = "MIT"
```

**Tasks:**

- [ ] Create `REUSE.toml`
- [ ] Create `LICENSES/MIT.txt`
- [ ] Create `LICENSES/GPL-3.0-or-later.txt`
- [ ] Add `reuse` pre-commit hook (see 1.6)
- [ ] Run `uv run reuse lint` to validate

### 1.4 — Reusable Taskfile Template

**Create `taskfiles/PythonApp.yml`:**

This template is included by the root Taskfile for each app. It receives `APP_NAME` and
optional `MODULE_NAME` as variables.

```yaml
# taskfiles/PythonApp.yml
# Reusable task definitions for cosalette apps.
# Included by root Taskfile.yml with per-app variables.
version: '3'

vars:
  APP_NAME: '{{.APP_NAME}}'
  MODULE_NAME: '{{.MODULE_NAME | default .APP_NAME}}'
  PKG: packages

  HAS_UNIT_TESTS:
    sh: >-
      find {{.PKG}}/tests/unit/ \( -name 'test_*.py' -o -name '*_test.py' \)
      2>/dev/null | grep -qm1 . && echo true || echo false
  HAS_INTEGRATION_TESTS:
    sh: >-
      find {{.PKG}}/tests/integration/ \( -name 'test_*.py' -o -name '*_test.py' \)
      2>/dev/null | grep -qm1 . && echo true || echo false

tasks:
  test:
    desc: 'Run all tests for {{.APP_NAME}} with coverage'
    cmds:
      - cmd: |
          if [ "{{.HAS_UNIT_TESTS}}" != "true" ]; then
            echo "ℹ No unit tests found — skipping"
            exit 0
          fi
          uv run --package {{.APP_NAME}} pytest {{.PKG}}/tests/unit/ -v --tb=short \
            --junitxml=results-unit.xml \
            --cov={{.PKG}}/src/{{.MODULE_NAME}} --cov-branch --cov-report=json
        ignore_error: true
      - |
        if [ -f results-unit.xml ]; then
          uv run python {{.PKG}}/tests/scripts/summarize_tests.py \
            --coverage-file=coverage.json
        else
          echo "ℹ No test results — skipping summary"
        fi

  test:unit:
    desc: 'Run unit tests for {{.APP_NAME}}'
    cmds:
      - |
        if [ "{{.HAS_UNIT_TESTS}}" != "true" ]; then
          echo "ℹ No unit tests found — skipping"
          exit 0
        fi
        uv run --package {{.APP_NAME}} pytest {{.PKG}}/tests/unit/ -v --tb=short \
          --junitxml=results-unit.xml

  test:file:
    desc: 'Run specific test file (e.g.: task {{.APP_NAME}}:test:file -- test_foo.py)'
    cmds:
      - |
        if [ -z "{{.CLI_ARGS}}" ]; then
          echo "Usage: task {{.APP_NAME}}:test:file -- <path-or-pattern>" >&2
          exit 1
        fi
        uv run --package {{.APP_NAME}} pytest {{.CLI_ARGS}} -v --tb=short

  test:integration:
    desc: 'Run integration tests for {{.APP_NAME}}'
    cmds:
      - |
        if [ "{{.HAS_INTEGRATION_TESTS}}" != "true" ]; then
          echo "ℹ No integration tests found — skipping"
          exit 0
        fi
        uv run --package {{.APP_NAME}} pytest {{.PKG}}/tests/integration/ -v --tb=short \
          -m integration

  test:cov:
    desc: 'Run tests with coverage for {{.APP_NAME}}'
    cmds:
      - uv run --package {{.APP_NAME}} pytest {{.PKG}}/tests/ \
          --cov={{.PKG}}/src/{{.MODULE_NAME}} --cov-branch \
          --cov-report=term-missing --cov-report=xml

  test:cov:html:
    desc: 'Run tests with HTML coverage for {{.APP_NAME}}'
    cmds:
      - uv run --package {{.APP_NAME}} pytest {{.PKG}}/tests/ \
          --cov={{.PKG}}/src/{{.MODULE_NAME}} --cov-branch \
          --cov-report=html --cov-report=term
      - cmd: '{{if eq OS "darwin"}}open{{else}}xdg-open{{end}} htmlcov/index.html'
        ignore_error: true

  lint:
    desc: 'Lint {{.APP_NAME}}'
    cmds:
      - uv run ruff check {{.PKG}}/src/ {{.PKG}}/tests/
      - uv run ruff format --check {{.PKG}}/src/ {{.PKG}}/tests/

  lint:fix:
    desc: 'Fix lint issues for {{.APP_NAME}}'
    cmds:
      - uv run ruff check --fix {{.PKG}}/src/ {{.PKG}}/tests/
      - uv run ruff format {{.PKG}}/src/ {{.PKG}}/tests/

  typecheck:
    desc: 'Type check {{.APP_NAME}}'
    cmds:
      - uv run mypy {{.PKG}}/src/

  check:
    desc: 'Run all checks for {{.APP_NAME}}'
    cmds:
      - task: lint
      - task: typecheck
      - task: test

  complexity:
    desc: 'Check code complexity for {{.APP_NAME}}'
    cmds:
      - uv run radon cc {{.PKG}}/src/{{.MODULE_NAME}} --average --show-complexity
      - uv run xenon {{.PKG}}/src/{{.MODULE_NAME}} --max-absolute B --max-modules A --max-average A
      - uv run flake8 --select CCR001 --max-cognitive-complexity 15 {{.PKG}}/src/{{.MODULE_NAME}}

  similarity:
    desc: 'Check code duplication for {{.APP_NAME}}'
    cmds:
      - |
        OUTPUT=$(uv run symilar -d 4 --ignore-imports --ignore-signatures \
          $(find {{.PKG}}/src/{{.MODULE_NAME}} -name '*.py'))
        echo "$OUTPUT"
        DUPES=$(printf '%s\n' "$OUTPUT" | sed -n 's/.*duplicates=\([0-9][0-9]*\).*/\1/p' | head -n1)
        if [ "${DUPES:-0}" -gt 0 ]; then
          echo "❌ Found $DUPES duplicate lines"
          exit 1
        fi

  docs:serve:
    desc: 'Preview docs for {{.APP_NAME}}'
    cmds:
      - uv run --group docs zensical serve --dev-addr 0.0.0.0:8001

  docs:build:
    desc: 'Build docs for {{.APP_NAME}}'
    cmds:
      - uv run --group docs zensical build --clean

  # ── CI Helpers ──────────────────────────────────────────────
  ci:test:unit:
    desc: 'CI unit tests with coverage for {{.APP_NAME}}'
    cmds:
      - |
        if [ "{{.HAS_UNIT_TESTS}}" != "true" ]; then
          echo "ℹ No unit tests found in {{.PKG}}/tests/unit/ — skipping"
          exit 0
        fi
        uv run --package {{.APP_NAME}} pytest {{.PKG}}/tests/unit/ \
          --cov={{.PKG}}/src/{{.MODULE_NAME}} --cov-branch \
          --cov-report=xml --cov-report=json --cov-report=term \
          --junitxml=results-unit.xml
        uv run python {{.PKG}}/tests/scripts/summarize_tests.py \
          --coverage-file=coverage.json --fail-under=80
```

**Tasks:**

- [ ] Create `taskfiles/PythonApp.yml`

### 1.5 — Root Taskfile (Orchestrator)

Replace the current single-app Taskfile with a workspace-aware orchestrator.

```yaml
# Taskfile.yml — root orchestrator
version: '3'

vars:
  # Add apps here as they are migrated. Order doesn't matter.
  APPS: []

# ── Per-app includes ─────────────────────────────────────────
# Each app is included from the reusable template with its own
# directory and variables. Add a new block per migrated app.
# Example (uncomment after Phase 2):
#
# includes:
#   gas2mqtt:
#     taskfile: ./taskfiles/PythonApp.yml
#     dir: ./apps/gas2mqtt
#     vars:
#       APP_NAME: gas2mqtt

tasks:
  default:
    desc: List available tasks
    cmds:
      - task --list

  # ── Cross-app orchestration ────────────────────────────────

  test:all:
    desc: Run tests for all apps
    cmds:
      - for: { var: APPS }
        task: '{{.ITEM}}:test:unit'

  lint:all:
    desc: Lint all apps
    cmds:
      - for: { var: APPS }
        task: '{{.ITEM}}:lint'

  typecheck:all:
    desc: Type check all apps
    cmds:
      - for: { var: APPS }
        task: '{{.ITEM}}:typecheck'

  check:all:
    desc: Run all checks for all apps
    cmds:
      - task: lint:all
      - task: typecheck:all
      - task: test:all

  pre-pr:
    desc: Run all pre-PR quality gates
    cmds:
      - pre-commit run --all-files
      - task: lint:all
      - task: typecheck:all
      - task: test:all

  # ── Planning tasks (beads) ─────────────────────────────────

  plan:
    desc: Show progress per phase (epic completion overview)
    silent: true
    cmds:
      - bash scripts/plan-overview.sh

  plan:ready:
    desc: Show unblocked work you can start right now
    silent: true
    cmds:
      - bd ready

  plan:phase:
    desc: 'Show backlog for a phase (e.g.: task plan:phase -- frontend)'
    silent: true
    cmds:
      - |
        SEARCH="{{.CLI_ARGS}}"
        if [ -z "$SEARCH" ]; then
          EPIC_ID=$(bd query 'type=epic AND status=open' --json 2>/dev/null | jq -r 'sort_by(.priority) | .[0].id // empty')
          if [ -z "$EPIC_ID" ]; then echo "No open epics found." >&2; exit 1; fi
          TITLE=$(bd show "$EPIC_ID" --json 2>/dev/null | jq -r '.[0].title')
          echo "Auto-selected: $TITLE ($EPIC_ID)"
          echo "─────────────────────────────────────────"
        else
          EPIC_ID=$(bd show "$SEARCH" --json 2>/dev/null | jq -r 'if type == "array" then .[0] | select(.issue_type == "epic") | .id // empty else empty end')
          if [ -z "$EPIC_ID" ]; then
            EPIC_ID=$(bd show "lh-$SEARCH" --json 2>/dev/null | jq -r 'if type == "array" then .[0] | select(.issue_type == "epic") | .id // empty else empty end')
          fi
          if [ -z "$EPIC_ID" ]; then
            EPIC_ID=$(bd query "type=epic AND title=$SEARCH" --json 2>/dev/null | jq -r '.[0].id // empty')
          fi
          if [ -z "$EPIC_ID" ]; then
            echo "No epic matching '$SEARCH'. Available epics:" >&2
            bd list --type epic --all --limit 0 >&2; exit 1
          fi
        fi
        bd children "$EPIC_ID"

  plan:ui:
    desc: Interactive epic/task browser (requires fzf)
    silent: true
    cmds:
      - bash scripts/plan-interactive.sh

  plan:task:
    desc: 'Show details of a task (e.g.: task plan:task -- lh-6yy.3)'
    silent: true
    cmds:
      - |
        SEARCH="{{.CLI_ARGS}}"
        if [ -z "$SEARCH" ]; then
          echo "Usage: task plan:task -- <task-id-or-title>" >&2; exit 1
        fi
        TASK_ID=$(bd show "$SEARCH" --json 2>/dev/null | jq -r 'if type == "array" then .[0] | select(.issue_type != "epic") | .id // empty else empty end')
        if [ -z "$TASK_ID" ]; then
          TASK_ID=$(bd show "lh-$SEARCH" --json 2>/dev/null | jq -r 'if type == "array" then .[0] | select(.issue_type != "epic") | .id // empty else empty end')
        fi
        if [ -z "$TASK_ID" ]; then
          TASK_ID=$(bd query "type!=epic AND title=$SEARCH" --json 2>/dev/null | jq -r '.[0].id // empty')
        fi
        if [ -z "$TASK_ID" ]; then echo "No task matching '$SEARCH'." >&2; exit 1; fi
        bd show "$TASK_ID"

  # ── Documentation ──────────────────────────────────────────

  docs:serve:
    desc: Preview root documentation site
    cmds:
      - uv run --group docs zensical serve --dev-addr 0.0.0.0:8001

  docs:build:
    desc: Build root documentation site
    cmds:
      - uv run --group docs zensical build --clean

  # ── Dependencies ───────────────────────────────────────────

  sync:
    desc: Sync all dependencies
    cmds:
      - uv sync --group dev --group docs

  # ── CI Helpers ─────────────────────────────────────────────

  ci:wait:
    desc: 'Wait for CI checks to pass (e.g.: task ci:wait -- 5)'
    cmds:
      - bash scripts/ci-wait.sh {{.CLI_ARGS}}
```

**Tasks:**

- [ ] Replace `Taskfile.yml` with workspace orchestrator
- [ ] Validate: `task --list` shows planning tasks and cross-app tasks
- [ ] Validate: `task pre-pr` runs (trivially passes — no apps yet)

### 1.6 — Pre-commit Configuration

Update `.pre-commit-config.yaml` to add REUSE validation and prepare for multi-app mypy.

**Changes:**

1. **Add REUSE hook** (checks license annotations)
2. **Replace mypy hook** with a comment explaining it runs per-app via Taskfile (mypy
   needs per-app context and dependencies; a global pre-commit hook can't handle that
   cleanly in a workspace)
3. **Update ruff `files` patterns** (no change needed — ruff already scopes to changed
   files)
4. **Update Prettier excludes** to include `apps/` packages

```yaml
# Add after the codespell hook:
  # REUSE: Verify license annotations cover all files
  - repo: https://github.com/fsfe/reuse-tool
    rev: v5.0.2
    hooks:
      - id: reuse
        name: REUSE (license compliance)
```

```yaml
# Replace the mypy hook with:
  # mypy: Runs per-app via Taskfile (needs per-app dependencies).
  # Use: task <app>:typecheck
  # Global pre-commit mypy is disabled because workspace apps have
  # different dependencies that can't be satisfied in a single hook.
```

```yaml
# Update Prettier excludes:
        exclude: |
          (?x)^(
            \.vscode/settings\.json$|
            apps/.*/packages/.*|
            .*\.prompt\.md$|
            .*\.instructions\.md$|
            CHANGELOG\.md$
          )$
```

**Tasks:**

- [ ] Add REUSE pre-commit hook
- [ ] Remove mypy pre-commit hook (replaced by per-app Taskfile typecheck)
- [ ] Update Prettier excludes for `apps/`
- [ ] Run `pre-commit run --all-files` to validate

### 1.7 — GitHub Actions (CI Infrastructure)

Replace the existing single-app workflows with monorepo-aware CI.

**New workflows:**

#### `.github/workflows/ci.yml` (Change detection + dispatch)

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      changes: ${{ steps.filter.outputs.changes }}
      shared: ${{ steps.filter.outputs.shared }}
    steps:
      - uses: actions/checkout@v6
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            shared:
              - 'pyproject.toml'
              - 'uv.lock'
              - '.github/**'
              - 'taskfiles/**'
              - '.pre-commit-config.yaml'
              - 'REUSE.toml'
            # Per-app filters added as apps are migrated:
            # gas2mqtt:
            #   - 'apps/gas2mqtt/**'

  # Shared infrastructure check (REUSE, pre-commit on shared files)
  shared:
    needs: detect
    if: needs.detect.outputs.shared == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - run: pipx install reuse && reuse lint

  # Per-app CI dispatched via matrix (uncomment after first migration)
  # app-ci:
  #   needs: detect
  #   if: needs.detect.outputs.changes != '[]'
  #   strategy:
  #     matrix:
  #       app: ${{ fromJson(needs.detect.outputs.changes) }}
  #     fail-fast: false
  #   uses: ./.github/workflows/ci-app.yml
  #   with:
  #     app: ${{ matrix.app }}
```

#### `.github/workflows/ci-app.yml` (Reusable per-app workflow)

```yaml
name: CI (per-app)
on:
  workflow_call:
    inputs:
      app:
        required: true
        type: string

concurrency:
  group: ci-${{ inputs.app }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --group dev
      - run: task ${{ inputs.app }}:lint

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --group dev
      - run: task ${{ inputs.app }}:typecheck

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --group dev
      - run: task ${{ inputs.app }}:ci:test:unit
      - uses: codecov/codecov-action@v5
        if: always()
        with:
          files: apps/${{ inputs.app }}/coverage.xml
          flags: ${{ inputs.app }}
```

#### `.github/workflows/docker-app.yml` (Reusable per-app Docker build)

```yaml
name: Docker Build (per-app)
on:
  workflow_call:
    inputs:
      app:
        required: true
        type: string
      version:
        required: true
        type: string

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v6
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: apps/${{ inputs.app }}
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ghcr.io/ff-fab/${{ inputs.app }}:${{ inputs.version }}
            ghcr.io/ff-fab/${{ inputs.app }}:latest
          cache-from: type=gha,scope=${{ inputs.app }}
          cache-to: type=gha,mode=max,scope=${{ inputs.app }}
```

#### `.github/workflows/release-please.yml` (Manifest mode)

```yaml
name: Release Please
on:
  push:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

jobs:
  release:
    runs-on: ubuntu-latest
    outputs:
      releases_created: ${{ steps.release.outputs.releases_created }}
      paths_released: ${{ steps.release.outputs.paths_released }}
    steps:
      - uses: googleapis/release-please-action@v4
        id: release
        with:
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json

  # Docker builds triggered per released app
  # (uncomment after first migration)
  # docker:
  #   needs: release
  #   if: needs.release.outputs.releases_created == 'true'
  #   strategy:
  #     matrix:
  #       include:
  #         # Dynamically populated from release outputs
  #         - app: gas2mqtt
  #           version: ${{ needs.release.outputs['apps/gas2mqtt--tag_name'] }}
  #   uses: ./.github/workflows/docker-app.yml
  #   with:
  #     app: ${{ matrix.app }}
  #     version: ${{ matrix.version }}
```

**Tasks:**

- [ ] Create `.github/workflows/ci.yml` (detection + shared checks)
- [ ] Create `.github/workflows/ci-app.yml` (reusable per-app)
- [ ] Create `.github/workflows/docker-app.yml` (reusable Docker build)
- [ ] Update `.github/workflows/release-please.yml` for manifest mode
- [ ] Remove old single-app workflows: `build-edge.yml`, `codeql.yml`,
      `devcontainer-build.yml`, `docs.yml` (will be replaced per-app or by the new CI)
- [ ] Keep `ci.yml` old version as reference until Phase 2 validates the new one

### 1.8 — Release Please Manifest Config

**Replace `release-please-config.json`:**

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "release-type": "simple",
  "bump-minor-pre-major": true,
  "bump-patch-for-minor-pre-major": true,
  "separate-pull-requests": true,
  "include-component-in-tag": true,
  "packages": {}
}
```

**Create `.release-please-manifest.json`:**

```json
{}
```

Both are empty — packages are added as apps are migrated.

**Tasks:**

- [ ] Replace `release-please-config.json`
- [ ] Create `.release-please-manifest.json`

### 1.9 — Codecov Configuration

**Update `codecov.yml` for per-app flag-based coverage:**

```yaml
coverage:
  status:
    project:
      default:
        target: 80%
        threshold: 4%
    patch:
      default:
        target: 50%

flags:
  gas2mqtt:
    paths:
      - apps/gas2mqtt/packages/src/
    carryforward: true
  jeelink2mqtt:
    paths:
      - apps/jeelink2mqtt/packages/src/
    carryforward: true
  vito2mqtt:
    paths:
      - apps/vito2mqtt/packages/src/
    carryforward: true

comment:
  layout: 'condensed_header, condensed_files, condensed_footer, components'
  behavior: default
  require_changes: true
```

**Tasks:**

- [ ] Update `codecov.yml` with per-app flags

### 1.10 — Documentation Deployment

**Create `.github/workflows/docs.yml`:**

```yaml
name: Documentation
on:
  push:
    branches: [main]
    paths:
      - 'docs/**'
      - 'zensical.toml'
      - 'apps/*/docs/**'
      - 'apps/*/zensical.toml'

permissions:
  pages: write
  id-token: write

jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      root: ${{ steps.filter.outputs.root }}
      # Per-app filters added as apps are migrated
    steps:
      - uses: actions/checkout@v6
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            root:
              - 'docs/**'
              - 'zensical.toml'

  deploy-root:
    needs: detect
    if: needs.detect.outputs.root == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --group docs
      - run: task docs:build
      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./site
          keep_files: true
```

**Tasks:**

- [ ] Create `.github/workflows/docs.yml`
- [ ] Remove old `docs.yml` if it exists with single-app logic

### 1.11 — Agent Instructions Update

Update `AGENTS.md`, `CLAUDE.md`, and `.github/copilot-instructions.md` to reflect
monorepo layout and conventions.

**Key changes:**

- Update Taskfile examples: `task gas2mqtt:test:unit` instead of `task test:unit`
- Update file paths: `apps/<name>/packages/src/` instead of `packages/src/`
- Add monorepo-specific conventions (commit scoping: `feat(gas2mqtt):`)
- Update tooling instructions: `uv run --package <name>`

**Tasks:**

- [ ] Update `AGENTS.md`
- [ ] Update `CLAUDE.md`
- [ ] Update `.github/copilot-instructions.md`
- [ ] Update `.github/instructions/tooling.instructions.md`

### 1.12 — Pyrightconfig Update

**Update `pyrightconfig.json`:**

```json
{
  "extraPaths": [],
  "venvPath": ".",
  "venv": ".venv",
  "pythonVersion": "3.14"
}
```

`extraPaths` is populated as apps are added.

**Tasks:**

- [ ] Update `pyrightconfig.json`

### Phase 1 — Validation Checklist

- [ ] `uv lock` succeeds
- [ ] `uv sync --group dev --group docs` succeeds
- [ ] `uv run reuse lint` passes
- [ ] `pre-commit run --all-files` passes
- [ ] `task --list` shows orchestration tasks
- [ ] `task pre-pr` passes (trivially — no apps)
- [ ] No errors in VS Code (pyright/pylance)

---

## Phase 2: Migrate gas2mqtt

**Goal:** First app migration. Validates the entire monorepo workflow: filter-repo,
uv workspace membership, Taskfile integration, per-app CI, docs deployment.

### 2.1 — History-Preserving Import

```bash
# 1. Fresh clone (filter-repo requires it)
cd /tmp
git clone https://github.com/ff-fab/gas2mqtt gas2mqtt-migration
cd gas2mqtt-migration

# 2. Rewrite all paths under apps/gas2mqtt/
git filter-repo --to-subdirectory-filter apps/gas2mqtt

# 3. Merge into monorepo
cd /home/fab/cosalette-apps
git remote add gas2mqtt-import /tmp/gas2mqtt-migration
git fetch gas2mqtt-import --no-tags
git merge gas2mqtt-import/main --allow-unrelated-histories \
    -m "feat: merge gas2mqtt history into monorepo"
git remote remove gas2mqtt-import
```

**Tasks:**

- [ ] Run filter-repo migration
- [ ] Verify: `git log --oneline -- apps/gas2mqtt/ | head -20` shows original commits
- [ ] Verify: `git blame apps/gas2mqtt/packages/src/gas2mqtt/main.py` shows original
      authorship

### 2.2 — Adapt gas2mqtt for Workspace Membership

**Changes to `apps/gas2mqtt/pyproject.toml`:**

- Remove `[tool.ruff]` section (uses root config, keep only `[tool.ruff.lint.isort]`)
- Remove `[tool.mypy]` shared settings (uses root config, keep only
  `[[tool.mypy.overrides]]`)
- Remove `[tool.setuptools_scm]` (moved to Release Please)
- Remove `[dependency-groups]` (dev deps are at workspace root)
- Add/update `[tool.pytest.ini_options]` with `testpaths` relative to app dir
- Add/update `[tool.coverage.*]` scoped to gas2mqtt
- Keep `[project]` metadata, dependencies, scripts, build-system intact

**Remove files that are now handled at monorepo level:**

- `apps/gas2mqtt/.pre-commit-config.yaml` (root handles it)
- `apps/gas2mqtt/renovate.json` (root handles it)
- `apps/gas2mqtt/codecov.yml` (root handles it)
- `apps/gas2mqtt/pyrightconfig.json` (root handles it)
- `apps/gas2mqtt/.github/` (entire directory — CI lives at root)
- `apps/gas2mqtt/AGENTS.md` (root handles it)
- `apps/gas2mqtt/CLAUDE.md` (root handles it)
- `apps/gas2mqtt/CONTRIBUTING.md` (root handles it)
- `apps/gas2mqtt/Taskfile.yml` (replaced by template include)
- `apps/gas2mqtt/release-please-config.json` (root manifest mode)
- `apps/gas2mqtt/scripts/ci-wait.sh` (root scripts)
- `apps/gas2mqtt/scripts/plan-*.sh` (root scripts)
- `apps/gas2mqtt/scripts/update-precommit.sh` (root scripts)

**Keep files:**

- `apps/gas2mqtt/pyproject.toml` (app-specific deps, metadata)
- `apps/gas2mqtt/LICENSE` (MIT)
- `apps/gas2mqtt/README.md`
- `apps/gas2mqtt/Dockerfile`
- `apps/gas2mqtt/docker-compose.yml`
- `apps/gas2mqtt/mosquitto.conf`
- `apps/gas2mqtt/zensical.toml` (update `site_url`)
- `apps/gas2mqtt/packages/` (source code and tests — untouched)
- `apps/gas2mqtt/docs/` (documentation content)

**Tasks:**

- [ ] Adapt `apps/gas2mqtt/pyproject.toml` for workspace membership
- [ ] Remove monorepo-level duplicate files (see list above)
- [ ] Update `apps/gas2mqtt/zensical.toml`: set `site_url` to
      `https://ff-fab.github.io/cosalette-apps/gas2mqtt/`
- [ ] Verify `apps/gas2mqtt/LICENSE` is MIT

### 2.3 — Register gas2mqtt in Workspace

**Root `pyproject.toml`:**

```toml
[tool.pyright]
extraPaths = ["apps/gas2mqtt/packages/src"]
```

**Root `Taskfile.yml`:**

```yaml
vars:
  APPS: [gas2mqtt]

includes:
  gas2mqtt:
    taskfile: ./taskfiles/PythonApp.yml
    dir: ./apps/gas2mqtt
    vars:
      APP_NAME: gas2mqtt
```

**`release-please-config.json`:**

```json
{
  "packages": {
    "apps/gas2mqtt": {
      "component": "gas2mqtt",
      "package-name": "gas2mqtt",
      "extra-files": [
        { "type": "generic", "path": "pyproject.toml" }
      ]
    }
  }
}
```

**`.release-please-manifest.json`:**

```json
{
  "apps/gas2mqtt": "0.1.0"
}
```

**`.github/workflows/ci.yml`** — uncomment gas2mqtt filter and app-ci job.

**`.github/workflows/docs.yml`** — add gas2mqtt docs filter and deploy job.

**Tasks:**

- [ ] Add gas2mqtt to root `pyproject.toml` extraPaths
- [ ] Add gas2mqtt to root `Taskfile.yml` (includes + APPS var)
- [ ] Add gas2mqtt to `release-please-config.json`
- [ ] Add gas2mqtt to `.release-please-manifest.json`
- [ ] Add gas2mqtt filter to CI workflow
- [ ] Add gas2mqtt docs deploy job

### 2.4 — Validate gas2mqtt Migration

```bash
uv lock                              # Resolve workspace with gas2mqtt
uv sync --group dev                  # Install all deps

task gas2mqtt:lint                    # Lint
task gas2mqtt:typecheck               # Type check
task gas2mqtt:test:unit               # Tests
task gas2mqtt:docs:build              # Docs build

uv run reuse lint                     # License compliance
pre-commit run --all-files            # All pre-commit hooks
task pre-pr                           # Full quality gate
```

**Tasks:**

- [ ] `uv lock` succeeds
- [ ] `task gas2mqtt:test:unit` passes
- [ ] `task gas2mqtt:lint` passes
- [ ] `task gas2mqtt:typecheck` passes
- [ ] `task gas2mqtt:docs:build` succeeds
- [ ] `uv run reuse lint` passes
- [ ] `task pre-pr` passes
- [ ] Zensical docs render correctly at subpath (manual check)

### 2.5 — Test Docs Subpath Deployment

This resolves open question #1 (Zensical multi-site capability):

- [ ] Build gas2mqtt docs: `task gas2mqtt:docs:build`
- [ ] Check generated HTML for correct relative links and asset paths
- [ ] If subpath issues: adjust `zensical.toml` `site_url` and/or `use_directory_urls`
- [ ] Document findings for Phase 3+

---

## Phase 3: Migrate jeelink2mqtt

**Goal:** Validate multi-app coexistence. Same process as Phase 2 with minor variations.

### 3.1 — History-Preserving Import

Same `git filter-repo` process as Phase 2, targeting `apps/jeelink2mqtt/`.

### 3.2 — Adapt jeelink2mqtt for Workspace

Same file cleanup as gas2mqtt (remove standalone CI, pre-commit, Renovate, etc.).

**Additional considerations:**

- jeelink2mqtt has `[project.optional-dependencies]` with `hardware = ["pylacrosse"]` —
  keep this in the app's `pyproject.toml`
- Coverage target is 90% (vs. gas2mqtt's 80%) — keep in app-level config

### 3.3 — Register in Workspace

Add to root Taskfile, release-please, CI workflows, codecov flags, pyright extraPaths.

### 3.4 — Validate

- [ ] Both apps' tests pass: `task gas2mqtt:test:unit && task jeelink2mqtt:test:unit`
- [ ] Cross-app orchestration works: `task test:all`
- [ ] `task pre-pr` passes with both apps
- [ ] No accidental cross-app imports (mypy strict + ruff isort catches these)

---

## Phase 4: Migrate vito2mqtt (GPL)

**Goal:** Validate GPL handling in the monorepo. Same migration process plus GPL-specific
steps.

### 4.1 — History-Preserving Import

Same `git filter-repo` process, targeting `apps/vito2mqtt/`.

### 4.2 — GPL-Specific Steps

- [ ] Verify `apps/vito2mqtt/LICENSE` contains GPL-3.0-or-later text
- [ ] Keep/adapt `add_gpl_headers.py` (scoped to `apps/vito2mqtt/`)
- [ ] Add GPL header pre-commit hook scoped to `apps/vito2mqtt/**/*.py`:

```yaml
- repo: local
  hooks:
    - id: gpl-header-check
      name: GPL header (vito2mqtt)
      entry: uv run python apps/vito2mqtt/scripts/add_gpl_headers.py --check
      language: system
      files: '^apps/vito2mqtt/.*\.py$'
      pass_filenames: false
```

- [ ] Verify `REUSE.toml` annotation covers `apps/vito2mqtt/**` with GPL license
- [ ] Run `uv run reuse lint` — must pass

### 4.3 — Adapt and Register

Same as Phases 2-3. Adapt `pyproject.toml`, register in workspace, CI, release-please.

### 4.4 — Validate

- [ ] All three apps' tests pass: `task test:all`
- [ ] `uv run reuse lint` passes (all files have license coverage)
- [ ] GPL header hook triggers only on vito2mqtt files
- [ ] `task pre-pr` passes with three apps

---

## Phase 5: New App Workflow

**Goal:** Validate that creating a new app from scratch works in the monorepo.

This phase happens naturally when you start the next app (e.g., `airthings2mqtt`):

### Steps for a New App

1. Create `apps/<name>/` with the standard structure:
   ```
   apps/<name>/
   ├── pyproject.toml
   ├── LICENSE
   ├── README.md
   ├── Dockerfile
   ├── docker-compose.yml
   ├── zensical.toml
   ├── docs/
   │   └── index.md
   └── packages/
       ├── src/<name>/
       │   ├── __init__.py
       │   ├── main.py
       │   ├── settings.py
       │   └── ports.py
       └── tests/
           ├── __init__.py
           ├── conftest.py
           ├── unit/
           └── integration/
   ```

2. Register in workspace:
   - Add to root `Taskfile.yml` includes + `APPS` var
   - Add to `release-please-config.json` and manifest
   - Add to CI workflow path filter
   - Add to `codecov.yml` flags
   - Add to root `pyproject.toml` pyright `extraPaths`
   - Add REUSE annotation (if not covered by existing glob)

3. Validate: `task <name>:test:unit`, `uv run reuse lint`, `task pre-pr`

**Outcome:** Document this as a checklist (or a `task app:new` script) for future use.

---

## Phase 6: Cleanup

**Goal:** Finalize migration, archive old repos, clean up temporary files.

### 6.1 — Archive Source Repos

For each migrated repo:

- [ ] Update README.md with: "This project has moved to
      [cosalette-apps](https://github.com/ff-fab/cosalette-apps)"
- [ ] Archive the repo on GitHub (Settings → Danger Zone → Archive)

### 6.2 — Remove Temporary Files

- [ ] Delete `docs/tmp/` (reference copies no longer needed)
- [ ] Delete `packages/` directory if still present from copier skeleton
- [ ] Remove any leftover copier-template files at root that don't apply

### 6.3 — Final Validation

- [ ] All apps pass: `task pre-pr`
- [ ] All docs build: per-app `docs:build` tasks
- [ ] `uv run reuse lint` passes
- [ ] GitHub Actions CI passes on main
- [ ] Release Please creates correct release PRs
- [ ] Docker builds work for each app

### 6.4 — Write ADR

Create `docs/adr/ADR-001-monorepo-structure.md` documenting:

- Decision: Monorepo with uv workspaces + Taskfile
- Context: template friction, agent context, atomic changes
- Consequences: shared CI, REUSE licensing, Release Please manifest mode

---

## Appendix: Files Changed Per Phase

### Phase 1 — New Files

| File | Purpose |
|---|---|
| `apps/.gitkeep` | Placeholder for app directory |
| `taskfiles/PythonApp.yml` | Reusable per-app Taskfile template |
| `LICENSES/MIT.txt` | Full MIT license text |
| `LICENSES/GPL-3.0-or-later.txt` | Full GPL license text |
| `REUSE.toml` | License annotations |
| `.release-please-manifest.json` | Release Please manifest |
| `.github/workflows/ci-app.yml` | Reusable per-app CI |
| `.github/workflows/docker-app.yml` | Reusable per-app Docker build |
| `docs/index.md` | Root landing page |
| `docs/adr/ADR-001-monorepo-structure.md` | Architecture decision |

### Phase 1 — Modified Files

| File | Change |
|---|---|
| `pyproject.toml` | Workspace root (remove single-package config) |
| `Taskfile.yml` | Workspace orchestrator |
| `.pre-commit-config.yaml` | Add REUSE, remove mypy, update Prettier |
| `.github/workflows/ci.yml` | Path-filtered detection |
| `.github/workflows/release-please.yml` | Manifest mode |
| `codecov.yml` | Per-app flags |
| `pyrightconfig.json` | Clear extraPaths |
| `release-please-config.json` | Manifest mode (empty packages) |
| `AGENTS.md` | Monorepo conventions |
| `CLAUDE.md` | Monorepo conventions |

### Phase 1 — Deleted Files

| File | Reason |
|---|---|
| `packages/src/cosalette-apps/` | Copier skeleton replaced by apps/ |
| `packages/tests/` | Copier skeleton replaced by per-app tests |
| `.github/workflows/build-edge.yml` | Replaced by per-app Docker workflow |
| `.github/workflows/codeql.yml` | Can be re-added per-app if needed |
| `.github/workflows/devcontainer-build.yml` | Separate concern |

### Phases 2-4 — Per Migration

| Category | Files |
|---|---|
| **Added (via filter-repo)** | Full app history under `apps/<name>/` |
| **Removed from app** | `.pre-commit-config.yaml`, `renovate.json`, `codecov.yml`, `pyrightconfig.json`, `.github/`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `Taskfile.yml`, `release-please-config.json`, `scripts/ci-wait.sh`, `scripts/plan-*.sh`, `scripts/update-precommit.sh` |
| **Modified in app** | `pyproject.toml` (strip shared config), `zensical.toml` (update site_url) |
| **Modified at root** | `Taskfile.yml`, `release-please-config.json`, `.release-please-manifest.json`, `codecov.yml`, `pyrightconfig.json`, CI workflows |
