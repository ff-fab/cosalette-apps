"""Magnetometer test fixtures.

Provides FakeMagnetometer instances for device tests.
"""

from __future__ import annotations

import pytest

from gas2mqtt.adapters.fake import FakeMagnetometer


@pytest.fixture
def fake_magnetometer() -> FakeMagnetometer:
    """Create a fresh FakeMagnetometer for each test.

    Returns:
        FakeMagnetometer with all values at 0.
    """
    mag = FakeMagnetometer()
    mag.initialize()
    return mag
