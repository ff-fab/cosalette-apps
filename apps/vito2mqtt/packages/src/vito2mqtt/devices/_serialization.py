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

"""Value serialization helpers for MQTT publishing.

Converts codec return values that aren't directly JSON-serializable
into JSON-safe types.  Each type code maps to a converter function;
passthrough types return the value unchanged.

Return type mapping by type code:

    IS10, IUNON, IU3600, PR2, PR3, BA, USV, CT — passthrough
    RT  — ReturnStatus.name.lower()  →  "on" | "off" | "error" | "unknown"
    ES  — [label, datetime]          →  {"error": label, "timestamp": iso}
    TI  — datetime                   →  iso string
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

from vito2mqtt.optolink.codec import ReturnStatus

__all__ = ["serialize_value"]

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
