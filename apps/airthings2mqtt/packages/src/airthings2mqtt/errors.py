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


class BleDeviceNotFoundError(BleConnectionError):
    """Raised when the target's advertisement is not observed by the adapter."""


class BleReadError(AirthingsError):
    """Raised when a GATT characteristic cannot be read."""


class BleTimeoutError(AirthingsError):
    """Raised when a BLE connection or read operation times out."""


ERROR_TYPE_MAP: dict[type[BaseException], type[AirthingsError]] = {
    ConnectionError: BleConnectionError,
    OSError: BleConnectionError,
    TimeoutError: BleTimeoutError,
}
"""Maps standard exception types to airthings2mqtt error classes.

Used by adapters to translate low-level BLE library exceptions into
domain-specific errors. Lookups walk the exception's MRO (see
:func:`map_exception`), so subclasses such as ``ConnectionRefusedError``
inherit their base's mapping and ``TimeoutError`` wins over its ``OSError`` base.
"""


error_type_map: dict[type[Exception], str] = {
    AirthingsError: "airthings_error",
    BleConnectionError: "ble_connection",
    BleDeviceNotFoundError: "ble_device_not_found",
    BleReadError: "ble_read",
    BleTimeoutError: "ble_timeout",
}
"""Mapping from domain exception types to MQTT error-topic string identifiers.

Registered with cosalette's :class:`~cosalette.App` (0.5.7 ``error_type_map``
hook) so these domain exceptions opt in to surfacing their messages on the
error topic (LEAK-01 hardening: unregistered exception messages are redacted).
"""


def map_exception(
    exc: BaseException,
    mapping: dict[type[BaseException], type[AirthingsError]] = ERROR_TYPE_MAP,
) -> type[AirthingsError]:
    """Return the domain error for *exc*, most specific MRO entry first.

    Unmapped exceptions (e.g. ``struct.error`` from a malformed frame) fall
    back to :class:`BleReadError`.
    """
    for cls in type(exc).__mro__:
        if (mapped := mapping.get(cls)) is not None:
            return mapped
    return BleReadError
