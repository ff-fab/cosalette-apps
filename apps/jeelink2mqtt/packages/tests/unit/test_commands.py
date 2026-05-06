"""Unit tests for jeelink2mqtt.commands — mapping command handlers."""

from __future__ import annotations

import pytest

from jeelink2mqtt.app import SharedState
from jeelink2mqtt.commands import (
    MappingCommandPayloadError,
    _handle_assign,
    _handle_list_unknown,
    _handle_reset,
    _handle_reset_all,
    parse_command_payload,
)
from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import SensorConfig
from jeelink2mqtt.registry import SensorRegistry

# -- parse_command_payload ---------------------------------------------------


class TestParseCommandPayload:
    def test_parse_valid_json_object(self) -> None:
        """Valid JSON object is parsed correctly."""
        payload = '{"command": "assign", "sensor_name": "office"}'
        result = parse_command_payload(payload)
        assert result == {"command": "assign", "sensor_name": "office"}

    def test_parse_valid_json_object_with_error_key(self) -> None:
        """Valid JSON object with 'error' key is parsed correctly."""
        payload = '{"command": "assign", "sensor_name": "office", "error": "metadata"}'
        result = parse_command_payload(payload)
        assert result == {
            "command": "assign",
            "sensor_name": "office",
            "error": "metadata",
        }

    def test_parse_invalid_json_raises_exception(self) -> None:
        """Invalid JSON raises MappingCommandPayloadError."""
        payload = "not-json{{{{"
        with pytest.raises(MappingCommandPayloadError, match="Invalid JSON payload"):
            parse_command_payload(payload)

    def test_parse_non_object_json_raises_exception(self) -> None:
        """JSON that is not an object raises MappingCommandPayloadError."""
        payload = '"string"'
        with pytest.raises(
            MappingCommandPayloadError, match="JSON payload must be an object"
        ):
            parse_command_payload(payload)

        payload = "42"
        with pytest.raises(
            MappingCommandPayloadError, match="JSON payload must be an object"
        ):
            parse_command_payload(payload)

        payload = "[]"
        with pytest.raises(
            MappingCommandPayloadError, match="JSON payload must be an object"
        ):
            parse_command_payload(payload)


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

    def test_assign_success_with_error_key(self, state: SharedState) -> None:
        """Valid assign payload with 'error' key succeeds."""
        result = _handle_assign(
            state, {"sensor_name": "office", "sensor_id": 42, "error": "metadata"}
        )
        assert result["status"] == "ok"
        assert result["event"]["sensor_name"] == "office"
        assert result["event"]["new_sensor_id"] == 42
        # Check that the assignment was persisted to the registry
        assert state.registry.resolve(42) == "office"

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
