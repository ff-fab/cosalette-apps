"""Unit tests for intent.py — desired state persistence and the pending queue.

Test Techniques Used:
- Round-trip Testing: DesiredState ⇄ dict ⇄ DeviceStore
- State Transition: command merge reusing BulbState.apply_command semantics;
  SharedState-cache-first / device-store-fallback-once resolution
- Boundary Value Analysis: the pending-command TTL, exactly at/over the limit
- Error Guessing: a corrupt/legacy record, an absent record
"""

from __future__ import annotations

from cosalette import DeviceStore
from cosalette.stores import MemoryStore

from wiz2mqtt.intent import (
    Appearance,
    DesiredState,
    desired_state_from_dict,
    desired_state_to_dict,
    enqueue,
    pop_valid,
    record_command,
    record_observation,
    resolve_desired_state,
)
from wiz2mqtt.models import BulbState
from wiz2mqtt.state import SharedState

_APPEARANCE = Appearance(
    brightness=100,
    hue=None,
    saturation=None,
    color_temp_kelvin=4000,
    scene=None,
    speed=None,
)

_DESIRED = DesiredState(
    state="ON", appearance=_APPEARANCE, writer="observation", written_at=1000.0
)


def _store(record: dict[str, object] | None = None) -> DeviceStore:
    backend = MemoryStore(initial={"office": record} if record else None)
    store = DeviceStore(backend, "office")
    store.load()
    return store


class TestSerialisation:
    def test_desired_state_dict_round_trips(self) -> None:
        assert desired_state_from_dict(desired_state_to_dict(_DESIRED)) == _DESIRED

    def test_as_bulb_state_carries_the_appearance_fields(self) -> None:
        bulb_state = _DESIRED.as_bulb_state()
        assert bulb_state.state is True
        assert bulb_state.brightness == 100
        assert bulb_state.color_temp_kelvin == 4000
        assert bulb_state.power_draw_w is None

    def test_as_bulb_state_off_maps_to_false(self) -> None:
        off = DesiredState(
            state="OFF", appearance=_APPEARANCE, writer="command", written_at=1.0
        )
        assert off.as_bulb_state().state is False


class TestResolveDesiredState:
    """The SharedState-cache-first, device-store-fallback-once resolution.

    cosalette caches one DeviceStore per telemetry registration for the
    whole run (loaded once, before the first tick), so a bulb's
    command-side store and telemetry-side store are separate objects that
    never see each other's writes without a restart — SharedState is what
    makes a command and the very next tick agree within one process. This
    is the regression class for that finding.
    """

    def test_returns_none_when_nothing_recorded_and_no_store(self) -> None:
        assert resolve_desired_state(SharedState(), None, "office") is None

    def test_returns_none_for_an_empty_store(self) -> None:
        assert resolve_desired_state(SharedState(), _store(), "office") is None

    def test_returns_none_for_a_malformed_record(self) -> None:
        store = _store({"desired_state": {"state": "ON"}})  # missing fields
        assert resolve_desired_state(SharedState(), store, "office") is None

    def test_falls_back_to_the_store_on_a_cold_cache(self) -> None:
        """Simulates a restart: fresh SharedState, a store with a record."""
        store = _store({"desired_state": desired_state_to_dict(_DESIRED)})
        assert resolve_desired_state(SharedState(), store, "office") == _DESIRED

    def test_populates_the_cache_from_the_store_fallback(self) -> None:
        state = SharedState()
        store = _store({"desired_state": desired_state_to_dict(_DESIRED)})

        resolve_desired_state(state, store, "office")

        assert state.desired_state["office"] == _DESIRED

    def test_prefers_the_cache_over_a_stale_store(self) -> None:
        """The in-process write always wins — it postdates whatever the
        device store's own (possibly stale, cross-process) copy holds."""
        state = SharedState()
        newer = DesiredState(
            state="OFF", appearance=_APPEARANCE, writer="command", written_at=9999.0
        )
        state.desired_state["office"] = newer
        store = _store({"desired_state": desired_state_to_dict(_DESIRED)})  # older

        assert resolve_desired_state(state, store, "office") == newer

    def test_a_command_is_visible_to_the_very_next_call_in_process(self) -> None:
        """The exact scenario that motivated SharedState as the source of
        truth: a command's write and a subsequent read must agree even
        when they go through two independently-cached DeviceStore objects
        for the same device name (command-side vs. telemetry-side)."""
        state = SharedState()
        command_side_store = _store()
        telemetry_side_store = _store()  # a distinct DeviceStore, same "office" key

        record_command(
            state,
            command_side_store,
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
            1000.0,
        )

        resolved = resolve_desired_state(state, telemetry_side_store, "office")
        assert resolved is not None
        assert resolved.state == "ON"
        assert resolved.appearance.brightness == 200


