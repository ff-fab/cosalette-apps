"""Unit tests for entity.py — bulb_entity_tick (cap-10u.13).

Test Techniques Used:
- State Transition Testing: online/offline availability debounce transitions
- Boundary Value Analysis: the 3-consecutive-failure availability threshold
- Decision Table: when_unreachable "unavailable" vs. "off" branches
- Equivalence Partitioning: deduplication of repeated availability calls
"""

from __future__ import annotations

from tests.fixtures.doubles import FakeDeviceContext
from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.entity import bulb_entity_tick
from wiz2mqtt.errors import WizTimeoutError
from wiz2mqtt.settings import BulbConfig
from wiz2mqtt.state import SharedState

_IP = "10.0.0.5"


def _config(**overrides: object) -> BulbConfig:
    defaults: dict[str, object] = {"name": "office", "ip": _IP}
    return BulbConfig(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestSuccessfulPoll:
    """A successful get_state() publishes state and signals recovery."""

    async def test_first_success_marks_available_and_returns_payload(self) -> None:
        """Technique: Specification-based — full happy path, first tick.

        Uses FakeWizBulbAdapter's real default state (off) so the payload
        assembly path is exercised through :func:`build_state_payload`,
        not just the availability branch.
        """
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext()

        result = await bulb_entity_tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == ["available"]
        assert state.last_availability["office"] == "online"
        assert result == {"state": "OFF"}

    async def test_already_online_not_re_marked(self) -> None:
        """Technique: Equivalence Partitioning — dedup of availability calls."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.last_availability["office"] = "online"
        ctx = FakeDeviceContext()

        await bulb_entity_tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == []

    async def test_success_resets_consecutive_failures(self) -> None:
        """Technique: State Transition Testing — failure counter reset on success."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.consecutive_failures["office"] = 2
        ctx = FakeDeviceContext()

        await bulb_entity_tick(ctx, _config(), adapter, state)

        assert state.consecutive_failures["office"] == 0

    async def test_recovery_marks_available_once(self) -> None:
        """Technique: State Transition Testing — offline -> online recovery."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.last_availability["office"] = "offline"
        ctx = FakeDeviceContext()

        await bulb_entity_tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == ["available"]
        assert state.last_availability["office"] == "online"


class TestFailureDebounce:
    """Failures accumulate; only the 3rd consecutive failure goes offline."""

    async def test_single_failure_below_threshold_returns_none(self) -> None:
        """Technique: Boundary Value Analysis — below threshold (1 of 3)."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        ctx = FakeDeviceContext()

        result = await bulb_entity_tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == []
        assert state.consecutive_failures["office"] == 1
        assert result is None

    async def test_second_consecutive_failure_still_below_threshold(self) -> None:
        """Technique: Boundary Value Analysis — nominal value between boundaries
        (2 of 3)."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.consecutive_failures["office"] = 1
        ctx = FakeDeviceContext()

        adapter.fail_next(_IP, WizTimeoutError("boom"))
        result = await bulb_entity_tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == []
        assert state.consecutive_failures["office"] == 2
        assert result is None

    async def test_third_consecutive_failure_marks_unavailable(self) -> None:
        """Technique: Boundary Value Analysis — exactly at threshold (3 of 3)."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext()
        config = _config()

        for _ in range(3):
            adapter.fail_next(_IP, WizTimeoutError("boom"))
            await bulb_entity_tick(ctx, config, adapter, state)

        assert ctx.availability_calls == ["unavailable"]
        assert state.last_availability["office"] == "offline"

    async def test_already_offline_not_re_marked(self) -> None:
        """Technique: Equivalence Partitioning — dedup of availability calls."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        state.consecutive_failures["office"] = 5
        state.last_availability["office"] = "offline"
        ctx = FakeDeviceContext()

        result = await bulb_entity_tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == []
        assert result is None


class TestWhenUnreachableOff:
    """when_unreachable='off' bulbs stay available and report state OFF."""

    async def test_failure_reports_off_and_stays_available(self) -> None:
        """Technique: Decision Table — when_unreachable='off' failure branch."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        ctx = FakeDeviceContext()

        result = await bulb_entity_tick(
            ctx, _config(when_unreachable="off"), adapter, state
        )

        assert result == {"state": "OFF"}
        assert ctx.availability_calls == ["available"]
        assert state.last_availability["office"] == "online"

    async def test_repeated_failures_never_go_offline(self) -> None:
        """Technique: Boundary Value Analysis — well past the 3-failure threshold."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext()
        config = _config(when_unreachable="off")

        for _ in range(5):
            adapter.fail_next(_IP, WizTimeoutError("boom"))
            await bulb_entity_tick(ctx, config, adapter, state)

        assert "unavailable" not in ctx.availability_calls

    async def test_when_unreachable_off_already_online_does_not_remark(self) -> None:
        """Technique: Equivalence Partitioning — dedup guard on the off-policy path."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        state.last_availability["office"] = "online"
        ctx = FakeDeviceContext()

        await bulb_entity_tick(ctx, _config(when_unreachable="off"), adapter, state)

        assert ctx.availability_calls == []
