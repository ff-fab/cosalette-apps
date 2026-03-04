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

"""Bidirectional value conversion between codec types and MQTT payloads.

Serialization (codec → MQTT)
----------------------------
:func:`serialize_value` converts codec return values that aren't
directly JSON-serializable into JSON-safe types.

    IS10, IUNON, IU3600, PR2, PR3, BA, USV, CT — passthrough
    RT  — ReturnStatus.name.lower()  →  "on" | "off" | "error" | "unknown"
    ES  — [label, datetime]          →  {"error": label, "timestamp": iso}
    TI  — datetime                   →  iso string

Deserialization (MQTT → codec)
------------------------------
:func:`deserialize_value` converts incoming JSON values to the types
expected by ``OptolinkPort.write_signal()``.

    IS10, IUNON, IU3600, PR2, PR3, BA, USV, RT, ES — passthrough
    CT  — validate CycleTimeSchedule shape (4 pairs × 2 slots × [h, m])
    TI  — iso string  →  datetime
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

from vito2mqtt.errors import InvalidSignalError
from vito2mqtt.optolink.codec import ReturnStatus

__all__ = ["serialize_value", "deserialize_value"]

# ---------------------------------------------------------------------------
# Converter helpers
# ---------------------------------------------------------------------------


def _passthrough(value: Any) -> Any:
    """Return the value unchanged (already JSON-serializable)."""
    return value


def _convert_return_status(value: ReturnStatus) -> str:
    """Convert a ReturnStatus IntEnum member to its lowercase name."""
    return value.name.lower()


def _convert_error_history(value: list[object]) -> dict[str, str]:
    """Convert an ES ``[label, datetime]`` pair to a JSON-safe dict.

    The codec returns a two-element list: ``[error_label: str, timestamp: datetime]``.
    We use ``cast`` because the heterogeneous structure can't be expressed as a
    single ``list[T]`` type.
    """
    label = str(value[0])
    timestamp = cast(datetime, value[1])
    return {"error": label, "timestamp": timestamp.isoformat()}


def _convert_system_time(value: datetime) -> str:
    """Convert a datetime to an ISO 8601 string."""
    return value.isoformat()


# ---------------------------------------------------------------------------
# Dispatch table: type_code → converter
# ---------------------------------------------------------------------------

_CONVERTERS: dict[str, Callable[[Any], Any]] = {
    "IS10": _passthrough,
    "IUNON": _passthrough,
    "IU3600": _passthrough,
    "PR2": _passthrough,
    "PR3": _passthrough,
    "BA": _passthrough,
    "USV": _passthrough,
    "CT": _passthrough,
    "RT": _convert_return_status,
    "ES": _convert_error_history,
    "TI": _convert_system_time,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def serialize_value(value: Any, type_code: str) -> Any:
    """Convert a codec-decoded value to a JSON-serializable form.

    Args:
        value: The decoded value from codec.decode().
        type_code: The command's type_code (e.g., "RT", "ES", "TI").

    Returns:
        A JSON-serializable value suitable for MQTT publishing.
    """
    converter = _CONVERTERS.get(type_code, _passthrough)  # defensive fallback
    return converter(value)


# ---------------------------------------------------------------------------
# Deserializer helpers
# ---------------------------------------------------------------------------


def _deserialize_system_time(value: Any) -> Any:
    """Convert an ISO 8601 string to a datetime object.

    Raises:
        InvalidSignalError: If *value* is a string that is not valid
            ISO 8601.
    """
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            msg = f"Invalid ISO 8601 timestamp: {value!r}"
            raise InvalidSignalError(msg) from exc
    # Already a datetime (defensive)
    return value


def _validate_ct_slot(pair_idx: int, slot_idx: int, slot: Any) -> None:
    """Validate a single ``[hours, minutes]`` time slot.

    Raises:
        InvalidSignalError: If *slot* is not ``[int|None, int|None]``.
    """
    if not isinstance(slot, list) or len(slot) != 2:  # noqa: PLR2004
        msg = (
            f"CT pair {pair_idx} slot {slot_idx} must be [hours, minutes], got {slot!r}"
        )
        raise InvalidSignalError(msg)
    for k, elem in enumerate(slot):
        if elem is not None and not isinstance(elem, int):
            label = "hours" if k == 0 else "minutes"
            msg = (
                f"CT pair {pair_idx} slot {slot_idx} {label} must be int or null, "
                f"got {type(elem).__name__}"
            )
            raise InvalidSignalError(msg)


def _deserialize_cycle_time(value: Any) -> Any:
    """Validate and pass through a ``CycleTimeSchedule`` structure.

    The codec expects exactly 4 pairs, each containing 2 time slots,
    each slot being ``[hours, minutes]`` with ``int | None`` elements.
    This function validates the shape before the value reaches the
    codec encoder.

    Raises:
        InvalidSignalError: If *value* does not conform to the
            expected ``CycleTimeSchedule`` shape.
    """
    if not isinstance(value, list) or len(value) != 4:  # noqa: PLR2004
        msg = (
            "CT value must be a list of 4 cycle-time pairs, "
            f"got {type(value).__name__}"
            + (f" with length {len(value)}" if isinstance(value, list) else "")
        )
        raise InvalidSignalError(msg)

    for i, pair in enumerate(value):
        if not isinstance(pair, list) or len(pair) != 2:  # noqa: PLR2004
            msg = f"CT pair {i} must be a list of 2 time slots, got {pair!r}"
            raise InvalidSignalError(msg)
        for j, slot in enumerate(pair):
            _validate_ct_slot(i, j, slot)

    return value


# ---------------------------------------------------------------------------
# Deserializer dispatch table: type_code → deserializer
# ---------------------------------------------------------------------------

_DESERIALIZERS: dict[str, Callable[[Any], Any]] = {
    "IS10": _passthrough,
    "IUNON": _passthrough,
    "IU3600": _passthrough,
    "PR2": _passthrough,
    "PR3": _passthrough,
    "BA": _passthrough,
    "USV": _passthrough,
    "CT": _deserialize_cycle_time,
    "RT": _passthrough,  # Commands don't write RT signals, but defensive
    "ES": _passthrough,  # Commands don't write ES signals, but defensive
    "TI": _deserialize_system_time,
}


# ---------------------------------------------------------------------------
# Public API — deserialization
# ---------------------------------------------------------------------------


def deserialize_value(value: Any, type_code: str) -> Any:
    """Convert a JSON-parsed value to the type expected by the codec.

    This is the inverse of :func:`serialize_value`.  Most types pass
    through unchanged; ``TI`` converts an ISO 8601 string to
    :class:`~datetime.datetime`.

    Args:
        value: The JSON-decoded value from the MQTT payload.
        type_code: The command's type_code (e.g., "TI", "IUNON").

    Returns:
        A value suitable for ``OptolinkPort.write_signal()``.
    """
    deserializer = _DESERIALIZERS.get(type_code, _passthrough)
    return deserializer(value)
