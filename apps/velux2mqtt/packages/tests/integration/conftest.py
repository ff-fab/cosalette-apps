"""Integration test fixtures for velux2mqtt.

Provides a fully-wired App instance backed by in-memory test doubles
(FakeGpio, MockMqttClient) so integration tests can drive the real
application logic without real GPIO or MQTT I/O.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient
from cosalette.testing import AppHarness, FakeClock

from velux2mqtt.adapters.fake import FakeGpio
from velux2mqtt.devices.cover import cover_device
from velux2mqtt.main import _cover_map
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
    app.device(name=_cover_map)(cover_device)
    return app


async def run_app_briefly(harness: AppHarness, *, wait: float = 0.3) -> None:
    """Start the harness as a background task, wait, then shut it down cleanly."""
    task = asyncio.create_task(harness.run())
    await asyncio.sleep(wait)
    harness.shutdown_event.set()
    await task


async def run_app_with_commands(
    harness: AppHarness,
    commands: list[tuple[str, str | dict[str, object]]],
    *,
    startup_wait: float = 0.15,
    per_command_wait: float = 0.1,
) -> None:
    """Start the harness, deliver commands via inject_command, then shut down cleanly.

    Args:
        harness: AppHarness wrapping the fully-wired App.
        commands: Ordered list of (topic, payload) pairs to deliver.
        startup_wait: Seconds to wait before delivering first command.
        per_command_wait: Seconds to wait after each delivered command.
    """
    task = asyncio.create_task(harness.run())
    await asyncio.sleep(startup_wait)
    for topic, payload in commands:
        await harness.inject_command(device=None, payload=payload, topic=topic)
        await asyncio.sleep(per_command_wait)
    harness.shutdown_event.set()
    await task


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_gpio() -> FakeGpio:
    """A fresh FakeGpio that records all presses."""
    return FakeGpio()


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
def harness(fake_gpio: FakeGpio, test_settings: Velux2MqttSettings) -> AppHarness:
    """Fresh AppHarness with 2 covers, homing enabled."""
    return AppHarness(
        app=build_integration_app(fake_gpio, test_settings),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=test_settings,
        shutdown_event=asyncio.Event(),
    )


@pytest.fixture
def harness_no_homing(
    fake_gpio: FakeGpio,
    test_settings_no_homing: Velux2MqttSettings,
) -> AppHarness:
    """Fresh AppHarness with 2 covers, homing disabled."""
    return AppHarness(
        app=build_integration_app(fake_gpio, test_settings_no_homing),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=test_settings_no_homing,
        shutdown_event=asyncio.Event(),
    )
