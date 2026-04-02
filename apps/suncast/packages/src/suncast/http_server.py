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

"""Embedded HTTP server for serving shadow visualizations.

Provides a lightweight aiohttp server with endpoints for SVG, PNG, and
health-check responses.  Designed for integration with the cosalette
framework's lifespan hook via :func:`create_http_lifespan`.

Requires the ``http`` extra (``aiohttp``).  When aiohttp is not installed,
:func:`create_http_lifespan` raises :class:`HttpServerError` at startup.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from suncast.rasterize import RasterizationError, svg_to_png

logger = logging.getLogger(__name__)

_aiohttp_available = False
try:
    from aiohttp import web  # type: ignore[import-not-found]

    _aiohttp_available = True
except ImportError:
    web = None


class HttpServerError(Exception):
    """Raised when the HTTP server cannot be started."""


@dataclass(frozen=True, slots=True)
class HttpSettings:
    """Configuration for the embedded HTTP server."""

    http_enabled: bool = False
    """Whether to start the HTTP server."""

    http_host: str = "0.0.0.0"  # noqa: S104 — intentional bind-all for container use
    """Host address to bind."""

    http_port: int = 8080
    """Port to bind."""

    png_width: int = 800
    """PNG width for the ``/shadow.png`` endpoint."""

    png_height: int = 800
    """PNG height for the ``/shadow.png`` endpoint."""


SvgProvider = Callable[[], str | None]
"""Callable that returns the latest SVG content, or None if not yet available."""


def _build_app(
    svg_provider: SvgProvider,
    settings: HttpSettings,
) -> web.Application:
    """Build the aiohttp application with routes wired to *svg_provider*."""

    async def handle_svg(request: web.Request) -> web.Response:
        svg = svg_provider()
        if svg is None:
            return web.Response(status=503, text="No shadow data available yet")
        return web.Response(text=svg, content_type="image/svg+xml")

    async def handle_png(request: web.Request) -> web.Response:
        svg = svg_provider()
        if svg is None:
            return web.Response(status=503, text="No shadow data available yet")
        try:
            png_bytes = svg_to_png(
                svg, width=settings.png_width, height=settings.png_height
            )
        except RasterizationError as exc:
            return web.Response(status=500, text=str(exc))
        return web.Response(body=png_bytes, content_type="image/png")

    async def handle_health(request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/shadow.svg", handle_svg)
    app.router.add_get("/shadow.png", handle_png)
    app.router.add_get("/health", handle_health)
    return app


@asynccontextmanager
async def create_http_lifespan(
    svg_provider: SvgProvider,
    settings: HttpSettings,
) -> AsyncIterator[None]:
    """Async context manager that runs the HTTP server during its lifespan.

    Intended for use as a cosalette ``lifespan`` hook or within an
    ``async with`` block.

    Args:
        svg_provider: Callable returning the latest SVG string or None.
        settings: HTTP server configuration.

    Yields:
        Control to the caller while the server runs in the background.

    Raises:
        HttpServerError: If aiohttp is not installed.
    """
    if not settings.http_enabled:
        yield
        return

    if not _aiohttp_available:
        msg = (
            "HTTP server requires the 'http' extra: "
            "install with `uv pip install suncast[http]`"
        )
        raise HttpServerError(msg)

    app = _build_app(svg_provider, settings)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.http_host, settings.http_port)

    try:
        await site.start()
        logger.info(
            "HTTP server listening on %s:%d", settings.http_host, settings.http_port
        )
        yield
    finally:
        await runner.cleanup()
        logger.info("HTTP server stopped")
