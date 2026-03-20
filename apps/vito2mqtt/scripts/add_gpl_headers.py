#!/usr/bin/env python3
# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Add GPLv3 copyright headers to source files.

Usage:
    # Add header to specific files:
    uv run scripts/add_gpl_headers.py packages/src/vito2mqtt/new_module.py

    # Add header to multiple files:
    uv run scripts/add_gpl_headers.py file1.py file2.sh file3.py

    # Check all tracked .py and .sh files for missing headers:
    uv run scripts/add_gpl_headers.py --check

    # Add headers to all tracked files missing them:
    uv run scripts/add_gpl_headers.py --all

The script automatically detects whether a file starts with a shebang line
(``#!``) and places the header after it. Otherwise the header is prepended
at the top of the file.

Files under ``docs/planning/legacy/`` are always skipped (third-party code).
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

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

# Marker to detect whether *any* GPLv3 header is already present.
# Matches regardless of who authored the notice or when.
COPYRIGHT_MARKER = (
    "# This program is free software: you can redistribute it and/or modify"
)

# Skip these paths (relative to workspace root)
SKIP_PREFIXES = ("docs/planning/legacy/",)

# File extensions that receive comment-style GPL headers
HEADER_EXTENSIONS = frozenset({".py", ".sh"})


def _git_config(key: str) -> str:
    """Read a value from git config, raising if not set."""
    result = subprocess.run(
        ["git", "config", key],
        capture_output=True,
        text=True,
        cwd=WORKSPACE,
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


def _should_skip(rel_path: str) -> bool:
    """Return True if the file should be skipped."""
    return any(rel_path.startswith(prefix) for prefix in SKIP_PREFIXES)


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


def _get_tracked_source_files() -> list[str]:
    """Return git-tracked .py and .sh files relative to workspace root."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
        cwd=WORKSPACE,
    )
    return [
        f
        for f in result.stdout.strip().split("\n")
        if f
        and Path(f).suffix in HEADER_EXTENSIONS
        and not f.endswith("_version.py")  # auto-generated
        and not _should_skip(f)
    ]


def cmd_check() -> int:
    """Check all tracked source files for missing headers. Return exit code."""
    files = _get_tracked_source_files()
    missing: list[str] = []

    for rel in files:
        filepath = WORKSPACE / rel
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

    print(f"All {len(files)} tracked source files have GPLv3 headers.")
    return 0


def cmd_all() -> None:
    """Add headers to all tracked source files missing them."""
    header = _build_header()
    files = _get_tracked_source_files()
    added = 0
    skipped = 0

    for rel in files:
        filepath = WORKSPACE / rel
        if not filepath.exists():
            continue
        if add_header(filepath, header):
            print(f"  Added: {rel}")
            added += 1
        else:
            skipped += 1

    print(f"\nDone: {added} added, {skipped} already had headers.")


def cmd_files(paths: list[str]) -> int:
    """Add headers to specific files. Return 1 if any were modified."""
    header = _build_header()
    modified = 0
    for path_str in paths:
        filepath = Path(path_str).resolve()
        try:
            rel = filepath.relative_to(WORKSPACE)
        except ValueError:
            rel = filepath

        if _should_skip(str(rel)):
            continue

        if not filepath.exists():
            continue

        if filepath.suffix not in HEADER_EXTENSIONS:
            continue

        if filepath.name == "_version.py":
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
