"""Unit tests for adapters/wizlight.py — WizBulbAdapter.

``pywizlight`` itself is never contacted over the network: ``pywizlight.wizlight``
and ``pywizlight.PilotBuilder`` are monkeypatched with local fakes/spies so this
module tests the adapter's own logic (capability caching, error wrapping,
push-staleness fallback, Kelvin clamping, scene validation, optimistic state
merge, lifecycle) without hardware. Real-bulb push/heartbeat behaviour is
verified separately (cap-10u.19).

Test Techniques Used:
- Sociable Unit Tests: real BulbType/Features/KelvinRange, faked transport only
- State Transition Testing: push cache freshness vs. staleness fallback to polling
- Boundary Value Analysis: Kelvin clamping at the bulb's real range
- Equivalence Partitioning: WizLightTimeOutError/ConnectionError/Error -> domain types
- Error Guessing: no-op set_state, scene validated before any hardware call
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from pywizlight.bulblibrary import BulbClass, BulbType, Features, KelvinRange
from pywizlight.exceptions import (
    WizLightConnectionError,
    WizLightError,
    WizLightTimeOutError,
)

from wiz2mqtt.adapters.wizlight import WizBulbAdapter
from wiz2mqtt.errors import (
    WizBridgeError,
    WizConnectionError,
    WizTimeoutError,
    WizUnsupportedCommandError,
)

_IP = "10.0.0.42"

_RGB_BULB_TYPE = BulbType(
    features=Features(
        color=True, color_tmp=True, effect=True, brightness=True, dual_head=False
    ),
    name="ESP01_SHRGB_03",
    kelvin_range=KelvinRange(max=6500, min=2200),
    bulb_type=BulbClass.RGB,
    fw_version="1.0.0",
    white_channels=2,
    white_to_color_ratio=20,
)

_TW_BULB_TYPE = BulbType(
    features=Features(
        color=False, color_tmp=True, effect=True, brightness=True, dual_head=False
    ),
    name="ESP01_TW",
    kelvin_range=KelvinRange(max=6500, min=2700),
    bulb_type=BulbClass.TW,
    fw_version="1.0.0",
    white_channels=2,
    white_to_color_ratio=20,
)


class _FakeParser:
    """Duck-types PilotParser's getters used by ``_parse_state``."""

    def __init__(
        self,
        *,
        state: bool | None = True,
        brightness: int | None = 200,
        rgb: tuple[float, float, float] | None = (255.0, 0.0, 0.0),
        colortemp: int | None = None,
        scene_id: int | None = None,
    ) -> None:
        self._state = state
        self._brightness = brightness
        self._rgb = rgb
        self._colortemp = colortemp
        self._scene_id = scene_id

    def get_state(self) -> bool | None:
        return self._state

    def get_brightness(self) -> int | None:
        return self._brightness

    def get_rgb(self) -> tuple[float, float, float] | None:
        return self._rgb

    def get_colortemp(self) -> int | None:
        return self._colortemp

    def get_scene_id(self) -> int | None:
        return self._scene_id


class _FakeWizLight:
    """Fake standing in for pywizlight's ``wizlight`` — no network I/O."""

    def __init__(self, ip: str) -> None:
        self.ip = ip
        self.bulb_type: BulbType = _RGB_BULB_TYPE
        self.get_bulbtype_exc: Exception | None = None
        self.start_push_exc: Exception | None = None
        self.start_push_calls: list[Any] = []
        self.update_state_result: list[_FakeParser | None] | None = None
        self.update_state_exc: Exception | None = None
        self.update_state_calls = 0
        self.turn_on_calls: list[Any] = []
        self.turn_on_exc: Exception | None = None
        self.turn_off_calls = 0
        self.turn_off_exc: Exception | None = None
        self.closed = False

    async def get_bulbtype(self) -> BulbType:
        if self.get_bulbtype_exc is not None:
            raise self.get_bulbtype_exc
        return self.bulb_type

    async def start_push(self, callback: Any) -> bool:
        self.start_push_calls.append(callback)
        if self.start_push_exc is not None:
            raise self.start_push_exc
        return True

    async def updateState(self, device: int = 0) -> list[_FakeParser | None] | None:
        self.update_state_calls += 1
        if self.update_state_exc is not None:
            raise self.update_state_exc
        return self.update_state_result

    async def turn_on(self, pilot_builder: Any, device: int | None = None) -> None:
        if self.turn_on_exc is not None:
            raise self.turn_on_exc
        self.turn_on_calls.append(pilot_builder)

    async def turn_off(self, device: int | None = None) -> None:
        if self.turn_off_exc is not None:
            raise self.turn_off_exc
        self.turn_off_calls += 1

    async def async_close(self) -> None:
        self.closed = True


