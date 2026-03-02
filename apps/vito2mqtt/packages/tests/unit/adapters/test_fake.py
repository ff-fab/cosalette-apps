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

"""Unit tests for FakeOptolinkAdapter.

Test Techniques Used:
- Protocol conformance: isinstance check against OptolinkPort
- Default value coverage: Verify every type code returns a sensible default
- Custom response injection: Override defaults with constructor parameter
- Write tracking: Verify writes are recorded for test assertions
- Language parameterization: Test DE vs EN defaults for enum types
- AAA pattern: Arrange-Act-Assert structure throughout
"""

from __future__ import annotations

from datetime import datetime

import pytest

from vito2mqtt.adapters.fake import FakeOptolinkAdapter, _get_default
from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.errors import CommandNotWritableError, InvalidSignalError
from vito2mqtt.optolink.codec import ReturnStatus
from vito2mqtt.ports import OptolinkPort

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """FakeOptolinkAdapter must satisfy the OptolinkPort protocol."""

    def test_fake_adapter_isinstance_optolink_port(self) -> None:
        """Structural subtyping — adapter implements all protocol methods.

        Technique: PEP 544 runtime_checkable isinstance check.
        """
        adapter = FakeOptolinkAdapter()
        assert isinstance(adapter, OptolinkPort)


# ---------------------------------------------------------------------------
# Default responses by type code
# ---------------------------------------------------------------------------


class TestDefaultResponses:
    """Verify each type_code returns a sensible default value."""

    async def test_default_is10_returns_float(self) -> None:
        """IS10 signals (e.g. outdoor_temperature) default to 20.5."""
        adapter = FakeOptolinkAdapter()
        result = await adapter.read_signal("outdoor_temperature")
        assert result == 20.5

    async def test_default_iunon_returns_int(self) -> None:
        """IUNON signals (e.g. burner_modulation) default to 42."""
        adapter = FakeOptolinkAdapter()
        result = await adapter.read_signal("burner_modulation")
        assert result == 42

    async def test_default_iu3600_returns_float(self) -> None:
        """IU3600 signals (e.g. burner_hours_stage1) default to 1.5."""
        adapter = FakeOptolinkAdapter()
        result = await adapter.read_signal("burner_hours_stage1")
        assert result == 1.5

    async def test_default_pr2_returns_int(self) -> None:
        """PR2 signals (e.g. pump_speed_m2) default to 128."""
        adapter = FakeOptolinkAdapter()
        result = await adapter.read_signal("pump_speed_m2")
        assert result == 128

    async def test_default_pr3_returns_float(self) -> None:
        """PR3 signals (e.g. plant_power_output) default to 50.0."""
        adapter = FakeOptolinkAdapter()
        result = await adapter.read_signal("plant_power_output")
        assert result == 50.0

    async def test_default_ba_returns_string_en(self) -> None:
        """BA signals (e.g. operating_mode_m1) default to 'shutdown' in EN."""
        adapter = FakeOptolinkAdapter()
        result = await adapter.read_signal("operating_mode_m1")
        assert result == "shutdown"

    async def test_default_usv_returns_string_en(self) -> None:
        """USV signals (e.g. switch_valve_status) default to 'undefined' in EN."""
        adapter = FakeOptolinkAdapter()
        result = await adapter.read_signal("switch_valve_status")
        assert result == "undefined"

    async def test_default_es_returns_list_en(self) -> None:
        """ES signals (e.g. error_history_1) default to [label, datetime] in EN."""
        adapter = FakeOptolinkAdapter()
        result = await adapter.read_signal("error_history_1")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == "normal operation (no error)"
        assert result[1] == datetime(2026, 1, 1)

    async def test_default_rt_returns_return_status(self) -> None:
        """RT signals (e.g. internal_pump_status) default to ReturnStatus.OFF."""
        adapter = FakeOptolinkAdapter()
        result = await adapter.read_signal("internal_pump_status")
        assert result == ReturnStatus.OFF

    def test_default_ct_returns_empty_schedule(self) -> None:
        """CT default returns an empty schedule.

        All CT signals are WRITE-only in the command registry, so we
        test the default factory directly rather than via read_signal.

        Technique: Specification-based — validate internal default.
        """
        result = _get_default("CT", "en")
        assert isinstance(result, list)
        assert len(result) == 4
        for pair in result:
            for slot in pair:
                assert slot == [None, None]

    def test_default_ti_returns_datetime(self) -> None:
        """TI default returns current-ish datetime.

        All TI signals are WRITE-only in the command registry, so we
        test the default factory directly rather than via read_signal.

        Technique: Specification-based — validate internal default.
        """
        result = _get_default("TI", "en")
        assert isinstance(result, datetime)


# ---------------------------------------------------------------------------
# Custom responses
# ---------------------------------------------------------------------------


class TestCustomResponses:
    """Verify that constructor-provided responses override defaults."""

    async def test_custom_response_overrides_default(self) -> None:
        """Custom value takes precedence over type-based default."""
        adapter = FakeOptolinkAdapter(responses={"outdoor_temperature": 25.0})
        result = await adapter.read_signal("outdoor_temperature")
        assert result == 25.0

    async def test_non_overridden_signal_uses_default(self) -> None:
        """Signals not in responses dict still use type-based defaults."""
        adapter = FakeOptolinkAdapter(responses={"outdoor_temperature": 25.0})
        result = await adapter.read_signal("burner_modulation")
        assert result == 42  # IUNON default


# ---------------------------------------------------------------------------
# Signal validation
# ---------------------------------------------------------------------------


