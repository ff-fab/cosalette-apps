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

"""Placeholder test to validate CI pipeline.

This test imports the application package so coverage is non-zero.
Replace it with real tests as the project evolves.
"""

import importlib


def test_package_imports() -> None:
    """Ensure the scaffolded package can be imported."""
    mod = importlib.import_module("suncast")
    assert mod is not None
