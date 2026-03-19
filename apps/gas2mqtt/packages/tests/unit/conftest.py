"""Unit test fixtures and plugin registration.

Provides gas_counter-specific test fixtures that extend the
cosalette testing plugin's fixtures with Gas2MqttSettings and
FakeMagnetometer.
"""

from __future__ import annotations

import asyncio

import cosalette
import pytest
from cosalette.testing import FakeClock, MockMqttClient

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.ports import MagnetometerPort
from tests.fixtures.config import make_gas2mqtt_settings


@pytest.fixture
def fake_magnetometer() -> FakeMagnetometer:
    """Create a fresh, initialised FakeMagnetometer for each test."""
    mag = FakeMagnetometer()
    mag.initialize()
    return mag


@pytest.fixture
def gas_counter_context(
    mock_mqtt: MockMqttClient,
    fake_clock: FakeClock,
    fake_magnetometer: FakeMagnetometer,
) -> cosalette.DeviceContext:
    """DeviceContext wired for gas_counter device tests.

    Extends the standard cosalette device_context with:
    - Gas2MqttSettings (isolated, no env leakage)
    - FakeMagnetometer registered as MagnetometerPort adapter
    """
    return cosalette.DeviceContext(
        name="gas_counter",
        settings=make_gas2mqtt_settings(),
        mqtt=mock_mqtt,
        topic_prefix="gas2mqtt",
        shutdown_event=asyncio.Event(),
        adapters={
            MagnetometerPort: fake_magnetometer,
        },
        clock=fake_clock,
    )


@pytest.fixture
def gas_counter_store() -> cosalette.DeviceStore:
    """Empty DeviceStore backed by MemoryStore for gas_counter tests."""
    backend = cosalette.MemoryStore()
    device_store = cosalette.DeviceStore(backend, "gas_counter")
    device_store.load()
    return device_store