class TestRecordObservation:
    def test_writes_unconditionally(self) -> None:
        state = SharedState()
        bulb_state = BulbState(
            state=True,
            brightness=50,
            hue=None,
            saturation=None,
            color_temp_kelvin=None,
            scene=None,
            effect_speed=None,
            power_draw_w=12.3,
        )

        record_observation(state, _store(), "office", bulb_state, 2000.0)

        desired = state.desired_state["office"]
        assert desired.state == "ON"
        assert desired.appearance.brightness == 50
        assert desired.writer == "observation"
        assert desired.written_at == 2000.0

    def test_observation_overwrites_an_older_record(self) -> None:
        state = SharedState()
        state.desired_state["office"] = _DESIRED
        off = BulbState(
            state=False,
            brightness=None,
            hue=None,
            saturation=None,
            color_temp_kelvin=None,
            scene=None,
            effect_speed=None,
            power_draw_w=None,
        )

        record_observation(state, None, "office", off, 3000.0)

        desired = state.desired_state["office"]
        assert desired.state == "OFF"
        assert desired.written_at == 3000.0

    def test_persists_to_the_store_when_configured(self) -> None:
        state = SharedState()
        store = _store()
        bulb_state = BulbState(
            state=True,
            brightness=50,
            hue=None,
            saturation=None,
            color_temp_kelvin=None,
            scene=None,
            effect_speed=None,
            power_draw_w=None,
        )

        record_observation(state, store, "office", bulb_state, 2000.0)

        assert store.get("desired_state") is not None

    def test_skips_persistence_when_store_is_none(self) -> None:
        """No store configured (persistence opted out) must not raise."""
        state = SharedState()
        bulb_state = BulbState(
            state=True,
            brightness=None,
            hue=None,
            saturation=None,
            color_temp_kelvin=None,
            scene=None,
            effect_speed=None,
            power_draw_w=None,
        )

        record_observation(state, None, "office", bulb_state, 2000.0)

        assert state.desired_state["office"].state == "ON"


