"""Unit tests for GPIO adapters (FakeGpio test double and GpiozeroAdapter health check).

Test Techniques Used:
- State Transition Testing: GPIO adapter lifecycle (init → press → cleanup)
- Specification-based Testing: Async context manager enter/exit behavior
- Specification-based Testing: GpiozeroAdapter health_check GPIO-device probing
"""

import pytest

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

    async def test_health_check_returns_true(self) -> None:
        """health_check always returns True for the fake adapter.

        Technique: Specification-based — test double is unconditionally healthy.
        """
        fake = FakeGpio()

        result = await fake.health_check()

        assert result is True


@pytest.mark.unit
class TestGpiozeroAdapterHealthCheck:
    """Specification-based tests for GpiozeroAdapter.health_check GPIO-device probing."""

    async def test_returns_true_when_gpiochip0_exists(self) -> None:
        """health_check returns True when /dev/gpiochip0 is present.

        Technique: Specification-based — GPIO character device accessible → healthy.
        """
        from unittest.mock import patch

        from velux2mqtt.adapters.gpiozero_adapter import GpiozeroAdapter
        from velux2mqtt.settings import CoverConfig, Velux2MqttSettings

        settings = Velux2MqttSettings(
            covers=[
                CoverConfig(
                    name="blind",
                    pin_up=1,
                    pin_stop=2,
                    pin_down=3,
                    travel_duration_up=10.0,
                    travel_duration_down=12.0,
                )
            ]
        )
        adapter = GpiozeroAdapter(settings)

        with patch("os.path.exists", return_value=True):
            result = await adapter.health_check()

        assert result is True

    async def test_returns_false_when_gpiochip0_missing(self) -> None:
        """health_check returns False when /dev/gpiochip0 is absent.

        Technique: Error Guessing — GPIO subsystem unavailable → unhealthy.
        """
        from unittest.mock import patch

        from velux2mqtt.adapters.gpiozero_adapter import GpiozeroAdapter
        from velux2mqtt.settings import CoverConfig, Velux2MqttSettings

        settings = Velux2MqttSettings(
            covers=[
                CoverConfig(
                    name="blind",
                    pin_up=1,
                    pin_stop=2,
                    pin_down=3,
                    travel_duration_up=10.0,
                    travel_duration_down=12.0,
                )
            ]
        )
        adapter = GpiozeroAdapter(settings)

        with patch("os.path.exists", return_value=False):
            result = await adapter.health_check()

        assert result is False

    async def test_probes_gpiochip0_path(self) -> None:
        """health_check probes the /dev/gpiochip0 device path specifically.

        Technique: Specification-based — confirms the exact probe path so
        any future refactor that changes the path fails loudly.
        """
        from unittest.mock import patch

        from velux2mqtt.adapters.gpiozero_adapter import GpiozeroAdapter
        from velux2mqtt.settings import CoverConfig, Velux2MqttSettings

        settings = Velux2MqttSettings(
            covers=[
                CoverConfig(
                    name="blind",
                    pin_up=1,
                    pin_stop=2,
                    pin_down=3,
                    travel_duration_up=10.0,
                    travel_duration_down=12.0,
                )
            ]
        )
        adapter = GpiozeroAdapter(settings)

        with patch("os.path.exists", return_value=True) as mock_exists:
            await adapter.health_check()

        mock_exists.assert_called_once_with("/dev/gpiochip0")
