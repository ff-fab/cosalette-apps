#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Fabian Koerner <mail@fabiankoerner.com>
# SPDX-License-Identifier: MIT
#
# Scaffold a new cosalette app in apps/<name>/.
set -euo pipefail

# ── Helpers ──────────────────────────────────────────────────
die()   { echo "error: $*" >&2; exit 1; }
usage() {
  cat <<'EOF'
Usage: scaffold-app.sh <name> <description> [--license MIT|GPL-3.0-or-later]

  name         Lowercase alphanumeric + hyphens (e.g. airthings2mqtt)
  description  One-line project description
  --license    MIT (default) or GPL-3.0-or-later
EOF
  exit 1
}

# ── Args ─────────────────────────────────────────────────────
[[ $# -lt 2 || "$1" == "--help" || "$1" == "-h" ]] && usage

NAME="$1"; DESC="$2"; shift 2
LICENSE="MIT"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --license) LICENSE="${2:?--license requires a value}"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done

# ── Validation ───────────────────────────────────────────────
[[ -f pyproject.toml ]] || die "run from repo root (pyproject.toml not found)"
[[ "$NAME" =~ ^[a-z][a-z0-9-]*$ ]] || die "name must be lowercase alphanumeric + hyphens"
[[ "$DESC" =~ [\"\\\`] ]] && die "description must not contain quotes, backslashes, or backticks"
[[ "$DESC" == *'$('* ]] && die "description must not contain command substitutions"
[[ "$LICENSE" == "MIT" || "$LICENSE" == "GPL-3.0-or-later" ]] || die "license must be MIT or GPL-3.0-or-later"
[[ -d "apps/$NAME" ]] && die "apps/$NAME already exists"

# Prerequisites
for cmd in jq sed grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "$cmd is required but not found"
done

APP="apps/$NAME"
PKG_NAME="${NAME//-/_}"   # Python package name (hyphens → underscores)

echo "Scaffolding $NAME ($LICENSE) …"

# ── Directory structure ──────────────────────────────────────
mkdir -p \
  "$APP/packages/src/$PKG_NAME" \
  "$APP/packages/tests/unit" \
  "$APP/packages/tests/integration" \
  "$APP/packages/tests/fixtures" \
  "$APP/packages/tests/scripts" \
  "$APP/docs/adr" \
  "$APP/docs/testing"

# ── Source files ─────────────────────────────────────────────
cat > "$APP/packages/src/$PKG_NAME/__init__.py" <<EOF
"""$NAME — $DESC."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("$NAME")
except PackageNotFoundError:  # pragma: no cover
    # Fallback for editable installs without metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
EOF

touch "$APP/packages/src/$PKG_NAME/py.typed"

cat > "$APP/packages/src/$PKG_NAME/main.py" <<EOF
"""Entry point for $NAME."""

from __future__ import annotations


def main() -> None:
    """Start the application."""
    raise SystemExit("Not yet implemented. See docs/index.md for next steps.")
EOF

# ── Test files ───────────────────────────────────────────────
touch "$APP/packages/tests/__init__.py"
touch "$APP/packages/tests/conftest.py"
touch "$APP/packages/tests/unit/__init__.py"
touch "$APP/packages/tests/unit/conftest.py"
touch "$APP/packages/tests/integration/__init__.py"

cat > "$APP/packages/tests/unit/test_placeholder.py" <<EOF
"""Placeholder test to validate CI pipeline.

This test imports the application package so coverage is non-zero.
Replace it with real tests as the project evolves.

Test Techniques Used:
- Smoke Testing: Verifies the $NAME package can be imported without errors.
"""

import importlib


def test_package_imports() -> None:
    """Ensure the scaffolded package can be imported."""
    mod = importlib.import_module("$PKG_NAME")
    assert mod is not None
EOF

# ── pyproject.toml ───────────────────────────────────────────
cat > "$APP/pyproject.toml" <<EOF
[project]
name = "$NAME"
version = "0.1.0"
description = "$DESC"
readme = "README.md"
requires-python = ">=3.14"
license = { text = "$LICENSE" }
authors = [
    { name = "Fabian Koerner", email = "mail@fabiankoerner.com" }
]

dependencies = [
    "cosalette>=0.1.7",
]

[project.scripts]
$NAME = "$PKG_NAME.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["packages/src/$PKG_NAME"]

[tool.pytest.ini_options]
testpaths = ["packages/tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = [
    "-v",
    "--tb=short",
    "--strict-markers",
    "--strict-config",
]
markers = [
    "unit: Unit tests (fast, no external dependencies)",
    "integration: Integration tests (require mock servers)",
    "slow: Tests that take > 1 second",
]
filterwarnings = [
    "error",
    "ignore::DeprecationWarning",
]

[tool.coverage.run]
source = ["packages/src/$PKG_NAME"]
branch = true
omit = [
    "*/__pycache__/*",
    "*/tests/*",
    "*/main.py",
    "*/app.py",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "@abstractmethod",
    "def __repr__",
    'if __name__ == "__main__":',
    "^\\\\s*\\\\.\\\\.\\\\.\$",
]
fail_under = 80
show_missing = true
skip_covered = false

[tool.coverage.json]
output = "coverage.json"

[tool.coverage.html]
directory = "htmlcov"

[tool.coverage.xml]
output = "coverage.xml"

[tool.ruff.lint.isort]
known-first-party = ["$PKG_NAME"]
EOF

# ── Badges ───────────────────────────────────────────────────
# README badge links to relative LICENSE; docs badge links to GitHub URL.
if [[ "$LICENSE" == "MIT" ]]; then
  BADGE='[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)'
  DOCS_BADGE='[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ff-fab/cosalette-apps/blob/main/apps/'"$NAME"'/LICENSE)'
else
  BADGE='[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](LICENSE)'
  DOCS_BADGE='[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](https://github.com/ff-fab/cosalette-apps/blob/main/apps/'"$NAME"'/LICENSE)'
fi

# ── README.md ────────────────────────────────────────────────
cat > "$APP/README.md" <<EOF
# $NAME

$DESC

$BADGE
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

$LICENSE License. See [LICENSE](LICENSE) for details.
EOF

# ── CHANGELOG.md ─────────────────────────────────────────────
cat > "$APP/CHANGELOG.md" <<'EOF'
# Changelog
EOF

# ── LICENSE ──────────────────────────────────────────────────
cp "LICENSES/${LICENSE}.txt" "$APP/LICENSE"

# ── Dockerfile ───────────────────────────────────────────────
cat > "$APP/Dockerfile" <<EOF
FROM python:3.14-alpine

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

WORKDIR /app

# Copy monorepo root lockfile and workspace config for reproducible builds.
# Build context must be the repository root (docker build -f apps/$NAME/Dockerfile .)
COPY pyproject.toml uv.lock ./
COPY apps/$NAME/pyproject.toml apps/$NAME/
COPY apps/$NAME/README.md apps/$NAME/
COPY apps/$NAME/packages/src/ apps/$NAME/packages/src/

# Install the application using locked dependencies (no cache to keep image small)
RUN uv pip install --system --no-cache ./apps/$NAME

# Prepare persistence directory and non-root user
RUN adduser -D appuser \\
    && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

VOLUME /app/data

ENTRYPOINT ["$NAME"]
EOF

# ── docker-compose.yml ───────────────────────────────────────
ENV_PREFIX="${PKG_NAME^^}"   # uppercase for env vars
cat > "$APP/docker-compose.yml" <<EOF
services:
  $NAME:
    build:
      context: ../..
      dockerfile: apps/$NAME/Dockerfile
    restart: unless-stopped
    volumes:
      - ${PKG_NAME//-/_}-data:/app/data
    environment:
      ${ENV_PREFIX}_MQTT__HOST: mosquitto
    depends_on:
      - mosquitto

  mosquitto:
    image: eclipse-mosquitto:2
    restart: unless-stopped
    ports:
      - '127.0.0.1:1883:1883'
    volumes:
      - mosquitto-data:/mosquitto/data
      - mosquitto-config:/mosquitto/config

volumes:
  ${PKG_NAME//-/_}-data:
  mosquitto-data:
  mosquitto-config:
EOF

# ── zensical.toml ────────────────────────────────────────────
cat > "$APP/zensical.toml" <<EOF
# Documentation site configuration (native Zensical format)
#
# Zensical is a documentation framework by the creators of Material for MkDocs.
# This file replaces mkdocs.yml with native TOML configuration.
#
# Usage (via Taskfile — single source of truth for tool commands):
#   task ${NAME}:docs:serve   # Local preview with hot reload
#   task ${NAME}:docs:build   # Build static site to site/


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

[project]
site_name = "$NAME"
site_description = "$DESC"

# Canonical URL for the deployed site. Used for sitemap and social cards.
site_url = "https://ff-fab.github.io/cosalette-apps/${NAME}/"

repo_url = "https://github.com/ff-fab/cosalette-apps"
repo_name = "ff-fab/cosalette-apps"
edit_uri = "edit/main/apps/${NAME}/docs/"
extra_css = ["stylesheets/extra.css", "stylesheets/click-zoom.css"]
extra_javascript = ["javascripts/click-zoom.js", "javascripts/version-fetch.js", "javascripts/header-breadcrumb.js", "javascripts/palette-sync.js"]

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

nav = [
    { "Home" = "index.md" },
    { "Getting Started" = "getting-started.md" },
    { "Configuration" = "configuration.md" },
    { "MQTT Topics" = "mqtt-topics.md" },
    { "ADRs" = "adr/" },
]

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

[project.theme]
features = [
    "navigation.tabs",
    "navigation.tabs.sticky",
    "navigation.sections",
    "navigation.expand",
    "navigation.indexes",
    "navigation.top",
    "search.suggest",
    "search.highlight",
    "content.code.copy",
    "content.code.annotate",
    "content.tabs.link",
    "content.action.edit",
]

[project.theme.icon]
repo = "fontawesome/brands/github"

# --- Color palette toggle (dark / light) ---

[[project.theme.palette]]
scheme = "slate"
primary = "teal"
accent = "cyan"
toggle.icon = "material/brightness-4"
toggle.name = "Switch to light mode"

[[project.theme.palette]]
scheme = "default"
primary = "teal"
accent = "cyan"
toggle.icon = "material/brightness-7"
toggle.name = "Switch to dark mode"

# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------

[project.plugins.autorefs]

[project.plugins.mkdocstrings.handlers.python]
paths = ["packages/src"]

[project.plugins.mkdocstrings.handlers.python.options]
show_source = true
show_root_heading = true
show_symbol_type_heading = true
members_order = "source"
show_signature_annotations = true
separate_signature = true
signature_crossrefs = true
merge_init_into_class = true
docstring_style = "google"

# ---------------------------------------------------------------------------
# Markdown extensions
# ---------------------------------------------------------------------------

# Admonitions (note, warning, tip, etc.)
[project.markdown_extensions.admonition]
[project.markdown_extensions.pymdownx.details]

# HTML / attribute extensions (required for grid cards, icon sizing)
[project.markdown_extensions.attr_list]
[project.markdown_extensions.md_in_html]

# Code blocks
[project.markdown_extensions.pymdownx.highlight]
anchor_linenums = true
line_spans = "__span"
pygments_lang_class = true

[project.markdown_extensions.pymdownx.inlinehilite]

[project.markdown_extensions.pymdownx.superfences]

[[project.markdown_extensions.pymdownx.superfences.custom_fences]]
name = "mermaid"
class = "mermaid"
format = "pymdownx.superfences.fence_code_format"

# Content tabs (e.g., showing Python / TypeScript side by side)
[project.markdown_extensions.pymdownx.tabbed]
alternate_style = true

# Typography and formatting
[project.markdown_extensions.pymdownx.mark]
[project.markdown_extensions.pymdownx.smartsymbols]
[project.markdown_extensions.pymdownx.keys]

# Lists and task lists
[project.markdown_extensions.def_list]
[project.markdown_extensions.pymdownx.tasklist]
custom_checkbox = true

# Table of contents
[project.markdown_extensions.toc]
permalink = true
toc_depth = 3

# Tables
[project.markdown_extensions.tables]

# Footnotes
[project.markdown_extensions.footnotes]

# Emoji (used sparingly for status indicators)
[project.markdown_extensions.pymdownx.emoji]
emoji_index = "zensical.extensions.emoji.twemoji"
emoji_generator = "zensical.extensions.emoji.to_svg"

# ---------------------------------------------------------------------------
# Extra
# ---------------------------------------------------------------------------

[[project.extra.social]]
icon = "fontawesome/brands/github"
link = "https://github.com/ff-fab/cosalette-apps"
EOF

# ── docs/index.md ────────────────────────────────────────────
cat > "$APP/docs/index.md" <<EOF
# $NAME

$DOCS_BADGE
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)

**$DESC**

---

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install $NAME and see your first MQTT messages.

    [:octicons-arrow-right-24: Get started](getting-started.md)

-   :material-cog:{ .lg .middle } **Configuration**

    ---

    All settings — environment variables, \`.env\` files, and CLI flags.

    [:octicons-arrow-right-24: Configure](configuration.md)

-   :material-access-point:{ .lg .middle } **MQTT Topics**

    ---

    Topic reference with payload schemas, directions, and retain flags.

    [:octicons-arrow-right-24: Topics](mqtt-topics.md)

-   :material-file-document-multiple:{ .lg .middle } **ADRs**

    ---

    Architecture decision records documenting design choices.

    [:octicons-arrow-right-24: Decisions](adr/)

</div>
EOF

# ── Repo-root config modifications ──────────────────────────

# 1. Taskfile.yml — add to APPS list
# Find the opening bracket of the APPS array (line after "APPS:") and insert there
APPS_LINE=$(grep -n '^\s*APPS:' Taskfile.yml | head -1 | cut -d: -f1)
APPS_BRACKET=$((APPS_LINE + 1))
sed -i "${APPS_BRACKET}a\\      ${NAME}," Taskfile.yml

# 2. Taskfile.yml — add include block after last app include
LAST_APP_INCLUDE=$(grep -n 'MODULE_NAME:' Taskfile.yml | tail -1 | cut -d: -f1)
sed -i "${LAST_APP_INCLUDE}a\\
\\
  ${NAME}:\\
    taskfile: ./taskfiles/PythonApp.yml\\
    dir: ./apps/${NAME}\\
    vars:\\
      APP_NAME: ${NAME}\\
      MODULE_NAME: ${PKG_NAME}" Taskfile.yml

# 3. release-please-config.json — add package entry
TMP=$(mktemp)
jq --arg name "$NAME" --arg path "apps/$NAME" \
  '.packages[$path] = { component: $name, "release-type": "python" }' \
  release-please-config.json > "$TMP" && mv "$TMP" release-please-config.json

# 4. .release-please-manifest.json — add entry
TMP=$(mktemp)
jq --arg path "apps/$NAME" '.[$path] = "0.1.0"' \
  .release-please-manifest.json > "$TMP" && mv "$TMP" .release-please-manifest.json

# 5. CI and docs workflows use dynamic app discovery — no edits needed.

# 6. codecov.yml — add flag entry under flags section
LAST_FLAG=$(grep -n "carryforward: true" codecov.yml | tail -1 | cut -d: -f1)
sed -i "${LAST_FLAG}a\\
  ${NAME}:\\
    paths:\\
      - apps/${NAME}/packages/src/\\
    carryforward: true" codecov.yml

# 7. pyproject.toml — add extraPaths entry for Pyright
sed -i "s|extraPaths = \[|extraPaths = [\"apps/${NAME}/packages/src\", |" pyproject.toml

# 8. REUSE.toml — update annotations
if [[ "$LICENSE" == "MIT" ]]; then
  # Add to existing MIT annotation path array (insert after first element)
  # Find the line with the MIT app paths array and add to it
  MIT_PATH_LINE=$(grep -n 'path = \["apps/.*\*\*"' REUSE.toml | head -1 | cut -d: -f1)
  if [[ -n "$MIT_PATH_LINE" ]]; then
    sed -i "${MIT_PATH_LINE}s|path = \[|path = [\"apps/${NAME}/\*\*\", |" REUSE.toml
  else
    die "cannot find MIT annotation path array in REUSE.toml"
  fi
else
  # Add to existing GPL annotation (convert string to array if needed, or append)
  GPL_PATH_LINE=$(grep -n 'path = "apps/.*\*\*"' REUSE.toml | grep -v '\[' | head -1 | cut -d: -f1)
  if [[ -n "$GPL_PATH_LINE" ]]; then
    # Convert single string path to array with new entry
    OLD_PATH=$(sed -n "${GPL_PATH_LINE}p" REUSE.toml | sed 's/.*path = "\(.*\)"/\1/')
    sed -i "${GPL_PATH_LINE}s|.*|path = [\"apps/${NAME}/\*\*\", \"${OLD_PATH}\"]|" REUSE.toml
  else
    # Already an array — insert at start
    GPL_PATH_LINE=$(grep -n 'GPL-3.0-or-later' REUSE.toml | head -1 | cut -d: -f1)
    if [[ -n "$GPL_PATH_LINE" ]]; then
      # Find the path line above the GPL license identifier
      GPL_BLOCK_START=$((GPL_PATH_LINE - 2))
      sed -i "${GPL_BLOCK_START}s|path = \[|path = [\"apps/${NAME}/\*\*\", |" REUSE.toml
    else
      # No GPL block exists yet — create one after the MIT  block
      MIT_END=$(grep -n 'SPDX-License-Identifier = "MIT"' REUSE.toml | head -1 | cut -d: -f1)
      sed -i "${MIT_END}a\\\n\\\n[[annotations]]\\\npath = \"apps/${NAME}/**\"\\\nSPDX-FileCopyrightText = \"2026 Fabian Koerner <mail@fabiankoerner.com>\"\\\nSPDX-License-Identifier = \"GPL-3.0-or-later\"" REUSE.toml
    fi
  fi
fi

# ── Verify critical edits ────────────────────────────────────
echo "Verifying integration edits…"
grep -q "$NAME" Taskfile.yml || die "Taskfile.yml edit failed — $NAME not found"
jq -e --arg p "apps/$NAME" '.packages[$p]' release-please-config.json >/dev/null || die "release-please-config.json edit failed"
jq -e --arg p "apps/$NAME" '.[$p]' .release-please-manifest.json >/dev/null || die ".release-please-manifest.json edit failed"
grep -q "$NAME" codecov.yml || die "codecov.yml edit failed — $NAME not found"
grep -q "apps/${NAME}/packages/src" pyproject.toml || die "pyproject.toml extraPaths edit failed"
grep -q "$NAME" REUSE.toml || die "REUSE.toml edit failed — $NAME not found"

echo "✓ Scaffolded apps/$NAME"
echo "  Next: run 'uv sync' then 'task ${NAME}:test:unit' to verify"
