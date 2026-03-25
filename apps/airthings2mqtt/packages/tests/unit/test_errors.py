"""Unit tests for airthings2mqtt errors — error hierarchy and type map.

Test Techniques Used:
- Specification-based: Verify inheritance chain and ERROR_TYPE_MAP mapping
- Equivalence Partitioning: Each error type inherits from AirthingsError
"""

from __future__ import annotations

import pytest

from airthings2mqtt.errors import (
    ERROR_TYPE_MAP,
    AirthingsError,
    BleConnectionError,
    BleReadError,
    BleTimeoutError,
)


@pytest.mark.unit
class TestErrorHierarchy:
    """Verify error class inheritance."""

    def test_ble_connection_error_inherits_base(self) -> None:
        """BleConnectionError is an AirthingsError."""
        assert issubclass(BleConnectionError, AirthingsError)

    def test_ble_read_error_inherits_base(self) -> None:
        """BleReadError is an AirthingsError."""
        assert issubclass(BleReadError, AirthingsError)

    def test_ble_timeout_error_inherits_base(self) -> None:
        """BleTimeoutError is an AirthingsError."""
        assert issubclass(BleTimeoutError, AirthingsError)

    def test_base_inherits_exception(self) -> None:
        """AirthingsError is a standard Exception."""
        assert issubclass(AirthingsError, Exception)


@pytest.mark.unit
class TestErrorTypeMap:
    """Verify ERROR_TYPE_MAP maps standard exceptions to domain errors."""

    def test_connection_error_maps_to_ble_connection(self) -> None:
        """ConnectionError maps to BleConnectionError."""
        assert ERROR_TYPE_MAP[ConnectionError] is BleConnectionError

    def test_os_error_maps_to_ble_connection(self) -> None:
        """OSError maps to BleConnectionError."""
        assert ERROR_TYPE_MAP[OSError] is BleConnectionError

    def test_timeout_error_maps_to_ble_timeout(self) -> None:
        """TimeoutError maps to BleTimeoutError."""
        assert ERROR_TYPE_MAP[TimeoutError] is BleTimeoutError

    def test_unmapped_exception_not_in_map(self) -> None:
        """ValueError is not in the error type map."""
        assert ValueError not in ERROR_TYPE_MAP
