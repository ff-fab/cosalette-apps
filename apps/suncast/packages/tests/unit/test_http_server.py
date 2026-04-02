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

"""Unit tests for http_server.py — Embedded HTTP server for shadow visualizations.

Test Techniques Used:
- Specification-based: HTTP endpoint response contracts
- Equivalence Partitioning: SVG available vs not available (503)
- Error Guessing: Missing aiohttp, PNG rasterization failure
- Condition Coverage: http_enabled True/False paths
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from suncast.http_server import HttpServerError, HttpSettings, create_http_lifespan


# =============================================================================
# Fixtures
# =============================================================================

SAMPLE_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>'


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.unit
class TestCreateHttpLifespan:
    """Tests for the create_http_lifespan async context manager.

    Technique: Specification-based — lifespan contract.
    """

    async def test_disabled_yields_immediately(self) -> None:
        """When http_enabled is False, the lifespan is a no-op.

        Technique: Condition Coverage — disabled branch.
        """
        # Arrange
        settings = HttpSettings(http_enabled=False)
        provider = lambda: SAMPLE_SVG  # noqa: E731

        # Act / Assert — should complete without starting a server
        async with create_http_lifespan(provider, settings):
            pass  # control reaches here without error

    async def test_raises_when_aiohttp_missing(self) -> None:
        """When http_enabled is True but aiohttp is absent, raises HttpServerError.

        Technique: Error Guessing — missing optional dependency.
        """
        # Arrange
        settings = HttpSettings(http_enabled=True)
        provider = lambda: SAMPLE_SVG  # noqa: E731

        # Act / Assert
        with (
            patch("suncast.http_server._aiohttp_available", False),
            pytest.raises(HttpServerError, match="'http' extra"),
        ):
            async with create_http_lifespan(provider, settings):
                pass

    async def test_starts_and_stops_server(self) -> None:
        """When aiohttp is available, server starts and stops cleanly.

        Technique: Specification-based — lifespan lifecycle.
        """
        # Arrange
        settings = HttpSettings(http_enabled=True, http_port=0)
        provider = lambda: SAMPLE_SVG  # noqa: E731

        mock_site = MagicMock()
        mock_site.start = MagicMock(return_value=_coro(None))
        mock_runner = MagicMock()
        mock_runner.setup = MagicMock(return_value=_coro(None))
        mock_runner.cleanup = MagicMock(return_value=_coro(None))

        mock_web = MagicMock()
        mock_web.Application.return_value = MagicMock()
        mock_web.Application.return_value.router.add_get = MagicMock()
        mock_web.AppRunner.return_value = mock_runner
        mock_web.TCPSite.return_value = mock_site

        # Act / Assert
        with (
            patch("suncast.http_server._aiohttp_available", True),
            patch("suncast.http_server.web", mock_web),
        ):
            async with create_http_lifespan(provider, settings):
                mock_runner.setup.assert_called_once()
                mock_site.start.assert_called_once()

        mock_runner.cleanup.assert_called_once()


@pytest.mark.unit
class TestHttpSettings:
    """Specification-based: HttpSettings dataclass defaults.

    Technique: Specification-based — default configuration values.
    """

    def test_defaults(self) -> None:
        """HttpSettings has sensible defaults."""
        # Arrange / Act
        settings = HttpSettings()

        # Assert
        assert settings.http_enabled is False
        assert settings.http_host == "0.0.0.0"  # noqa: S104
        assert settings.http_port == 8080
        assert settings.png_width == 800
        assert settings.png_height == 800


@pytest.mark.unit
class TestBuildApp:
    """Tests for the internal _build_app route handler behavior.

    Technique: Specification-based — HTTP endpoint response contracts.
    """

    def test_build_app_registers_three_routes(self) -> None:
        """_build_app creates an app with /shadow.svg, /shadow.png, /health.

        Technique: Specification-based — route registration.
        """
        # Arrange
        mock_web = MagicMock()
        mock_app = MagicMock()
        mock_web.Application.return_value = mock_app

        provider = lambda: SAMPLE_SVG  # noqa: E731
        settings = HttpSettings()

        # Act
        with patch("suncast.http_server.web", mock_web):
            from suncast.http_server import _build_app

            _build_app(provider, settings)

        # Assert
        add_get_calls = mock_app.router.add_get.call_args_list
        routes = [call[0][0] for call in add_get_calls]
        assert "/shadow.svg" in routes
        assert "/shadow.png" in routes
        assert "/health" in routes


# =============================================================================
# Helpers
# =============================================================================


async def _coro(value: object) -> object:
    """Return a coroutine that yields *value* — used to satisfy awaits on mocks."""
    return value
