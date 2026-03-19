"""Unit tests for jeelink2mqtt.adapters.

Test Techniques Used:
- State Transition Testing: Adapter lifecycle (open → callback → inject → close)
- Error Guessing: inject without callback raises RuntimeError
- Specification-based Testing: No-op methods don't crash
- Boundary Value Analysis: Frame regex edge cases (negative temps, zero)
"""

from __future__ import annotations

import pytest

from jeelink2mqtt.adapters import _FRAME_RE, FakeJeeLinkAdapter
from jeelink2mqtt.models import SensorReading

# ======================================================================
# Frame regex (_FRAME_RE)
# ======================================================================


@pytest.mark.unit
class TestFrameRegex:
    """Boundary Value Analysis for the pylacrosse frame regex."""

    def test_positive_temperature(self) -> None:
        """Standard positive temperature parses correctly.

        Technique: Specification-based — happy path.
        """
        match = _FRAME_RE.search("id=42 t=21.5 h=55 nbat=0")
        assert match is not None
        assert match.group(1) == "42"
        assert match.group(2) == "21.5"
        assert match.group(3) == "55"
        assert match.group(4) == "0"

    def test_negative_temperature(self) -> None:
        """Sub-zero temperature (winter outdoor) parses correctly.

        Technique: Boundary Value Analysis — sign change boundary.
        Regression: Codex review caught that the original regex
        ``[\\d.]+`` silently dropped negative readings.
        """
        match = _FRAME_RE.search("id=17 t=-2.1 h=80 nbat=0")
        assert match is not None
        assert match.group(2) == "-2.1"

    def test_zero_temperature(self) -> None:
        """Exactly 0.0 °C parses correctly.

        Technique: Boundary Value Analysis — zero boundary.
        """
        match = _FRAME_RE.search("id=5 t=0.0 h=90 nbat=1")
        assert match is not None
        assert match.group(2) == "0.0"

    def test_large_negative_temperature(self) -> None:
        """Extreme cold (-40 °C, LaCrosse sensor lower bound) parses.

        Technique: Boundary Value Analysis — lower bound.
        """
        match = _FRAME_RE.search("id=99 t=-40.0 h=100 nbat=0")
        assert match is not None
        assert match.group(2) == "-40.0"

    def test_malformed_frame_returns_none(self) -> None:
        """Garbage input yields no match.

        Technique: Error Guessing — unparsable input.
        """
        assert _FRAME_RE.search("garbage data") is None


# ======================================================================
# FakeJeeLinkAdapter lifecycle
# ======================================================================


@pytest.mark.unit
class TestFakeJeeLinkAdapterLifecycle:
    """State Transition tests for FakeJeeLinkAdapter open/close lifecycle."""

    def test_open_marks_adapter_open(self) -> None:
        """open() sets the internal _open flag.

        Technique: State Transition — closed → open.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act
        adapter.open()

        # Assert
        assert adapter._open is True

    def test_close_marks_adapter_closed(self) -> None:
        """close() clears the _open flag.

        Technique: State Transition — open → closed.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()
        adapter.open()

        # Act
        adapter.close()

        # Assert
        assert adapter._open is False

    def test_close_clears_callback(self, make_reading) -> None:
        """close() removes the registered callback.

        Technique: State Transition — callback registered → cleared.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()
        adapter.register_callback(lambda r: None)

        # Act
        adapter.close()

        # Assert — inject should now raise because callback is gone
        with pytest.raises(RuntimeError, match="No callback registered"):
            adapter.inject(make_reading())


@pytest.mark.unit
class TestFakeJeeLinkAdapterInject:
    """Specification-based tests for inject/inject_batch."""

    def test_inject_without_callback_raises_runtime_error(self, make_reading) -> None:
        """inject() raises RuntimeError when no callback is registered.

        Technique: Error Guessing — missing precondition.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act / Assert
        with pytest.raises(RuntimeError, match="No callback registered"):
            adapter.inject(make_reading())

    def test_inject_calls_callback_with_reading(self, make_reading) -> None:
        """inject() forwards the reading to the registered callback.

        Technique: Specification-based — callback invocation.
        """
        # Arrange
        received: list[SensorReading] = []
        adapter = FakeJeeLinkAdapter()
        adapter.register_callback(received.append)
        reading = make_reading(sensor_id=42, temperature=21.5)

        # Act
        adapter.inject(reading)

        # Assert
        assert len(received) == 1
        assert received[0] is reading
        assert received[0].sensor_id == 42

    def test_inject_batch_calls_callback_for_each(self, make_reading) -> None:
        """inject_batch() invokes the callback once per reading.

        Technique: Specification-based — batch processing contract.
        """
        # Arrange
        received: list[SensorReading] = []
        adapter = FakeJeeLinkAdapter()
        adapter.register_callback(received.append)
        readings = [make_reading(sensor_id=i) for i in range(5)]

        # Act
        adapter.inject_batch(readings)

        # Assert
        assert len(received) == 5
        assert [r.sensor_id for r in received] == [0, 1, 2, 3, 4]

    def test_inject_batch_empty_list_is_noop(self) -> None:
        """inject_batch([]) with callback doesn't call it.

        Technique: Boundary Value Analysis — empty input.
        """
        # Arrange
        call_count = 0

        def counter(_: SensorReading) -> None:
            nonlocal call_count
            call_count += 1

        adapter = FakeJeeLinkAdapter()
        adapter.register_callback(counter)

        # Act
        adapter.inject_batch([])

        # Assert
        assert call_count == 0


@pytest.mark.unit
class TestFakeJeeLinkAdapterNoOps:
    """Specification-based tests — no-op methods don't crash."""

    def test_start_scan_is_noop(self) -> None:
        """start_scan() executes without error.

        Technique: Specification-based — no-op contract.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act / Assert — should not raise
        adapter.start_scan()

    def test_stop_scan_is_noop(self) -> None:
        """stop_scan() executes without error.

        Technique: Specification-based — no-op contract.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act / Assert — should not raise
        adapter.stop_scan()

    def test_set_led_is_noop(self) -> None:
        """set_led() executes without error.

        Technique: Specification-based — no-op contract.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act / Assert — should not raise
        adapter.set_led(True)
        adapter.set_led(False)
