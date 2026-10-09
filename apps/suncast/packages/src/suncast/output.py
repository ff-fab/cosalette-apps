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

"""Output delivery for SVG and PNG shadow visualizations.

Supports three delivery channels:

- **Filesystem:** writes ``shadow.svg`` and optionally ``shadow.png`` to a
  configurable directory.
- **MQTT:** publishes SVG and PNG payloads to additional device channels
  via :meth:`DeviceContext.publish`.
- **Telemetry return dict:** sun state metadata returned for the framework's
  automatic ``/state`` publication.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path

from cosalette import DeviceContext

from suncast.rasterize import RasterizationError, svg_to_png

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutputSettings:
    """Configuration for output delivery channels."""

    output_path: Path | None = None
    """Directory for filesystem output.  ``None`` disables file writing."""

    png_enabled: bool = False
    """Whether to rasterize PNG output (requires cairosvg)."""

    png_width: int = 800
    """PNG image width in pixels."""

    png_height: int = 800
    """PNG image height in pixels."""

    mqtt_svg_channel: str = "svg"
    """MQTT channel name for SVG payload."""

    mqtt_png_channel: str = "png"
    """MQTT channel name for PNG payload (base64-encoded)."""


@dataclass(slots=True)
class DeliveryResult:
    """Tracks what was delivered during an output cycle."""

    svg_file_written: bool = False
    png_file_written: bool = False
    mqtt_svg_published: bool = False
    mqtt_png_published: bool = False
    errors: list[str] = field(default_factory=list)


class OutputManager:
    """Delivers SVG/PNG output to filesystem and MQTT channels."""

    def __init__(self, settings: OutputSettings) -> None:
        self._settings = settings
        self._write_task: asyncio.Task[None] | None = None

    async def deliver(
        self,
        svg_content: str,
        sun_state: dict[str, object],
        ctx: DeviceContext | None = None,
    ) -> dict[str, object]:
        """Deliver shadow visualization outputs and return sun state telemetry.

        This method:

        1. Writes SVG (and optionally PNG) to the filesystem if configured.
        2. Publishes SVG (and optionally PNG) to MQTT channels via *ctx*.
        3. Returns *sun_state* unchanged for the framework's automatic
           state publication.  Delivery status is logged internally.

        Args:
            svg_content: The rendered SVG string.
            sun_state: Sun position metadata dict (returned as telemetry).
            ctx: cosalette DeviceContext for MQTT publishing.  ``None``
                skips MQTT delivery.

        Rasterization and file writes run in a worker thread
        (:func:`asyncio.to_thread`) so a slow CairoSVG call or a hung output
        mount never blocks the event loop. A cancelled write remains in flight;
        later cycles do not queue additional writes until it completes.

        Returns:
            The *sun_state* dict, suitable as a telemetry return value.
        """
        result = DeliveryResult()
        s = self._settings

        # -- PNG rasterization (shared by file and MQTT) -------------------
        png_bytes: bytes | None = None
        if s.png_enabled:
            try:
                png_bytes = await asyncio.to_thread(
                    svg_to_png, svg_content, width=s.png_width, height=s.png_height
                )
            except RasterizationError as exc:
                result.errors.append(str(exc))
                logger.warning("PNG rasterization failed: %s", exc)

        # -- MQTT output ---------------------------------------------------
        if ctx is not None:
            await self._publish_mqtt(ctx, svg_content, png_bytes, result)

        # -- Filesystem output ---------------------------------------------
        if s.output_path is not None:
            task = self._write_task
            if task is not None and not task.done():
                msg = "Skipping filesystem output; previous write still running"
                result.errors.append(msg)
                logger.warning(msg)
            else:
                task = asyncio.create_task(
                    asyncio.to_thread(
                        self._write_files, s.output_path, svg_content, png_bytes, result
                    )
                )
                self._write_task = task
                task.add_done_callback(self._write_finished)
                await asyncio.shield(task)

        if result.errors:
            logger.warning(
                "Output delivery completed with %d error(s)", len(result.errors)
            )

        return sun_state

    def _write_finished(self, task: asyncio.Task[None]) -> None:
        """Clear completed writes and consume errors after caller cancellation."""
        if self._write_task is task:
            self._write_task = None
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                logger.error(
                    "Filesystem output worker failed",
                    exc_info=(type(error), error, error.__traceback__),
                )

    # -- private helpers ---------------------------------------------------

    @classmethod
    def _write_files(
        cls,
        directory: Path,
        svg_content: str,
        png_bytes: bytes | None,
        result: DeliveryResult,
    ) -> None:
        """Write ``shadow.svg`` and, if given, ``shadow.png`` to *directory*."""
        cls._write_file(directory, "shadow.svg", svg_content, result)
        if png_bytes is not None:
            cls._write_file(directory, "shadow.png", png_bytes, result)

    @staticmethod
    def _write_file(
        directory: Path,
        filename: str,
        content: str | bytes,
        result: DeliveryResult,
    ) -> None:
        """Write *content* to *directory/filename*, creating dirs as needed."""
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / filename
            if isinstance(content, bytes):
                path.write_bytes(content)
                result.png_file_written = True
            else:
                path.write_text(content, encoding="utf-8")
                result.svg_file_written = True
            logger.debug("Wrote %s", path)
        except OSError as exc:
            msg = f"Failed to write {directory / filename}: {exc}"
            result.errors.append(msg)
            logger.warning(msg)

    async def _publish_mqtt(
        self,
        ctx: DeviceContext,
        svg_content: str,
        png_bytes: bytes | None,
        result: DeliveryResult,
    ) -> None:
        """Publish SVG and optional PNG to MQTT channels."""
        s = self._settings

        try:
            await ctx.publish(s.mqtt_svg_channel, svg_content, retain=True)
            result.mqtt_svg_published = True
        except Exception as exc:
            msg = f"MQTT SVG publish failed: {exc}"
            result.errors.append(msg)
            logger.warning(msg)

        if png_bytes is not None:
            try:
                await ctx.publish(
                    s.mqtt_png_channel,
                    base64.b64encode(png_bytes).decode("ascii"),
                    retain=True,
                )
                result.mqtt_png_published = True
            except Exception as exc:
                msg = f"MQTT PNG publish failed: {exc}"
                result.errors.append(msg)
                logger.warning(msg)
