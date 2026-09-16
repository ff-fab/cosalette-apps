"""Unit tests for entity.py — bulb_entity_tick .

Test Techniques Used:
- State Transition Testing: online/offline availability debounce transitions,
  ADR-008 phase resolution (steady/reconnect)
- Boundary Value Analysis: the 3-consecutive-failure availability threshold
- Decision Table: power source when_unreachable "fault" vs. "no_power" branches
- Equivalence Partitioning: deduplication of repeated availability calls
- Round-trip Testing: desired-state fallback publish while unreachable
"""

from __future__ import annotations

from cosalette import DeviceStore
from cosalette.stores import MemoryStore

from tests.fixtures.doubles import FakeDeviceContext, RecordingNotifier
from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.entity import bulb_entity_tick
from wiz2mqtt.errors import WizIdentityError, WizTimeoutError
from wiz2mqtt.intent import Appearance, DesiredState, desired_state_to_dict
from wiz2mqtt.models import POWERED_UNKNOWN
from wiz2mqtt.settings import BulbConfig, Wiz2MqttSettings
from wiz2mqtt.state import SharedState

_IP = "10.0.0.5"


def _config(**overrides: object) -> BulbConfig:
    defaults: dict[str, object] = {"name": "office", "ip": _IP}
    return BulbConfig(**{**defaults, **overrides})  # type: ignore[arg-type]


def _settings_with_office() -> Wiz2MqttSettings:
    """Settings carrying the same 'office' bulb :func:`_config` builds by hand.

    ``bulb_entity_tick`` derives its firstBeat ip→name map from
    ``ctx.settings.bulbs`` (the real source of truth in production) rather
    than from the ad-hoc ``config`` object a test passes in — boot-callback
    tests need the two to agree.
    """
    return Wiz2MqttSettings(
        bulbs=[{"name": "office", "ip": _IP}],
        _env_file=None,
        _config_file=None,
    )  # type: ignore[call-arg]


def _settings_with_no_power_policy_source() -> Wiz2MqttSettings:
    """Settings whose 'office' bulb sits behind a source that reports OFF."""
    return Wiz2MqttSettings(
        bulbs=[{"name": "office", "ip": _IP}],
        power_sources=[
            {
                "name": "office-power",
                "members": ["office"],
                "when_unreachable": "no_power",
            }
        ],
        _env_file=None,
        _config_file=None,
    )  # type: ignore[call-arg]


def _store(record: dict[str, object] | None = None) -> DeviceStore:
    """A per-bulb ``DeviceStore`` for ``office``, optionally pre-seeded."""
    backend = MemoryStore(initial={"office": record} if record else None)
    store = DeviceStore(backend, "office")
    store.load()
    return store


_DESIRED_ON = DesiredState(
    state="ON",
    appearance=Appearance(
        brightness=100,
        hue=None,
        saturation=None,
        color_temp_kelvin=None,
        scene=None,
        speed=None,
    ),
    writer="observation",
    written_at=1000.0,
)


def _store_with_desired() -> DeviceStore:
    return _store({"desired_state": desired_state_to_dict(_DESIRED_ON)})


