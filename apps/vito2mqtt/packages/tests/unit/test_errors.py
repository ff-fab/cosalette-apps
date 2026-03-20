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

"""Unit tests for errors.py — Domain error types.

Test Techniques Used:
- Specification-based: Verify inheritance hierarchy
- Error Guessing: Ensure each error is catchable by parent type
- Equivalence Partitioning: Each error type as an equivalence class
- Parametrize: Test families with shared assertions
"""

from __future__ import annotations

import pytest

from vito2mqtt.errors import (
    CommandNotWritableError,
    InvalidSignalError,
    OptolinkConnectionError,
    OptolinkTimeoutError,
    VitoBridgeError,
    error_type_map,
)

# ---------------------------------------------------------------------------
# Inheritance hierarchy
# ---------------------------------------------------------------------------


class TestInheritance:
    """All domain errors inherit from VitoBridgeError → Exception."""

    def test_errors_vito_bridge_error_inherits_exception(self) -> None:
        """VitoBridgeError is a direct subclass of Exception.

        Technique: Specification-based — root of the domain error hierarchy.
        """
        assert issubclass(VitoBridgeError, Exception)

    @pytest.mark.parametrize(
        "error_cls",
        [
            OptolinkConnectionError,
            OptolinkTimeoutError,
            InvalidSignalError,
            CommandNotWritableError,
        ],
        ids=lambda c: c.__name__,
    )
    def test_errors_subclass_inherits_vito_bridge_error(
        self, error_cls: type[VitoBridgeError]
    ) -> None:
        """Every concrete error must inherit from VitoBridgeError.

        Technique: Equivalence Partitioning — one check per error class.
        """
        assert issubclass(error_cls, VitoBridgeError)


# ---------------------------------------------------------------------------
# Raise / catch semantics
# ---------------------------------------------------------------------------


class TestRaiseCatch:
    """Each error can be raised and caught by the parent type."""

    @pytest.mark.parametrize(
        "error_cls",
        [
            OptolinkConnectionError,
            OptolinkTimeoutError,
            InvalidSignalError,
            CommandNotWritableError,
        ],
        ids=lambda c: c.__name__,
    )
    def test_errors_catchable_by_parent(self, error_cls: type[VitoBridgeError]) -> None:
        """Raising a concrete error must be catchable as VitoBridgeError.

        Technique: Error Guessing — confirm polymorphic catch works.
        """
        with pytest.raises(VitoBridgeError):
            raise error_cls("test message")


# ---------------------------------------------------------------------------
# Error messages
# ---------------------------------------------------------------------------


class TestErrorMessages:
    """Errors carry the message passed to the constructor."""

    @pytest.mark.parametrize(
        ("error_cls", "message"),
        [
            (VitoBridgeError, "root error"),
            (OptolinkConnectionError, "cannot open /dev/ttyUSB0"),
            (OptolinkTimeoutError, "no response in 3 s"),
            (InvalidSignalError, "unknown signal 'foobar'"),
            (CommandNotWritableError, "signal 'outdoor_temp' is read-only"),
        ],
        ids=lambda c: c.__name__ if isinstance(c, type) else c,
    )
    def test_errors_message_preserved(
        self, error_cls: type[VitoBridgeError], message: str
    ) -> None:
        """The str() of the error must match the original message.

        Technique: Specification-based — standard Exception contract.
        """
        err = error_cls(message)
        assert str(err) == message


# ---------------------------------------------------------------------------
# error_type_map
# ---------------------------------------------------------------------------


class TestErrorTypeMap:
    """error_type_map maps each error to a descriptive string key."""

    def test_errors_type_map_contains_all_error_types(self) -> None:
        """Map must include every domain error class.

        Technique: Specification-based — no type left unmapped.
        """
        expected_types = {
            VitoBridgeError,
            OptolinkConnectionError,
            OptolinkTimeoutError,
            InvalidSignalError,
            CommandNotWritableError,
        }
        assert set(error_type_map.keys()) == expected_types

    @pytest.mark.parametrize(
        ("error_cls", "expected_key"),
        [
            (VitoBridgeError, "vito_bridge"),
            (OptolinkConnectionError, "optolink_connection"),
            (OptolinkTimeoutError, "optolink_timeout"),
            (InvalidSignalError, "invalid_signal"),
            (CommandNotWritableError, "command_not_writable"),
        ],
        ids=lambda c: c.__name__ if isinstance(c, type) else c,
    )
    def test_errors_type_map_correct_value(
        self, error_cls: type[Exception], expected_key: str
    ) -> None:
        """Each error type maps to its expected string key.

        Technique: Specification-based — exact key values.
        """
        assert error_type_map[error_cls] == expected_key

    def test_errors_type_map_values_are_unique(self) -> None:
        """No two error types should share the same string key.

        Technique: Error Guessing — accidental duplicate values.
        """
        values = list(error_type_map.values())
        assert len(values) == len(set(values))
