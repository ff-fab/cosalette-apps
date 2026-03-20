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

"""Unit tests for devices/_serialization.py — Value deserialization.

Test Techniques Used:
- Round-trip Testing: serialize → deserialize produces original value
- Equivalence Partitioning: Passthrough types vs. converted types
- Specification-based: TI type converts ISO 8601 string to datetime
"""

from __future__ import annotations

from datetime import datetime

import pytest

from vito2mqtt.devices._serialization import deserialize_value, serialize_value
from vito2mqtt.errors import InvalidSignalError

# ---------------------------------------------------------------------------
# Deserialization
# ---------------------------------------------------------------------------


class TestDeserializeValue:
    """Verify deserialize_value() converts JSON values to codec-expected types."""

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
            (
                "CT",
                [
                    [[8, 0], [22, 0]],
                    [[None, None], [None, None]],
                    [[None, None], [None, None]],
                    [[None, None], [None, None]],
                ],
            ),
            ("RT", "on"),
            ("ES", {"error": "normal operation", "timestamp": "2026-01-01T00:00:00"}),
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
            "RT/str",
            "ES/dict",
        ],
    )
    def test_passthrough_types_unchanged(self, type_code: str, value: object) -> None:
        """Passthrough types return an equal value.

        Technique: Equivalence Partitioning — all non-TI/CT-active types
        are passthrough.  CT is validated (so identity is preserved for
        valid structures).
        """
        result = deserialize_value(value, type_code)
        assert result == value

    def test_system_time_from_iso_string(self) -> None:
        """TI type converts an ISO 8601 string to a datetime object.

        Technique: Specification-based — inverse of serialize_value for TI.
        """
        # Arrange
        iso_string = "2026-03-01T12:30:00"

        # Act
        result = deserialize_value(iso_string, "TI")

        # Assert
        assert isinstance(result, datetime)
        assert result == datetime(2026, 3, 1, 12, 30)

    def test_system_time_already_datetime(self) -> None:
        """TI type passes through a datetime unchanged (defensive).

        Technique: Error Guessing — caller may already have a datetime.
        """
        # Arrange
        value = datetime(2026, 3, 1, 12, 30)

        # Act
        result = deserialize_value(value, "TI")

        # Assert
        assert result is value

    def test_unknown_type_code_passes_through(self) -> None:
        """An unrecognized type_code falls through to passthrough.

        Technique: Error Guessing — future-proofing against new types.
        """
        sentinel = object()
        assert deserialize_value(sentinel, "XYZZY") is sentinel

    def test_invalid_iso_string_raises(self) -> None:
        """TI type with malformed ISO string must raise InvalidSignalError.

        Technique: Error Guessing — bad timestamp from MQTT payload.
        """
        with pytest.raises(InvalidSignalError, match="Invalid ISO 8601 timestamp"):
            deserialize_value("not-a-date", "TI")

    def test_ct_wrong_outer_type_raises(self) -> None:
        """CT with a non-list value must raise InvalidSignalError.

        Technique: Error Guessing — plain string instead of schedule.
        """
        with pytest.raises(InvalidSignalError, match="CT value must be a list"):
            deserialize_value("08:00-22:00", "CT")

    def test_ct_wrong_pair_count_raises(self) -> None:
        """CT with != 4 pairs must raise InvalidSignalError.

        Technique: Equivalence Partitioning — wrong length.
        """
        with pytest.raises(InvalidSignalError, match="CT value must be a list of 4"):
            deserialize_value([[[8, 0], [22, 0]]], "CT")

    def test_ct_string_time_slots_raises(self) -> None:
        """CT with string time values must raise InvalidSignalError.

        Technique: Error Guessing — common mistake of sending "HH:MM" strings.
        """
        schedule = [
            ["08:00", "22:00"],
            ["00:00", "00:00"],
            ["00:00", "00:00"],
            ["00:00", "00:00"],
        ]
        with pytest.raises(InvalidSignalError, match="CT pair 0"):
            deserialize_value(schedule, "CT")

    def test_ct_float_element_raises(self) -> None:
        """CT with float instead of int raises InvalidSignalError.

        Technique: Error Guessing — JSON numbers are often floats.
        """
        schedule = [
            [[8.0, 0], [22, 0]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]
        with pytest.raises(InvalidSignalError, match="hours must be int or null"):
            deserialize_value(schedule, "CT")


# ---------------------------------------------------------------------------
# Round-trip: serialize ↔ deserialize
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    """Verify serialize/deserialize round-trips preserve values."""

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
            (
                "CT",
                [
                    [[8, 0], [22, 0]],
                    [[None, None], [None, None]],
                    [[None, None], [None, None]],
                    [[None, None], [None, None]],
                ],
            ),
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
    def test_round_trip_passthrough_types(self, type_code: str, value: object) -> None:
        """serialize(deserialize(v)) == v for passthrough types.

        Technique: Round-trip — both directions are identity for these types.
        """
        deserialized = deserialize_value(value, type_code)
        serialized = serialize_value(deserialized, type_code)
        assert serialized == value

    def test_round_trip_system_time(self) -> None:
        """serialize(datetime) → ISO string, deserialize(ISO) → datetime.

        Technique: Round-trip — TI conversion is reversible.
        """
        # Arrange
        original = datetime(2026, 3, 1, 12, 30)

        # Act — serialize then deserialize
        serialized = serialize_value(original, "TI")
        assert isinstance(serialized, str)
        assert serialized == "2026-03-01T12:30:00"

        deserialized = deserialize_value(serialized, "TI")
        assert isinstance(deserialized, datetime)
        assert deserialized == original
