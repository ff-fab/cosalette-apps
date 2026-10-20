"""Unit tests for geiger2mqtt.adapters.gpiozero_adapter — GPIO pulse counter.

gpiozero is replaced by a fake module in ``sys.modules``; no GPIO is touched.

Test Techniques Used:
- Specification-based: DigitalInputDevice arguments for both pull-up modes;
  only the activation callback is wired.
- Error Guessing: importing the adapter module must not import gpiozero
  (dev machines, --help); counting the release edge would double the CPM.
- State Transition: enter (device created, buffer reset) → exit (device
  closed); exit without entry is a no-op.
- Boundary Value Analysis: pruning at exactly the retention limit.
- Equivalence Partitioning: health check with existing vs missing chip path.
"""

from __future__ import annotations

import importlib
import sys
import threading
from types import ModuleType
from typing import Any

import pytest

from geiger2mqtt.adapters.gpiozero_adapter import GpiozeroPulseCounter
from tests.fixtures.config import FakeTime, make_settings

pytestmark = pytest.mark.unit


class FakeInputDevice:
    """Records constructor arguments and the callbacks the adapter sets."""

    instances: list[FakeInputDevice] = []

    def __init__(self, pin: int, **kwargs: Any) -> None:
        self.pin = pin
        self.kwargs = kwargs
        self.when_activated: Any = None
        self.when_deactivated: Any = None
        self.closed = False
        FakeInputDevice.instances.append(self)

    def close(self) -> None:
        self.closed = True


class FakeFactory:
    """Tracks chip-handle ownership without importing lgpio."""

    instances: list[FakeFactory] = []

    def __init__(self) -> None:
        self.closed = False
        FakeFactory.instances.append(self)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_gpiozero(monkeypatch: pytest.MonkeyPatch) -> type[FakeInputDevice]:
    module = ModuleType("gpiozero")
    module.DigitalInputDevice = FakeInputDevice  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gpiozero", module)
    lgpio_module = ModuleType("gpiozero.pins.lgpio")
    lgpio_module.LGPIOFactory = FakeFactory  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gpiozero.pins.lgpio", lgpio_module)
    FakeInputDevice.instances = []
    FakeFactory.instances = []
    return FakeInputDevice


