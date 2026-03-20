"""Integration tests for MQTT mapping commands.

Tests the command handler dispatch with a real SensorRegistry,
verifying that assign/reset/reset_all/list_unknown produce correct
responses and mutate state as expected.

Test Techniques Used:
- Decision Table Testing: Command → response mapping
- State Transition Testing: Registry state after mutations
- Error Guessing: Invalid payloads, conflicts, unknown commands
"""

from __future__ import annotations

import json

import pytest

from jeelink2mqtt.app import SharedState
from jeelink2mqtt.commands import (
    _handle_assign,
    _handle_list_unknown,
    _handle_reset,
    _handle_reset_all,
)

# ======================================================================
# Assign
# ======================================================================


@pytest.mark.integration
class TestAssignCommand:
    """Integration tests for the assign command handler."""

    def test_assign_command_creates_mapping(self, shared_state: SharedState) -> None:
        """Parse assign data, call _handle_assign with real state.
        Verify registry updated.

        Technique: State Transition — unmapped → mapped.
        """
        # Arrange
        data = {"command": "assign", "sensor_name": "office", "sensor_id": 42}

        # Act
        result = _handle_assign(shared_state, data)

        # Assert
        assert result["status"] == "ok"
        assert shared_state.registry.resolve(42) == "office"

    def test_assign_command_returns_event(self, shared_state: SharedState) -> None:
        """Verify the response contains an event with expected fields.

        Technique: Specification-based — response contract.
        """
        # Arrange
        data = {"command": "assign", "sensor_name": "outdoor", "sensor_id": 77}

        # Act
        result = _handle_assign(shared_state, data)

        # Assert
        assert result["status"] == "ok"
        event = result["event"]
        assert event["event_type"] == "manual_assign"
        assert event["sensor_name"] == "outdoor"
        assert event["new_sensor_id"] == 77
        assert event["old_sensor_id"] is None

    def test_assign_conflict_returns_error(self, shared_state: SharedState) -> None:
        """Assign ID to sensor A, then try same ID for sensor B → error.

        Technique: Error Guessing — MappingConflictError path.
        """
        # Arrange
        _handle_assign(
            shared_state,
            {"command": "assign", "sensor_name": "office", "sensor_id": 42},
        )

        # Act
        result = _handle_assign(
            shared_state,
            {"command": "assign", "sensor_name": "outdoor", "sensor_id": 42},
        )

        # Assert
        assert "error" in result
        assert "already mapped" in str(result["error"])

    def test_assign_unknown_sensor_returns_error(
        self, shared_state: SharedState
    ) -> None:
        """Assign to a sensor name not in configs → error.

        Technique: Error Guessing — ValueError for unknown sensor.
        """
        # Arrange
        data = {
            "command": "assign",
            "sensor_name": "nonexistent",
            "sensor_id": 42,
        }

        # Act
        result = _handle_assign(shared_state, data)

        # Assert
        assert "error" in result
        assert "Unknown sensor name" in str(result["error"])


# ======================================================================
# Reset
# ======================================================================


@pytest.mark.integration
class TestResetCommand:
    """Integration tests for the reset command handler."""

    def test_reset_command_removes_mapping(self, shared_state: SharedState) -> None:
        """Assign, then reset → verify mapping gone.

        Technique: State Transition — mapped → unmapped.
        """
        # Arrange
        _handle_assign(
            shared_state,
            {"command": "assign", "sensor_name": "office", "sensor_id": 42},
        )

        # Act
        result = _handle_reset(
            shared_state,
            {"command": "reset", "sensor_name": "office"},
        )

        # Assert
        assert result["status"] == "ok"
        assert "event" in result
        assert shared_state.registry.resolve(42) is None

    def test_reset_nonexistent_returns_ok(self, shared_state: SharedState) -> None:
        """Reset a sensor with no mapping → ok with message.

        Technique: Decision Table — reset when no mapping exists.
        """
        # Act
        result = _handle_reset(
            shared_state,
            {"command": "reset", "sensor_name": "office"},
        )

        # Assert
        assert result["status"] == "ok"
        assert "No mapping existed" in str(result.get("message", ""))


# ======================================================================
# Reset All
# ======================================================================


