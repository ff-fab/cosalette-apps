"""Unit tests for jeelink2mqtt.commands — mapping command handlers."""

from __future__ import annotations


import pytest

from jeelink2mqtt.app import SharedState
from jeelink2mqtt.commands import (
    _handle_assign,
    _handle_list_unknown,
    _handle_reset,
    _handle_reset_all,
)
from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import SensorConfig
from jeelink2mqtt.registry import SensorRegistry


@pytest.fixture
def state(sensor_configs: list[SensorConfig]) -> SharedState:
    """SharedState wired with a fresh registry and filter bank."""
    registry = SensorRegistry(
        sensors=sensor_configs,
        staleness_timeout=600.0,
    )
    return SharedState(
        registry=registry,
        filter_bank=FilterBank(window=5),
        sensor_configs={c.name: c for c in sensor_configs},
    )


# -- _handle_assign ----------------------------------------------------------


class TestHandleAssign:
    def test_assign_success(self, state: SharedState) -> None:
        result = _handle_assign(state, {"sensor_name": "office", "sensor_id": 42})
        assert result["status"] == "ok"
        assert result["event"]["sensor_name"] == "office"
        assert result["event"]["new_sensor_id"] == 42

    def test_assign_missing_sensor_name(self, state: SharedState) -> None:
        result = _handle_assign(state, {"sensor_id": 42})
        assert "error" in result

    def test_assign_missing_sensor_id(self, state: SharedState) -> None:
        result = _handle_assign(state, {"sensor_name": "office"})
        assert "error" in result

    def test_assign_unknown_name(self, state: SharedState) -> None:
        result = _handle_assign(state, {"sensor_name": "nonexistent", "sensor_id": 42})
        assert "error" in result

    def test_assign_conflict(self, state: SharedState) -> None:
        _handle_assign(state, {"sensor_name": "office", "sensor_id": 42})
        result = _handle_assign(state, {"sensor_name": "outdoor", "sensor_id": 42})
        assert "error" in result


# -- _handle_reset ------------------------------------------------------------


class TestHandleReset:
    def test_reset_existing_mapping(self, state: SharedState) -> None:
        _handle_assign(state, {"sensor_name": "office", "sensor_id": 42})
        result = _handle_reset(state, {"sensor_name": "office"})
        assert result["status"] == "ok"
        assert result["event"]["sensor_name"] == "office"

    def test_reset_nonexistent_mapping(self, state: SharedState) -> None:
        result = _handle_reset(state, {"sensor_name": "office"})
        assert result["status"] == "ok"
        assert "message" in result

    def test_reset_missing_sensor_name(self, state: SharedState) -> None:
        result = _handle_reset(state, {})
        assert "error" in result


# -- _handle_reset_all --------------------------------------------------------


class TestHandleResetAll:
    def test_reset_all_clears_mappings(self, state: SharedState) -> None:
        _handle_assign(state, {"sensor_name": "office", "sensor_id": 42})
        _handle_assign(state, {"sensor_name": "outdoor", "sensor_id": 43})
        result = _handle_reset_all(state, {})
        assert result["status"] == "ok"
        assert result["cleared"] == 2

    def test_reset_all_empty_registry(self, state: SharedState) -> None:
        result = _handle_reset_all(state, {})
        assert result["status"] == "ok"
        assert result["cleared"] == 0


# -- _handle_list_unknown -----------------------------------------------------


class TestHandleListUnknown:
    def test_list_unknown_empty(self, state: SharedState) -> None:
        result = _handle_list_unknown(state, {})
        assert result["status"] == "ok"
        assert result["unknown_sensors"] == {}

    def test_list_unknown_with_unmapped(self, state: SharedState, make_reading) -> None:
        reading = make_reading(sensor_id=99)
        state.registry.record_reading(reading)
        result = _handle_list_unknown(state, {})
        assert "99" in result["unknown_sensors"]
