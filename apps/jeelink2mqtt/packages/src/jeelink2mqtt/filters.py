"""Per-sensor signal filtering.

Manages a bank of MedianFilter instances — one per active sensor ID —
for outlier rejection on temperature and humidity readings.
"""

from __future__ import annotations

from cosalette.filters import MedianFilter

from jeelink2mqtt.models import SensorReading


class FilterBank:
    """Maintains per-sensor median filters for temperature and humidity.

    A filter pair is lazily created the first time a sensor ID is seen.
    Filters can be individually reset (e.g. after a mapping change) or
    bulk-cleared.
    """

    def __init__(self, window: int = 7) -> None:
        self._window = window
        self._temp_filters: dict[int, MedianFilter] = {}
        self._humidity_filters: dict[int, MedianFilter] = {}

    def filter(self, reading: SensorReading) -> tuple[float, float]:
        """Apply median filtering to a sensor reading.

        Returns:
            ``(filtered_temperature, filtered_humidity)`` after the
            sliding-window median has been applied.
        """
        sid = reading.sensor_id

        if sid not in self._temp_filters:
            self._temp_filters[sid] = MedianFilter(self._window)
            self._humidity_filters[sid] = MedianFilter(self._window)

        filtered_temp = self._temp_filters[sid].update(reading.temperature)
        filtered_humidity = self._humidity_filters[sid].update(
            float(reading.humidity),
        )

        return filtered_temp, filtered_humidity

    def reset(self, sensor_id: int) -> None:
        """Remove filters for a sensor ID (e.g. on mapping change)."""
        self._temp_filters.pop(sensor_id, None)
        self._humidity_filters.pop(sensor_id, None)

    def reset_all(self) -> None:
        """Clear all filters."""
        self._temp_filters.clear()
        self._humidity_filters.clear()
