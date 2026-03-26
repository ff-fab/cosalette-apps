"""Error hierarchy for caldates2mqtt.

All application-specific errors inherit from CalDavError.
ERROR_TYPE_MAP provides a mapping from upstream exception types
to caldates2mqtt-specific error classes for adapter-level
exception translation.
"""

from __future__ import annotations

import socket

import caldav.lib.error
import requests


class CalDavError(Exception):
    """Base error for all caldates2mqtt operations."""


class CalDavAuthError(CalDavError):
    """Raised when CalDAV authentication or authorization fails."""


class CalDavConnectionError(CalDavError):
    """Raised when the CalDAV server is unreachable."""


class CalDavTimeoutError(CalDavError):
    """Raised when a CalDAV request times out."""


class CalDavReadError(CalDavError):
    """Raised for catch-all CalDAV protocol or parsing errors."""


ERROR_TYPE_MAP: dict[type[Exception], type[CalDavError]] = {
    caldav.lib.error.AuthorizationError: CalDavAuthError,
    requests.ConnectionError: CalDavConnectionError,
    requests.Timeout: CalDavTimeoutError,
    socket.timeout: CalDavTimeoutError,
}
"""Maps upstream exception types to caldates2mqtt error classes.

Used by adapters to translate low-level CalDAV library exceptions
into domain-specific errors.
"""
