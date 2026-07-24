"""Error hierarchy for caldates2mqtt.

All application-specific errors inherit from CalDavError.
ERROR_TYPE_MAP provides a mapping from upstream exception types
to caldates2mqtt-specific error classes for adapter-level
exception translation.
"""

from __future__ import annotations

import socket

import caldav.lib.error
import niquests


class CalDavError(Exception):
    """Base error for all caldates2mqtt operations."""


class CalDavAuthError(CalDavError):
    """Raised when CalDAV authentication or authorization fails."""


class CalDavConnectionError(CalDavError):
    """Raised when the CalDAV server is unreachable."""


class CalDavNotFoundError(CalDavError):
    """Raised when a CalDAV calendar does not exist on the server."""


class CalDavTimeoutError(CalDavError):
    """Raised when a CalDAV request times out."""


class CalDavReadError(CalDavError):
    """Raised for catch-all CalDAV protocol or parsing errors."""


ERROR_TYPE_MAP: dict[type[Exception], type[CalDavError]] = {
    caldav.lib.error.AuthorizationError: CalDavAuthError,
    niquests.ConnectionError: CalDavConnectionError,
    niquests.Timeout: CalDavTimeoutError,
    socket.timeout: CalDavTimeoutError,
}
"""Maps upstream exception types to caldates2mqtt error classes.

Used by adapters to translate low-level CalDAV library exceptions
into domain-specific errors.
"""


error_type_map: dict[type[Exception], str] = {
    CalDavError: "caldav_error",
    CalDavAuthError: "caldav_auth",
    CalDavConnectionError: "caldav_connection",
    CalDavNotFoundError: "caldav_not_found",
    CalDavTimeoutError: "caldav_timeout",
    CalDavReadError: "caldav_read",
}
"""Mapping from domain exception types to MQTT error-topic string identifiers.

Registered with cosalette's :class:`~cosalette.App` (0.5.7 ``error_type_map``
hook) so these domain exceptions opt in to surfacing their messages on the
error topic (LEAK-01 hardening: unregistered exception messages are redacted).
"""
