"""Unit test fixtures for jeelink2mqtt."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jeelink2mqtt.models import SensorConfig, SensorReading


@pytest.fixture
def now() -> datetime:
    """Current UTC timestamp for test consistency."""
    return datetime.now(UTC)


@pytest.fixture
def sensor_configs() -> list[SensorConfig]:
    """Standard 3-sensor configuration for tests."""
    return [
        SensorConfig(name="office"),
        SensorConfig(name="outdoor", temp_offset=-0.5, humidity_offset=2.0),
        SensorConfig(name="bedroom", staleness_timeout=300.0),
    ]


@pytest.fixture
def make_reading():
    """Factory fixture for creating SensorReading instances."""

    def _make(
        sensor_id: int = 42,
        temperature: float = 21.5,
        humidity: int = 55,
        low_battery: bool = False,
        timestamp: datetime | None = None,
    ) -> SensorReading:
        return SensorReading(
            sensor_id=sensor_id,
            temperature=temperature,
            humidity=humidity,
            low_battery=low_battery,
            timestamp=timestamp or datetime.now(UTC),
        )

    return _make
