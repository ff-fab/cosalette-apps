"""Cover command parsing — text, numeric, and JSON formats.

Translates inbound MQTT payloads into typed CoverCommand values.
Supports Home Assistant semantics: 0 = fully closed, 100 = fully open.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum, auto


class Direction(Enum):
    """Movement direction for a cover."""

    OPEN = auto()  # toward 100% (up)
    CLOSE = auto()  # toward 0% (down)
    STOP = auto()


class InvalidCommandError(Exception):
    """Raised when a command payload cannot be parsed."""


@dataclass(frozen=True, slots=True)
class CoverCommand:
    """Parsed cover command.

    Attributes:
        direction: OPEN, CLOSE, or STOP.
        position: Target position (0–100) for positional commands,
            or None for simple directional commands.
    """

    direction: Direction
    position: int | None = None


# Text aliases (case-insensitive)
_OPEN_ALIASES = frozenset({"up", "open"})
_CLOSE_ALIASES = frozenset({"down", "close"})
_STOP_ALIASES = frozenset({"stop"})


def parse_command(payload: str) -> CoverCommand:
    """Parse an MQTT payload into a CoverCommand.

    Supported formats:
        - Text: ``"up"``, ``"open"``, ``"down"``, ``"close"``, ``"stop"``
        - Numeric string: ``"0"`` (close), ``"100"`` (open), ``"42"`` (position)
        - JSON: ``{"position": 42}`` or ``{"command": "stop"}``

    Args:
        payload: Raw MQTT payload string.

    Returns:
        Parsed CoverCommand.

    Raises:
        InvalidCommandError: If the payload cannot be parsed.
    """
    text = payload.strip()
    if not text:
        raise InvalidCommandError("empty payload")

    # Try JSON first (starts with '{')
    if text.startswith("{"):
        return _parse_json(text)

    # Try text alias
    lower = text.casefold()
    if lower in _OPEN_ALIASES:
        return CoverCommand(direction=Direction.OPEN, position=100)
    if lower in _CLOSE_ALIASES:
        return CoverCommand(direction=Direction.CLOSE, position=0)
    if lower in _STOP_ALIASES:
        return CoverCommand(direction=Direction.STOP)

    # Try numeric
    try:
        value = int(lower)
    except ValueError:
        raise InvalidCommandError(f"unrecognized command: {text!r}") from None

    return _position_command(value)


def _parse_json(text: str) -> CoverCommand:
    """Parse a JSON command payload."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidCommandError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise InvalidCommandError(f"expected JSON object, got {type(data).__name__}")

    if "position" in data:
        try:
            position = int(data["position"])
        except (ValueError, TypeError) as exc:
            raise InvalidCommandError(
                f"invalid position value: {data['position']!r}"
            ) from exc
        return _position_command(position)

    if "command" in data:
        cmd = str(data["command"]).casefold()
        if cmd in _OPEN_ALIASES:
            return CoverCommand(direction=Direction.OPEN, position=100)
        if cmd in _CLOSE_ALIASES:
            return CoverCommand(direction=Direction.CLOSE, position=0)
        if cmd in _STOP_ALIASES:
            return CoverCommand(direction=Direction.STOP)
        raise InvalidCommandError(f"unknown command in JSON: {cmd!r}")

    raise InvalidCommandError(f"JSON must contain 'position' or 'command': {data}")


def _position_command(value: int) -> CoverCommand:
    """Create a positional command, clamping to [0, 100]."""
    clamped = max(0, min(100, value))
    if clamped == 0:
        return CoverCommand(direction=Direction.CLOSE, position=0)
    if clamped == 100:
        return CoverCommand(direction=Direction.OPEN, position=100)
    # Intermediate positions: direction will be determined by PositionTracker
    # relative to current position. We use OPEN as placeholder — the device
    # handler computes actual direction.
    return CoverCommand(direction=Direction.OPEN, position=clamped)
