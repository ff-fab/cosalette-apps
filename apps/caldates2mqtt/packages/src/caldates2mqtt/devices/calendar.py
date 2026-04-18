"""Calendar device handler for caldates2mqtt.

Each configured CalDAV calendar becomes an independent device with
periodic polling and on-demand re-read via MQTT command.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import cosalette

from caldates2mqtt.ports import CalDavPort

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any

    from caldates2mqtt.settings import CalendarConfig


async def _read_and_publish(
    ctx: cosalette.DeviceContext,
    reader: CalDavPort,
    cal: CalendarConfig,
    *,
    entries: int | None = None,
    days: int | None = None,
) -> None:
    """Read events from CalDAV and publish state.

    Args:
        ctx: Device context for publishing.
        reader: CalDAV adapter.
        cal: Calendar configuration.
        entries: Override number of entries (None = use cal.entries).
        days: Override lookahead days (None = use cal.days).
    """
    effective_entries = entries if entries is not None else cal.entries
    effective_days = days if days is not None else cal.days

    events = await reader.read_events(
        url=cal.url,
        calendar_name=cal.calendar_name,
        username=cal.username,
        password=cal.password.get_secret_value(),
        days=effective_days,
    )

    sliced = events[:effective_entries]
    payload: dict[str, object] = {
        "events": [{"title": e.title, "date": e.date.isoformat()} for e in sliced]
    }
    await ctx.publish_state(payload)


def _parse_command_overrides(payload: str) -> tuple[int | None, int | None]:
    """Parse JSON command payload for entries and days overrides.

    Args:
        payload: JSON string that may contain {"entries": int, "days": int}.

    Returns:
        Tuple of (entries, days) where None means use config default.
    """
    override_entries: int | None = None
    override_days: int | None = None

    if payload:
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                raw_entries = data.get("entries")
                if isinstance(raw_entries, int) and raw_entries > 0:
                    override_entries = raw_entries
                raw_days = data.get("days")
                if isinstance(raw_days, int) and raw_days > 0:
                    override_days = raw_days
        except json.JSONDecodeError:
            pass

    return override_entries, override_days


def make_calendar_handler(
    cal: CalendarConfig,
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Create a device handler for a single calendar.

    Args:
        cal: Calendar configuration captured in the closure.

    Returns:
        Async device handler function for use with app.add_device().
    """

    async def calendar_device(
        ctx: cosalette.DeviceContext,
        reader: CalDavPort,
        logger: logging.Logger,
    ) -> None:
        """Device loop for a single CalDAV calendar."""
        # Initial read
        logger.debug("Reading calendar %s", cal.key)
        await _read_and_publish(ctx, reader, cal)

        # Command processing loop
        async for cmd in ctx.commands(timeout=cal.poll_interval):
            if cmd is None:
                # Timeout = periodic re-read
                logger.debug("Reading calendar %s", cal.key)
                await _read_and_publish(ctx, reader, cal)
            else:
                # Command received = re-read with optional overrides
                override_entries, override_days = _parse_command_overrides(cmd.payload)
                logger.info("Re-read command received for calendar %s", cal.key)
                await _read_and_publish(
                    ctx, reader, cal, entries=override_entries, days=override_days
                )

    return calendar_device