class TestSignalValidation:
    """Validate signal name and access mode checks."""

    async def test_read_signal_unknown_name_raises_invalid_signal(self) -> None:
        """Unknown signal name raises InvalidSignalError."""
        adapter = FakeOptolinkAdapter()
        with pytest.raises(InvalidSignalError, match="Unknown signal"):
            await adapter.read_signal("nonexistent_signal")

    async def test_write_signal_unknown_name_raises_invalid_signal(self) -> None:
        """Unknown signal name on write raises InvalidSignalError."""
        adapter = FakeOptolinkAdapter()
        with pytest.raises(InvalidSignalError, match="Unknown signal"):
            await adapter.write_signal("nonexistent_signal", 42)

    async def test_write_signal_read_only_raises_not_writable(self) -> None:
        """Writing a READ-only signal raises CommandNotWritableError.

        ``outdoor_temperature`` is ``AccessMode.READ`` — writing must fail.
        """
        adapter = FakeOptolinkAdapter()
        with pytest.raises(CommandNotWritableError, match="read-only"):
            await adapter.write_signal("outdoor_temperature", 20.0)

    async def test_read_signal_write_only_raises_invalid_signal(self) -> None:
        """Reading a WRITE-only signal raises InvalidSignalError.

        ``hot_water_setpoint`` is ``AccessMode.WRITE`` — reading must fail.
        Ensures behavioral parity with OptolinkAdapter.

        Technique: Error Guessing — write-only guard on read path.
        """
        adapter = FakeOptolinkAdapter()
        with pytest.raises(InvalidSignalError, match="write-only"):
            await adapter.read_signal("hot_water_setpoint")


# ---------------------------------------------------------------------------
# Write tracking
# ---------------------------------------------------------------------------


class TestWriteTracking:
    """Verify writes are recorded for test assertions."""

    async def test_write_signal_stores_value(self) -> None:
        """After write_signal, the value appears in adapter.writes."""
        adapter = FakeOptolinkAdapter()
        await adapter.write_signal("hot_water_setpoint", 50)
        assert adapter.writes["hot_water_setpoint"] == 50

    async def test_multiple_writes_tracked(self) -> None:
        """Multiple writes to different signals are all tracked."""
        adapter = FakeOptolinkAdapter()
        await adapter.write_signal("hot_water_setpoint", 50)
        await adapter.write_signal("room_temperature_setpoint_m1", 22)
        assert adapter.writes == {
            "hot_water_setpoint": 50,
            "room_temperature_setpoint_m1": 22,
        }

    async def test_write_overwrites_previous_value(self) -> None:
        """Writing the same signal twice keeps only the last value."""
        adapter = FakeOptolinkAdapter()
        await adapter.write_signal("hot_water_setpoint", 50)
        await adapter.write_signal("hot_water_setpoint", 55)
        assert adapter.writes["hot_water_setpoint"] == 55


# ---------------------------------------------------------------------------
# Batch read
# ---------------------------------------------------------------------------


class TestReadSignals:
    """Verify read_signals returns a dict of decoded values."""

    async def test_read_signals_returns_dict(self) -> None:
        """Batch read returns {name: value} for each signal."""
        adapter = FakeOptolinkAdapter(
            responses={"outdoor_temperature": 18.5, "burner_modulation": 75}
        )
        result = await adapter.read_signals(
            ["outdoor_temperature", "burner_modulation"]
        )
        assert result == {"outdoor_temperature": 18.5, "burner_modulation": 75}


# ---------------------------------------------------------------------------
# Language support
# ---------------------------------------------------------------------------


class TestLanguageSupport:
    """Verify DE vs EN default values for language-dependent types."""

    async def test_ba_default_de(
        self, vito2mqtt_settings_de: Vito2MqttSettings
    ) -> None:
        """BA defaults to 'Abschaltbetrieb' in German."""
        adapter = FakeOptolinkAdapter(settings=vito2mqtt_settings_de)
        result = await adapter.read_signal("operating_mode_m1")
        assert result == "Abschaltbetrieb"

    async def test_usv_default_de(
        self, vito2mqtt_settings_de: Vito2MqttSettings
    ) -> None:
        """USV defaults to 'undefiniert' in German."""
        adapter = FakeOptolinkAdapter(settings=vito2mqtt_settings_de)
        result = await adapter.read_signal("switch_valve_status")
        assert result == "undefiniert"

    async def test_es_default_de(
        self, vito2mqtt_settings_de: Vito2MqttSettings
    ) -> None:
        """ES defaults to German error label in German mode."""
        adapter = FakeOptolinkAdapter(settings=vito2mqtt_settings_de)
        result = await adapter.read_signal("error_history_1")
        assert result[0] == "Regelbetrieb (kein Fehler)"
        assert result[1] == datetime(2026, 1, 1)

    async def test_ba_default_en(self, vito2mqtt_settings: Vito2MqttSettings) -> None:
        """BA defaults to 'shutdown' in English."""
        adapter = FakeOptolinkAdapter(settings=vito2mqtt_settings)
        result = await adapter.read_signal("operating_mode_m1")
        assert result == "shutdown"


# ---------------------------------------------------------------------------
# Async context manager
# ---------------------------------------------------------------------------


class TestAsyncContextManager:
    """Verify __aenter__/__aexit__ work correctly."""

    async def test_context_manager_returns_self(self) -> None:
        """async with adapter returns the adapter itself."""
        adapter = FakeOptolinkAdapter()
        async with adapter as ctx:
            assert ctx is adapter
