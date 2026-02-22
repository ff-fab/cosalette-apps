"""Integration tests for gas2mqtt application wiring.

Verifies that ``create_app()`` correctly wires all components, that
the lifespan properly manages the magnetometer adapter lifecycle,
and that extracted device coroutines publish the expected MQTT state.

Test Techniques Used:
- Specification-based: App configuration matches expectations
- Integration: Real device coroutines exercised end-to-end
- State Transition: Lifespan startup/shutdown lifecycle
- Branch Coverage: Magnetometer early-return when disabled
- Error Guessing: Lifespan closes adapter even on error
"""

from __future__ import annotations

import asyncio
import json

import cosalette
import pytest
from cosalette.testing import FakeClock, MockMqttClient

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.devices.magnetometer import magnetometer_device
from gas2mqtt.devices.temperature import temperature_device
from gas2mqtt.main import create_app, lifespan
from gas2mqtt.ports import MagnetometerPort
from tests.fixtures.config import make_gas2mqtt_settings

# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAppCreation:
    """Verify create_app() produces a properly configured App."""

    def test_creates_app_instance(self) -> None:
        """create_app() returns a cosalette App.

        Technique: Specification-based — verifying factory contract.
        """
        # Act
        app = create_app()

        # Assert
        assert isinstance(app, cosalette.App)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLifespan:
    """Verify lifespan initializes and cleans up the magnetometer."""

    async def test_initializes_magnetometer(self) -> None:
        """Lifespan calls magnetometer.initialize() on startup.

        Technique: State Transition — verifying startup lifecycle.
        """
        # Arrange
        mag = FakeMagnetometer()
        ctx = cosalette.AppContext(
            settings=make_gas2mqtt_settings(),
            adapters={MagnetometerPort: mag},
        )

        # Act
        async with lifespan(ctx):
            # Assert
            assert mag.initialized is True

    async def test_closes_magnetometer(self) -> None:
        """Lifespan calls magnetometer.close() on shutdown.

        Technique: State Transition — verifying shutdown lifecycle.
        """
        # Arrange
        mag = FakeMagnetometer()
        ctx = cosalette.AppContext(
            settings=make_gas2mqtt_settings(),
            adapters={MagnetometerPort: mag},
        )

        # Act
        async with lifespan(ctx):
            pass

        # Assert
        assert mag.closed is True

    async def test_closes_on_error(self) -> None:
        """Lifespan closes magnetometer even if the body raises.

        Technique: Error Guessing — cleanup must happen on exceptions.
        """
        # Arrange
        mag = FakeMagnetometer()
        ctx = cosalette.AppContext(
            settings=make_gas2mqtt_settings(),
            adapters={MagnetometerPort: mag},
        )

        # Act
        with pytest.raises(RuntimeError, match="boom"):
            async with lifespan(ctx):
                raise RuntimeError("boom")

        # Assert
        assert mag.closed is True


# ---------------------------------------------------------------------------
# Temperature device wiring
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTemperatureDeviceWiring:
    """Verify temperature_device() publishes calibrated state via MQTT."""

    async def test_publishes_calibrated_temperature(self) -> None:
        """temperature_device() publishes initial state, then exits on shutdown.

        Technique: Integration — end-to-end data flow through the real
        device coroutine with shutdown pre-signalled so the loop exits
        after the initial publish.
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.temperature_raw = 2500  # → 0.008 * 2500 + 20.3 = 40.3
        settings = make_gas2mqtt_settings(temperature_interval=0.01)
        mqtt = MockMqttClient()
        shutdown = asyncio.Event()

        ctx = cosalette.DeviceContext(
            name="temperature",
            settings=settings,
            mqtt=mqtt,
            topic_prefix="gas2mqtt",
            shutdown_event=shutdown,
            adapters={MagnetometerPort: mag},
            clock=FakeClock(),
        )

        # Pre-signal shutdown so the loop exits after the initial publish
        shutdown.set()

        # Act
        await temperature_device(ctx)

        # Assert
        assert mqtt.publish_count >= 1
        topic, raw_payload, _retain, _qos = mqtt.published[0]
        assert topic == "gas2mqtt/temperature/state"
        payload = json.loads(raw_payload)
        assert payload["temperature"] == pytest.approx(40.3, abs=0.1)


# ---------------------------------------------------------------------------
# Debug magnetometer device wiring
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMagnetometerDeviceWiring:
    """Verify magnetometer_device() conditional behavior."""

    async def test_publishes_raw_values_when_enabled(self) -> None:
        """magnetometer_device() publishes raw bx/by/bz when enabled.

        Technique: Integration — real device coroutine exercised with
        shutdown pre-signalled so it exits after the initial publish.
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.bx = 100
        mag.by = -200
        mag.bz = -5000
        mqtt = MockMqttClient()
        shutdown = asyncio.Event()

        ctx = cosalette.DeviceContext(
            name="magnetometer",
            settings=make_gas2mqtt_settings(enable_debug_device=True),
            mqtt=mqtt,
            topic_prefix="gas2mqtt",
            shutdown_event=shutdown,
            adapters={MagnetometerPort: mag},
            clock=FakeClock(),
        )

        # Pre-signal shutdown so the loop exits after the initial publish
        shutdown.set()

        # Act
        await magnetometer_device(ctx)

        # Assert
        assert mqtt.publish_count >= 1
        topic, raw_payload, _retain, _qos = mqtt.published[0]
        assert topic == "gas2mqtt/magnetometer/state"
        payload = json.loads(raw_payload)
        assert payload == {"bx": 100, "by": -200, "bz": -5000}

    async def test_noop_when_disabled(self) -> None:
        """magnetometer_device() returns immediately when disabled.

        Technique: Branch Coverage — verifying the early-return path by
        calling the real device coroutine and asserting zero publishes.
        """
        # Arrange
        mag = FakeMagnetometer()
        mqtt = MockMqttClient()
        shutdown = asyncio.Event()

        ctx = cosalette.DeviceContext(
            name="magnetometer",
            settings=make_gas2mqtt_settings(enable_debug_device=False),
            mqtt=mqtt,
            topic_prefix="gas2mqtt",
            shutdown_event=shutdown,
            adapters={MagnetometerPort: mag},
            clock=FakeClock(),
        )

        # Act — call the real device coroutine
        await magnetometer_device(ctx)

        # Assert — no messages published when debug is off
        assert mqtt.publish_count == 0
