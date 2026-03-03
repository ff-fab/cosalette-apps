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

"""Unit tests for devices/_serialization.py — Value serialization helpers.

Test Techniques Used:
- Specification-based: Verify each type_code conversion rule
- Equivalence Partitioning: Passthrough vs. converted types
- Error Guessing: Unknown type codes handled defensively
"""

from __future__ import annotations

from datetime import datetime

import pytest

from vito2mqtt.devices._serialization import serialize_value
from vito2mqtt.optolink.codec import ReturnStatus

# ---------------------------------------------------------------------------
# Passthrough types
# ---------------------------------------------------------------------------


class TestSerializePassthrough:
    """Passthrough type codes return the value unchanged."""

    @pytest.mark.parametrize(
        ("type_code", "value"),
        [
            ("IS10", 23.9),
            ("IUNON", 42),
            ("IU3600", 1.5),
            ("PR2", 80),
            ("PR3", 12.5),
            ("BA", "normal"),
            ("USV", "heating"),
            ("CT", [["08:00", "22:00"], ["00:00", "00:00"]]),
        ],
        ids=[
            "IS10/float",
            "IUNON/int",
            "IU3600/float",
            "PR2/int",
            "PR3/float",
            "BA/str",
            "USV/str",
            "CT/list",
        ],
    )
    def test_passthrough_returns_value_unchanged(
        self, type_code: str, value: object
    ) -> None:
        """Passthrough types must return the exact same value.

        Technique: Specification-based — no conversion needed.
        """
        result = serialize_value(value, type_code)
        assert result is value


# ---------------------------------------------------------------------------
# RT — ReturnStatus
# ---------------------------------------------------------------------------


class TestSerializeReturnStatus:
    """RT type code converts ReturnStatus IntEnum to lowercase name."""

    @pytest.mark.parametrize(
        ("member", "expected"),
        [
            (ReturnStatus.OFF, "off"),
            (ReturnStatus.ON, "on"),
            (ReturnStatus.UNKNOWN, "unknown"),
            (ReturnStatus.ERROR, "error"),
        ],
        ids=["OFF", "ON", "UNKNOWN", "ERROR"],
    )
    def test_return_status_to_lowercase_name(
        self, member: ReturnStatus, expected: str
    ) -> None:
        """Each ReturnStatus member serializes to its lowercase name.

        Technique: Specification-based — matches MQTT convention.
        """
        assert serialize_value(member, "RT") == expected


# ---------------------------------------------------------------------------
# ES — Error History
# ---------------------------------------------------------------------------


class TestSerializeErrorHistory:
    """ES type code converts [label, datetime] to a JSON-safe dict."""

    def test_error_history_to_dict(self) -> None:
        """ES value becomes {"error": label, "timestamp": iso_string}.

        Technique: Specification-based — structured MQTT payload.
        """
        value: list[object] = ["normal operation", datetime(2026, 1, 1)]
        result = serialize_value(value, "ES")
        assert result == {
            "error": "normal operation",
            "timestamp": "2026-01-01T00:00:00",
        }


# ---------------------------------------------------------------------------
# TI — System Time
# ---------------------------------------------------------------------------


class TestSerializeSystemTime:
    """TI type code converts datetime to ISO 8601 string."""

    def test_system_time_to_isoformat(self) -> None:
        """datetime(2026, 3, 1, 12, 30) → "2026-03-01T12:30:00".

        Technique: Specification-based — ISO 8601 for MQTT.
        """
        value = datetime(2026, 3, 1, 12, 30)
        assert serialize_value(value, "TI") == "2026-03-01T12:30:00"


# ---------------------------------------------------------------------------
# Unknown type code — defensive fallback
# ---------------------------------------------------------------------------


class TestSerializeUnknownTypeCode:
    """Unknown type codes return the value unchanged (defensive)."""

    def test_unknown_type_code_returns_value_unchanged(self) -> None:
        """An unrecognized type_code falls through to passthrough.

        Technique: Error guessing — future-proofing against new types.
        """
        sentinel = object()
        assert serialize_value(sentinel, "XYZZY") is sentinel