class TestRecordCommand:
    def test_writes_a_complete_state_with_no_prior_record(self) -> None:
        state = SharedState()

        record_command(
            state,
            None,
            "office",
            {
                "state": True,
                "brightness": 128,
                "hue": None,
                "saturation": None,
                "color_temp_kelvin": None,
                "scene": None,
                "speed": None,
            },
            1500.0,
        )

        desired = state.desired_state["office"]
        assert desired.state == "ON"
        assert desired.appearance.brightness == 128
        assert desired.writer == "command"

    def test_partial_command_merges_onto_the_cached_appearance(self) -> None:
        """Technique: State Transition — untouched fields keep their value."""
        state = SharedState()
        state.desired_state["office"] = _DESIRED

        record_command(
            state,
            None,
            "office",
            {
                "state": None,
                "brightness": 200,
                "hue": None,
                "saturation": None,
                "color_temp_kelvin": None,
                "scene": None,
                "speed": None,
            },
            1600.0,
        )

        desired = state.desired_state["office"]
        assert desired.state == "ON"  # untouched, kept from _DESIRED
        assert desired.appearance.brightness == 200  # updated
        assert desired.appearance.color_temp_kelvin == 4000  # untouched, kept

    def test_a_complete_colour_mode_update_clears_the_superseded_mode(self) -> None:
        """Reuses BulbState.apply_command's mode-aware clearing."""
        state = SharedState()
        state.desired_state["office"] = _DESIRED  # CCT mode

        record_command(
            state,
            None,
            "office",
            {
                "state": None,
                "brightness": None,
                "hue": 0.0,
                "saturation": 100.0,
                "color_temp_kelvin": None,
                "scene": None,
                "speed": None,
            },
            1700.0,
        )

        desired = state.desired_state["office"]
        assert desired.appearance.hue == 0.0
        assert desired.appearance.saturation == 100.0
        assert desired.appearance.color_temp_kelvin is None  # cleared

    def test_state_false_writes_off(self) -> None:
        state = SharedState()
        state.desired_state["office"] = _DESIRED

        record_command(
            state,
            None,
            "office",
            {
                "state": False,
                "brightness": None,
                "hue": None,
                "saturation": None,
                "color_temp_kelvin": None,
                "scene": None,
                "speed": None,
            },
            1800.0,
        )

        assert state.desired_state["office"].state == "OFF"

    def test_returns_the_written_desired_state(self) -> None:
        state = SharedState()

        result = record_command(
            state,
            None,
            "office",
            {
                "state": True,
                "brightness": None,
                "hue": None,
                "saturation": None,
                "color_temp_kelvin": None,
                "scene": None,
                "speed": None,
            },
            1900.0,
        )

        assert result == state.desired_state["office"]

    def test_merges_onto_a_stored_record_on_a_cold_cache(self) -> None:
        """The store fallback (:class:`TestResolveDesiredState`) applies to
        the merge base too, not only to a plain read."""
        state = SharedState()
        store = _store({"desired_state": desired_state_to_dict(_DESIRED)})

        record_command(
            state,
            store,
            "office",
            {
                "state": None,
                "brightness": 77,
                "hue": None,
                "saturation": None,
                "color_temp_kelvin": None,
                "scene": None,
                "speed": None,
            },
            2100.0,
        )

        desired = state.desired_state["office"]
        assert desired.appearance.brightness == 77
        assert desired.appearance.color_temp_kelvin == 4000  # kept from the store


class TestQueue:
    """The single-slot per-bulb pending-command queue (cap-bjw9.6)."""

    def test_enqueue_then_pop_returns_the_kwargs(self) -> None:
        pending: dict[str, object] = {}
        kwargs = {"state": True}

        enqueue(pending, "office", kwargs, 100.0)  # type: ignore[arg-type]

        assert pop_valid(pending, "office", ttl=60.0, now=110.0) == kwargs

    def test_pop_removes_the_entry(self) -> None:
        pending: dict[str, object] = {}
        enqueue(pending, "office", {"state": True}, 100.0)  # type: ignore[arg-type]

        pop_valid(pending, "office", ttl=60.0, now=110.0)

        assert "office" not in pending

    def test_a_second_enqueue_replaces_the_first(self) -> None:
        pending: dict[str, object] = {}
        enqueue(pending, "office", {"state": True}, 100.0)  # type: ignore[arg-type]
        enqueue(pending, "office", {"state": False}, 105.0)  # type: ignore[arg-type]

        assert len(pending) == 1
        assert pop_valid(pending, "office", ttl=60.0, now=110.0) == {"state": False}

    def test_pop_returns_none_when_absent(self) -> None:
        assert pop_valid({}, "office", ttl=60.0, now=110.0) is None

    def test_pop_returns_the_kwargs_exactly_at_the_ttl_boundary(self) -> None:
        """Technique: Boundary Value Analysis — age == ttl is still valid."""
        pending: dict[str, object] = {}
        enqueue(pending, "office", {"state": True}, 0.0)  # type: ignore[arg-type]

        assert pop_valid(pending, "office", ttl=60.0, now=60.0) == {"state": True}

    def test_pop_drops_a_command_older_than_the_ttl(self) -> None:
        """Technique: Boundary Value Analysis — just over the limit is expired."""
        pending: dict[str, object] = {}
        enqueue(pending, "office", {"state": True}, 0.0)  # type: ignore[arg-type]

        assert pop_valid(pending, "office", ttl=60.0, now=60.001) is None
        assert "office" not in pending
