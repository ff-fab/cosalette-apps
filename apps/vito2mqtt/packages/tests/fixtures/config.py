# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Configuration test fixtures and factories.

Provides fixtures for testing config.py:
- Vito2MqttSettings construction helpers
"""

from __future__ import annotations

import pytest

from vito2mqtt.config import Vito2MqttSettings


@pytest.fixture
def vito2mqtt_settings(monkeypatch: pytest.MonkeyPatch) -> Vito2MqttSettings:
    """Construct a Vito2MqttSettings with required env vars set.

    Provides a ready-to-use settings instance with the minimum required
    environment variables (``VITO2MQTT_SERIAL_PORT``) so tests don't need
    to set them every time.

    Usage::

        def test_something(vito2mqtt_settings):
            assert vito2mqtt_settings.serial_port == "/dev/ttyUSB0"
    """
    monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyUSB0")
    return Vito2MqttSettings()