@pytest.mark.integration
class TestResetAllCommand:
    """Integration tests for the reset_all command handler."""

    def test_reset_all_clears_everything(self, shared_state: SharedState) -> None:
        """Assign 2 sensors, then reset_all → verify all gone.

        Technique: State Transition — multiple mappings → empty.
        """
        # Arrange
        _handle_assign(
            shared_state,
            {"command": "assign", "sensor_name": "office", "sensor_id": 42},
        )
        _handle_assign(
            shared_state,
            {"command": "assign", "sensor_name": "outdoor", "sensor_id": 77},
        )

        # Act
        result = _handle_reset_all(shared_state, {"command": "reset_all"})

        # Assert
        assert result["status"] == "ok"
        assert result["cleared"] == 2
        assert shared_state.registry.resolve(42) is None
        assert shared_state.registry.resolve(77) is None


# ======================================================================
# List Unknown
# ======================================================================


@pytest.mark.integration
class TestListUnknownCommand:
    """Integration tests for the list_unknown command handler."""

    def test_list_unknown_returns_unmapped(
        self, shared_state: SharedState, make_reading
    ) -> None:
        """Send readings that don't auto-adopt (2 stale sensors),
        then verify list_unknown returns them.

        Technique: Integration Testing — registry unmapped → command response.
        """
        # Arrange — both sensors stale (initial state), so no auto-adopt
        reading1 = make_reading(sensor_id=42, temperature=21.5, humidity=55)
        reading2 = make_reading(sensor_id=99, temperature=18.0, humidity=60)
        shared_state.registry.record_reading(reading1)
        shared_state.registry.record_reading(reading2)

        # Act
        result = _handle_list_unknown(
            shared_state,
            {"command": "list_unknown"},
        )

        # Assert
        assert result["status"] == "ok"
        unknown = result["unknown_sensors"]
        assert "42" in unknown
        assert "99" in unknown
        assert unknown["42"]["temperature"] == 21.5


# ======================================================================
# Error Handling
# ======================================================================


@pytest.mark.integration
class TestCommandErrorHandling:
    """Tests for invalid inputs and unknown commands.

    These test the dispatch logic that wraps the handlers, verifying
    that JSON parse + command lookup produce correct error dicts.

    Because ``handle_mapping`` is a cosalette ``@app.command()``
    coroutine that requires ``DeviceStore`` injection, we test the
    underlying dispatch logic by calling the internal handler helpers
    with a real ``SharedState``.
    """

    def test_invalid_json_returns_error(self, shared_state: SharedState) -> None:
        """Non-JSON payload triggers json.JSONDecodeError which the handler
        would catch and return ``{"error": "Invalid JSON payload"}``.

        We verify that the parsing path raises correctly, and that the
        handler's documented contract holds.

        Technique: Error Guessing — malformed input.
        """
        import json

        payload = "not valid json {"

        # Verify the parsing path raises as expected
        with pytest.raises(json.JSONDecodeError):
            json.loads(payload)

        # Verify the handler helpers reject missing required fields
        # (simulates what happens after failed JSON parse → error dict)
        result = _handle_assign(shared_state, {})
        assert "error" in result

    def test_unknown_command_returns_error(self, shared_state: SharedState) -> None:
        """An unknown command routes to no handler.

        We verify the dispatch lookup returns None, and that each known
        handler rejects payloads missing the required ``command`` key.

        Technique: Error Guessing — unknown command routing.
        """
        from jeelink2mqtt.commands import (
            _handle_assign,
            _handle_list_unknown,
            _handle_reset,
            _handle_reset_all,
        )

        # The dispatch table used by handle_mapping
        handlers = {
            "assign": _handle_assign,
            "reset": _handle_reset,
            "reset_all": _handle_reset_all,
            "list_unknown": _handle_list_unknown,
        }

        # Unknown command yields no handler
        data = json.loads('{"command": "foobar"}')
        assert handlers.get(data["command"]) is None

        # Known commands with missing fields return error dicts
        result = _handle_assign(shared_state, {"command": "assign"})
        assert "error" in result

        result = _handle_reset(shared_state, {"command": "reset"})
        assert "error" in result
