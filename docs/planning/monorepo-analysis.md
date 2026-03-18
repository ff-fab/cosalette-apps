# Monorepo Analysis: cosalette-apps

> **Status:** Decisions made — see [Decisions Record](#decisions-record) below
> **Author:** AI-assisted analysis, March 2026
> **Scope:** Evaluate consolidating ~10 standalone IoT app repos into a single monorepo
> **Implementation plan:** [monorepo-implementation-plan.md](monorepo-implementation-plan.md)

### Decisions Record

| # | Question | Decision |
|---|----------|----------|
| 1 | Licensing approach | **Option A** — REUSE + per-file GPL headers (belt and suspenders) |
| 2 | Cosalette as workspace member? | **No** — keep as external PyPI dependency |
| 3 | Build system | **Option C** — uv Workspaces + Taskfile (no Bazel sandbox) |
| 4 | Top-level directory naming | **`apps/`** as proposed |
| 5 | vito2mqtt migration | **Include as planned** in Phase 4 |

---

## Table of Contents

- [Part I — Strategic Context](#part-i--strategic-context)
  - [1. Current State Assessment](#1-current-state-assessment)
  - [2. Monorepo vs. Polyrepo vs. Hybrid](#2-monorepo-vs-polyrepo-vs-hybrid)
- [Part II — Topic Deep-Dives](#part-ii--topic-deep-dives)
  - [3. Licensing](#3-licensing)
  - [4. Build System](#4-build-system)
  - [5. Repository Structure](#5-repository-structure)
  - [6. Dependency Management](#6-dependency-management)
  - [7. Testing](#7-testing)
  - [8. CI/CD](#8-cicd)
  - [9. Taskfile](#9-taskfile)
  - [10. Environment & Tooling](#10-environment--tooling)
  - [11. Documentation](#11-documentation)
  - [12. Deployment](#12-deployment)
  - [13. Release Management](#13-release-management)
  - [14. Migration Strategy](#14-migration-strategy)
- [Part III — Synthesis](#part-iii--synthesis)
  - [15. Decision Matrix](#15-decision-matrix)
  - [16. Recommended Approach](#16-recommended-approach)
  - [17. Open Questions & Risks](#17-open-questions--risks)

---

# Part I — Strategic Context

## 1. Current State Assessment

### What You Have Today

~10 IoT-to-MQTT bridge applications built on the **cosalette** framework, each in its
own GitHub repository created from the same **copier template**. Three repos are already
developed (gas2mqtt, jeelink2mqtt, vito2mqtt), the rest are planned.

Each repo contains ~90% identical boilerplate:

| Identical Across Repos          | Project-Specific                       |
| ------------------------------- | -------------------------------------- |
| Taskfile.yml (90%)              | Hardware dependencies (smbus2, serial) |
| pyproject.toml structure        | Coverage thresholds                    |
| .pre-commit-config.yaml (95%)  | ADRs and documentation content         |
| GitHub Actions workflows (80%) | Dockerfile strategy (Alpine vs. slim)  |
| AGENTS.md, CLAUDE.md           | License (MIT vs. GPL)                  |
| renovate.json, codecov.yml     | Entry point conventions                |
| pyrightconfig.json              | App-specific settings/ports/adapters   |
| docs structure (Zensical)       |                                        |
| scripts/ directory              |                                        |
| release-please-config.json      |                                        |

### What Works

- **Copier template** ensures high initial consistency when creating new projects
- **cosalette framework** provides the real shared infrastructure (MQTT, logging,
  health, configuration, testing utilities)
- **Per-repo CI** is simple: each repo owns its workflows
- **Per-repo docs** deploy independently to `ff-fab.github.io/<app>/`

### What Hurts

| Pain Point                           | Impact                                                 |
| ------------------------------------ | ------------------------------------------------------ |
| **Template update friction**         | `copier update` creates merge conflicts; easy to skip  |
| **No atomic cross-project changes**  | Updating a cosalette convention requires N separate PRs |
| **Disjunct coding agent context**    | Agent working on gas2mqtt has no visibility into vito2mqtt's patterns or decisions |
| **N×M maintenance**                  | N repos × M config files = many places to keep in sync |
| **Documentation scatter**            | Hard to ensure consistent look/feel across project docs |
| **Cosalette version drift**          | Each repo pins its own cosalette version; upgrades are uncoordinated |

---

## 2. Monorepo vs. Polyrepo vs. Hybrid

### Option A: Full Monorepo (All Apps in One Repo)

All apps live in `cosalette-apps`, including the GPL-licensed vito2mqtt.

**Advantages:**

- Single source of truth for all configuration, CI, tooling
- Atomic cross-app changes (update a convention once, apply everywhere)
- Coding agents see the full context — can learn patterns from one app and apply to
  another
- Single `copier` target eliminated — template maintenance becomes repo maintenance
- Shared lockfile ensures consistent dependency resolution
- Cost: every PR runs only the affected app's CI (with path filtering)

**Disadvantages:**

- Mixed licensing complexity (MIT + GPL in same repo)
- Repo grows larger over time (git clone, IDE indexing)
- CI misconfiguration risk: a bad shared config change breaks all apps
- All apps share one issue tracker, PR queue, and release timeline concerns
- GPL source headers and compliance tooling needed for the GPL subset

### Option B: Polyrepo (Status Quo, Enhanced)

Keep separate repos, invest in better copier template automation and a template-update
bot.

**Advantages:**

- Clean per-project isolation (licensing, releases, CI)
- Simple mental model: one repo = one app
- GitHub's UI works best with single-purpose repos

**Disadvantages:**

- Does not solve the three core pain points (atomic changes, template friction, agent
  context)
- Copier update friction grows linearly with repo count
- No mechanism for coding agents to see cross-project patterns

### Option C: Hybrid (MIT Monorepo + GPL Separate)

All MIT-licensed apps in the monorepo; GPL-licensed apps (currently only vito2mqtt) stay
in their own repos but consume the same cosalette framework.

**Advantages:**

- Clean licensing: monorepo is MIT top-to-bottom, no mixed-license complexity
- Solves the pain points for the majority of projects (~9 of 10)
- GPL projects stay isolated with their own compliance tooling
- Can still share Taskfile templates, CI workflows via copier for the GPL repos

**Disadvantages:**

- GPL projects don't benefit from monorepo advantages
- Two maintenance patterns (monorepo + standalone)
- If more GPL projects appear, the "exception" pool grows

### Recommendation

**Option A (Full Monorepo)** is the best fit, with the understanding that mixed licensing
is manageable via per-directory LICENSE files and REUSE annotations (see
[Section 3](#3-licensing)). The three core pain points — atomic changes, template
friction, agent context — are all root-caused by having separate repos. The licensing
overhead is small and well-solved.

If the GPL compliance burden feels excessive after implementation, **falling back to
Option C** is straightforward: extract vito2mqtt back out.

---

# Part II — Topic Deep-Dives

## 3. Licensing

### Context

| App          | License            |
| ------------ | ------------------ |
| Most apps    | MIT                |
| vito2mqtt    | GPL-3.0-or-later   |
| cosalette    | MIT (external dep) |

GPL is chosen for vito2mqtt due to upstream dependencies. No shared code exists between
apps beyond cosalette itself (which is MIT and GPL-compatible).

### Key Legal Facts

- **MIT and GPL code can coexist in the same repository** — GPL only applies to code
  that is combined/linked/distributed as a single program
- Each app is an **independent program** — gas2mqtt and vito2mqtt don't link against
  each other
- **Distribution** is per-Docker-image: the gas2mqtt image is MIT, the vito2mqtt image
  is GPL
- The `license` field in `pyproject.toml` (PEP 639, SPDX expressions) applies
  **per-package**, not per-repo

### GPL Notice Requirements — Background

The GPL v3 text says: *"It is safest to attach [the license notices] to the start of
each source file..."* The key word is **"safest"** — it's a strong recommendation for
maximum legal clarity, not a hard syntactic requirement. The legal obligation is that
recipients can determine the license of every file they receive.

- **FSF (US)** recommends per-file headers as "the most reliable method"
- **FSFE (Europe)** endorses REUSE.toml annotations as a valid alternative that
  satisfies the same goal (machine-verifiable, per-file license attribution)
- **In practice:** both approaches are widely accepted in the GPL community. KDE (one
  of the largest GPL codebases) uses REUSE without per-file headers for many file types.

### Option A: REUSE + Per-File GPL Headers (Belt and Suspenders)

Use REUSE.toml for machine-readable compliance verification across the entire monorepo,
**and** keep per-file GPL headers on vito2mqtt's `.py` files for maximum legal safety.

```toml
# REUSE.toml
version = 1

[[annotations]]
path = "apps/gas2mqtt/**"
SPDX-FileCopyrightText = "2026 Fabian Koerner <mail@fabiankoerner.com>"
SPDX-License-Identifier = "MIT"

[[annotations]]
path = "apps/vito2mqtt/**"
SPDX-FileCopyrightText = "2026 Fabian Koerner <mail@fabiankoerner.com>"
SPDX-License-Identifier = "GPL-3.0-or-later"

[[annotations]]
path = ["*.toml", "*.yml", "*.yaml", "*.md", "Taskfile.yml"]
SPDX-FileCopyrightText = "2026 Fabian Koerner <mail@fabiankoerner.com>"
SPDX-License-Identifier = "MIT"
```

Directory structure:

```
cosalette-apps/
├── LICENSE                    # MIT (root/shared code)
├── REUSE.toml                 # Machine-readable license map
├── LICENSES/
│   ├── MIT.txt
│   └── GPL-3.0-or-later.txt
├── apps/
│   ├── gas2mqtt/
│   │   └── LICENSE            # MIT (per-app copy for tooling recognition)
│   └── vito2mqtt/
│       ├── LICENSE            # GPL-3.0-or-later
│       └── packages/src/vito2mqtt/
│           └── *.py           # Each file has GPL header comment
```

- CI validation: `reuse lint` as a pre-commit hook (covers all apps)
- GPL headers enforced by a pre-commit hook scoped to `apps/vito2mqtt/**/*.py`
  (keep/adapt the existing `add_gpl_headers.py` script)
- Adopted by KDE, Linux kernel, FSFE projects

**Advantages:**

- Maximum legal safety — satisfies both FSF and FSFE recommendations
- Machine-verifiable compliance for the entire monorepo (`reuse lint`)
- Per-file GPL headers give unambiguous notice even when files are extracted/copied
- Works with any number of licenses — future-proof

**Disadvantages:**

- Two compliance mechanisms to maintain (REUSE.toml + header script)
- GPL header hook adds friction when creating new `.py` files in vito2mqtt

### Option B: REUSE Only (No Per-File Headers)

Rely solely on REUSE.toml for all license declarations. No per-file GPL headers.

**Advantages:**

- Simplest maintenance — one TOML file covers everything
- REUSE.toml replaces vito2mqtt's custom `add_gpl_headers.py` entirely
- FSFE-endorsed as sufficient for GPL compliance

**Disadvantages:**

- Does not follow the FSF's "safest" recommendation for GPL
- If a `.py` file is extracted from the repo without the REUSE.toml, its license is
  not self-evident
- More conservative GPL interpretations may consider this insufficient

### Option C: Per-Directory LICENSE Files Only

Simpler approach: each app directory contains its own `LICENSE` file. No REUSE tooling.

**Advantages:**

- Simple, no new tooling
- GitHub auto-detects LICENSE files in directories

**Disadvantages:**

- No automated compliance verification
- Per-file GPL headers still needed (separate enforcement mechanism)
- Manual enforcement of license boundaries

### Option D: Keep GPL Projects Separate

Exclude vito2mqtt from the monorepo entirely.

**Advantages:**

- Monorepo is MIT-only — zero licensing complexity
- vito2mqtt keeps its own GPL compliance tooling independently

**Disadvantages:**

- vito2mqtt doesn't benefit from monorepo advantages
- Two maintenance patterns

### Recommendation

**Option A (REUSE + per-file GPL headers)** is the safest choice. The REUSE.toml
provides machine-verifiable compliance across the entire monorepo, while per-file GPL
headers on vito2mqtt's source files satisfy the FSF's strongest recommendation. The
overhead is modest: one TOML file, two license texts, and the existing GPL header
script scoped to `apps/vito2mqtt/`.

Option B (REUSE only) is a pragmatic alternative endorsed by FSFE, but given that
vito2mqtt already has the `add_gpl_headers.py` tooling, keeping it costs little.

If the GPL compliance burden feels excessive, Option D (separate repo) remains a clean
fallback.

---

## 4. Build System

### Context

Your stated interest in Bazel is driven by **learning** (required for work) and
**hermetic reproducibility**. Some apps may use Rust components via pyO3.

### Option A: Bazel (`rules_python` + `rules_rust`)

Bazel is the industry standard for large-scale, multi-language monorepos.

**Maturity for Python:** `rules_python` v1.9.0 is production-ready for core rules.
`aspect_rules_py` improves IDE support and uses `uv` under the hood.

**How it works:**

- Each package gets BUILD files defining `py_library`, `py_test`, `py_binary` targets
- Dependency resolution via `pip.parse()` from a requirements lockfile
- `rules_rust` (v0.69.0) is production-ready; pyO3 extensions require manual wiring
  (`rust_shared_library` → package as `py_library`)
- Docker images via `rules_oci` (successor to `rules_docker`) — builds OCI images
  without Docker daemon

**Advantages:**

- **Learning investment pays off** for your day job
- Hermetic builds — byte-for-byte reproducible
- Best-in-class build caching and incremental builds
- Rust/pyO3 integration (works, but no turnkey rule)
- Multi-language support if you ever add non-Python components
- Granular test caching — only re-runs tests whose inputs changed

**Disadvantages:**

- **Enormous setup cost**: MODULE.bazel, toolchain registration, BUILD files, Starlark
- Python is second-class in Bazel's ecosystem (Go/Java/C++ are the primary citizens)
- pytest integration is **fiddly**: each `py_test` is an isolated process, conftest.py
  fixtures and session-scoped fixtures need careful wiring
- IDE support is painful without `aspect_rules_py`
- Debugging is harder (sandboxed execution, no easy `pdb`)
- **No release automation** — Bazel doesn't handle versioning, changelogs, or SemVer.
  You'd bolt on Release Please externally anyway
- Per-package versioning is **not a Bazel concept** — it doesn't know about your
  packages' versions
- Overkill complexity: the build graph for ~10 small Python apps doesn't justify the
  infrastructure

### Option B: Pants Build System

Pants was built Python-first and later expanded to other languages. It's the
"Bazel for Python developers" alternative.

**How it works:**

- Auto-generates BUILD files from Python imports (`pants tailor ::`)
- Dependency inference by reading import statements — no manual dependency declarations
- Native pytest, mypy, ruff, coverage, Docker integration
- Per-file caching — only re-runs changed tests

**Advantages:**

- Python-first design — concepts map to Python packaging
- Automatic dependency inference (killer feature)
- Better pytest integration than Bazel (supports conftest.py, plugins, batching)
- Docker backend with automatic PEX → image packaging
- Lower learning curve than Bazel (moderate vs. very high)

**Disadvantages:**

- **No Rust/pyO3 support** — no Rust backend, would need escape hatches
- Still adds a meaningful infrastructure layer for ~10 small packages
- Smaller community than Bazel (though Python-focused)
- Another tool to learn (besides Bazel for work) — splits learning investment
- `pants.toml` + BUILD files = parallel config system to pyproject.toml

### Option C: uv Workspaces + Taskfile (Extend Current Stack)

Build on what you already use. No new build system — just `uv` for dependency
management, `Taskfile.yml` for orchestration, and `hatchling` for packaging.

**How it works:**

```toml
# Root pyproject.toml
[tool.uv.workspace]
members = ["apps/*"]
```

Each app keeps its own `pyproject.toml`. One shared `uv.lock` at the root. Taskfile
namespacing provides per-app and cross-app task execution.

For Rust/pyO3 extensions: **maturin** (the standard Python tool for building Rust
extensions) integrates natively with pyproject.toml and uv.

**Advantages:**

- **Minimal overhead** — you already use uv, Taskfile, hatchling
- No new paradigm, no BUILD files, no Starlark
- pyproject.toml remains the single source of truth (PEP 621)
- maturin handles Rust/pyO3 natively as a build backend — mature, widely adopted
- pytest/mypy/ruff/coverage work exactly as they do today
- Release Please, pre-commit, Renovate — all work unchanged
- Coding agents already understand this stack

**Disadvantages:**

- No build caching (tests always re-run unless you add a caching layer)
- No hermetic builds (relies on uv lockfile fidelity, which is high but not Bazel-grade)
- No dependency inference (Python imports just work — this is "normal" Python)
- Orchestrating "run across all apps" requires Taskfile loops (vs. Bazel's `//...`)
- Less structured than Bazel — discipline comes from convention, not enforcement

### Option D: Bazel as Learning Sandbox + uv for Production

Use Bazel in a **dedicated learning branch or subdirectory** to build familiarity, while
keeping the production workflow on uv + Taskfile. Migrate to Bazel later if the scale
justifies it.

**Advantages:**

- Learning Bazel on your own codebase (realistic practice)
- Production stays simple and reliable
- No risk of Bazel complexity blocking actual app development
- Can incrementally Bazel-ify one app at a time

**Disadvantages:**

- Dual maintenance during the learning period
- Learning in isolation may miss integration challenges

### Recommendation

**Option C (uv Workspaces + Taskfile)** for production, with **Option D** if you want
Bazel learning on the side. The rationale:

1. **Scale doesn't justify Bazel/Pants**: ~10 small Python apps maintained by one
   developer. These build systems solve problems at 100+ developers / 1000+ packages.
2. **Learning Bazel ≠ using Bazel for everything**: Learning it on your work codebase (or
   a dedicated sandbox) is more effective than forcing it onto a project where it adds
   friction.
3. **Rust/pyO3**: maturin is the Python ecosystem's answer and integrates cleanly with
   uv + hatchling. Bazel's pyO3 wiring is manual and fragile.
4. **Build caching**: If this ever becomes a bottleneck (unlikely at your scale), you can
   add a thin caching layer (e.g., `pytest-cache`, GHA cache) without switching build
   systems.

**If Bazel learning is a priority**, consider adding a `bazel/` directory with
`MODULE.bazel` and BUILD files for one or two apps. This gives you real practice without
forcing the entire repo through Bazel's workflow.

---

## 5. Repository Structure

### Proposed Layout

```
cosalette-apps/
├── .github/
│   ├── copilot-instructions.md
│   ├── instructions/          # Agent instruction files (shared)
│   ├── skills/                # Agent skills (shared)
│   ├── workflows/
│   │   ├── ci-detect.yml      # Change detection (path-filter)
│   │   ├── ci-app.yml         # Reusable per-app CI workflow
│   │   ├── docs.yml           # Documentation deployment
│   │   ├── docker-app.yml     # Reusable per-app Docker build
│   │   └── release-please.yml # Manifest-mode releases
│   └── actions/               # Composite actions (if needed)
├── apps/
│   ├── gas2mqtt/
│   │   ├── pyproject.toml     # App-specific deps, metadata, license
│   │   ├── LICENSE            # MIT
│   │   ├── Dockerfile
│   │   ├── docker-compose.yml
│   │   ├── zensical.toml      # App docs config
│   │   ├── docs/              # App documentation
│   │   ├── packages/
│   │   │   ├── src/gas2mqtt/  # Source code
│   │   │   └── tests/         # App tests
│   │   └── README.md
│   ├── jeelink2mqtt/
│   │   └── ...                # Same structure
│   └── vito2mqtt/
│       ├── pyproject.toml     # license = "GPL-3.0-or-later"
│       ├── LICENSE            # GPL-3.0-or-later
│       └── ...
├── taskfiles/
│   └── PythonApp.yml          # Reusable Taskfile template
├── docs/
│   ├── index.md               # Root landing page
│   ├── adr/                   # Monorepo-level ADRs
│   ├── planning/              # Deliberation docs (like this one)
│   └── testing/
├── scripts/                   # Shared scripts
├── LICENSES/
│   ├── MIT.txt
│   └── GPL-3.0-or-later.txt
├── pyproject.toml             # Workspace root (uv workspace config)
├── uv.lock                    # Single shared lockfile
├── Taskfile.yml               # Root orchestrator (includes per-app tasks)
├── REUSE.toml                 # License declarations
├── .pre-commit-config.yaml    # Shared hooks
├── .beads/                    # Issue tracking
├── AGENTS.md
├── CLAUDE.md
├── LICENSE                    # MIT (root)
└── README.md
```

### Design Decisions

**Why `apps/` not `packages/`?**

The current monorepo skeleton uses `packages/` for the copier template's single-package
layout. Switching to `apps/` avoids confusion with the existing `packages/src/` and
`packages/tests/` convention inside each app. The name `apps/` also clearly communicates
that each directory is an independently deployable application, not a library.

**Why keep `packages/src/` and `packages/tests/` inside each app?**

This preserves the existing app structure, minimizing migration diff. Each app's internal
layout doesn't change — only its root path in the filesystem moves.

**Why Dockerfiles per app?**

Each app has different base image needs (Alpine vs. slim), different system dependencies
(I2C tools vs. serial vs. Bluetooth), and different build strategies (single-stage vs.
multi-stage). A shared Dockerfile template would be over-abstracted.

---

## 6. Dependency Management

### How uv Workspaces Handle Dependencies

**Root `pyproject.toml`:**

```toml
[project]
name = "cosalette-apps"
version = "0.1.0"
requires-python = ">=3.14"

[tool.uv.workspace]
members = ["apps/*"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Per-app `pyproject.toml` (e.g., `apps/gas2mqtt/pyproject.toml`):**

```toml
[project]
name = "gas2mqtt"
version = "0.1.0"
requires-python = ">=3.14"
license = "MIT"
dependencies = [
    "cosalette>=0.2.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.6.0",
    "smbus2>=0.6.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["packages/src/gas2mqtt"]
```

### Shared Lockfile

`uv lock` produces a single `uv.lock` at the workspace root. This resolves all
dependencies for all apps simultaneously, ensuring:

- Consistent versions of shared deps (pydantic, cosalette) across all apps
- No "works in gas2mqtt but breaks in vito2mqtt" scenarios from version skew
- `uv sync --package gas2mqtt` installs only gas2mqtt's deps from the shared lock

### Commands

| Operation                     | Command                                    |
| ----------------------------- | ------------------------------------------ |
| Install all deps              | `uv sync`                                  |
| Install one app's deps        | `uv sync --package gas2mqtt`               |
| Run command for one app       | `uv run --package gas2mqtt pytest`         |
| Add a dep to an app           | `cd apps/gas2mqtt && uv add smbus2`        |
| Lock all deps                 | `uv lock`                                  |

### Trade-offs

| Aspect                  | Shared Lockfile (uv workspace)   | Separate Lockfiles (per-app)     |
| ----------------------- | -------------------------------- | -------------------------------- |
| Consistency             | Guaranteed — one resolution      | Can drift                        |
| Isolation               | All deps in one `.venv`          | Per-app `.venv`                  |
| Lock/install speed      | One `uv lock`, one `.venv`       | N locks, N `.venv`s              |
| Accidental cross-deps   | Possible (app A imports app B's dep) | No risk                     |
| Cosalette version       | Unified across all apps          | Each app pins independently      |

**Mitigation for accidental cross-deps:** Mypy and import linting can catch this. Ruff's
`I` rules combined with `known-first-party` per-app will flag unexpected imports. This is
a convention-level concern, not a hard isolation need.

### Cosalette Version Unification

With a shared lockfile, all apps use the **same cosalette version**. This is actually a
significant advantage: framework upgrades become atomic, and you can test all apps against
the new version in one PR.

---

## 7. Testing

### Per-App Test Isolation

Each app keeps its own test suite in `apps/<name>/packages/tests/`. Tests run in the
app's context:

```bash
# Run gas2mqtt tests only
task gas2mqtt:test:unit

# Under the hood:
uv run --package gas2mqtt pytest apps/gas2mqtt/packages/tests/unit/ -v
```

### Shared Test Fixtures

The cosalette framework already provides test utilities via `cosalette.testing`:
`MockMqttClient`, `FakeClock`, `NullMqttClient`, `make_settings()`, `AppHarness`.

If apps need **additional** shared fixtures (e.g., common assertions, test data
generators), these should go into cosalette itself if they're broadly applicable, or into
a `shared/testing/` directory in the monorepo for monorepo-specific helpers.

### Coverage

Per-app coverage thresholds are already different (80% vs. 90%). In the monorepo:

```toml
# apps/gas2mqtt/pyproject.toml
[tool.coverage.run]
source = ["packages/src/gas2mqtt"]

[tool.coverage.report]
fail_under = 80
```

Each app's `pyproject.toml` continues to own its coverage config. The Taskfile runs
coverage per-app.

### Test Discovery with Bazel vs. pytest

If you explore Bazel on the side, note that Bazel's `py_test` creates **isolated
processes per test file**. This means:

- `conftest.py` fixtures work only if they're in the same package
- Session-scoped fixtures don't share state across test files
- Cosalette's `pytest_plugins` registration needs to be in each test file's scope

With uv + pytest (the production path), none of this is a concern — pytest runs naturally
with full fixture scoping.

---

## 8. CI/CD

### Architecture: Path-Filtered Reusable Workflows

The CI strategy has three layers:

1. **Change detection** — determines which apps changed
2. **Per-app CI** — reusable workflow called for each affected app
3. **Docker build** — triggered on releases/tags for affected apps

### Layer 1: Change Detection

```yaml
# .github/workflows/ci-detect.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.filter.outputs.changes }}
      gas2mqtt: ${{ steps.filter.outputs.gas2mqtt }}
      vito2mqtt: ${{ steps.filter.outputs.vito2mqtt }}
      shared: ${{ steps.filter.outputs.shared }}
    steps:
      - uses: actions/checkout@v6
      - uses: dorny/paths-filter@v4
        id: filter
        with:
          filters: |
            gas2mqtt:
              - 'apps/gas2mqtt/**'
            vito2mqtt:
              - 'apps/vito2mqtt/**'
            jeelink2mqtt:
              - 'apps/jeelink2mqtt/**'
            shared:
              - 'pyproject.toml'
              - 'uv.lock'
              - '.github/**'
              - 'taskfiles/**'
              - '.pre-commit-config.yaml'
```

### Layer 2: Per-App CI (Reusable Workflow)

```yaml
# .github/workflows/ci-app.yml
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
      - run: task ${{ inputs.app }}:lint

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - run: task ${{ inputs.app }}:test:unit

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - run: task ${{ inputs.app }}:typecheck
```

### Shared Changes Trigger All Apps

When shared infrastructure changes (root configs, CI workflows, Taskfile templates),
**all** apps get their CI run:

```yaml
ci-all:
  needs: detect
  if: needs.detect.outputs.shared == 'true'
  strategy:
    matrix:
      app: [gas2mqtt, vito2mqtt, jeelink2mqtt]
  uses: ./.github/workflows/ci-app.yml
  with:
    app: ${{ matrix.app }}
```

### Budget Impact (GitHub Actions Free Tier)

| Scenario                  | Minutes per PR | PRs/month (est.) | Total minutes |
| ------------------------- | -------------- | ----------------- | ------------- |
| **With path filtering**   | ~10-15         | ~30               | ~300-450      |
| **Without path filtering**| ~100-150       | ~30               | ~3000-4500    |
| **Free tier budget**      |                |                   | **2,000**     |

Path filtering keeps you well within the free tier. Without it, you'd exceed the budget
immediately.

### Docker Build Optimization

Per-app Docker builds use scoped GHA cache:

```yaml
- uses: docker/build-push-action@v6
  with:
    context: apps/${{ inputs.app }}
    cache-from: type=gha,scope=${{ inputs.app }}
    cache-to: type=gha,mode=max,scope=${{ inputs.app }}
```

**Gotcha:** GHA cache has a **10 GB limit per repo**. With 10 apps building Docker
images, monitor cache usage. If limits are hit, switch to registry-based caching
(`type=registry`).

---

## 9. Taskfile

### Architecture: Root Orchestrator + Reusable Template

The key insight: your three repos have ~90% identical Taskfiles. In the monorepo, this
becomes **one template included multiple times**.

### Reusable Template

```yaml
# taskfiles/PythonApp.yml
version: '3'

vars:
  APP_NAME: '{{.APP_NAME}}'
  MODULE_NAME: '{{.MODULE_NAME | default .APP_NAME}}'
  PKG: packages

tasks:
  test:unit:
    desc: 'Run unit tests for {{.APP_NAME}}'
    cmds:
      - uv run --package {{.APP_NAME}} pytest {{.PKG}}/tests/unit/ -v

  test:cov:
    desc: 'Run tests with coverage for {{.APP_NAME}}'
    cmds:
      - uv run --package {{.APP_NAME}} pytest {{.PKG}}/tests/ --cov={{.PKG}}/src/{{.MODULE_NAME}} --cov-report=term-missing

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

  docs:serve:
    desc: 'Preview docs for {{.APP_NAME}}'
    cmds:
      - uv run zensical serve

  docs:build:
    desc: 'Build docs for {{.APP_NAME}}'
    cmds:
      - uv run zensical build
```

### Root Taskfile

```yaml
# Taskfile.yml (root)
version: '3'

vars:
  APPS: [gas2mqtt, jeelink2mqtt, vito2mqtt]

includes:
  gas2mqtt:
    taskfile: ./taskfiles/PythonApp.yml
    dir: ./apps/gas2mqtt
    vars:
      APP_NAME: gas2mqtt
  jeelink2mqtt:
    taskfile: ./taskfiles/PythonApp.yml
    dir: ./apps/jeelink2mqtt
    vars:
      APP_NAME: jeelink2mqtt
  vito2mqtt:
    taskfile: ./taskfiles/PythonApp.yml
    dir: ./apps/vito2mqtt
    vars:
      APP_NAME: vito2mqtt

tasks:
  test:all:
    desc: 'Run tests for all apps'
    cmds:
      - for: { var: APPS }
        task: '{{.ITEM}}:test:unit'

  lint:all:
    desc: 'Lint all apps'
    cmds:
      - for: { var: APPS }
        task: '{{.ITEM}}:lint'

  typecheck:all:
    desc: 'Type check all apps'
    cmds:
      - for: { var: APPS }
        task: '{{.ITEM}}:typecheck'

  pre-pr:
    desc: 'Run all quality gates'
    cmds:
      - task: lint:all
      - task: typecheck:all
      - task: test:all
```

### Per-App Task Overrides

If an app needs tasks beyond the template (e.g., `complexity`, `similarity`), it can have
its own `Taskfile.yml` in `apps/<name>/` that includes the template and adds extras:

```yaml
# apps/gas2mqtt/Taskfile.yml (optional override)
version: '3'
includes:
  _base:
    taskfile: ../../taskfiles/PythonApp.yml
    vars:
      APP_NAME: gas2mqtt

tasks:
  complexity:
    desc: 'Run complexity analysis'
    cmds:
      - uv run radon cc packages/src/ -a -nc
```

The root Taskfile then includes the app's own Taskfile instead of the template directly.

### Invocation Examples

```bash
task gas2mqtt:test:unit      # One app's tests
task gas2mqtt:lint            # One app's lint
task test:all                 # All apps' tests
task pre-pr                   # Full quality gate
task vito2mqtt:docs:serve     # Preview one app's docs
```

---

## 10. Environment & Tooling

### Linter & Formatter Configuration

**Shared (root `pyproject.toml`):**

```toml
[tool.ruff]
target-version = "py314"
line-length = 88

[tool.ruff.lint]
select = ["E", "W", "F", "B", "I", "C4", "UP", "SIM", "ARG"]

[tool.ruff.lint.per-file-ignores]
"**/tests/**" = ["ARG", "F841"]
"**/adapters/protocol.py" = ["ARG001"]
"**/__init__.py" = ["F401", "E402"]
```

**Per-app (app `pyproject.toml`):**

```toml
[tool.ruff.lint.isort]
known-first-party = ["gas2mqtt"]
```

Ruff reads config from the closest `pyproject.toml`, so per-app overrides
work naturally when running ruff from the app directory.

### mypy Configuration

**Shared (root):**

```toml
[tool.mypy]
python_version = "3.14"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
```

**Per-app overrides (app `pyproject.toml`):**

```toml
[[tool.mypy.overrides]]
module = "gas2mqtt._version"
ignore_missing_imports = true
```

When mypy runs per-app via Taskfile (which sets `dir` to the app directory), it picks up
the app-level config.

### Pre-commit Hooks

One `.pre-commit-config.yaml` at the root. Hooks run on **staged files only** — natural
per-change scoping, no performance concern at 10 apps.

**Special cases:**

```yaml
# REUSE compliance (handles license annotations for all apps)
- repo: https://github.com/fsfe/reuse-tool
  hooks:
    - id: reuse

# Ruff (runs on changed Python files, picks up closest pyproject.toml)
- repo: https://github.com/astral-sh/ruff-pre-commit
  hooks:
    - id: ruff
    - id: ruff-format
```

mypy in pre-commit is trickier — it needs per-app context. Two options:

1. **Per-app mypy hooks** (verbose but explicit): one hook per app with `files:` filter
2. **Skip mypy in pre-commit, run via Taskfile only** (simpler): add mypy to `task
   pre-pr` but not pre-commit. This is pragmatic given mypy's slowness.

### Editor Settings

One `.vscode/settings.json` (or `.editorconfig`) at the root. pyright/pylance config via
the root `pyrightconfig.json` with `extraPaths` pointing to all apps:

```json
{
  "extraPaths": ["apps/gas2mqtt/packages/src", "apps/vito2mqtt/packages/src"],
  "venvPath": ".",
  "venv": ".venv",
  "pythonVersion": "3.14"
}
```

### Virtual Environments

uv workspaces use a **single shared `.venv`** at the root. All app dependencies are
installed together. This is simpler than per-app venvs and matches the shared lockfile
model.

### Beads Issue Tracking

**Single `.beads/`** at the repo root with naming conventions for per-app scoping:

```bash
bd create "gas2mqtt: Add calibration mode" --type task --priority 2
bd create "vito2mqtt: Fix optolink timeout" --type task --priority 1
```

Use title prefixes (`gas2mqtt:`, `vito2mqtt:`) and epics per-app for grouping. One
`bd ready` gives visibility across all apps — valuable for a solo developer.

---

## 11. Documentation

### Goal

`ff-fab.github.io/cosalette-apps/` with a root landing page and per-app subpath docs:

```
ff-fab.github.io/cosalette-apps/           → Landing page (app directory, links)
ff-fab.github.io/cosalette-apps/gas2mqtt/   → gas2mqtt docs (full Zensical site)
ff-fab.github.io/cosalette-apps/vito2mqtt/  → vito2mqtt docs (full Zensical site)
```

### Architecture

Each app keeps its own `zensical.toml` with updated `site_url`:

```toml
# apps/gas2mqtt/zensical.toml
[project]
site_name = "gas2mqtt"
site_url = "https://ff-fab.github.io/cosalette-apps/gas2mqtt/"
```

The root gets a minimal docs site (single-page or a few pages) linking to all apps.

### Deployment Workflow

GitHub Pages supports one source per repo. Use `peaceiris/actions-gh-pages` with
`destination_dir` to deploy each app's docs to a subpath:

```yaml
# .github/workflows/docs.yml
jobs:
  detect:
    # dorny/paths-filter for apps/<name>/docs/** changes

  deploy-root:
    steps:
      - run: task docs:build  # builds root site
      - uses: peaceiris/actions-gh-pages@v4
        with:
          publish_dir: ./site
          keep_files: true  # Don't delete other apps' docs

  deploy-gas2mqtt:
    needs: detect
    if: needs.detect.outputs.gas2mqtt-docs == 'true'
    steps:
      - run: task gas2mqtt:docs:build
      - uses: peaceiris/actions-gh-pages@v4
        with:
          publish_dir: ./apps/gas2mqtt/site
          destination_dir: gas2mqtt
          keep_files: true
```

The `keep_files: true` flag is critical — it prevents each app's deploy from deleting
other apps' files on the `gh-pages` branch.

### Consistency Benefits

Having all docs in one repo means coding agents can reference other apps' documentation
structure when writing docs for a new app. The Zensical config and doc structure naturally
converge when they're in the same codebase.

---

## 12. Deployment

### Docker Images Per App

Each app has its own Dockerfile in `apps/<name>/Dockerfile`. The Docker build context is
the app directory:

```bash
docker build -t gas2mqtt:latest apps/gas2mqtt/
```

### Multi-Architecture Builds

Continue using `docker buildx` with QEMU for arm64 (Raspberry Pi). Per-app builds with
registry push:

```yaml
- uses: docker/build-push-action@v6
  with:
    context: apps/${{ inputs.app }}
    platforms: linux/amd64,linux/arm64
    push: true
    tags: ghcr.io/ff-fab/${{ inputs.app }}:${{ inputs.version }}
```

### Ansible Integration

Ansible playbooks reference per-app Docker images by name. The monorepo doesn't change
deployment topology — each app still produces an independent Docker image tagged with its
own version.

### docker-compose Per App

Each app keeps its own `docker-compose.yml` for local development. Ansible's Jinja2
templates generate production compose files per host (1-5 apps per Pi).

### What Doesn't Change

The deployment model is **unchanged** by the monorepo migration:

- Same Docker images (just built from a different repo)
- Same docker-compose patterns
- Same Ansible playbook targets
- Same multi-Pi distribution

The monorepo affects how images are **built and released**, not how they're **deployed**.

---

## 13. Release Management

### Release Please Manifest Mode

Release Please's manifest mode is designed exactly for monorepos with independent
per-package versioning.

**`release-please-config.json`:**

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "release-type": "simple",
  "bump-minor-pre-major": true,
  "bump-patch-for-minor-pre-major": true,
  "separate-pull-requests": true,
  "packages": {
    "apps/gas2mqtt": {
      "component": "gas2mqtt",
      "package-name": "gas2mqtt",
      "extra-files": [
        { "type": "generic", "path": "pyproject.toml" }
      ]
    },
    "apps/vito2mqtt": {
      "component": "vito2mqtt",
      "package-name": "vito2mqtt",
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
  "apps/gas2mqtt": "0.1.0",
  "apps/vito2mqtt": "0.1.0",
  "apps/jeelink2mqtt": "0.1.0"
}
```

### Behavior

| Aspect                | Behavior                                               |
| --------------------- | ------------------------------------------------------ |
| **Version tracking**  | Independent per-app in manifest JSON                   |
| **Changelogs**        | Per-app: `apps/gas2mqtt/CHANGELOG.md`                  |
| **Git tags**          | Component-prefixed: `gas2mqtt-v0.2.0`                  |
| **Release PRs**       | Separate per-app (with `separate-pull-requests: true`) |
| **Commit detection**  | Path-based: commits touching `apps/gas2mqtt/**` bump   |
| **Conventional scope**| `feat(gas2mqtt):` as supplementary signal              |

### Integration with Docker Releases

When Release Please creates a tag (e.g., `gas2mqtt-v0.2.0`), a workflow triggers the
Docker build for that specific app:

```yaml
on:
  push:
    tags:
      - '*-v*'  # Matches gas2mqtt-v0.2.0, vito2mqtt-v1.0.0, etc.
```

### Known Limitations

- **Commit search depth:** Default 500 commits. Set `"commit-search-depth": 1000` for
  active repos.
- **No Python workspace plugin:** Unlike npm/Cargo, Release Please can't auto-bump
  cross-dependencies between Python packages (but you don't have cross-deps by design).

---

## 14. Migration Strategy

### Tool: `git filter-repo`

`git filter-repo` (recommended by the Git project since git 2.22+, 11.9k stars) rewrites
history to move files into a subdirectory while preserving all commits, authorship, dates,
and messages.

### Per-Repo Migration Process

```bash
# 1. Fresh clone of the source repo (filter-repo requires a fresh clone)
git clone https://github.com/ff-fab/gas2mqtt gas2mqtt-migration
cd gas2mqtt-migration

# 2. Rewrite all paths to live under apps/gas2mqtt/
git filter-repo --to-subdirectory-filter apps/gas2mqtt

# 3. Back in the monorepo
cd /path/to/cosalette-apps
git remote add gas2mqtt-import ../gas2mqtt-migration
git fetch gas2mqtt-import --no-tags
git merge gas2mqtt-import/main --allow-unrelated-histories \
    -m "feat: merge gas2mqtt history into monorepo"
git remote remove gas2mqtt-import

# 4. Post-merge: adapt configs for monorepo layout
#    - Update pyproject.toml for uv workspace membership
#    - Update zensical.toml site_url
#    - Remove standalone CI workflows (replaced by mono CI)
#    - Remove standalone Taskfile (replaced by template include)
```

### History Preservation Results

| Operation          | Result                                                     |
| ------------------ | ---------------------------------------------------------- |
| `git blame`        | Works perfectly — each line shows original author/date     |
| `git log --follow` | Works within the app's history; stops at the merge commit  |
| `git log -- apps/gas2mqtt/` | Shows full commit history for that app            |
| Commit SHAs        | All change (filter-repo rewrites them)                     |
| Commit messages    | Preserved exactly                                          |
| PR/issue references| Old `#123` references point to the source repo, not here   |

### Incremental Migration Sequence

Recommended order (simplest → most complex):

1. **gas2mqtt** — simplest app, MIT, fewest ADRs. Proof-of-concept migration.
2. **jeelink2mqtt** — MIT, medium complexity. Validates the pattern.
3. **vito2mqtt** — GPL, most complex, most ADRs. Tests license handling.
4. **Remaining planned apps** — created directly in the monorepo (no migration needed).

### Post-Migration Cleanup

For each migrated repo:

1. **Archive the source repo** on GitHub (read-only, preserves PRs/issues)
2. **Update the source repo's README** with a pointer to the monorepo
3. **Remove the `docs/tmp/` copies** from the monorepo (they were only for analysis)
4. **Consolidate configs**: remove per-app CI workflows, Renovate configs, etc. that are
   now handled at the monorepo level

### Rollback Plan

If the migration doesn't work out for a specific app:

```bash
# Extract an app back out with full history
cd cosalette-apps
git filter-repo --subdirectory-filter apps/gas2mqtt --force
# This creates a repo with only gas2mqtt's files at the root
```

This is non-destructive to the monorepo (run it on a fresh clone).

---

# Part III — Synthesis

## 15. Decision Matrix

Scoring each approach against your stated priorities (1 = poor, 5 = excellent):

| Priority              | Full Monorepo (uv + Taskfile) | Polyrepo (enhanced template) | Hybrid (MIT mono + GPL poly) | Monorepo (Bazel) |
| --------------------- | ----------------------------- | ---------------------------- | ---------------------------- | ----------------- |
| Atomic cross-app changes | **5**                      | 1                            | 4                            | 5                 |
| Template friction eliminated | **5**                 | 2                            | 4                            | 5                 |
| Agent context unity   | **5**                         | 1                            | 4                            | 5                 |
| CI cost (free tier)   | **4** (path filtering)        | 5 (per-repo)                 | 4                            | 3 (complex setup) |
| Learning value        | 3 (uv workspaces, Taskfile)   | 1                            | 3                            | **5** (Bazel)     |
| Setup effort          | **4** (low)                   | 5 (none)                     | 3                            | 1 (very high)     |
| Maintainability       | **5**                         | 2                            | 3                            | 2                 |
| Licensing clarity     | 4 (REUSE handles it)          | 5 (per-repo)                 | **5**                        | 4                 |
| Rust/pyO3 readiness   | **4** (maturin)               | 4                            | 4                            | 3 (manual wiring) |
| **Total**             | **39**                        | 22                           | 34                           | 33                |

## 16. Recommended Approach

### Primary: Full Monorepo with uv Workspaces + Taskfile

Based on the analysis, the recommended approach is:

**Build system:** uv workspaces + Taskfile namespacing (not Bazel or Pants)

- Builds on your existing stack — no new paradigm
- pyproject.toml stays the single source of truth
- Shared lockfile ensures consistent dependencies
- Taskfile template eliminates per-app boilerplate

**Licensing:** REUSE specification with per-directory LICENSE files

- MIT root + per-app LICENSE files
- REUSE.toml for machine-readable compliance
- `reuse lint` as CI check

**CI/CD:** Path-filtered reusable workflows on GitHub Actions

- `dorny/paths-filter` for change detection
- One reusable workflow template called per-app
- Shared changes trigger all apps
- Well within free-tier budget

**Documentation:** Per-app Zensical sites on subpaths

- `ff-fab.github.io/cosalette-apps/<app>/`
- Root landing page
- Per-app `zensical.toml` with independent nav structure

**Release management:** Release Please manifest mode

- Independent per-app versioning and changelogs
- Separate release PRs per app
- Component-prefixed tags (`gas2mqtt-v0.2.0`)

**Migration:** Incremental via `git filter-repo`

- One app at a time, starting with gas2mqtt
- Full `git blame` preservation
- Archive source repos after migration

### Phased Adoption Roadmap

| Phase | What                                           | Validates                           |
| ----- | ---------------------------------------------- | ----------------------------------- |
| 1     | Set up monorepo skeleton (workspace, Taskfile, CI) | uv workspaces, Taskfile includes |
| 2     | Migrate gas2mqtt (simplest, MIT)               | filter-repo, per-app CI, docs       |
| 3     | Migrate jeelink2mqtt                           | Multi-app coexistence               |
| 4     | Migrate vito2mqtt (GPL)                        | REUSE licensing, GPL compliance     |
| 5     | Create a new app directly in monorepo          | New-app workflow                    |
| 6     | Clean up (archive old repos, remove docs/tmp)  | Complete migration                  |

---

## 17. Open Questions & Risks

### Remaining Open Questions (Resolved During Implementation)

1. **Zensical multi-site capability**: Does Zensical support deploying to subpaths
   cleanly? Specifically, do relative links and asset paths work when the site lives at
   `/cosalette-apps/gas2mqtt/` instead of `/gas2mqtt/`? This needs hands-on testing in
   Phase 2.

2. **Beads monorepo patterns**: The current beads tooling was designed for single repos.
   Title-prefix conventions work but are manual. If beads adds label/tag support, that
   would be a better fit. Worth checking `bd prime` for any monorepo-aware features.

3. **Devcontainer**: The existing repos use devcontainer-based CI. Does the monorepo
   devcontainer need different configuration (multiple Python packages, workspace-aware
   tooling)?

4. **Renovate**: A single `renovate.json` at the root may need per-app package rules.
   Currently all repos share identical Renovate config, so this is likely straightforward.

### Risks

| Risk                            | Likelihood | Impact | Mitigation                          |
| ------------------------------- | ---------- | ------ | ----------------------------------- |
| GHA 10 GB cache limit           | Medium     | Low    | Switch to registry caching          |
| Accidental cross-app imports    | Low        | Low    | Ruff isort + mypy strict mode       |
| Zensical subpath deploy issues  | Medium     | Medium | Test in Phase 2 before full commit  |
| Beads friction with prefix conventions | Low  | Low    | Epics per app provide grouping      |
| uv workspace breaking changes   | Low        | Medium | Pin uv version, test before upgrade |
| CI matrix complexity grows      | Low        | Low    | Convention: add new app to filter   |

### What Not to Do

- **Don't add Bazel to the production build path** until scale justifies it
- **Don't create shared code between apps** — that belongs in cosalette
- **Don't merge all release PRs together** — keep them per-app for clear blast radius
- **Don't consolidate Dockerfiles into a template** — each app's hardware needs are
  genuinely different
