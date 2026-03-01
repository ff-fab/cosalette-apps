#!/bin/bash
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
# Update pre-commit hooks to their latest versions
# Run this periodically to keep linting tools (ruff, mypy, etc.) current

set -e
cd /workspace

if [ ! -f ".pre-commit-config.yaml" ]; then
    echo "❌ No .pre-commit-config.yaml found in workspace root"
    exit 1
fi

echo "🔄 Updating pre-commit hooks to latest versions..."
uv run --group dev pre-commit autoupdate

echo ""
echo "✅ Pre-commit hooks updated!"
echo ""
echo "📋 Review changes with: git diff .pre-commit-config.yaml"
echo "🧪 Test hooks with:     pre-commit run --all-files"
