"""Unit tests for GPIO adapters (FakeGpio test double).

Test Techniques Used:
- State Transition Testing: GPIO adapter lifecycle (init → press → cleanup)
- Specification-based Testing: Async context manager enter/exit behavior
"""

from velux2mqtt.adapters.fake import FakeGpio, PressCall


class TestFakeGpio:
    """Tests for the FakeGpio test double."""

    def test_initial_state(self) -> None:
        """FakeGpio starts un-initialized with no recorded calls."""
        fake = FakeGpio()

        assert fake.presses == []
        assert fake.initialized_pins == []
        assert fake.is_initialized is False
        assert fake.is_closed is False

    def test_initialize_records_pins(self) -> None:
        """initialize() records the pin list and sets is_initialized."""
        fake = FakeGpio()

        fake.initialize([9, 10, 11])

        assert fake.initialized_pins == [9, 10, 11]
        assert fake.is_initialized is True

    async def test_press_records_call(self) -> None:
        """press() records pin and duration without delay."""
        fake = FakeGpio()

        await fake.press(9, 0.5)
        await fake.press(10, 0.3)

        assert fake.presses == [
            PressCall(pin=9, duration=0.5),
            PressCall(pin=10, duration=0.3),
        ]

    def test_cleanup_sets_flag(self) -> None:
        """cleanup() sets is_closed."""
        fake = FakeGpio()

        fake.cleanup()

        assert fake.is_closed is True

    async def test_async_context_manager(self) -> None:
        """Async context manager initializes on enter, cleans up on exit."""
        fake = FakeGpio()
        fake.initialized_pins = [9, 10, 11]

        async with fake as gpio:
            assert gpio.is_initialized is True
            assert gpio.is_closed is False

        assert fake.is_closed is True

    async def test_multiple_presses_ordered(self) -> None:
        """Press calls are recorded in order."""
        fake = FakeGpio()

        await fake.press(9, 0.5)
        await fake.press(11, 0.5)
        await fake.press(10, 0.5)

        pins = [p.pin for p in fake.presses]
        assert pins == [9, 11, 10]