class _PilotBuilderSpy:
    """Captures the kwargs the adapter builds, without pywizlight's own encoding."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@dataclass
class _Ctx:
    """Bundles the adapter under test with its patched pywizlight transport."""

    adapter: WizBulbAdapter
    fake_bulbs: dict[str, _FakeWizLight] = field(default_factory=dict)
    pilot_calls: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> _Ctx:
    import pywizlight

    c = _Ctx(adapter=WizBulbAdapter())

    def _factory(ip: str, port: int = 38899, mac: str | None = None) -> _FakeWizLight:
        return c.fake_bulbs.setdefault(ip, _FakeWizLight(ip))

    class _RecordingSpy(_PilotBuilderSpy):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            c.pilot_calls.append(kwargs)

    monkeypatch.setattr(pywizlight, "wizlight", _factory)
    monkeypatch.setattr(pywizlight, "PilotBuilder", _RecordingSpy)
    return c


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------


class TestGetCapabilities:
    """Capabilities are detected from get_bulbtype() at first contact."""

    async def test_wizlight_get_capabilities_detects_from_bulbtype(
        self, ctx: _Ctx
    ) -> None:
        """Technique: Sociable Unit Tests — real BulbType/Features/KelvinRange."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].bulb_type = _RGB_BULB_TYPE

        caps = await ctx.adapter.get_capabilities(_IP)

        assert caps.bulb_class == "RGB"
        assert caps.color is True
        assert caps.kelvin_min == 2200
        assert caps.kelvin_max == 6500

    async def test_wizlight_get_capabilities_registers_push_on_first_contact(
        self, ctx: _Ctx
    ) -> None:
        """Technique: Specification-based — first contact registers push."""
        await ctx.adapter.get_capabilities(_IP)
        assert len(ctx.fake_bulbs[_IP].start_push_calls) == 1

    async def test_wizlight_get_capabilities_caches_across_calls(
        self, ctx: _Ctx
    ) -> None:
        """Technique: State Transition Testing — first-contact vs. cached path."""
        await ctx.adapter.get_capabilities(_IP)
        await ctx.adapter.get_capabilities(_IP)
        assert len(ctx.fake_bulbs[_IP].start_push_calls) == 1


# ---------------------------------------------------------------------------
# Error wrapping
# ---------------------------------------------------------------------------


