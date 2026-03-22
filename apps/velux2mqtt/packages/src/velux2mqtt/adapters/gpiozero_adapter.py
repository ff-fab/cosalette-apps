"""Production GPIO adapter using gpiozero.

Controls M74HC4066 analog switches via Raspberry Pi GPIO pins.
Each pin drives one switch control input: HIGH closes the switch
(bridging KLF 050 button contacts), LOW opens it.

Compatible with Raspberry Pi 4, Pi 5, and Pi Zero 2 W via
gpiozero's pin factory abstraction (RPi.GPIO, lgpio, or native).
"""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import Self

from gpiozero import DigitalOutputDevice

from velux2mqtt.settings import Velux2MqttSettings

logger = logging.getLogger(__name__)


class GpiozeroAdapter:
    """Production adapter for GPIO-driven analog switches.

    Implements GpioSwitchPort protocol. Uses gpiozero's
    DigitalOutputDevice for each pin, which auto-selects the best
    pin factory for the current hardware.
    """

    def __init__(self, settings: Velux2MqttSettings) -> None:
        self._settings = settings
        self._devices: dict[int, DigitalOutputDevice] = {}

    def _collect_pins(self) -> list[int]:
        """Gather all GPIO pins from all cover configurations."""
        pins: list[int] = []
        for cover in self._settings.covers:
            pins.extend([cover.pin_up, cover.pin_stop, cover.pin_down])
        return pins

    def initialize(self, pins: list[int]) -> None:
        """Create DigitalOutputDevice for each pin (initially off/LOW).

        Args:
            pins: BCM GPIO pin numbers to initialize.
        """
        for pin in pins:
            if pin not in self._devices:
                self._devices[pin] = DigitalOutputDevice(pin, initial_value=False)
        logger.info(
            "GPIO initialized: %d pins (%s)",
            len(self._devices),
            sorted(self._devices.keys()),
        )

    async def press(self, pin: int, duration: float) -> None:
        """Pulse a GPIO pin HIGH for ``duration`` seconds.

        Args:
            pin: BCM GPIO pin number.
            duration: Seconds to hold HIGH.

        Raises:
            KeyError: If the pin was not initialized.
        """
        device = self._devices[pin]
        device.on()
        try:
            await asyncio.sleep(duration)
        finally:
            device.off()

    def cleanup(self) -> None:
        """Set all pins LOW and close gpiozero devices."""
        for pin, device in self._devices.items():
            try:
                device.off()
                device.close()
            except Exception:
                logger.warning("Failed to clean up GPIO pin %d", pin, exc_info=True)
        self._devices.clear()
        logger.info("GPIO resources released")

    async def __aenter__(self) -> Self:
        """Enter async context: initialize all cover GPIO pins."""
        self.initialize(self._collect_pins())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context: release GPIO resources."""
        self.cleanup()
