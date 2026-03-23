"""Integration test fixtures for velux2mqtt.

Provides a fully-wired App instance backed by in-memory test doubles
(FakeGpio, MockMqttClient) so integration tests can drive the real
application logic without real GPIO or MQTT I/O.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient

from velux2mqtt.adapters.fake import FakeGpio
from velux2mqtt.devices.cover import make_cover
from velux2mqtt.ports import GpioSwitchPort
from velux2mqtt.settings import CoverConfig, Velux2MqttSettings

TOPIC_PREFIX = "velux2mqtt"
"""Default MQTT topic prefix used by integration tests."""

BLIND_CFG = CoverConfig(
    name="blind",
    pin_up=17,
    pin_stop=27,
    pin_down=22,
    travel_duration_up=0.05,
    travel_duration_down=0.05,
    travel_time_offset=0.0,
    max_timer_margin=0.02,
    measure_offset=True,
)

WINDOW_CFG = CoverConfig(
    name="window",
    pin_up=5,
    pin_stop=6,
    pin_down=13,
    travel_duration_up=0.05,
    travel_duration_down=0.05,
    travel_time_offset=0.0,
    max_timer_margin=0.02,
)

TWO_COVERS = [BLIND_CFG, WINDOW_CFG]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_integration_app(
    fake_gpio: FakeGpio,
    settings: Velux2MqttSettings,
) -> App:
    """Construct a fully-wired App with 2 covers backed by *fake_gpio*.

    Mirrors the wiring in ``velux2mqtt.main`` but replaces the GPIO
    adapter with a shared FakeGpio instance so tests can inspect
    recorded presses.
    """
    app = App(
        name="velux2mqtt",
        version="0.0.0",
        description="Velux cover control via KLF 050 remotes and GPIO",
        settings_class=Velux2MqttSettings,
        adapters={GpioSwitchPort: lambda: fake_gpio},
    )
    for cover_cfg in settings.covers:
        app.add_device(cover_cfg.name, make_cover(cover_cfg, settings))
    return app


async def run_app_briefly(
    app: App,
    mock_mqtt: MockMqttClient,
    test_settings: Velux2MqttSettings,
    *,
    wait: float = 0.3,
) -> None:
    """Start the app as a background task, wait, then shut it down cleanly."""
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        app._run_async(
            mqtt=mock_mqtt,
            settings=test_settings,
            shutdown_event=shutdown_event,
        )
    )
    await asyncio.sleep(wait)
    shutdown_event.set()
    await task


async def run_app_with_commands(
    app: App,
    mock_mqtt: MockMqttClient,
    test_settings: Velux2MqttSettings,
    commands: list[tuple[str, str]],
    *,
    startup_wait: float = 0.15,
    per_command_wait: float = 0.1,
) -> None:
    """Start the app, deliver commands, then shut down cleanly.

    Args:
        app: Fully-wired App instance.
        mock_mqtt: MockMqttClient to use for MQTT I/O.
        test_settings: Settings (used by _run_async).
        commands: Ordered list of (topic, payload) pairs to deliver.
        startup_wait: Seconds to wait before delivering first command.
        per_command_wait: Seconds to wait after each delivered command.
    """
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        app._run_async(
            mqtt=mock_mqtt,
            settings=test_settings,
            shutdown_event=shutdown_event,
        )
    )
    await asyncio.sleep(startup_wait)
    for topic, payload in commands:
        await mock_mqtt.deliver(topic, payload)
        await asyncio.sleep(per_command_wait)
    shutdown_event.set()
    await task


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_gpio() -> FakeGpio:
    """A fresh FakeGpio that records all presses."""
    return FakeGpio()


@pytest.fixture
def mock_mqtt() -> MockMqttClient:
    """A fresh MockMqttClient that records all publishes."""
    return MockMqttClient()


@pytest.fixture
def test_settings() -> Velux2MqttSettings:
    """Settings with 2 covers and homing enabled for integration tests."""
    return Velux2MqttSettings(
        covers=TWO_COVERS,
        enable_startup_homing=True,
        homing_direction="close",
        button_press_duration=0.5,
        calibration_runs=3,
        drift_recalibration_threshold=2,
    )


@pytest.fixture
def test_settings_no_homing() -> Velux2MqttSettings:
    """Settings with 2 covers and homing disabled."""
    return Velux2MqttSettings(
        covers=TWO_COVERS,
        enable_startup_homing=False,
        button_press_duration=0.5,
        drift_recalibration_threshold=2,
    )


@pytest.fixture
def integration_app(
    fake_gpio: FakeGpio,
    test_settings: Velux2MqttSettings,
) -> App:
    """Fully-wired App with 2 covers, homing enabled."""
    return build_integration_app(fake_gpio, test_settings)


@pytest.fixture
def integration_app_no_homing(
    fake_gpio: FakeGpio,
    test_settings_no_homing: Velux2MqttSettings,
) -> App:
    """Fully-wired App with 2 covers, homing disabled."""
    return build_integration_app(fake_gpio, test_settings_no_homing)
