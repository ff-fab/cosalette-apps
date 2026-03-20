#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Fabian Koerner <mail@fabiankoerner.com>
# SPDX-License-Identifier: MIT

"""Add GPLv3 copyright headers to source files in GPL-licensed paths.

Reads REUSE.toml to discover which paths are GPL-3.0-or-later, then ensures
all .py and .sh files under those paths have the required copyright header.
Scales automatically to any new GPL-licensed app added to the monorepo.

Usage:
    # Check all GPL-path files for missing headers:
    uv run scripts/add_gpl_headers.py --check

    # Add headers to all GPL-path files missing them:
    uv run scripts/add_gpl_headers.py --all

    # Add header to specific files (only if under a GPL path):
    uv run scripts/add_gpl_headers.py file1.py file2.py
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent

_HEADER_TEMPLATE = """\
# Copyright (C) {year} {name} <{email}>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>."""

COPYRIGHT_MARKER = (
    "# This program is free software: you can redistribute it and/or modify"
)

HEADER_EXTENSIONS = frozenset({".py", ".sh"})

SKIP_SUFFIXES = ("_version.py",)

SKIP_PREFIXES = ("docs/planning/legacy/",)


def _load_gpl_globs() -> list[str]:
    """Read REUSE.toml and return glob patterns annotated as GPL-3.0-or-later."""
    reuse_toml = REPO_ROOT / "REUSE.toml"
    if not reuse_toml.exists():
        print("Error: REUSE.toml not found at repo root.", file=sys.stderr)
        sys.exit(1)

    data = tomllib.loads(reuse_toml.read_text(encoding="utf-8"))
    gpl_globs: list[str] = []

    for annotation in data.get("annotations", []):
        license_id = annotation.get("SPDX-License-Identifier", "")
        if "GPL-3.0" not in license_id:
            continue
        paths = annotation.get("path", [])
        if isinstance(paths, str):
            paths = [paths]
        gpl_globs.extend(paths)

    return gpl_globs


def _is_gpl_path(rel_path: str, gpl_globs: list[str]) -> bool:
    """Return True if rel_path matches any GPL glob pattern from REUSE.toml."""
    return any(fnmatch(rel_path, g) for g in gpl_globs)


def _should_skip(rel_path: str) -> bool:
    """Return True if the file should be skipped."""
    if any(rel_path.startswith(p) for p in SKIP_PREFIXES):
        return True
    return any(rel_path.endswith(s) for s in SKIP_SUFFIXES)


def _git_config(key: str) -> str:
    """Read a value from git config, raising if not set."""
    result = subprocess.run(
        ["git", "config", key],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    value = result.stdout.strip()
    if not value:
        print(f"Error: git config {key} is not set.", file=sys.stderr)
        sys.exit(1)
    return value


def _build_header() -> str:
    """Build the GPL header using the current git identity and year."""
    name = _git_config("user.name")
    email = _git_config("user.email")
    year = datetime.now(tz=UTC).year
    return _HEADER_TEMPLATE.format(year=year, name=name, email=email)


def _has_header(content: str) -> bool:
    """Return True if the file already contains the copyright notice."""
    return COPYRIGHT_MARKER in content


def add_header(filepath: Path, header: str) -> bool:
    """Add the GPLv3 header to a single file.

    Returns True if the header was added, False if skipped.
    """
    content = filepath.read_text(encoding="utf-8")

    if _has_header(content):
        return False

    first_line = content.split("\n", 1)[0] if content else ""
    has_shebang = first_line.startswith("#!")

    if has_shebang:
        rest = content.split("\n", 1)[1] if "\n" in content else ""
        new_content = first_line + "\n" + header + "\n" + rest
    elif content.strip():
        new_content = header + "\n\n" + content
    else:
        new_content = header + "\n"

    filepath.write_text(new_content, encoding="utf-8")
    return True


def _get_gpl_source_files(gpl_globs: list[str]) -> list[str]:
    """Return git-tracked .py/.sh files under GPL-annotated paths."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    return [
        f
        for f in result.stdout.strip().split("\n")
        if f
        and Path(f).suffix in HEADER_EXTENSIONS
        and _is_gpl_path(f, gpl_globs)
        and not _should_skip(f)
    ]


def cmd_check() -> int:
    """Check all GPL-path source files for missing headers. Return exit code."""
    gpl_globs = _load_gpl_globs()
    if not gpl_globs:
        print("No GPL-annotated paths found in REUSE.toml.")
        return 0

    files = _get_gpl_source_files(gpl_globs)
    missing: list[str] = []

    for rel in files:
        filepath = REPO_ROOT / rel
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        if not _has_header(content):
            missing.append(rel)

    if missing:
        print(f"Missing GPLv3 header in {len(missing)} file(s):")
        for f in missing:
            print(f"  {f}")
        return 1

    print(f"All {len(files)} GPL-path source files have GPLv3 headers.")
    return 0


def cmd_all() -> None:
    """Add headers to all GPL-path source files missing them."""
    gpl_globs = _load_gpl_globs()
    if not gpl_globs:
        print("No GPL-annotated paths found in REUSE.toml.")
        return

    header = _build_header()
    files = _get_gpl_source_files(gpl_globs)
    added = 0
    skipped = 0

    for rel in files:
        filepath = REPO_ROOT / rel
        if not filepath.exists():
            continue
        if add_header(filepath, header):
            print(f"  Added: {rel}")
            added += 1
        else:
            skipped += 1

    print(f"\nDone: {added} added, {skipped} already had headers.")


def cmd_files(paths: list[str]) -> int:
    """Add headers to specific files if under a GPL path.

    Returns 1 if any file was modified, 0 otherwise.
    """
    gpl_globs = _load_gpl_globs()
    header = _build_header()
    modified = 0

    for path_str in paths:
        filepath = Path(path_str).resolve()
        try:
            rel = str(filepath.relative_to(REPO_ROOT))
        except ValueError:
            continue

        if filepath.suffix not in HEADER_EXTENSIONS:
            continue

        if _should_skip(rel):
            continue

        if not _is_gpl_path(rel, gpl_globs):
            continue

        if not filepath.exists():
            continue

        if add_header(filepath, header):
            print(f"  Added GPLv3 header: {rel}")
            modified += 1

    return 1 if modified else 0


def main() -> None:
    """Entry point."""
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    if args == ["--check"]:
        sys.exit(cmd_check())
    elif args == ["--all"]:
        cmd_all()
    else:
        sys.exit(cmd_files(args))


if __name__ == "__main__":
    main()
