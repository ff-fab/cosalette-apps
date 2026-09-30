"""Domain exceptions for wiz2mqtt.

Adapters catch ``pywizlight``'s own exceptions at the boundary and re-raise
these instead, so ``unavailable_on``/``error_type_map`` wiring downstream
operates on domain exceptions rather than the SDK's.
"""

from __future__ import annotations


class WizBridgeError(Exception):
    """Root error for all wiz2mqtt domain exceptions."""


class WizConnectionError(WizBridgeError):
    """Bulb unreachable or the connection otherwise failed."""


class WizTimeoutError(WizBridgeError):
    """Bulb did not respond within pywizlight's own retry budget."""


class WizQueuedTimeoutError(WizTimeoutError):
    """A direct ``/set`` write timed out, and the command is queued for the return.

    Not a lost command: the ADR-008 return path replays it once the bulb
    answers again, so consumers can route it apart from other timeouts.
    """


class WizIdentityError(WizBridgeError):
    """Bulb at a configured IP reported an unexpected MAC address."""


class WizUnsupportedCommandError(WizBridgeError):
    """Command targets a capability the bulb's class does not support."""


error_type_map: dict[type[Exception], str] = {
    WizBridgeError: "wiz_bridge",
    WizConnectionError: "wiz_connection",
    WizTimeoutError: "wiz_timeout",
    WizQueuedTimeoutError: "timeout_queued",
    WizIdentityError: "wiz_identity",
    WizUnsupportedCommandError: "wiz_unsupported_command",
}

RESTORE_UNCONFIRMED = "restore_unconfirmed"
"""``error_type`` of the return-path error the bridge publishes itself when a
restore write is still unconfirmed after the last attempt (ADR-008)."""
