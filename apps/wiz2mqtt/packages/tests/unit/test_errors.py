"""Unit tests for errors.py — Domain error types.

Test Techniques Used:
- Specification-based: Verify inheritance hierarchy
- Error Guessing: Ensure each error is catchable by parent type
- Equivalence Partitioning: Each error type as an equivalence class
- Parametrize: Test families with shared assertions
"""

from __future__ import annotations

import pytest

from wiz2mqtt.errors import (
    WizBridgeError,
    WizConnectionError,
    WizTimeoutError,
    WizUnsupportedCommandError,
    error_type_map,
)

_SUBCLASSES = [WizConnectionError, WizTimeoutError, WizUnsupportedCommandError]


# ---------------------------------------------------------------------------
# Inheritance hierarchy
# ---------------------------------------------------------------------------


class TestInheritance:
    """All domain errors inherit from WizBridgeError -> Exception."""

    def test_errors_wiz_bridge_error_inherits_exception(self) -> None:
        """WizBridgeError is a direct subclass of Exception.

        Technique: Specification-based — root of the domain error hierarchy.
        """
        assert issubclass(WizBridgeError, Exception)

    @pytest.mark.parametrize("error_cls", _SUBCLASSES, ids=lambda c: c.__name__)
    def test_errors_subclass_inherits_wiz_bridge_error(
        self, error_cls: type[WizBridgeError]
    ) -> None:
        """Every concrete error must inherit from WizBridgeError.

        Technique: Equivalence Partitioning — one check per error class.
        """
        assert issubclass(error_cls, WizBridgeError)


# ---------------------------------------------------------------------------
# Raise / catch semantics
# ---------------------------------------------------------------------------


class TestRaiseCatch:
    """Each error can be raised and caught by the parent type."""

    @pytest.mark.parametrize("error_cls", _SUBCLASSES, ids=lambda c: c.__name__)
    def test_errors_catchable_by_parent(self, error_cls: type[WizBridgeError]) -> None:
        """Raising a concrete error must be catchable as WizBridgeError.

        Technique: Error Guessing — confirm polymorphic catch works.
        """
        with pytest.raises(WizBridgeError):
            raise error_cls("test message")


# ---------------------------------------------------------------------------
# error_type_map
# ---------------------------------------------------------------------------


class TestErrorTypeMap:
    """error_type_map maps each error to a descriptive string key."""

    def test_errors_type_map_contains_all_error_types(self) -> None:
        """Map must include every domain error class.

        Technique: Specification-based — no type left unmapped.
        """
        expected_types = {WizBridgeError, *_SUBCLASSES}
        assert set(error_type_map.keys()) == expected_types

    @pytest.mark.parametrize(
        ("error_cls", "expected_key"),
        [
            (WizBridgeError, "wiz_bridge"),
            (WizConnectionError, "wiz_connection"),
            (WizTimeoutError, "wiz_timeout"),
            (WizUnsupportedCommandError, "wiz_unsupported_command"),
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
