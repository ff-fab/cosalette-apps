"""Unit test fixtures for geiger2mqtt."""

from __future__ import annotations

import pytest

from geiger2mqtt.settings import Geiger2MqttSettings
from tests.fixtures.config import FakeTime, make_settings


@pytest.fixture
def settings() -> Geiger2MqttSettings:
    """Default settings, isolated from the host environment."""
    return make_settings()


@pytest.fixture
def fake_time() -> FakeTime:
    """A manual monotonic clock starting at 1000 s."""
    return FakeTime()
