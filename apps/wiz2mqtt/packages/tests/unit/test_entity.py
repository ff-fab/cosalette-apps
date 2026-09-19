"""Unit tests for entity.py — bulb_entity_tick .

Test Techniques Used:
- State Transition Testing: online/offline availability debounce transitions,
  ADR-008 phase resolution (steady/reconnect), the return-path settle to steady
- Boundary Value Analysis: the 3-consecutive-failure availability threshold,
  the 3-total-attempts return-path write/read-back retry ceiling
- Decision Table: power source when_unreachable "fault" vs. "no_power" branches;
  the ADR-008 three-way return-path rule (pending command / restore / accept)
- Equivalence Partitioning: deduplication of repeated availability calls
- Round-trip Testing: desired-state fallback publish while unreachable
"""

from __future__ import annotations

import asyncio
import json
import time

from cosalette import DeviceStore
from cosalette.stores import MemoryStore

from tests.fixtures.doubles import FakeDeviceContext, RecordingNotifier
from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.entity import _FAILURE_THRESHOLD, bulb_entity_tick
from wiz2mqtt.errors import WizIdentityError, WizTimeoutError
from wiz2mqtt.intent import (
    Appearance,
    DesiredState,
    desired_state_to_dict,
    enqueue,
    record_command,
)
from wiz2mqtt.models import POWERED_UNKNOWN, BulbState
from wiz2mqtt.power import record_signal
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


def _settings_with_office_power_source(
    when_unreachable: str,
) -> Wiz2MqttSettings:
    """Single-member power source over 'office' with the given policy."""
    return Wiz2MqttSettings(
        bulbs=[{"name": "office", "ip": _IP}],
        power_sources=[
            {
                "name": "office-power",
                "members": ["office"],
                "when_unreachable": when_unreachable,
            }
        ],
        _env_file=None,
        _config_file=None,
    )  # type: ignore[call-arg]


