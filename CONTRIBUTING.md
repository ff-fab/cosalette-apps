# Contributing to cosalette-apps

Thank you for your interest in contributing to cosalette-apps! This guide covers
everything you need to get a development environment running and start making changes.

## Prerequisites

- Python >= 3.14
- Docker (for DevContainer development)
- VS Code with DevContainers extension

## Setup (2 minutes)

```bash
# Clone the repository
git clone https://github.com/ff-fab/cosalette-apps.git
cd cosalette-apps

# Open in VS Code
code .

# In VS Code: Ctrl+Shift+P -> "Dev Containers: Reopen in Container"
# DevContainer will start automatically, install dependencies, and configure everything
```

That's it! You're ready to develop.

## Common Commands

**Quick reference (via [Taskfile](https://taskfile.dev)):**

```bash
# Per-app tasks (replace <app> with gas2mqtt, jeelink2mqtt, etc.)
task <app>:test           # Run all tests for one app (unit + coverage)
task <app>:test:unit      # Run unit tests only
task <app>:lint           # Lint one app (Ruff check + format)
task <app>:lint:fix       # Auto-fix lint issues
task <app>:typecheck      # Type check one app (mypy strict)
task <app>:check          # Run all checks for one app
task <app>:docs:serve     # Serve app documentation site locally

# Cross-app tasks
task test:all             # Run tests for all apps
task lint:all             # Lint all apps
task check:all            # Run all checks for all apps
task pre-pr               # Full pre-PR quality gate

# Root documentation
task docs:serve           # Serve root documentation site locally

task --list               # Show all available tasks
```

## Project Structure

```
cosalette-apps/
├── .devcontainer/              # DevContainer configuration
│   ├── devcontainer.json       # Container setup + VS Code settings
│   ├── Dockerfile              # Container image
│   └── post-create.sh          # Auto-setup script
├── apps/                       # Application workspaces
│   ├── gas2mqtt/               # Gas meter → MQTT bridge
│   │   ├── packages/
│   │   │   ├── src/gas2mqtt/   # Source code
│   │   │   └── tests/          # Unit & integration tests
│   │   ├── docs/               # App documentation (Zensical)
│   │   │   └── adr/            # App-specific ADRs
│   │   ├── pyproject.toml      # App package config
│   │   └── zensical.toml       # App docs site config
│   └── jeelink2mqtt/           # JeeLink sensor → MQTT bridge
│       ├── packages/
│       │   ├── src/jeelink2mqtt/
│       │   └── tests/
│       ├── docs/
│       │   └── adr/
│       ├── pyproject.toml
│       └── zensical.toml
├── docs/                       # Root documentation (Zensical)
│   └── adr/                    # Monorepo-wide ADRs
├── taskfiles/                  # Reusable Taskfile templates
│   └── PythonApp.yml           # Per-app task definitions
├── pyproject.toml              # Root workspace config (uv)
├── Taskfile.yml                # Root task orchestrator
└── zensical.toml               # Root docs site config
```

## Code Quality

- **Linting & formatting**: [Ruff](https://docs.astral.sh/ruff/) (88-char line length,
  double quotes)
- **Type checking**: [mypy](https://mypy-lang.org/) (strict mode)
- **Testing**: [pytest](https://docs.pytest.org/) with pytest-asyncio
- **Coverage**: >= 80% threshold (lines and branches)
- **Pre-commit**: EditorConfig, trailing whitespace, codespell, Ruff, mypy

All tools are **auto-configured in DevContainer** via `.devcontainer/devcontainer.json`.
Format on save is enabled by default.

## Workflow

This project follows **GitHub Flow**:

1. Create a feature branch from `main`
2. Make changes with [conventional commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `chore:`, etc.). Scope by app: `feat(gas2mqtt): ...`
3. Run `task pre-pr` to pass all quality gates
4. Open a pull request -- never push directly to `main`

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
