"""Domain exceptions for jeelink2mqtt.

Each exception maps to a structured MQTT error type via the
``error_type_map`` dict, used by cosalette's error handling system.
"""

from __future__ import annotations


class SerialConnectionError(Exception):
    """JeeLink serial port unavailable or disconnected."""


class FrameParseError(Exception):
    """Received data doesn't match the expected LaCrosse frame format."""


class MappingConflictError(Exception):
    """Attempted to map an ID that's already assigned to another sensor."""


class StalenessTimeoutError(Exception):
    """Sensor hasn't sent readings within the staleness window."""


class UnknownSensorError(Exception):
    """Received a reading from an unrecognised / unmapped sensor ID."""


error_type_map: dict[type[Exception], str] = {
    SerialConnectionError: "serial_connection",
    FrameParseError: "frame_parse",
    MappingConflictError: "mapping_conflict",
    StalenessTimeoutError: "staleness_timeout",
    UnknownSensorError: "unknown_sensor",
}
"""Mapping from exception types to MQTT error-topic string identifiers.

Used by cosalette's error publisher to route structured error payloads
to the correct MQTT sub-topic.
"""
