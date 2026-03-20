"""Unit tests for jeelink2mqtt.settings — Pydantic settings validation.

Test Techniques Used:
- Specification-based Testing: Default values and valid construction
- Boundary Value Analysis: Validator boundaries (ge, le, odd)
- Error Guessing: Invalid inputs caught by validators
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from jeelink2mqtt.settings import Jeelink2MqttSettings, SensorConfigSettings


@pytest.mark.unit
class TestJeelink2MqttSettingsDefaults:
    """Specification-based tests for default values."""

    def test_default_serial_port(self) -> None:
        """Default serial_port is /dev/ttyUSB0.

        Technique: Specification-based — default value.
        """
        # Act
        settings = Jeelink2MqttSettings()

        # Assert
        assert settings.serial_port == "/dev/ttyUSB0"

    def test_default_baud_rate(self) -> None:
        """Default baud_rate is 57600.

        Technique: Specification-based — default value.
        """
        # Act
        settings = Jeelink2MqttSettings()

        # Assert
        assert settings.baud_rate == 57600

    def test_default_staleness_timeout(self) -> None:
        """Default staleness_timeout_seconds is 600.0.

        Technique: Specification-based — default value.
        """
        # Act
        settings = Jeelink2MqttSettings()

        # Assert
        assert settings.staleness_timeout_seconds == 600.0

    def test_default_median_filter_window(self) -> None:
        """Default median_filter_window is 7.

        Technique: Specification-based — default value.
        """
        # Act
        settings = Jeelink2MqttSettings()

        # Assert
        assert settings.median_filter_window == 7

    def test_default_heartbeat_interval(self) -> None:
        """Default heartbeat_interval_seconds is 180.0.

        Technique: Specification-based — default value.
        """
        # Act
        settings = Jeelink2MqttSettings()

        # Assert
        assert settings.heartbeat_interval_seconds == 180.0

    def test_default_sensors_empty(self) -> None:
        """Default sensors list is empty.

        Technique: Specification-based — default value.
        """
        # Act
        settings = Jeelink2MqttSettings()

        # Assert
        assert settings.sensors == []


@pytest.mark.unit
class TestSerialPortValidator:
    """Boundary Value Analysis tests for the serial_port validator."""

    def test_valid_dev_path_accepted(self) -> None:
        """Paths starting with /dev/ pass validation.

        Technique: Specification-based — valid input.
        """
        # Act
        settings = Jeelink2MqttSettings(serial_port="/dev/ttyUSB0")

        # Assert
        assert settings.serial_port == "/dev/ttyUSB0"

    @pytest.mark.parametrize(
        "invalid_port",
        [
            "COM3",
            "/usr/ttyUSB0",
            "ttyUSB0",
            "",
            "/devices/tty",
        ],
        ids=["windows-com", "wrong-prefix", "no-slash", "empty", "wrong-dir"],
    )
    def test_non_dev_path_rejected(self, invalid_port: str) -> None:
        """Paths NOT starting with /dev/ raise ValidationError.

        Technique: Equivalence Partitioning — invalid path classes.
        """
        # Act / Assert
        with pytest.raises(ValidationError, match="serial_port"):
            Jeelink2MqttSettings(serial_port=invalid_port)


@pytest.mark.unit
class TestMedianFilterWindowValidator:
    """Boundary Value Analysis tests for median_filter_window validator."""

    @pytest.mark.parametrize("window", [3, 5, 7, 9, 11, 21])
    def test_valid_odd_values_accepted(self, window: int) -> None:
        """Odd values in 3-21 range pass validation.

        Technique: Boundary Value Analysis — valid boundaries.
        """
        # Act
        settings = Jeelink2MqttSettings(median_filter_window=window)

        # Assert
        assert settings.median_filter_window == window

    @pytest.mark.parametrize(
        "even_value",
        [4, 6, 8, 10, 20],
        ids=["4", "6", "8", "10", "20"],
    )
    def test_even_values_rejected(self, even_value: int) -> None:
        """Even window sizes raise ValidationError.

        Technique: Boundary Value Analysis — odd constraint.
        """
        # Act / Assert
        with pytest.raises(ValidationError, match="median_filter_window"):
            Jeelink2MqttSettings(median_filter_window=even_value)

    def test_below_minimum_rejected(self) -> None:
        """Window size below 3 raises ValidationError.

        Technique: Boundary Value Analysis — lower bound.
        """
        # Act / Assert
        with pytest.raises(ValidationError):
            Jeelink2MqttSettings(median_filter_window=1)

    def test_above_maximum_rejected(self) -> None:
        """Window size above 21 raises ValidationError.

        Technique: Boundary Value Analysis — upper bound.
        """
        # Act / Assert
        with pytest.raises(ValidationError):
            Jeelink2MqttSettings(median_filter_window=23)


@pytest.mark.unit
class TestStalenessTimeoutValidator:
    """Boundary Value Analysis tests for staleness_timeout_seconds."""

    def test_minimum_value_accepted(self) -> None:
        """staleness_timeout_seconds=60.0 (minimum) passes.

        Technique: Boundary Value Analysis — lower bound.
        """
        # Act
        settings = Jeelink2MqttSettings(staleness_timeout_seconds=60.0)

        # Assert
        assert settings.staleness_timeout_seconds == 60.0

    def test_below_minimum_rejected(self) -> None:
        """staleness_timeout_seconds < 60.0 raises ValidationError.

        Technique: Boundary Value Analysis — below lower bound.
        """
        # Act / Assert
        with pytest.raises(ValidationError):
            Jeelink2MqttSettings(staleness_timeout_seconds=59.9)


@pytest.mark.unit
class TestHeartbeatIntervalValidator:
    """Boundary Value Analysis tests for heartbeat_interval_seconds."""

    def test_minimum_value_accepted(self) -> None:
        """heartbeat_interval_seconds=10.0 (minimum) passes.

        Technique: Boundary Value Analysis — lower bound.
        """
        # Act
        settings = Jeelink2MqttSettings(heartbeat_interval_seconds=10.0)

        # Assert
        assert settings.heartbeat_interval_seconds == 10.0

    def test_below_minimum_rejected(self) -> None:
        """heartbeat_interval_seconds < 10.0 raises ValidationError.

        Technique: Boundary Value Analysis — below lower bound.
        """
        # Act / Assert
        with pytest.raises(ValidationError):
            Jeelink2MqttSettings(heartbeat_interval_seconds=9.9)


@pytest.mark.unit
class TestSensorConfigSettings:
    """Specification-based tests for sensor configuration model."""

    def test_sensor_config_settings_defaults(self) -> None:
        """SensorConfigSettings applies correct defaults.

        Technique: Specification-based — default values.
        """
        # Act
        cfg = SensorConfigSettings(name="office")

        # Assert
        assert cfg.name == "office"
        assert cfg.temp_offset == 0.0
        assert cfg.humidity_offset == 0.0
        assert cfg.staleness_timeout is None

    def test_sensor_config_settings_with_all_fields(self) -> None:
        """SensorConfigSettings stores all provided values.

        Technique: Specification-based — constructor contract.
        """
        # Act
        cfg = SensorConfigSettings(
            name="outdoor",
            temp_offset=-0.5,
            humidity_offset=2.0,
            staleness_timeout=300.0,
        )

        # Assert
        assert cfg.name == "outdoor"
        assert cfg.temp_offset == -0.5
        assert cfg.humidity_offset == 2.0
        assert cfg.staleness_timeout == 300.0
