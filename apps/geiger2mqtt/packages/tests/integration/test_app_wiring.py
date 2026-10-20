"""Integration tests for geiger2mqtt.main — the wired app end to end.

The real ``create_app()`` runs on the harness with a seeded fake counter whose
clock is the harness ``ManualClock``; only the GPIO adapter is replaced.

Test Techniques Used:
- Specification-based: state topic and payload fields; module-level app.
- Boundary Value Analysis: nothing at 59 s, the first state once 60 s pass.
- Equivalence Partitioning: no-pulse timeout disabled (0) never goes offline;
  the enabled case lives in test_freshness.py.
- Error Guessing: both registered adapter factories resolve with only the
  settings injected, without importing gpiozero for the dry-run variant.
"""

from __future__ import annotations

import json
import sys
from types import ModuleType

import cosalette
import pytest
from cosalette._wiring._adapter_lifecycle import resolve_adapters

from geiger2mqtt.adapters.fake import FakePulseCounter
from geiger2mqtt.adapters.gpiozero_adapter import GpiozeroPulseCounter
from geiger2mqtt.main import app, create_app
from geiger2mqtt.ports import PulseCounterPort
from tests.fixtures.config import make_settings

from .conftest import AVAILABILITY_TOPIC, STATE_TOPIC, make_harness, running

pytestmark = pytest.mark.integration


def _states(harness: cosalette.testing.AppHarness) -> list[dict[str, object]]:
    return [json.loads(payload) for payload, _, _ in harness.messages_for(STATE_TOPIC)]


def _availability(harness: cosalette.testing.AppHarness) -> list[str]:
    return [payload for payload, _, _ in harness.messages_for(AVAILABILITY_TOPIC)]


def test_module_level_app() -> None:
    assert isinstance(app, cosalette.App)
    assert app.name == "geiger2mqtt"


@pytest.mark.parametrize(
    ("dry_run", "expected"),
    [(True, FakePulseCounter), (False, GpiozeroPulseCounter)],
)
def test_registered_adapters_resolve_with_settings_only(
    monkeypatch: pytest.MonkeyPatch, dry_run: bool, expected: type
) -> None:
    """Technique: Error Guessing — cosalette injects only the settings."""
    monkeypatch.setitem(sys.modules, "gpiozero", ModuleType("gpiozero"))

    adapters = resolve_adapters(
        create_app()._adapters, dry_run=dry_run, settings=make_settings()
    )

    assert isinstance(adapters[PulseCounterPort], expected)


async def test_first_state_after_cpm_window() -> None:
    """Technique: Boundary Value Analysis — the CPM window must be full."""
    harness = make_harness(publish_interval=1)

    async with running(harness):
        for _ in range(59):
            await harness.advance_time(1)
        assert _states(harness) == []

        await harness.advance_time(1)
        await harness.wait_for_publish_count(STATE_TOPIC, 1)

    (state,) = _states(harness)
    assert set(state) == {"cpm", "dose_rate", "dose_rate_avg"}
    assert isinstance(state["cpm"], int)
    assert state["dose_rate"] == round(state["cpm"] * 0.0057, 4)


async def test_publishes_every_interval_even_when_unchanged() -> None:
    """Technique: Specification-based — no OnChange, every run publishes."""
    harness = make_harness(fake={"cpm": 0.0}, no_pulse_timeout=0)

    async with running(harness):
        for _ in range(6):
            await harness.advance_time(30)
        await harness.wait_for_publish_count(STATE_TOPIC, 5)

    assert _states(harness)[-1] == {"cpm": 0, "dose_rate": 0.0, "dose_rate_avg": 0.0}


async def test_zero_timeout_never_goes_offline() -> None:
    """Technique: Equivalence Partitioning — 0 disables the no-pulse check."""
    harness = make_harness(fake={"cpm": 0.0}, no_pulse_timeout=0)

    async with running(harness):
        for _ in range(30):
            await harness.advance_time(30)

        assert "offline" not in _availability(harness)
    assert _states(harness)[-1]["cpm"] == 0