class TestErrorWrapping:
    """pywizlight exceptions are re-raised as domain exceptions at the boundary."""

    @pytest.mark.parametrize(
        ("pywizlight_exc", "domain_exc"),
        [
            (WizLightTimeOutError, WizTimeoutError),
            (WizLightConnectionError, WizConnectionError),
            (WizLightError, WizBridgeError),
        ],
        ids=["timeout", "connection", "generic"],
    )
    async def test_wizlight_get_capabilities_wraps_pywizlight_errors(
        self, ctx: _Ctx, pywizlight_exc: type[Exception], domain_exc: type[Exception]
    ) -> None:
        """Technique: Equivalence Partitioning — one class per pywizlight exception."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].get_bulbtype_exc = pywizlight_exc("boom")

        with pytest.raises(domain_exc):
            await ctx.adapter.get_capabilities(_IP)

    async def test_wizlight_get_state_wraps_poll_errors(self, ctx: _Ctx) -> None:
        """Technique: Equivalence Partitioning — polling path wraps errors too."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].update_state_exc = WizLightTimeOutError("boom")

        with pytest.raises(WizTimeoutError):
            await ctx.adapter.get_state(_IP)

    async def test_wizlight_set_state_wraps_turn_on_errors(self, ctx: _Ctx) -> None:
        """Technique: Equivalence Partitioning — command path wraps errors too."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].turn_on_exc = WizLightConnectionError("boom")

        with pytest.raises(WizConnectionError):
            await ctx.adapter.set_state(_IP, brightness=100)


# ---------------------------------------------------------------------------
# get_state — push cache vs. polling fallback
# ---------------------------------------------------------------------------


class TestGetState:
    """get_state prefers the push cache; falls back to polling when stale."""

    async def test_wizlight_get_state_polls_on_first_call(self, ctx: _Ctx) -> None:
        """No push has ever arrived, so the very first call must poll.

        Technique: State Transition Testing — initial state has no push history.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].update_state_result = [_FakeParser(brightness=128)]

        state = await ctx.adapter.get_state(_IP)

        assert ctx.fake_bulbs[_IP].update_state_calls == 1
        assert state.brightness == 128

    async def test_wizlight_get_state_parses_rgb_into_hue_saturation(
        self, ctx: _Ctx
    ) -> None:
        """Technique: Round-trip Testing — pure red readback -> known hue/saturation."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].update_state_result = [_FakeParser(rgb=(255.0, 0.0, 0.0))]

        state = await ctx.adapter.get_state(_IP)

        assert state.hue == pytest.approx(0.0, abs=0.01)
        assert state.saturation == pytest.approx(100.0, abs=0.01)

    async def test_wizlight_get_state_uses_push_cache_when_fresh(
        self, ctx: _Ctx
    ) -> None:
        """A push received just before the call must short-circuit polling.

        Technique: State Transition Testing — fresh-push state.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        await ctx.adapter.get_capabilities(_IP)  # first contact registers push
        push_callback = ctx.fake_bulbs[_IP].start_push_calls[0]
        push_callback([_FakeParser(brightness=77)])

        state = await ctx.adapter.get_state(_IP)

        assert ctx.fake_bulbs[_IP].update_state_calls == 0
        assert state.brightness == 77

    async def test_wizlight_get_state_falls_back_to_polling_when_stale(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A threshold of 0 means any prior push is immediately stale.

        Technique: Boundary Value Analysis — staleness threshold at zero.
        """
        import pywizlight

        fake_bulbs: dict[str, _FakeWizLight] = {}

        def _factory(
            ip: str, port: int = 38899, mac: str | None = None
        ) -> _FakeWizLight:
            return fake_bulbs.setdefault(ip, _FakeWizLight(ip))

        monkeypatch.setattr(pywizlight, "wizlight", _factory)
        monkeypatch.setattr(pywizlight, "PilotBuilder", _PilotBuilderSpy)
        adapter = WizBulbAdapter(push_staleness_threshold=0.0)
        fake_bulbs[_IP] = _FakeWizLight(_IP)
        await adapter.get_capabilities(_IP)
        push_callback = fake_bulbs[_IP].start_push_calls[0]
        push_callback([_FakeParser(brightness=77)])
        fake_bulbs[_IP].update_state_result = [_FakeParser(brightness=99)]

        state = await adapter.get_state(_IP)

        assert fake_bulbs[_IP].update_state_calls == 1
        assert state.brightness == 99


# ---------------------------------------------------------------------------
# set_state
# ---------------------------------------------------------------------------


class TestSetState:
    """set_state clamps/validates before building the pywizlight command."""

    async def test_wizlight_set_state_no_op_when_all_fields_none(
        self, ctx: _Ctx
    ) -> None:
        """Technique: Error Guessing — nothing to send means no bulb contact at all."""
        await ctx.adapter.set_state(_IP)
        assert _IP not in ctx.fake_bulbs

    async def test_wizlight_set_state_false_calls_turn_off(self, ctx: _Ctx) -> None:
        """Technique: State Transition Testing — off path bypasses PilotBuilder."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        await ctx.adapter.set_state(_IP, state=False)

        assert ctx.fake_bulbs[_IP].turn_off_calls == 1
        assert ctx.fake_bulbs[_IP].turn_on_calls == []

    async def test_wizlight_set_state_clamps_colortemp_to_bulb_range(
        self, ctx: _Ctx
    ) -> None:
        """Technique: Boundary Value Analysis — value above the RGB bulb's 6500K max."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].bulb_type = _RGB_BULB_TYPE

        await ctx.adapter.set_state(_IP, color_temp_kelvin=10000)

        assert ctx.pilot_calls[-1]["colortemp"] == 6500

    async def test_wizlight_set_state_rejects_unsupported_scene_before_hardware_call(
        self, ctx: _Ctx
    ) -> None:
        """Technique: Error Guessing — validation must precede any turn_on call."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].bulb_type = _TW_BULB_TYPE

        with pytest.raises(WizUnsupportedCommandError):
            await ctx.adapter.set_state(_IP, scene=1)  # "Ocean" is RGB-only

        assert ctx.fake_bulbs[_IP].turn_on_calls == []

    async def test_wizlight_set_state_builds_hucolor_from_hue_and_saturation(
        self, ctx: _Ctx
    ) -> None:
        """Technique: Specification-based — hucolor tuple, never rgb=."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)

        await ctx.adapter.set_state(_IP, hue=200.0, saturation=50.0)

        assert ctx.pilot_calls[-1]["hucolor"] == (200.0, 50.0)
        assert ctx.pilot_calls[-1].get("rgb") is None

    async def test_wizlight_set_state_optimistically_merges_into_cache(
        self, ctx: _Ctx
    ) -> None:
        """Cache reflects the sent command immediately, pending the next push/poll.

        Technique: State Transition Testing.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)

        await ctx.adapter.set_state(_IP, brightness=42)

        cached = ctx.adapter._state_cache[_IP]  # noqa: SLF001 — inspecting internal cache is the point
        assert cached.brightness == 42


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """health_check and the async context manager protocol."""

    async def test_wizlight_health_check_always_true(self, ctx: _Ctx) -> None:
        """Technique: Specification-based — UDP is connectionless, no link to probe."""
        assert await ctx.adapter.health_check() is True

    async def test_wizlight_aenter_returns_self(self, ctx: _Ctx) -> None:
        """Technique: Specification-based — no-op, connections are lazy per bulb."""
        async with ctx.adapter as entered:
            assert entered is ctx.adapter

    async def test_wizlight_aexit_closes_every_connected_bulb(self, ctx: _Ctx) -> None:
        """Every cached bulb is closed on exit, not just one.

        Technique: Specification-based.
        """
        await ctx.adapter.get_capabilities("10.0.0.1")
        await ctx.adapter.get_capabilities("10.0.0.2")

        async with ctx.adapter:
            pass

        assert ctx.fake_bulbs["10.0.0.1"].closed is True
        assert ctx.fake_bulbs["10.0.0.2"].closed is True
