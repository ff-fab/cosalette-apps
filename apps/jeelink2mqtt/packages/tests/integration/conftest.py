"""Integration test fixtures for jeelink2mqtt."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jeelink2mqtt.adapters import FakeJeeLinkAdapter
from jeelink2mqtt.app import SharedState
from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import SensorConfig, SensorReading
from jeelink2mqtt.registry import SensorRegistry


@pytest.fixture
def sensor_configs() -> list[SensorConfig]:
    """Two-sensor configuration for integration tests.

    Office has calibration offsets; outdoor is zero-offset (pass-through).
    """
    return [
        SensorConfig(name="office", temp_offset=-0.3, humidity_offset=1.0),
        SensorConfig(name="outdoor", temp_offset=0.0, humidity_offset=0.0),
    ]


@pytest.fixture
def shared_state(sensor_configs: list[SensorConfig]) -> SharedState:
    """Wire up a real SharedState with domain objects.

    Uses a small filter window (3) so tests converge quickly.
    """
    return SharedState(
        registry=SensorRegistry(sensor_configs, staleness_timeout=600.0),
        filter_bank=FilterBank(window=3),
        sensor_configs={c.name: c for c in sensor_configs},
    )


@pytest.fixture
def fake_adapter() -> FakeJeeLinkAdapter:
    """Pre-opened FakeJeeLinkAdapter ready for callback registration."""
    adapter = FakeJeeLinkAdapter()
    adapter.open()
    return adapter


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
