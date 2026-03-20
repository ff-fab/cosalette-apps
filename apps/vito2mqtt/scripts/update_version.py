#!/usr/bin/env python
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
"""Script to regenerate version file from git tags using setuptools_scm."""

import sys
from pathlib import Path

try:
    import setuptools_scm
except ImportError:
    print("setuptools_scm not found. Install with: uv sync --group dev")
    sys.exit(1)

# Use absolute path for workspace root
workspace_root = Path("/workspace")
version = setuptools_scm.get_version(root=workspace_root, fallback_version="0.0.0")
version_file = workspace_root / "packages" / "src" / "vito2mqtt" / "_version.py"
version_file.write_text(f'__version__ = "{version}"\n')
print(f"Updated {version_file} with version: {version}")
