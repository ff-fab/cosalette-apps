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

"""Configuration test fixtures and factories.

Provides fixtures for testing config.py:
- Settings LRU cache management
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from vito2mqtt.config import get_settings


@pytest.fixture
def _reset_settings_cache() -> Iterator[None]:
    """Clear Settings LRU cache before and after test.

    The get_settings() function is cached with @lru_cache. Tests that modify
    environment variables or config files need a fresh Settings instance.

    Usage:
        def test_env_override(_reset_settings_cache, monkeypatch):
            monkeypatch.setenv("OPENHAB_URL", "http://custom:8080")
            settings = get_settings()
            assert settings.openhab_url == "http://custom:8080"
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
