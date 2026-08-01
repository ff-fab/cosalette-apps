"""Unit tests for jeelink2mqtt.state — SharedState factory functions.

Test Techniques Used:
- Specification-based Testing: build_shared_state_logged log message + return contract
- Round-trip Testing: build_shared_state_logged output matches build_shared_state
"""

from __future__ import annotations

import logging

import pytest

from jeelink2mqtt.settings import Jeelink2MqttSettings, SensorConfigSettings
from jeelink2mqtt.state import (
    SharedState,
    build_shared_state,
    build_shared_state_logged,
)

# ======================================================================
# Helpers
# ======================================================================


def _make_settings(
    *,
    sensor_names: list[str] | None = None,
    staleness_timeout: float = 600.0,
) -> Jeelink2MqttSettings:
    """Build settings with the given sensor names."""
    names = sensor_names if sensor_names is not None else ["office", "outdoor"]
    return Jeelink2MqttSettings(
        serial_port="/dev/ttyUSB0",
        staleness_timeout_seconds=staleness_timeout,
        sensors=[SensorConfigSettings(name=n) for n in names],
    )


# ======================================================================
# build_shared_state_logged
# ======================================================================


@pytest.mark.unit
class TestBuildSharedStateLogged:
    """build_shared_state_logged wraps build_shared_state with a log line."""

    def test_logs_readiness_summary(self, caplog: pytest.LogCaptureFixture) -> None:
        """Logs a one-line readiness summary naming every sensor.

        Technique: Specification-based — verifies the exact log contract
        documented on build_shared_state_logged.
        """
        settings = _make_settings(sensor_names=["office", "outdoor"])

        with caplog.at_level(logging.INFO, logger="jeelink2mqtt.state"):
            build_shared_state_logged(settings)

        assert "Shared state ready — 2 sensor(s): office, outdoor" in caplog.text

    def test_logs_none_for_empty_sensors(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """With no configured sensors, the summary says '(none)'.

        Technique: Boundary Value Analysis — zero-sensor edge case.
        """
        settings = _make_settings(sensor_names=[])

        with caplog.at_level(logging.INFO, logger="jeelink2mqtt.state"):
            build_shared_state_logged(settings)

        assert "Shared state ready — 0 sensor(s): (none)" in caplog.text

    def test_returns_equivalent_state_to_build_shared_state(self) -> None:
        """Returned SharedState matches build_shared_state's output for the same input.

        Technique: Round-trip/Equivalence — the logging wrapper must not alter
        the produced state, only add a log line.
        """
        settings = _make_settings(sensor_names=["office", "outdoor"])

        plain = build_shared_state(settings)
        logged = build_shared_state_logged(settings)

        assert isinstance(logged, SharedState)
        assert logged.sensor_configs.keys() == plain.sensor_configs.keys()
        assert logged.sensor_configs == plain.sensor_configs
        assert logged.registry.get_all_mappings() == plain.registry.get_all_mappings()
        assert type(logged.filter_bank) is type(plain.filter_bank)
