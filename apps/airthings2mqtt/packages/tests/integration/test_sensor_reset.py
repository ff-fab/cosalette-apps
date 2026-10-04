"""Integration test: replay of the 2026-10-01/02 battery change (ADR-004).

Test Techniques Used:
- Integration Testing: reader -> reset tracker -> device store -> MQTT state
- State Transition Testing: ok -> warming_up -> warming_up -> provisional
"""

from __future__ import annotations

import json

import pytest
from cosalette.stores import MemoryStore

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.ports import AirthingsReading

from .conftest import DEVICE_NAME, TOPIC_PREFIX, make_harness, run_app_briefly


def _reading(r24: int, lta: int) -> AirthingsReading:
    return AirthingsReading(
        temperature=31.0, humidity=43.5, radon_24h_avg=r24, radon_long_term_avg=lta
    )


@pytest.mark.integration
async def test_battery_change_never_publishes_radon_zero() -> None:
    """The incident replay publishes no radon 0 and records the lost LTA.

    Technique: State Transition — proposal acceptance criterion 10.
    """
    # Arrange
    reader = FakeAirthingsReader()
    reader.readings = [
        _reading(127, 113),
        _reading(0, 0),
        _reading(0, 0),
        _reading(95, 4),
    ]
    store = MemoryStore()
    harness = make_harness(adapter=lambda: reader, store=store)

    # Act
    await run_app_briefly(harness, polls=3)

    # Assert
    payloads = [
        json.loads(payload)
        for payload, _retain, _qos in harness.messages_for(
            f"{TOPIC_PREFIX}/{DEVICE_NAME}/state"
        )
    ]
    assert [p["measurement_state"] for p in payloads] == [
        "ok",
        "warming_up",
        "warming_up",
        "provisional",
    ]
    assert all(
        p[field] != 0
        for p in payloads
        for field in ("radon_24h_avg", "radon_long_term_avg")
    )
    assert payloads[1]["radon_24h_avg"] is None
    assert payloads[0]["sensor_reset_at"] is None
    assert payloads[3]["sensor_reset_at"] == payloads[1]["sensor_reset_at"]
    saved = store.load(DEVICE_NAME)
    assert saved is not None
    assert saved["reset_tracker"]["lta_before_reset"] == 113
    assert saved["reset_tracker"]["reset_count"] == 1
