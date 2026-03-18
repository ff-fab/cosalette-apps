# Contributing to cosalette-apps

Thank you for your interest in contributing to cosalette-apps! This guide covers
everything you need to get a development environment running and start making changes.

## Prerequisites

- Python ≥ 3.14
- Docker (for DevContainer development)
- VS Code with DevContainers extension

## Setup (2 minutes)

```bash
# Clone the repository
git clone https://github.com/ff-fab/cosalette-apps.git
cd cosalette-apps

# Open in VS Code
code .

# In VS Code: Ctrl+Shift+P → "Dev Containers: Reopen in Container"
# DevContainer will start automatically, install dependencies, and configure everything
```

That's it! You're ready to develop.

## Common Commands

**Quick reference (via [Taskfile](https://taskfile.dev)):**

```bash
task test              # Run all tests (unit + integration + coverage)
task test:unit         # Run unit tests only
task lint              # Lint all code (Ruff check + format)
task lint:fix          # Auto-fix lint issues
task typecheck         # Type check (mypy strict)
task check             # Run all checks (lint + typecheck + test)
task pre-pr            # Full pre-PR quality gate
task docs:serve        # Serve documentation site locally
task --list            # Show all available tasks
```

## Project Structure

```
cosalette-apps/
├── .devcontainer/              # DevContainer configuration
│   ├── devcontainer.json       # Container setup + VS Code settings
│   ├── Dockerfile              # Container image
│   └── post-create.sh          # Auto-setup script
├── packages/
│   ├── src/cosalette-apps/  # Source code
│   ├── tests/                  # Unit & integration tests
│   └── pyproject.toml          # Python project configuration
├── docs/                       # Documentation (Zensical)
│   ├── adr/                    # Architecture Decision Records (scaffolded)
│   ├── getting-started/        # TODO: add quickstart content
│   ├── concepts/               # TODO: add architecture explanations
│   ├── guides/                 # TODO: add how-to guides
│   └── reference/              # TODO: add API reference
├── renovate.json               # Automated dependency updates
└── zensical.toml               # Documentation site config
```

## Code Quality

- **Linting & formatting**: [Ruff](https://docs.astral.sh/ruff/) (88-char line length,
  double quotes)
- **Type checking**: [mypy](https://mypy-lang.org/) (strict mode)
- **Testing**: [pytest](https://docs.pytest.org/) with pytest-asyncio
- **Coverage**: ≥80% threshold (lines and branches)
- **Pre-commit**: EditorConfig, trailing whitespace, codespell, Ruff, mypy

All tools are **auto-configured in DevContainer** via `.devcontainer/devcontainer.json`.
Format on save is enabled by default.

## Workflow

This project follows **GitHub Flow**:

1. Create a feature branch from `main`
2. Make changes with [conventional commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `chore:`, etc.)
3. Run `task pre-pr` to pass all quality gates
4. Open a pull request — never push directly to `main`

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