def _settings_no_power_with_peer() -> Wiz2MqttSettings:
    """Two-member no_power source: 'office' plus a 'peer' the test seeds as answering.

    Used where a test needs the source belief pinned to "on" (a peer answers)
    while exercising 'office's own failure path — cap-bjw9.9: belief == "on"
    is a real fault, distinct from the whole circuit being off.
    """
    return Wiz2MqttSettings(
        bulbs=[{"name": "office", "ip": _IP}, {"name": "peer", "ip": "10.0.0.6"}],
        power_sources=[
            {
                "name": "office-power",
                "members": ["office", "peer"],
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

    async def test_reconnect_phase_with_no_restore_runs_return_path(self) -> None:
        """Technique: Decision Table — ADR-008 reconnect phase runs the return
        path (cap-bjw9.8) instead of a plain steady-phase observation write.

        Default config (``restore_previous_state=False``) with no pending
        command takes branch 3 of the three-way rule: the bulb's own report
        becomes the new desired state, overwriting what was seeded, and the
        phase settles back to steady within this same tick.
        """
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.phase["office"] = "reconnect"
        ctx = FakeDeviceContext()
        store = _store_with_desired()

        await _tick(ctx, _config(), adapter, state, store=store)

        stored = store.get("desired_state")
        assert stored is not None
        assert stored["state"] == "OFF"
        assert stored["writer"] == "observation"
        assert state.phase["office"] == "steady"

    async def test_first_tick_with_no_stored_intent_starts_steady(self) -> None:
        """Technique: State Transition — no record ⇒ steady (cap-bjw9.5 AC)."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext()
        store = _store()

        await _tick(ctx, _config(), adapter, state, store=store)

        assert state.phase["office"] == "steady"

    async def test_first_tick_with_stored_intent_runs_return_path_to_steady(
        self,
    ) -> None:
        """Technique: State Transition — a stored intent ⇒ reconnect, then the
        ADR-008 return path (cap-bjw9.8) runs synchronously within the same
        first tick and settles the phase back to steady.

        Simulates a restart: fresh ``SharedState`` (no phase yet), a store
        already carrying a desired-state record.
        """
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext()
        store = _store_with_desired()

        await _tick(ctx, _config(), adapter, state, store=store)

        assert state.phase["office"] == "steady"

    async def test_command_during_poll_keeps_newer_desired_state(self) -> None:
        """Technique: State Transition — command wins a racing observation."""

        class AwaitingPort:
            def __init__(self) -> None:
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            def register_boot_callback(self, callback: object) -> None:  # noqa: ARG002
                pass

            async def get_state(self, ip: str) -> BulbState:  # noqa: ARG002
                self.started.set()
                await self.release.wait()
                return BulbState(
                    state=False,
                    brightness=None,
                    hue=None,
                    saturation=None,
                    color_temp_kelvin=None,
                    scene=None,
                )

        port = AwaitingPort()
        state = SharedState(phase={"office": "steady"})
        ctx = FakeDeviceContext()
        tick = asyncio.create_task(
            bulb_entity_tick(ctx, _config(), port, state, None, RecordingNotifier())
        )
        await port.started.wait()
        record_command(
            state,
            None,
            "office",
            {
                "state": True,
                "brightness": 200,
                "hue": None,
                "saturation": None,
                "color_temp_kelvin": None,
                "scene": None,
                "speed": None,
            },
            2000.0,
        )
        port.release.set()
        await tick

        assert state.desired_state["office"].state == "ON"
        assert state.desired_state["office"].appearance.brightness == 200


_DESIRED_OFF = DesiredState(
    state="OFF",
    appearance=Appearance(
        brightness=150,
        hue=10.0,
        saturation=50.0,
        color_temp_kelvin=None,
        scene=None,
        speed=None,
    ),
    writer="observation",
    written_at=1000.0,
)


class TestReturnPath:
    """cap-bjw9.8 — ADR-008's return-to-reachability path, run once per return
    from ``bulb_entity_tick``'s success branch when the phase is reconnect.

    Every test below arranges ``state.phase["office"] = "reconnect"`` directly
    rather than going through a boot event, since AC8 already proves the boot
    callback never runs this logic itself — these tests isolate what a tick
    does once the phase says reconnect.
    """

    async def test_pending_command_applies_regardless_of_restore_setting(
        self,
    ) -> None:
        """Technique: Decision Table — branch 1 always wins, restore or not."""
        adapter = FakeWizBulbAdapter()
        state = SharedState(phase={"office": "reconnect"})
        enqueue(
            state.pending_commands,
            "office",
            {
                "state": True,
                "brightness": 200,
                "hue": None,
                "saturation": None,
                "color_temp_kelvin": None,
                "scene": None,
                "speed": None,
            },
            time.time(),
        )
        ctx = FakeDeviceContext()
        store = _store_with_desired()

        await _tick(
            ctx, _config(restore_previous_state=False), adapter, state, store=store
        )

        assert adapter.set_state_calls == [
            (
                _IP,
                {
                    "state": True,
                    "brightness": 200,
                    "hue": None,
                    "saturation": None,
                    "color_temp_kelvin": None,
                    "scene": None,
                    "speed": None,
                },
            )
        ]
        assert state.phase["office"] == "steady"
        assert ctx.published == []

    async def test_no_pending_command_with_restore_enabled_applies_stored_intent(
        self,
    ) -> None:
        """Technique: Decision Table — branch 2, restore enabled, no pending."""
        adapter = FakeWizBulbAdapter()
        state = SharedState(phase={"office": "reconnect"})
        ctx = FakeDeviceContext()
        store = _store_with_desired()

        await _tick(
            ctx, _config(restore_previous_state=True), adapter, state, store=store
        )

        assert adapter.set_state_calls == [
            (
                _IP,
                {
                    "state": True,
                    "brightness": 100,
                    "hue": None,
                    "saturation": None,
                    "color_temp_kelvin": None,
                    "scene": None,
                    "speed": None,
                },
            )
        ]
        assert state.phase["office"] == "steady"
        assert ctx.published == []

    async def test_no_pending_no_restore_accepts_report_as_new_desired_state(
        self,
    ) -> None:
        """Technique: Decision Table — branch 3, the fallthrough default."""
        adapter = FakeWizBulbAdapter()
        state = SharedState(phase={"office": "reconnect"})
        ctx = FakeDeviceContext()
        store = _store_with_desired()

        await _tick(
            ctx, _config(restore_previous_state=False), adapter, state, store=store
        )

        assert adapter.set_state_calls == []
        stored = store.get("desired_state")
        assert stored is not None
        assert stored["state"] == "OFF"
        assert stored["writer"] == "observation"
        assert state.phase["office"] == "steady"

    async def test_desired_off_sends_single_call_without_appearance(self) -> None:
        """Technique: Boundary Value Analysis — OFF strips appearance kwargs."""
        adapter = FakeWizBulbAdapter()
        state = SharedState(phase={"office": "reconnect"})
        ctx = FakeDeviceContext()
        store = _store({"desired_state": desired_state_to_dict(_DESIRED_OFF)})

        await _tick(
            ctx, _config(restore_previous_state=True), adapter, state, store=store
        )

        assert adapter.set_state_calls == [
            (
                _IP,
                {
                    "state": False,
                    "brightness": None,
                    "hue": None,
                    "saturation": None,
                    "color_temp_kelvin": None,
                    "scene": None,
                    "speed": None,
                },
            )
        ]

    async def test_desired_on_sends_single_call_with_appearance(self) -> None:
        """Technique: Boundary Value Analysis — ON carries state + appearance
        in one call."""
        adapter = FakeWizBulbAdapter()
        state = SharedState(phase={"office": "reconnect"})
        ctx = FakeDeviceContext()
        store = _store_with_desired()

        await _tick(
            ctx, _config(restore_previous_state=True), adapter, state, store=store
        )

        assert len(adapter.set_state_calls) == 1
        ip, kwargs = adapter.set_state_calls[0]
        assert ip == _IP
        assert kwargs["state"] is True
        assert kwargs["brightness"] == 100

    async def test_two_refused_writes_then_third_succeeds_no_error(self) -> None:
        """Technique: Boundary Value Analysis — exactly at the 3-attempt
        ceiling, succeeding on the last one."""
        adapter = FakeWizBulbAdapter()
        adapter.refuse_writes(_IP, 2)
        state = SharedState(phase={"office": "reconnect"})
        ctx = FakeDeviceContext()
        store = _store_with_desired()

        await _tick(
            ctx, _config(restore_previous_state=True), adapter, state, store=store
        )

        assert len(adapter.set_state_calls) == 3
        assert ctx.published == []
        assert state.phase["office"] == "steady"

    async def test_three_refused_writes_publishes_error_and_hands_back_authority(
        self,
    ) -> None:
        """Technique: Boundary Value Analysis — exhausts all 3 attempts."""
        adapter = FakeWizBulbAdapter()
        adapter.refuse_writes(_IP, 3)
        state = SharedState(phase={"office": "reconnect"})
        ctx = FakeDeviceContext()
        store = _store_with_desired()

        await _tick(
            ctx, _config(restore_previous_state=True), adapter, state, store=store
        )

        assert len(adapter.set_state_calls) == 3
        assert len(ctx.published) == 1
        channel, payload = ctx.published[0]
        assert channel == "error"
        body = json.loads(payload)
        assert body["attempts"] == 3
        assert "state" in body
        assert state.phase["office"] == "steady"
        # Authority hands back to the lamp: desired state now matches its
        # (unchanged, since every write was refused) actual report.
        assert state.desired_state["office"].state == "OFF"

    async def test_boot_callback_alone_never_triggers_writes_or_publish(
        self,
    ) -> None:
        """Technique: Specification-based — the return path never runs from
        the push callback, only from the next entity tick."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_office())

        await _tick(ctx, _config(), adapter, state)
        adapter.boot(_IP, adapter._state[_IP])  # noqa: SLF001

        assert adapter.set_state_calls == []
        assert ctx.published == []


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

    async def test_failures_keep_answer_evidence_until_the_threshold(self) -> None:
        """Technique: Boundary Value Analysis — evidence clears at 3, not 1."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_no_power_policy_source())
        config = _config()

        await _tick(ctx, config, adapter, state)
        for expected_failures in (1, 2):
            adapter.fail_next(_IP, WizTimeoutError("boom"))
            result = await _tick(ctx, config, adapter, state)

            assert state.consecutive_failures["office"] == expected_failures
            assert state.bulb_answered["office"] is True
            assert result == {"state": "OFF", "powered": True}

        adapter.fail_next(_IP, WizTimeoutError("boom"))
        result = await _tick(ctx, config, adapter, state)

        assert state.bulb_answered["office"] is False
        assert result == {"state": "OFF", "powered": False}

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
        """Identity failures never masquerade as an unreachable bulb switched off.

        Technique: Error Guessing — a peer keeps answering, so the source
        belief is pinned to "on" (cap-bjw9.9: a real fault, not a dark
        circuit), and office's identity mismatch must still go offline.
        """
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.bulb_answered["peer"] = True
        ctx = FakeDeviceContext(settings=_settings_no_power_with_peer())
        config = _config()

        for _ in range(3):
            adapter.fail_next(_IP, WizIdentityError("wrong bulb"))
            assert await _tick(ctx, config, adapter, state) is None

        assert ctx.availability_calls == ["unavailable"]
        assert state.last_availability["office"] == "offline"

    async def test_belief_off_skips_the_read_after_evidence_establishes_it(
        self,
    ) -> None:
        """cap-bjw9.9 — once evidence says off, further ticks cost no read.

        Technique: Boundary Value Analysis — the skip only applies once the
        failure counter reaches the threshold (seeded here, simulating a
        source already known off), never on a bulb that has not had its
        chance yet (see ``test_belief_off_after_one_failure_still_reads``).
        """
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.bulb_answered["office"] = False
        state.consecutive_failures["office"] = _FAILURE_THRESHOLD
        ctx = FakeDeviceContext(settings=_settings_with_no_power_policy_source())
        config = _config()

        for _ in range(3):
            result = await _tick(ctx, config, adapter, state)
            assert result is None

        assert adapter.get_state_call_count == 0
        assert state.consecutive_failures["office"] == _FAILURE_THRESHOLD
        assert ctx.availability_calls == ["available"]

    async def test_belief_off_after_one_failure_still_reads(self) -> None:
        """cap-bjw9.9 — one transient timeout must not latch the bulb dark.

        Technique: Boundary Value Analysis — threshold minus one. The
        ``no_power`` tie-break already yields belief "off" after the first
        failure, but ADR-007 skips reads only after the threshold.
        """
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_no_power_policy_source())
        config = _config()

        adapter.fail_next(_IP, WizTimeoutError("boom"))
        await _tick(ctx, config, adapter, state)
        result = await _tick(ctx, config, adapter, state)

        assert adapter.get_state_call_count == 2
        assert state.bulb_answered["office"] is True
        assert result is not None
        assert result["powered"] is True

    async def test_belief_off_reports_desired_state_with_powered_false(self) -> None:
        """cap-bjw9.9 — the skip path still reports intent, not a bare None."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.bulb_answered["office"] = False
        state.consecutive_failures["office"] = _FAILURE_THRESHOLD
        state.desired_state["office"] = _DESIRED_ON
        state.phase["office"] = "steady"  # a persisted desired state alone
        # would otherwise resolve the *lazy* phase init to "reconnect" and
        # bypass the skip this test targets — pin it explicitly instead.
        ctx = FakeDeviceContext(settings=_settings_with_no_power_policy_source())

        result = await _tick(ctx, _config(), adapter, state)

        assert result == {"state": "ON", "brightness": 100, "powered": False}
        assert state.last_availability["office"] == "online"
        assert adapter.get_state_call_count == 0

    async def test_belief_on_with_repeated_failure_goes_offline(self) -> None:
        """cap-bjw9.9 — a peer answers, so this bulb's own silence is a fault."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.bulb_answered["peer"] = True
        ctx = FakeDeviceContext(settings=_settings_no_power_with_peer())
        config = _config()

        for _ in range(3):
            adapter.fail_next(_IP, WizTimeoutError("boom"))
            await _tick(ctx, config, adapter, state)

        assert ctx.availability_calls == ["unavailable"]
        assert state.last_availability["office"] == "offline"

    async def test_belief_leaving_off_lets_the_next_tick_read_again(self) -> None:
        """cap-bjw9.9 — the reconnect phase (a firstBeat) bypasses the skip."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        state.bulb_answered["office"] = False
        state.phase["office"] = "reconnect"
        ctx = FakeDeviceContext(settings=_settings_with_no_power_policy_source())
        config = _config()

        result = await _tick(ctx, config, adapter, state)

        assert adapter.get_state_call_count == 1
        assert state.bulb_answered["office"] is True
        assert result is not None
        assert result["powered"] is True

    async def test_fault_source_with_no_signal_goes_offline_after_threshold(
        self,
    ) -> None:
        """AC: no signal + when_unreachable='fault' + 3 failures -> offline."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_office_power_source("fault"))
        config = _config()

        for _ in range(3):
            adapter.fail_next(_IP, WizTimeoutError("boom"))
            await _tick(ctx, config, adapter, state)

        assert ctx.availability_calls == ["unavailable"]
        assert state.last_availability["office"] == "offline"


class TestSignalOff:
    """A relay signal ``off`` newer than the last answer decides at once
    (ADR-007 amendment 2026-09-19, cap-hfro)."""

    @staticmethod
    async def _answered_then_signal_off(
        adapter: FakeWizBulbAdapter, ctx: FakeDeviceContext, state: SharedState
    ) -> None:
        await _tick(ctx, _config(), adapter, state)
        assert state.bulb_answered["office"] is True
        record_signal(ctx.settings, state, "office-power", "off")

    async def test_first_failed_read_after_the_signal_is_firm(self) -> None:
        """Technique: Boundary Value Analysis — one failure reaches the threshold.

        The bulb stays online with ``powered: false``, and the next tick
        skips the read instead of waiting for two more 13 s timeouts.
        """
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_office_power_source("fault"))
        await self._answered_then_signal_off(adapter, ctx, state)

        adapter.fail_next(_IP, WizTimeoutError("boom"))
        result = await _tick(ctx, _config(), adapter, state)
        await _tick(ctx, _config(), adapter, state)

        assert result == {"state": "OFF", "powered": False}
        assert state.consecutive_failures["office"] == _FAILURE_THRESHOLD
        assert adapter.get_state_call_count == 2
        assert ctx.availability_calls == ["available"]

    async def test_answer_after_the_signal_outranks_it(self) -> None:
        """Technique: Decision Table — rule 1 with evidence newer than the signal.

        The read after the signal bypasses the push cache (a push from before
        the signal is not newer evidence, cap-hfro review). Its answer clears
        the stale mark and does not arm the return path: a wrong signal is
        not a return to reachability.
        """
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_office_power_source("fault"))
        await self._answered_then_signal_off(adapter, ctx, state)

        result = await _tick(ctx, _config(), adapter, state)
        await _tick(ctx, _config(), adapter, state)

        assert result == {"state": "OFF", "powered": True}
        assert adapter.invalidate_cache_calls == [_IP]
        assert "office" not in state.stale_answers
        assert state.phase["office"] == "steady"

    async def test_failure_after_a_newer_answer_keeps_the_debounce(self) -> None:
        """Technique: State Transition — signal, answer, then one lost read.

        The answer after the signal holds the belief ``on``, so one timeout
        is transient again and the bulb keeps its answer evidence.
        """
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        ctx = FakeDeviceContext(settings=_settings_with_office_power_source("fault"))
        await self._answered_then_signal_off(adapter, ctx, state)
        await _tick(ctx, _config(), adapter, state)

        adapter.fail_next(_IP, WizTimeoutError("boom"))
        result = await _tick(ctx, _config(), adapter, state)

        assert result == {"state": "OFF", "powered": True}
        assert state.consecutive_failures["office"] == 1


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