async def _tick(
    ctx: FakeDeviceContext,
    config: BulbConfig,
    adapter: FakeWizBulbAdapter,
    state: SharedState,
    *,
    store: DeviceStore | None = None,
    notify: RecordingNotifier | None = None,
) -> dict[str, object] | None:
    """Thin wrapper supplying the store/notify params most tests don't care about."""
    return await bulb_entity_tick(
        ctx, config, adapter, state, store, notify or RecordingNotifier()
    )


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

        result = await _tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == ["available"]
        assert state.last_availability["office"] == "online"
        assert result == {"state": "OFF", "powered": POWERED_UNKNOWN}

    async def test_already_online_not_re_marked(self) -> None:
        """Technique: Equivalence Partitioning — dedup of availability calls."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.last_availability["office"] = "online"
        ctx = FakeDeviceContext()

        await _tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == []

    async def test_success_resets_consecutive_failures(self) -> None:
        """Technique: State Transition Testing — failure counter reset on success."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.consecutive_failures["office"] = 2
        ctx = FakeDeviceContext()

        await _tick(ctx, _config(), adapter, state)

        assert state.consecutive_failures["office"] == 0

    async def test_recovery_marks_available_once(self) -> None:
        """Technique: State Transition Testing — offline -> online recovery."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.last_availability["office"] = "offline"
        ctx = FakeDeviceContext()

        await _tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == ["available"]
        assert state.last_availability["office"] == "online"

    async def test_success_marks_bulb_as_answered(self) -> None:
        """Technique: Specification-based — the belief evidence cap-bjw9.7 reads."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext()

        await _tick(ctx, _config(), adapter, state)

        assert state.bulb_answered["office"] is True

    async def test_steady_phase_observation_writes_desired_state(self) -> None:
        """Technique: Specification-based — cap-bjw9.5 observation writer."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.phase["office"] = "steady"
        ctx = FakeDeviceContext()
        store = _store()

        await _tick(ctx, _config(), adapter, state, store=store)

        assert store.get("desired_state") is not None

    async def test_reconnect_phase_observation_does_not_write_desired_state(
        self,
    ) -> None:
        """Technique: Decision Table — ADR-008 reconnect phase shields intent."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.phase["office"] = "reconnect"
        ctx = FakeDeviceContext()
        store = _store_with_desired()

        await _tick(ctx, _config(), adapter, state, store=store)

        # Unchanged: still the seeded record, not an overwrite from the poll.
        assert store.get("desired_state") == desired_state_to_dict(_DESIRED_ON)

    async def test_first_tick_with_no_stored_intent_starts_steady(self) -> None:
        """Technique: State Transition — no record ⇒ steady (cap-bjw9.5 AC)."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext()
        store = _store()

        await _tick(ctx, _config(), adapter, state, store=store)

        assert state.phase["office"] == "steady"

    async def test_first_tick_with_stored_intent_starts_reconnect(self) -> None:
        """Technique: State Transition — a stored intent ⇒ reconnect (cap-bjw9.5 AC).

        Simulates a restart: fresh ``SharedState`` (no phase yet), a store
        already carrying a desired-state record.
        """
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext()
        store = _store_with_desired()

        await _tick(ctx, _config(), adapter, state, store=store)

        assert state.phase["office"] == "reconnect"


class TestFailureDebounce:
    """Failures accumulate; only the 3rd consecutive failure goes offline."""

    async def test_single_failure_below_threshold_returns_none(self) -> None:
        """Technique: Boundary Value Analysis — below threshold (1 of 3)."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        ctx = FakeDeviceContext()

        result = await _tick(ctx, _config(), adapter, state)

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
        result = await _tick(ctx, _config(), adapter, state)

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
            await _tick(ctx, config, adapter, state)

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

        result = await _tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == []
        assert result is None

    async def test_failure_marks_bulb_as_not_answered(self) -> None:
        """Technique: Specification-based — the belief evidence cap-bjw9.7 reads."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        ctx = FakeDeviceContext()

        await _tick(ctx, _config(), adapter, state)

        assert state.bulb_answered["office"] is False

    async def test_failure_with_no_desired_state_publishes_nothing(self) -> None:
        """Technique: Error Guessing — nothing observed yet, nothing to show."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        ctx = FakeDeviceContext()

        result = await _tick(ctx, _config(), adapter, state, store=_store())

        assert result is None

    async def test_failure_with_desired_state_publishes_it_not_off(self) -> None:
        """Technique: Specification-based — cap-bjw9.6, never a hard-coded OFF."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        ctx = FakeDeviceContext()

        result = await _tick(
            ctx, _config(), adapter, state, store=_store_with_desired()
        )

        assert result == {
            "state": "ON",
            "brightness": 100,
            "powered": POWERED_UNKNOWN,
        }

    async def test_failure_still_publishes_desired_state_past_threshold(self) -> None:
        """Technique: Boundary Value Analysis — offline AND showing desired state."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext()
        config = _config()
        store = _store_with_desired()

        result = None
        for _ in range(3):
            adapter.fail_next(_IP, WizTimeoutError("boom"))
            result = await _tick(ctx, config, adapter, state, store=store)

        assert ctx.availability_calls == ["unavailable"]
        assert result == {
            "state": "ON",
            "brightness": 100,
            "powered": POWERED_UNKNOWN,
        }


