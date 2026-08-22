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


_COMMAND_SETTLE_TIME = 0.03
"""Real seconds to wait after each injected command before sending the next.

Dispatch is asynchronous — TopicRouter.route enqueues onto a per-entity
queue and returns immediately; a worker task drains it, and calibration
commands hop through a second internal queue before anything observable
happens. This needs to be a real sleep, not just event-loop ticks: an
earlier version drained a fixed 200 ticks (no real delay) and passed
dozens of local runs, but still failed intermittently in CI, because tick
count doesn't bound real thread-scheduling latency (the same category of
delay as the default JsonFileStore's thread-pool-backed I/O — see
``_wait_until_subscribed``).

A condition-based wait (poll ``harness.published()`` until growth stops)
was tried and rejected: cosalette's heartbeat loop publishes to
``{prefix}/status`` continuously throughout the harness's lifetime,
because it's paced by ``ctx.sleep()`` against ``FakeClock`` — which
advances virtual time with no real delay (see
``cosalette.testing.FakeClock.sleep``) — so it free-runs as fast as the
event loop allows and the publish count never goes quiet. There is no
generic observable signal for "this command finished processing" that
isn't also true for commands with no effect (e.g. calibration silently
rejecting an out-of-turn command), so this stays a fixed real sleep —
sized well above the ~2ms margin that failed in CI, while remaining far
below the original bug's 100ms per command.

This also gives calibration's real-clock timing (see
``CalibrationStateMachine.time_source`` — ``time.perf_counter``, not
FakeClock, because it measures actual blind travel) a positive gap
between consecutive go/mark commands.
"""


async def _wait_until_subscribed(
    harness: AppHarness,
    topics: set[str],
    *,
    timeout: float = 2.0,
    poll_interval: float = 0.005,
) -> None:
    """Poll until *topics* all appear in ``harness.mqtt.subscriptions``.

    Startup involves real thread-pool-backed store I/O (see
    ``cosalette._persistence._stores``), which needs real elapsed time
    regardless of how much in-process work is yielded through — a genuine
    condition to poll for, unlike per-command settling below (see
    ``_COMMAND_SETTLE_TIME``), which has no such observable signal.
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
                f"— router was not listening yet. "
                f"Actual subscriptions: {sorted(harness.mqtt.subscriptions)}"
            )
        await asyncio.sleep(poll_interval)


def _expected_subscriptions(topic: str) -> set[str]:
    """Subscription topic(s) the router must register before *topic* can route.

    A root command (``{prefix}/{device}/set``) depends on exactly that
    subscription. A sub-topic command (e.g.
    ``{prefix}/{device}/calibrate/set``) is matched via the wildcard
    ``{prefix}/{device}/+/set`` subscription instead — a distinct topic
    string (see ``TopicRouter.subscriptions``) — so both must be checked to
    confirm the device's command dispatch is actually wired up.
    """
    parts = topic.split("/")
    if len(parts) <= 2:
        return {topic}
    root = f"{parts[0]}/{parts[1]}/set"
    if len(parts) == 3:
        return {root}
    return {root, f"{parts[0]}/{parts[1]}/+/set"}


_SHUTDOWN_TIMEOUT = 5.0
"""Bound on waiting for the harness task after shutdown is signalled.

If the harness under test ever fails to observe ``shutdown_event``, this
fails the test with a clear timeout instead of hanging CI indefinitely.
"""


async def _wait_until_startup_settled(harness: AppHarness) -> None:
    """Wait for the harness's startup sequence to finish.

    ``subscribe_and_connect()`` subscribes every registered device's
    topics in one atomic burst with no ``await`` in between (see
    ``_wait_until_subscribed``'s reasoning) — so waiting for at least one
    subscription to appear confirms MQTT dispatch is wired up without
    needing to know the harness's specific devices. That eliminates the
    default JsonFileStore's thread-pool-backed I/O race, which happens
    *before* subscribe_and_connect and was the confirmed cause of
    cap-6rm: 'run_app_briefly's fixed 0.3s wait can still race under heavy
    combined test-suite load'.

    Startup device work that runs *after* subscriptions are wired (homing,
    initial state publish, health status) is FakeClock/FakeGpio-driven —
    no real I/O — so it needs only the same order of real-time margin as
    ``_COMMAND_SETTLE_TIME``, not another condition to poll for.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 2.0
    while not harness.mqtt.subscriptions:
        if loop.time() >= deadline:
            raise AssertionError(
                "App did not subscribe to any command topics within 2.0s "
                "— router was not listening yet."
            )
        await asyncio.sleep(0.005)
    await asyncio.sleep(_COMMAND_SETTLE_TIME)


async def run_app_briefly(harness: AppHarness) -> None:
    """Start the harness as a background task, wait for startup to settle,
    then shut it down cleanly.

    Bounds task completion with asyncio.wait_for to prevent indefinite test hangs.
    """
    task = asyncio.create_task(harness.run())
    await _wait_until_startup_settled(harness)
    harness.shutdown_event.set()
    await asyncio.wait_for(task, timeout=_SHUTDOWN_TIMEOUT)


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
    expected_topics: set[str] = set()
    for topic, _ in commands:
        expected_topics |= _expected_subscriptions(topic)
    await _wait_until_subscribed(harness, expected_topics)
    for topic, payload in commands:
        await harness.inject_command(device=None, payload=payload, topic=topic)
        await asyncio.sleep(_COMMAND_SETTLE_TIME)
    harness.shutdown_event.set()
    await asyncio.wait_for(task, timeout=_SHUTDOWN_TIMEOUT)


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
