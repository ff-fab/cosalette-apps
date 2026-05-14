"""Unit tests for main.py — command handler invariant guards.

Test Techniques Used:
- Error Guessing: inject the (None, None) impossible return value from
  _parse_or_error to verify the defensive RuntimeError is raised for both
  mapping_assign and mapping_reset command handlers.
- Specification-based: reactor publishes mapping events and state, persists
  registry, and resets filter bank on sensor ID reassignment.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.main import _PARSE_OR_ERROR_IMPOSSIBLE
from jeelink2mqtt.models import MappingEvent, SensorConfig, SensorReading
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.state import SharedState
from tests.fixtures.doubles import FakeDeviceContext


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_store() -> MagicMock:
    return MagicMock()


def _make_state() -> MagicMock:
    return MagicMock()


# ── _parse_or_error invariant guard ──────────────────────────────────────────


@pytest.mark.unit
class TestParseOrErrorGuard:
    """Error Guessing: (None, None) path raises RuntimeError with known message."""

    @pytest.mark.asyncio
    async def test_mapping_assign_raises_on_impossible_none(self) -> None:
        """mapping_assign raises RuntimeError when _parse_or_error returns (None, None).

        Technique: Error Guessing — monkey-patch _parse_or_error to trigger the
        invariant that should be unreachable in normal operation.
        """
        with patch("jeelink2mqtt.main._parse_or_error", return_value=(None, None)):
            from jeelink2mqtt.main import mapping_assign

            with pytest.raises(
                RuntimeError, match=re.escape(_PARSE_OR_ERROR_IMPOSSIBLE)
            ):
                await mapping_assign(
                    payload="{}",
                    store=_make_store(),
                    state=_make_state(),
                )

    @pytest.mark.asyncio
    async def test_mapping_reset_raises_on_impossible_none(self) -> None:
        """mapping_reset raises RuntimeError when _parse_or_error returns (None, None).

        Technique: Error Guessing — same invariant guard as mapping_assign.
        """
        with patch("jeelink2mqtt.main._parse_or_error", return_value=(None, None)):
            from jeelink2mqtt.main import mapping_reset

            with pytest.raises(
                RuntimeError, match=re.escape(_PARSE_OR_ERROR_IMPOSSIBLE)
            ):
                await mapping_reset(
                    payload="{}",
                    store=_make_store(),
                    state=_make_state(),
                )

    def test_impossible_none_message_matches_constant(self) -> None:
        """The guard message constant is non-empty and references the function name.

        Technique: Specification-based — constant value check so future renames
        stay intentional.
        """
        assert "_parse_or_error" in _PARSE_OR_ERROR_IMPOSSIBLE
        assert "(None, None)" in _PARSE_OR_ERROR_IMPOSSIBLE


# ── on_registry_events reactor ───────────────────────────────────────────────


@pytest.mark.unit
class TestOnRegistryEvents:
    """Verifies the on_registry_events reactor publishes events/state and persists."""

    @pytest.mark.asyncio
    async def test_publishes_mapping_events_and_state(self) -> None:
        """on_registry_events publishes each mapping event and the registry state.

        Technique: Specification-based — reactor contract for mapping lifecycle.
        """
        from jeelink2mqtt.main import on_registry_events

        # Arrange
        ctx = FakeDeviceContext()
        store: dict[str, object] = {}
        config = SensorConfig(name="office")
        state = SharedState(
            registry=SensorRegistry([config], 600),
            filter_bank=FilterBank(3),
            sensor_configs={"office": config},
        )

        events = [
            MappingEvent(
                event_type="auto_adopt",
                sensor_name="office",
                old_sensor_id=None,
                new_sensor_id=42,
                timestamp=datetime.now(UTC),
                reason="First reading",
            )
        ]

        # Act
        await on_registry_events(events, ctx, store, state)  # type: ignore[arg-type]

        # Assert — mapping/event and mapping/state published
        topics = [t for t, _, _ in ctx.published]
        assert "mapping/event" in topics
        assert "mapping/state" in topics

        # Assert — registry persisted
        assert "registry" in store
        assert isinstance(store["registry"], dict)

    @pytest.mark.asyncio
    async def test_resets_filter_bank_on_reassignment(self) -> None:
        """on_registry_events resets filter_bank when old_sensor_id is not None.

        Technique: Specification-based — ADR-003 filter reset contract.
        """
        from jeelink2mqtt.main import on_registry_events

        # Arrange
        ctx = FakeDeviceContext()
        store: dict[str, object] = {}
        config = SensorConfig(name="office")
        filter_bank = FilterBank(3)
        state = SharedState(
            registry=SensorRegistry([config], 600),
            filter_bank=filter_bank,
            sensor_configs={"office": config},
        )

        # Populate the filter bank for old sensor ID 10 with 3 readings
        for i in range(3):
            old_reading = SensorReading(10, 20.0 + i, 50, False, datetime.now(UTC))
            filter_bank.filter(old_reading)

        events = [
            MappingEvent(
                event_type="auto_adopt",
                sensor_name="office",
                old_sensor_id=10,  # Reassignment
                new_sensor_id=42,
                timestamp=datetime.now(UTC),
                reason="Battery swap",
            )
        ]

        # Act
        await on_registry_events(events, ctx, store, state)  # type: ignore[arg-type]

        # Assert — filter for old ID was reset (fresh window)
        # After reset, first reading through the filter should pass through unmodified
        test_reading = SensorReading(10, 99.0, 99, False, datetime.now(UTC))
        filtered_temp, filtered_hum = filter_bank.filter(test_reading)
        assert filtered_temp == 99.0  # Unfiltered (window size 1)
        assert filtered_hum == 99.0

    @pytest.mark.asyncio
    async def test_multiple_events_all_published(self) -> None:
        """on_registry_events publishes all events in the batch.

        Technique: Specification-based — reactor drains full event list.
        """
        from jeelink2mqtt.main import on_registry_events

        # Arrange
        ctx = FakeDeviceContext()
        store: dict[str, object] = {}
        configs = [SensorConfig(name="office"), SensorConfig(name="outdoor")]
        state = SharedState(
            registry=SensorRegistry(configs, 600),
            filter_bank=FilterBank(3),
            sensor_configs={c.name: c for c in configs},
        )

        events = [
            MappingEvent(
                event_type="auto_adopt",
                sensor_name="office",
                old_sensor_id=None,
                new_sensor_id=42,
                timestamp=datetime.now(UTC),
                reason="First office reading",
            ),
            MappingEvent(
                event_type="auto_adopt",
                sensor_name="outdoor",
                old_sensor_id=None,
                new_sensor_id=99,
                timestamp=datetime.now(UTC),
                reason="First outdoor reading",
            ),
        ]

        # Act
        await on_registry_events(events, ctx, store, state)  # type: ignore[arg-type]

        # Assert — two mapping/event publishes, one mapping/state
        event_topics = [t for t, _, _ in ctx.published if t == "mapping/event"]
        assert len(event_topics) == 2

        state_topics = [t for t, _, _ in ctx.published if t == "mapping/state"]
        assert len(state_topics) == 1
