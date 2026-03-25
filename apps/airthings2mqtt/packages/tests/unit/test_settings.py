"""Unit tests for airthings2mqtt settings — Airthings2MqttSettings validation.

Test Techniques Used:
- Boundary Value Analysis: Numeric field constraints (ge)
- Equivalence Partitioning: Valid/invalid setting values
- Specification-based: Default values match documentation
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.fixtures.config import make_airthings2mqtt_settings


@pytest.mark.unit
class TestAirthings2MqttSettingsDefaults:
    """Verify default values match documentation."""

    def test_default_device_name(self) -> None:
        """Default device name is 'airthings'."""
        settings = make_airthings2mqtt_settings()
        assert settings.device_name == "airthings"

    def test_default_poll_interval(self) -> None:
        """Default poll interval is 1500 seconds."""
        settings = make_airthings2mqtt_settings()
        assert settings.poll_interval == 1500

    def test_device_mac_required(self) -> None:
        """device_mac has no default — omitting it raises ValidationError."""
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(device_mac=None)


@pytest.mark.unit
class TestAirthings2MqttSettingsValidation:
    """Verify field validation constraints.

    Technique: Boundary Value Analysis — test at and beyond boundaries.
    """

    def test_poll_interval_rejects_below_minimum(self) -> None:
        """Poll interval must be >= 60."""
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(poll_interval=59)

    def test_poll_interval_accepts_minimum(self) -> None:
        """Poll interval of 60 is valid (boundary for ge=60)."""
        settings = make_airthings2mqtt_settings(poll_interval=60)
        assert settings.poll_interval == 60

    def test_poll_interval_rejects_negative(self) -> None:
        """Poll interval must be >= 60."""
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(poll_interval=-1)

    def test_custom_device_name(self) -> None:
        """Custom device name is accepted."""
        settings = make_airthings2mqtt_settings(device_name="wave-bedroom")
        assert settings.device_name == "wave-bedroom"

    def test_custom_device_mac(self) -> None:
        """Custom MAC address is stored."""
        settings = make_airthings2mqtt_settings(device_mac="11:22:33:44:55:66")
        assert settings.device_mac == "11:22:33:44:55:66"