def test_importing_the_adapter_does_not_import_gpiozero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Technique: Error Guessing — a module-level import would load lgpio."""
    monkeypatch.delitem(sys.modules, "gpiozero", raising=False)
    monkeypatch.delitem(
        sys.modules, "geiger2mqtt.adapters.gpiozero_adapter", raising=False
    )

    importlib.import_module("geiger2mqtt.adapters.gpiozero_adapter")

    assert "gpiozero" not in sys.modules


async def test_default_reads_line_as_is_active_low(
    fake_gpiozero: type[FakeInputDevice], fake_time: FakeTime
) -> None:
    counter = GpiozeroPulseCounter(make_settings(gpio_pin=17), clock=fake_time)

    async with counter:
        (device,) = fake_gpiozero.instances

    assert device.pin == 17
    assert device.kwargs == {
        "pull_up": None,
        "active_state": False,
        "pin_factory": FakeFactory.instances[0],
    }


async def test_pull_up_mode_enables_internal_pull_up(
    fake_gpiozero: type[FakeInputDevice], fake_time: FakeTime
) -> None:
    counter = GpiozeroPulseCounter(make_settings(gpio_pull_up=True), clock=fake_time)

    async with counter:
        (device,) = fake_gpiozero.instances

    assert device.pin == 4
    assert device.kwargs == {
        "pull_up": True,
        "pin_factory": FakeFactory.instances[0],
    }


async def test_only_activation_counts(
    fake_gpiozero: type[FakeInputDevice], fake_time: FakeTime
) -> None:
    """Technique: Error Guessing — the release edge must not count."""
    counter = GpiozeroPulseCounter(make_settings(), clock=fake_time)

    async with counter:
        (device,) = fake_gpiozero.instances
        assert device.when_deactivated is None
        device.when_activated()
        fake_time.advance(0.5)
        device.when_activated()

        assert counter.snapshot(since=0.0) == [1000.0, 1000.5]
        assert counter.last_pulse() == 1000.5


async def test_enter_resets_start_and_pulses(
    fake_gpiozero: type[FakeInputDevice], fake_time: FakeTime
) -> None:
    """Technique: State Transition — a restart begins a fresh count."""
    counter = GpiozeroPulseCounter(make_settings(), clock=fake_time)
    counter.record()
    fake_time.advance(30)

    async with counter:
        assert counter.started_at == 1030.0
        assert counter.snapshot(since=0.0) == []
        assert counter.last_pulse() is None


async def test_exit_closes_device(
    fake_gpiozero: type[FakeInputDevice], fake_time: FakeTime
) -> None:
    counter = GpiozeroPulseCounter(make_settings(), clock=fake_time)

    async with counter:
        (device,) = fake_gpiozero.instances
        assert device.closed is False

    assert device.closed is True
    assert FakeFactory.instances[0].closed is True
    await counter.__aexit__(None, None, None)  # second exit is a no-op


async def test_restart_reopens_chip_with_fresh_factory(
    fake_gpiozero: type[FakeInputDevice],
) -> None:
    counter = GpiozeroPulseCounter(make_settings())

    async with counter:
        first_factory = FakeFactory.instances[0]
    async with counter:
        second_factory = FakeFactory.instances[1]
        assert first_factory.closed
        assert not second_factory.closed
        assert first_factory is not second_factory
        assert fake_gpiozero.instances[1].kwargs["pin_factory"] is second_factory

    assert second_factory.closed


async def test_device_constructor_failure_closes_factory(
    fake_gpiozero: type[FakeInputDevice], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("pin unavailable")

    monkeypatch.setattr(sys.modules["gpiozero"], "DigitalInputDevice", fail)
    counter = GpiozeroPulseCounter(make_settings())

    with pytest.raises(OSError, match="pin unavailable"):
        await counter.__aenter__()

    assert FakeFactory.instances[0].closed
    await counter.__aexit__(None, None, None)


async def test_callback_setup_failure_closes_device_and_factory(
    fake_gpiozero: type[FakeInputDevice], monkeypatch: pytest.MonkeyPatch
) -> None:
    def set_callback(device: FakeInputDevice, callback: Any) -> None:
        if callback is not None:
            raise OSError("callback unavailable")

    monkeypatch.setattr(
        FakeInputDevice, "when_activated", property(fset=set_callback), raising=False
    )
    counter = GpiozeroPulseCounter(make_settings())

    with pytest.raises(OSError, match="callback unavailable"):
        await counter.__aenter__()

    assert fake_gpiozero.instances[0].closed
    assert FakeFactory.instances[0].closed


@pytest.mark.parametrize("failing_resource", [FakeInputDevice, FakeFactory])
async def test_close_failure_releases_both_resources_and_allows_restart(
    fake_gpiozero: type[FakeInputDevice],
    monkeypatch: pytest.MonkeyPatch,
    failing_resource: type[FakeInputDevice] | type[FakeFactory],
) -> None:
    def fail_close(resource: FakeInputDevice | FakeFactory) -> None:
        resource.closed = True
        raise OSError("close failed")

    counter = GpiozeroPulseCounter(make_settings())
    await counter.__aenter__()
    with monkeypatch.context() as patch:
        patch.setattr(failing_resource, "close", fail_close)
        with pytest.raises(OSError, match="close failed"):
            await counter.__aexit__(None, None, None)
        # Failed cleanup must not leave stale references for another exit.
        await counter.__aexit__(None, None, None)

    assert fake_gpiozero.instances[0].closed
    assert FakeFactory.instances[0].closed
    async with counter:
        assert not FakeFactory.instances[1].closed


def test_pulses_pruned_to_longest_window(fake_time: FakeTime) -> None:
    """Technique: Boundary Value Analysis — retention is max(60, window)."""
    counter = GpiozeroPulseCounter(make_settings(average_window=120), clock=fake_time)
    counter.record()  # t=1000
    fake_time.advance(1)
    counter.record()  # t=1001

    fake_time.advance(119)  # now 1120: the first pulse is exactly 120 s old

    assert counter.snapshot(since=0.0) == [1001.0]
    assert counter.last_pulse() == 1001.0


def test_last_pulse_survives_pruning(fake_time: FakeTime) -> None:
    """Technique: Error Guessing — the no-pulse check needs the real last pulse."""
    counter = GpiozeroPulseCounter(make_settings(average_window=60), clock=fake_time)
    counter.record()
    fake_time.advance(600)

    assert counter.snapshot(since=0.0) == []
    assert counter.last_pulse() == 1000.0


def test_snapshot_filters_by_since(fake_time: FakeTime) -> None:
    counter = GpiozeroPulseCounter(make_settings(), clock=fake_time)
    for _ in range(3):
        counter.record()
        fake_time.advance(10)

    assert counter.snapshot(since=1010.0) == [1020.0]
    assert counter.now() == 1030.0


def test_record_is_thread_safe(fake_time: FakeTime) -> None:
    """Technique: Error Guessing — callbacks arrive on lgpio's thread."""
    counter = GpiozeroPulseCounter(make_settings(), clock=fake_time)

    def burst() -> None:
        for _ in range(1000):
            counter.record()

    threads = [threading.Thread(target=burst) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(counter.snapshot(since=0.0)) == 4000


@pytest.mark.parametrize(
    ("chip", "healthy"), [("/dev/null", True), ("/dev/no-such-gpiochip", False)]
)
async def test_health_check_reflects_chip_path(chip: str, healthy: bool) -> None:
    counter = GpiozeroPulseCounter(make_settings(gpio_chip=chip))

    assert await counter.health_check() is healthy
