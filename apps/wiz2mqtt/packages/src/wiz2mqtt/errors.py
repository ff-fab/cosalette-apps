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


class WizUnsupportedCommandError(WizBridgeError):
    """Command targets a capability the bulb's class does not support."""


error_type_map: dict[type[Exception], str] = {
    WizBridgeError: "wiz_bridge",
    WizConnectionError: "wiz_connection",
    WizTimeoutError: "wiz_timeout",
    WizUnsupportedCommandError: "wiz_unsupported_command",
}
