"""Unit tests for caldates2mqtt errors — error hierarchy and ERROR_TYPE_MAP.

Test Techniques Used:
- Specification-based: Inheritance hierarchy, error map completeness
"""

from __future__ import annotations

import socket

import caldav.lib.error
import niquests
import pytest

from caldates2mqtt.errors import (
    ERROR_TYPE_MAP,
    CalDavAuthError,
    CalDavConnectionError,
    CalDavError,
    CalDavNotFoundError,
    CalDavReadError,
    CalDavTimeoutError,
)


@pytest.mark.unit
class TestErrorHierarchy:
    """Verify all error types inherit from CalDavError."""

    @pytest.mark.parametrize(
        "error_class",
        [
            CalDavAuthError,
            CalDavConnectionError,
            CalDavNotFoundError,
            CalDavTimeoutError,
            CalDavReadError,
        ],
    )
    def test_inherits_from_caldav_error(self, error_class: type[CalDavError]) -> None:
        """All domain errors inherit from CalDavError."""
        assert issubclass(error_class, CalDavError)

    def test_caldav_error_inherits_from_exception(self) -> None:
        """CalDavError inherits from Exception."""
        assert issubclass(CalDavError, Exception)

    @pytest.mark.parametrize(
        "error_class",
        [
            CalDavAuthError,
            CalDavConnectionError,
            CalDavNotFoundError,
            CalDavTimeoutError,
            CalDavReadError,
        ],
    )
    def test_error_can_carry_message(self, error_class: type[CalDavError]) -> None:
        """Domain errors carry a message."""
        err = error_class("something went wrong")
        assert str(err) == "something went wrong"


@pytest.mark.unit
class TestErrorTypeMap:
    """Verify ERROR_TYPE_MAP maps expected upstream exceptions.

    Note: caldav.lib.error.NotFoundError is intentionally absent from this map.
    It is caught explicitly in _read_sync (not via ERROR_TYPE_MAP) because the
    error message needs calendar_name and URL context unavailable at the
    ERROR_TYPE_MAP dispatch level.
    """

    def test_authorization_error_mapped(self) -> None:
        """caldav AuthorizationError maps to CalDavAuthError."""
        assert ERROR_TYPE_MAP[caldav.lib.error.AuthorizationError] is CalDavAuthError

    def test_connection_error_mapped(self) -> None:
        """niquests ConnectionError maps to CalDavConnectionError."""
        assert ERROR_TYPE_MAP[niquests.ConnectionError] is CalDavConnectionError

    def test_timeout_mapped(self) -> None:
        """niquests Timeout maps to CalDavTimeoutError."""
        assert ERROR_TYPE_MAP[niquests.Timeout] is CalDavTimeoutError

    def test_socket_timeout_mapped(self) -> None:
        """socket.timeout maps to CalDavTimeoutError."""
        assert ERROR_TYPE_MAP[socket.timeout] is CalDavTimeoutError
