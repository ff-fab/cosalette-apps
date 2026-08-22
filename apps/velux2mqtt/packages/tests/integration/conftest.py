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
    """Start the harness as a background task, wait, then shut it down cleanly.

    Bounds task completion with asyncio.wait_for to prevent indefinite test hangs.
    """
    task = asyncio.create_task(harness.run())
    await asyncio.sleep(wait)
    harness.shutdown_event.set()
    await asyncio.wait_for(task, timeout=wait * 5)


_DRAIN_TICKS = 200
"""Event-loop iterations to yield when settling purely in-process async work.

Command dispatch, calibration's internal queue hop, and state publication
involve no real timers (FakeClock — see ``cosalette.testing.FakeClock.sleep``),
so each becomes runnable within a bounded, code-structure-determined number
of iterations. This is *not* sufficient for startup: the default JsonFileStore
does its load via thread-pool-backed file I/O (see
``cosalette._persistence._stores``), which needs real elapsed time to
complete regardless of how many event-loop ticks are yielded — that's what
``_wait_until_subscribed`` polls for below.
"""


async def _drain_event_loop(ticks: int = _DRAIN_TICKS) -> None:
    """Yield to the event loop *ticks* times so pending async work settles."""
    for _ in range(ticks):
        await asyncio.sleep(0)


async def _wait_until_subscribed(
    harness: AppHarness,
    topics: set[str],
    *,
    timeout: float = 2.0,
    poll_interval: float = 0.005,
) -> None:
    """Poll until *topics* all appear in ``harness.mqtt.subscriptions``.

    Startup involves real thread-pool-backed store I/O (see module note on
    ``_DRAIN_TICKS``), so this polls with a real sleep and a generous
    timeout rather than a fixed tick count — the same condition-over-fixed-
    wait fix as the rest of this helper, just for the one step that
    genuinely needs wall-clock patience.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        unsubscribed = topics - set(harness.mqtt.subscriptions)
        if not unsubscribed:
            return
        if loop.time() >= deadline:
            raise AssertionError(
                f"App did not subscribe to {unsubscribed} within {timeout}s "
                f"— router was not listening yet."
            )
        await asyncio.sleep(poll_interval)


def _root_command_topic(topic: str) -> str:
    """Map *topic* to the ``{prefix}/{device}/set`` topic the router subscribes to.

    Sub-topic commands (e.g. ``{prefix}/{device}/calibrate/set``) are routed
    through the same per-device subscription as the root ``.../set`` topic
    (see ``TopicRouter.subscriptions``), so checking the root form is enough
    to confirm the device is wired up regardless of which topic a command
    actually targets.
    """
    parts = topic.split("/")
    return topic if len(parts) <= 2 else f"{parts[0]}/{parts[1]}/set"


async def run_app_with_commands(
    harness: AppHarness,
    commands: list[tuple[str, str | dict[str, object]]],
) -> None:
    """Start the harness, deliver commands via inject_command, then shut down cleanly.

    Args:
        harness: AppHarness wrapping the fully-wired App.
        commands: Ordered list of (topic, payload) pairs to deliver.
    """
    task = asyncio.create_task(harness.run())
    expected_topics = {_root_command_topic(topic) for topic, _ in commands}
    await _wait_until_subscribed(harness, expected_topics)
    for topic, payload in commands:
        await harness.inject_command(device=None, payload=payload, topic=topic)
        await _drain_event_loop()
        # Calibration measures elapsed duration via time.perf_counter (real
        # wall clock, by design — it times actual blind travel), not
        # FakeClock. A minimal real sleep gives consecutive go/mark commands
        # a measurably positive gap without reintroducing a race: unlike the
        # old fixed wait, this value only needs to be > 0, never "long
        # enough" for anything, so CI load can't make it insufficient.
        await asyncio.sleep(0.001)
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
