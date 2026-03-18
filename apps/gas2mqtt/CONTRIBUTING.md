# Contributing to gas2mqtt

## Quick Start

### Prerequisites

- Docker and Docker Compose (for DevContainer)
- VS Code with DevContainers extension

### Setup (2 minutes)

```bash
# Clone the repository
git clone https://github.com/ff-fab/gas2mqtt.git
cd gas2mqtt

# Open in VS Code
code .

# In VS Code: Ctrl+Shift+P → "Dev Containers: Reopen in Container"
# DevContainer will start automatically, install dependencies, and configure everything
```

That's it! You're ready to develop.

### Optional Local Authentication

You can provide two local variables during setup to authenticate against their
respective services:

- `GH_TOKEN` for GitHub
- `CONTEXT7_API_KEY` for Context7

## Common Commands

**Quick reference (via [Taskfile](https://taskfile.dev)):**

```bash
task test              # Run all tests
task lint              # Lint all code
task lint:fix          # Auto-fix lint issues
task check             # Run all checks (lint + typecheck + test)
task docs:build        # Build documentation site
task docs:serve        # Serve documentation site locally
task plan              # Show project phase progress
task plan:ui           # Interactive project progress view
task --list            # Show all available tasks
```

## Project Structure

```
gas2mqtt/
├── .devcontainer/              # DevContainer configuration
│   ├── devcontainer.json       # Container setup + VS Code settings
│   ├── Dockerfile              # Container image
│   ├── post-create.sh          # Auto-setup script
├── packages/
│   ├── src/gas2mqtt/           # Source code
│   │   ├── main.py             # App factory, lifespan, device wiring
│   │   ├── settings.py         # Pydantic settings (extends cosalette.Settings)
│   │   ├── ports.py            # MagnetometerPort protocol
│   │   ├── adapters/           # Hardware adapters
│   │   │   ├── qmc5883l.py     # Production I2C adapter (smbus2)
│   │   │   └── fake.py         # Test double + dry-run adapter
│   │   ├── devices/            # cosalette device handlers
│   │   │   ├── gas_counter.py  # Schmitt trigger tick detection
│   │   │   ├── temperature.py  # EWMA-filtered temperature
│   │   │   └── magnetometer.py # Optional raw debug output
│   │   └── domain/             # Pure business logic (no I/O)
│   │       ├── schmitt.py      # Schmitt trigger
│   │       ├── ewma.py         # Exponential weighted moving average
│   │       └── consumption.py  # Gas consumption tracker
│   └── tests/                  # All tests (94 unit + 7 integration)
│       ├── unit/               # Fast, isolated tests
│       ├── integration/        # App wiring tests
│       └── fixtures/           # Shared test fixtures
├── docs/                       # Documentation
│   ├── adr/                    # Architecture Decision Records
│   └── planning/               # Planning docs and future opportunities
├── Dockerfile                  # Production container image
├── docker-compose.yml          # Docker Compose stack (app + Mosquitto)
├── .env.example                # Configuration template
├── VERSIONING.md               # Version management documentation
├── zensical.toml               # Documentation site config
```

## Code Quality

### Formatting

- **Python**: Ruff (88-char line length, double quotes)
- **All files**: LF line endings (enforced via `.gitattributes`)

### Linting

- **Python**: Ruff (comprehensive rule set)

### Type Checking

- **Python**: mypy (strict mode)

All tools are **auto-configured in DevContainer** via `.devcontainer/devcontainer.json`.
Format on save is enabled by default.

## Versioning

Versions are automatically derived from git tags using `setuptools_scm`:

```bash
# Current version (from git tag or dev counter)
python -c "from gas2mqtt import __version__; print(__version__)"

# Tag a release
git tag v0.1.0
```

See [VERSIONING.md](VERSIONING.md) for details.
