"""Unit tests for gas2mqtt main — telemetry registration and retry configuration.

Test Techniques Used:
- Specification-based: retry and retry_on metadata matches declared configuration
  for all three telemetry handlers (gas_counter, temperature, magnetometer)
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
class TestGasCounterRetryConfig:
    """Verify retry metadata on the gas_counter telemetry registration."""

    def test_retry_count_is_three(self) -> None:
        """gas_counter registration has retry=3.

        Technique: Specification-based — verify declared retry configuration.
        """
        from gas2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == "gas_counter")
        assert reg.retry == 3

    def test_retry_on_includes_oserror(self) -> None:
        """gas_counter retry_on tuple contains OSError.

        Technique: Specification-based — OSError covers smbus2 IOError/OSError
        (IOError is an alias of OSError since PEP 3151 / Python 3.3).
        """
        from gas2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == "gas_counter")
        assert OSError in reg.retry_on


@pytest.mark.unit
class TestTemperatureRetryConfig:
    """Verify retry metadata on the temperature telemetry registration."""

    def test_retry_count_is_three(self) -> None:
        """temperature registration has retry=3.

        Technique: Specification-based — verify declared retry configuration.
        """
        from gas2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == "temperature")
        assert reg.retry == 3

    def test_retry_on_includes_oserror(self) -> None:
        """temperature retry_on tuple contains OSError.

        Technique: Specification-based — OSError covers smbus2 I2C bus failures.
        """
        from gas2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == "temperature")
        assert OSError in reg.retry_on


@pytest.mark.unit
class TestMagnetometerRetryConfig:
    """Verify retry metadata on the magnetometer telemetry registration."""

    def test_retry_count_is_three(self) -> None:
        """magnetometer registration has retry=3.

        Technique: Specification-based — verify declared retry configuration.
        """
        from gas2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == "magnetometer")
        assert reg.retry == 3

    def test_retry_on_includes_oserror(self) -> None:
        """magnetometer retry_on tuple contains OSError.

        Technique: Specification-based — OSError covers smbus2 I2C bus failures.
        """
        from gas2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == "magnetometer")
        assert OSError in reg.retry_on
