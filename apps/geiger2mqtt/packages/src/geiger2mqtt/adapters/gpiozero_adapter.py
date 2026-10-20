"""Production pulse counter on a Raspberry Pi GPIO pin via gpiozero.

gpiozero is imported in ``__aenter__``, not at module level, so ``--help``,
``--dry-run`` and dev machines never import it or start lgpio's thread.
"""

from __future__ import annotations

import logging
import os
import time
from types import TracebackType
from typing import TYPE_CHECKING, Self

from geiger2mqtt.adapters._buffer import Clock, PulseBuffer
from geiger2mqtt.settings import Geiger2MqttSettings

if TYPE_CHECKING:
    from gpiozero import DigitalInputDevice

logger = logging.getLogger(__name__)


class GpiozeroPulseCounter(PulseBuffer):
    """Counts falling edges of the counter board output on one GPIO pin.

    The board holds its output high and pulls it low for each pulse. Without
    the internal pull-up the line is read as-is with ``active_state=False``;
    with ``GPIO_PULL_UP`` gpiozero enables the pull-up, which also makes the
    pin active-low. Only activation counts: gpiozero watches both edges, and
    the release edge of the same pulse must not count twice. No
    ``bounce_time``: pulses are short and a debounce window would swallow
    pulses that arrive close together.
    """

    def __init__(
        self, settings: Geiger2MqttSettings, clock: Clock = time.monotonic
    ) -> None:
        super().__init__(retention=settings.average_window, clock=clock)
        self._settings = settings
        self._device: DigitalInputDevice | None = None

    async def __aenter__(self) -> Self:
        from gpiozero import DigitalInputDevice

        pin = self._settings.gpio_pin
        if self._settings.gpio_pull_up:
            device = DigitalInputDevice(pin, pull_up=True)
        else:
            device = DigitalInputDevice(pin, pull_up=None, active_state=False)
        self.reset()
        device.when_activated = self.record
        self._device = device
        logger.info(
            "Counting pulses on GPIO %d (pull-up %s)",
            pin,
            "on" if self._settings.gpio_pull_up else "off",
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._device is not None:
            self._device.close()
            self._device = None

    async def health_check(self) -> bool:
        """Return True if the configured GPIO character device exists."""
        return os.path.exists(self._settings.gpio_chip)
