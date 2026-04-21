"""Unit test fixtures and plugin registration.

Provides gas2mqtt-specific test fixtures that extend the
cosalette testing plugin's fixtures with FakeMagnetometer.
"""

from __future__ import annotations

import cosalette
import pytest

from gas2mqtt.adapters.fake import FakeMagnetometer


@pytest.fixture
def fake_magnetometer() -> FakeMagnetometer:
    """Create a fresh, initialised FakeMagnetometer for each test."""
    mag = FakeMagnetometer()
    mag.initialize()
    return mag


@pytest.fixture
def gas_counter_store() -> cosalette.DeviceStore:
    """Create a fresh DeviceStore for gas_counter tests."""
    return cosalette.DeviceStore(cosalette.MemoryStore(), "gas_counter")