class TestWhenUnreachableOff:
    """A bulb behind a power source declaring when_unreachable='no_power'
    stays available and reports its desired state, never a hard-coded OFF."""

    async def test_failure_with_no_desired_state_stays_available(self) -> None:
        """Technique: Decision Table — power source when_unreachable='no_power'
        failure branch, nothing observed yet."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_no_power_policy_source())

        result = await _tick(ctx, _config(), adapter, state)

        assert result is None
        assert ctx.availability_calls == ["available"]
        assert state.last_availability["office"] == "online"

    async def test_failure_reports_desired_state_not_off(self) -> None:
        """Technique: Specification-based — cap-bjw9.6 replaces the hard-coded OFF."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_no_power_policy_source())

        result = await _tick(
            ctx, _config(), adapter, state, store=_store_with_desired()
        )

        assert result == {"state": "ON", "brightness": 100, "powered": False}

    async def test_repeated_failures_never_go_offline(self) -> None:
        """Technique: Boundary Value Analysis — well past the 3-failure threshold."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_no_power_policy_source())
        config = _config()

        for _ in range(5):
            adapter.fail_next(_IP, WizTimeoutError("boom"))
            await _tick(ctx, config, adapter, state)

        assert "unavailable" not in ctx.availability_calls

    async def test_when_unreachable_off_already_online_does_not_remark(self) -> None:
        """Technique: Equivalence Partitioning — dedup guard on the off-policy path."""
        adapter = FakeWizBulbAdapter()
        adapter.fail_next(_IP, WizTimeoutError("boom"))
        state = SharedState()
        state.last_availability["office"] = "online"
        ctx = FakeDeviceContext(settings=_settings_with_no_power_policy_source())

        await _tick(ctx, _config(), adapter, state)

        assert ctx.availability_calls == []

    async def test_identity_failure_uses_normal_offline_policy(self) -> None:
        """Identity failures never masquerade as an unreachable bulb switched off."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_no_power_policy_source())
        config = _config()

        for _ in range(3):
            adapter.fail_next(_IP, WizIdentityError("wrong bulb"))
            assert await _tick(ctx, config, adapter, state) is None

        assert ctx.availability_calls == ["unavailable"]
        assert state.last_availability["office"] == "offline"


class TestBootCallback:
    """cap-bjw9.4 — registering and driving the real firstBeat handler."""

    async def test_registers_boot_callback_once(self) -> None:
        """Technique: State Transition — the guard fires only on the first tick."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext()

        await _tick(ctx, _config(), adapter, state)
        first_callback = adapter._boot_callback  # noqa: SLF001
        await _tick(ctx, _config(), adapter, state)

        assert adapter._boot_callback is first_callback  # noqa: SLF001
        assert state.boot_callback_registered is True

    async def test_boot_event_arms_entity_and_resets_failures(self) -> None:
        """Technique: Specification-based — cap-bjw9.4 AC, next tick runs unforced."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.consecutive_failures["office"] = 2
        ctx = FakeDeviceContext(settings=_settings_with_office())
        notify = RecordingNotifier()

        await _tick(ctx, _config(), adapter, state, notify=notify)
        adapter.boot(_IP, adapter._state[_IP])  # noqa: SLF001

        assert state.phase["office"] == "reconnect"
        assert state.consecutive_failures["office"] == 0
        assert "office" in notify.armed

    async def test_boot_event_for_unconfigured_ip_is_ignored(self) -> None:
        """Technique: Error Guessing — a boot event outside the inventory."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_office())
        notify = RecordingNotifier()

        await _tick(ctx, _config(), adapter, state, notify=notify)
        adapter.boot("10.0.0.99", adapter._state[_IP])  # noqa: SLF001

        # Phase stays whatever the tick itself resolved — untouched by a
        # boot event for a different, unconfigured ip.
        assert state.phase["office"] == "steady"
        assert notify.armed == []
