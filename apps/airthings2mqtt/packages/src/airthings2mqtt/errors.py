"""Error hierarchy for airthings2mqtt.

All application-specific errors inherit from AirthingsError.
ERROR_TYPE_MAP provides a mapping from standard exception types
to airthings2mqtt-specific error classes for adapter-level
exception translation.
"""

from __future__ import annotations


class AirthingsError(Exception):
    """Base error for all airthings2mqtt operations."""


class BleConnectionError(AirthingsError):
    """Raised when the BLE device cannot be reached."""


class BleReadError(AirthingsError):
    """Raised when a GATT characteristic cannot be read."""


class BleTimeoutError(AirthingsError):
    """Raised when a BLE connection or read operation times out."""


ERROR_TYPE_MAP: dict[type[Exception], type[AirthingsError]] = {
    ConnectionError: BleConnectionError,
    OSError: BleConnectionError,
    TimeoutError: BleTimeoutError,
}
"""Maps standard exception types to airthings2mqtt error classes.

Used by adapters to translate low-level BLE library exceptions
into domain-specific errors.
"""
