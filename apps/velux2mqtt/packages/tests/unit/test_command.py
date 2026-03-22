"""Unit tests for CoverCommand parsing.

Test Techniques Used:
- Equivalence Partitioning: Text, numeric, and JSON command payload variants
- Boundary Value Analysis: Position boundaries (0, 100, negative, >100)
- Error Guessing: Malformed JSON, empty payload, garbage text
"""

import pytest

from velux2mqtt.domain.command import (
    Direction,
    InvalidCommandError,
    parse_command,
)


class TestTextCommands:
    """Test plain-text command parsing."""

    @pytest.mark.parametrize("payload", ["up", "UP", "Up", "open", "OPEN", "Open"])
    def test_open_aliases(self, payload: str) -> None:
        cmd = parse_command(payload)
        assert cmd.direction == Direction.OPEN
        assert cmd.position == 100

    @pytest.mark.parametrize("payload", ["down", "DOWN", "close", "CLOSE"])
    def test_close_aliases(self, payload: str) -> None:
        cmd = parse_command(payload)
        assert cmd.direction == Direction.CLOSE
        assert cmd.position == 0

    @pytest.mark.parametrize("payload", ["stop", "STOP", "Stop"])
    def test_stop(self, payload: str) -> None:
        cmd = parse_command(payload)
        assert cmd.direction == Direction.STOP
        assert cmd.position is None


class TestNumericCommands:
    """Test numeric string command parsing."""

    def test_zero_is_close(self) -> None:
        cmd = parse_command("0")
        assert cmd.direction == Direction.CLOSE
        assert cmd.position == 0

    def test_hundred_is_open(self) -> None:
        cmd = parse_command("100")
        assert cmd.direction == Direction.OPEN
        assert cmd.position == 100

    def test_intermediate_position(self) -> None:
        cmd = parse_command("42")
        assert cmd.position == 42

    def test_negative_clamped_to_zero(self) -> None:
        cmd = parse_command("-10")
        assert cmd.position == 0
        assert cmd.direction == Direction.CLOSE

    def test_over_100_clamped(self) -> None:
        cmd = parse_command("150")
        assert cmd.position == 100
        assert cmd.direction == Direction.OPEN


class TestJsonCommands:
    """Test JSON command parsing."""

    def test_position_json(self) -> None:
        cmd = parse_command('{"position": 42}')
        assert cmd.position == 42

    def test_command_open_json(self) -> None:
        cmd = parse_command('{"command": "open"}')
        assert cmd.direction == Direction.OPEN
        assert cmd.position == 100

    def test_command_stop_json(self) -> None:
        cmd = parse_command('{"command": "stop"}')
        assert cmd.direction == Direction.STOP

    def test_position_zero_json(self) -> None:
        cmd = parse_command('{"position": 0}')
        assert cmd.direction == Direction.CLOSE

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(InvalidCommandError, match="invalid JSON"):
            parse_command("{bad json}")

    def test_unknown_command_in_json_raises(self) -> None:
        with pytest.raises(InvalidCommandError, match="unknown command"):
            parse_command('{"command": "explode"}')

    def test_invalid_position_value_raises(self) -> None:
        with pytest.raises(InvalidCommandError, match="invalid position value"):
            parse_command('{"position": "foo"}')

    def test_missing_keys_raises(self) -> None:
        with pytest.raises(InvalidCommandError, match="must contain"):
            parse_command('{"foo": "bar"}')


class TestEdgeCases:
    """Test error handling and edge cases."""

    def test_empty_payload_raises(self) -> None:
        with pytest.raises(InvalidCommandError, match="empty"):
            parse_command("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(InvalidCommandError, match="empty"):
            parse_command("   ")

    def test_garbage_text_raises(self) -> None:
        with pytest.raises(InvalidCommandError, match="unrecognized"):
            parse_command("wiggle")

    def test_whitespace_trimmed(self) -> None:
        cmd = parse_command("  open  ")
        assert cmd.direction == Direction.OPEN
