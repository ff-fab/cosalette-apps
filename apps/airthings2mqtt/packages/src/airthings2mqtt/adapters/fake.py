"""Fake Airthings reader adapter for testing and dry-run mode.

Provides deterministic readings for unit tests and --dry-run operation.
Supports cycling through multiple readings and raising errors on demand.
"""

from __future__ import annotations

from airthings2mqtt.ports import AirthingsReading

_DEFAULT_READING = AirthingsReading(
    temperature=21.5,
    humidity=45.0,
    radon_24h_avg=80,
    radon_long_term_avg=65,
)


class FakeAirthingsReader:
    """Test double for AirthingsReaderPort.

    Returns configurable, deterministic readings. Supports:
    - Default values (21.5 C, 45% RH, 80 Bq/m3 24h, 65 Bq/m3 LTA)
    - Cycling through a list of readings
    - Raising a specific error on the next read

    Attributes:
        readings: List of readings to cycle through.
        calls: List of MAC addresses passed to read().
        raise_on_next: Exception to raise on next read(), cleared after use.
    """

    def __init__(self) -> None:
        self.readings: list[AirthingsReading] = [_DEFAULT_READING]
        self.calls: list[str] = []
        self.raise_on_next: Exception | None = None
        self._index: int = 0

    async def read(self, mac: str) -> AirthingsReading:
        """Return the next reading from the cycle.

        Args:
            mac: Bluetooth MAC address (recorded but not used).

        Returns:
            The next AirthingsReading in the cycle.

        Raises:
            Exception: Whatever is set in raise_on_next, if any.
        """
        self.calls.append(mac)
        if self.raise_on_next is not None:
            err = self.raise_on_next
            self.raise_on_next = None
            raise err
        reading = self.readings[self._index % len(self.readings)]
        self._index += 1
        return reading
