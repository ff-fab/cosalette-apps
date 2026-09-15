"""Unit tests for adapters/wizlight.py — WizBulbAdapter.

``pywizlight`` itself is never contacted over the network: ``pywizlight.wizlight``
and ``pywizlight.PilotBuilder`` are monkeypatched with local fakes/spies so this
module tests the adapter's own logic (capability caching, error wrapping,
push-staleness fallback, Kelvin clamping, scene validation, optimistic state
merge, lifecycle) without hardware. Real-bulb push/heartbeat behaviour is
verified separately .

Test Techniques Used:
- Sociable Unit Tests: real BulbType/Features/KelvinRange, faked transport only
- State Transition Testing: push cache freshness vs. staleness fallback to polling
- Boundary Value Analysis: Kelvin clamping at the bulb's real range
- Equivalence Partitioning: WizLightTimeOutError/ConnectionError/Error -> domain types
- Error Guessing: no-op set_state, scene validated before any hardware call
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from cosalette import EntityNotifier
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
    WizIdentityError,
    WizTimeoutError,
    WizUnsupportedCommandError,
)
from wiz2mqtt.models import BulbState
from wiz2mqtt.settings import Wiz2MqttSettings

_IP = "10.0.0.42"
_NAME = "office"
_UNCONFIGURED_IP = "10.0.0.99"


class _RecordingNotifier(EntityNotifier):
    """An ``EntityNotifier`` that records names instead of arming real slots.

    Subclassing keeps the adapter's ``notify: EntityNotifier`` annotation
    honest while sidestepping the framework's Phase-2 slot binding, which
    a unit test has no App to perform.
    """

    def __init__(self) -> None:
        super().__init__()
        self.armed: list[str] = []
        self.on_arm: Callable[[str], None] | None = None
        """Optional hook, run after recording — lets a test observe arm ordering."""

    def __call__(self, entity_name: str) -> None:
        self.armed.append(entity_name)
        if self.on_arm is not None:
            self.on_arm(entity_name)


def _settings(*, mac: str | None = None) -> Wiz2MqttSettings:
    """Isolated settings with exactly one bulb, ``office`` at ``_IP``."""
    return Wiz2MqttSettings(
        bulbs=[{"name": _NAME, "ip": _IP, "mac": mac}],  # type: ignore[list-item]
        _env_file=None,  # type: ignore[call-arg]
        _config_file=None,  # type: ignore[call-arg]
    )


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
        cold_white: int | None = 0,
        colortemp: int | None = None,
        scene_id: int | None = None,
        speed: int | None = None,
        power: float | None = None,
    ) -> None:
        self._state = state
        self._brightness = brightness
        self._rgb = rgb
        self._cold_white = cold_white
        self._colortemp = colortemp
        self._scene_id = scene_id
        self._speed = speed
        self._power = power

    def get_state(self) -> bool | None:
        return self._state

    def get_brightness(self) -> int | None:
        return self._brightness

    def get_rgb(self) -> tuple[float, float, float] | None:
        return self._rgb

    def get_cold_white(self) -> int | None:
        return self._cold_white

    def get_colortemp(self) -> int | None:
        return self._colortemp

    def get_scene_id(self) -> int | None:
        return self._scene_id

    def get_speed(self) -> int | None:
        return self._speed

    def get_power(self) -> float | None:
        return self._power


class _FakeWizLight:
    """Fake standing in for pywizlight's ``wizlight`` — no network I/O.

    ``last_push``, the cached ``state``, and ``updateState``'s short-circuit gate mirror
    pywizlight's own ``bulb.py:582,702,936`` (cap-dc5y): a real send only
    happens once ``last_push`` is older than ``_MAX_TIME_BETWEEN_PUSH``,
    exactly like the object ``WizBulbAdapter`` actually polls.
    """

    _MAX_TIME_BETWEEN_PUSH = 33.0  # PUSH_KEEP_ALIVE_INTERVAL(20) + TIMEOUT(13)
    _NEVER_TIME = -120.0

    def __init__(self, ip: str) -> None:
        self.ip = ip
        self.bulb_type: BulbType = _RGB_BULB_TYPE
        self.get_bulbtype_exc: Exception | None = None
        self.mac: str | None = "a8bb5006033d"
        self.get_mac_exc: Exception | None = None
        self.get_mac_calls = 0
        self.start_push_exc: Exception | None = None
        self.start_push_result = True
        self.start_push_calls: list[Any] = []
        self.last_push: float = self._NEVER_TIME
        self.state: list[_FakeParser | None] = []
        self.update_state_result: list[_FakeParser | None] | None = None
        self.update_state_exc: Exception | None = None
        self.update_state_calls = 0
        self.real_send_calls = 0
        self.turn_on_calls: list[Any] = []
        self.turn_on_exc: Exception | None = None
        self.turn_off_calls = 0
        self.turn_off_exc: Exception | None = None
        self.closed = False
        self.async_close_exc: Exception | None = None

    def receive_heartbeat(
        self, changed_state: list[_FakeParser | None] | None = None
    ) -> None:
        """Simulate an incoming syncPilot at this fake's local UDP socket.

        Always stamps ``last_push``, mirroring pywizlight's unconditional
        stamp at ``bulb.py:702``. Only invokes the registered push callback
        when *changed_state* is given, mirroring pywizlight's suppression of
        an unchanged heartbeat before the callback (``bulb.py:705-708``).
        """
        self.last_push = time.monotonic()
        if changed_state is not None and self.start_push_calls:
            self.state = changed_state
            self.start_push_calls[0](changed_state)

    async def get_bulbtype(self) -> BulbType:
        if self.get_bulbtype_exc is not None:
            raise self.get_bulbtype_exc
        return self.bulb_type

    async def getMac(self) -> str | None:  # noqa: N802 — pywizlight API
        self.get_mac_calls += 1
        if self.get_mac_exc is not None:
            raise self.get_mac_exc
        return self.mac

    async def start_push(self, callback: Any) -> bool:
        def _stamped(parsers: Any) -> None:
            # Mirrors pywizlight bulb.py:702 — last_push is stamped
            # unconditionally, before the suppression check decides
            # whether the adapter callback below even runs.
            self.last_push = time.monotonic()
            callback(parsers)

        self.start_push_calls.append(_stamped)
        if self.start_push_exc is not None:
            raise self.start_push_exc
        return self.start_push_result

    async def updateState(self, device: int = 0) -> list[_FakeParser | None] | None:
        self.update_state_calls += 1
        if self.last_push + self._MAX_TIME_BETWEEN_PUSH >= time.monotonic():
            return self.state  # short-circuit: reuse cache, mirrors bulb.py:922
        self.real_send_calls += 1
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
        if self.async_close_exc is not None:
            raise self.async_close_exc
        self.closed = True


class _PilotBuilderSpy:
    """Captures the kwargs the adapter builds, without pywizlight's own encoding."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@dataclass
class _Ctx:
    """Bundles the adapter under test with its patched pywizlight transport."""

    adapter: WizBulbAdapter
    notifier: _RecordingNotifier
    fake_bulbs: dict[str, _FakeWizLight] = field(default_factory=dict)
    pilot_calls: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> _Ctx:
    import pywizlight

    notifier = _RecordingNotifier()
    c = _Ctx(adapter=WizBulbAdapter(_settings(), notifier), notifier=notifier)

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


class TestIdentityVerification:
    """A configured MAC is checked once before publishing the bulb cache."""

    async def test_matching_mac_normalizes_case_and_separators(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pywizlight

        bulb = _FakeWizLight(_IP)
        bulb.mac = "A8:BB-50:06-03:3D"
        monkeypatch.setattr(pywizlight, "wizlight", lambda ip: bulb)
        adapter = WizBulbAdapter(_settings(mac="a8bb5006033d"), _RecordingNotifier())

        await adapter.get_capabilities(_IP)
        await adapter.get_capabilities(_IP)

        assert bulb.get_mac_calls == 1
        assert len(bulb.start_push_calls) == 1

    async def test_mismatch_does_not_cache_or_register_push(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        import pywizlight

        bulb = _FakeWizLight(_IP)
        bulb.mac = "001122334455"
        monkeypatch.setattr(pywizlight, "wizlight", lambda ip: bulb)
        adapter = WizBulbAdapter(_settings(mac="a8bb5006033d"), _RecordingNotifier())

        with caplog.at_level(logging.ERROR), pytest.raises(WizIdentityError):
            await adapter.get_capabilities(_IP)

        assert "identity mismatch" in caplog.text
        assert bulb.start_push_calls == []
        assert bulb.closed is True
        assert _IP not in adapter._bulbs  # noqa: SLF001
        assert _IP not in adapter._capabilities  # noqa: SLF001

    async def test_close_error_does_not_mask_identity_mismatch(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Cleanup is best-effort; the initialization error remains authoritative."""
        import pywizlight

        bulb = _FakeWizLight(_IP)
        bulb.mac = "001122334455"
        bulb.async_close_exc = RuntimeError("close failed")
        monkeypatch.setattr(pywizlight, "wizlight", lambda ip: bulb)
        adapter = WizBulbAdapter(_settings(mac="a8bb5006033d"), _RecordingNotifier())

        with caplog.at_level(logging.WARNING), pytest.raises(WizIdentityError):
            await adapter.get_capabilities(_IP)

        assert "failed to close rejected bulb" in caplog.text.lower()
        assert _IP not in adapter._bulbs  # noqa: SLF001

    @pytest.mark.parametrize(
        ("pywizlight_exc", "domain_exc"),
        [
            (WizLightTimeOutError, WizTimeoutError),
            (WizLightConnectionError, WizConnectionError),
            (WizLightError, WizBridgeError),
        ],
        ids=["timeout", "connection", "generic"],
    )
    async def test_get_mac_errors_close_without_caching_or_push(
        self,
        monkeypatch: pytest.MonkeyPatch,
        pywizlight_exc: type[Exception],
        domain_exc: type[Exception],
    ) -> None:
        """MAC-read failures reject and close the unpublished bulb instance."""
        import pywizlight

        bulb = _FakeWizLight(_IP)
        bulb.get_mac_exc = pywizlight_exc("boom")
        monkeypatch.setattr(pywizlight, "wizlight", lambda ip: bulb)
        adapter = WizBulbAdapter(_settings(mac="a8bb5006033d"), _RecordingNotifier())

        with pytest.raises(domain_exc):
            await adapter.get_capabilities(_IP)

        assert bulb.closed is True
        assert bulb.start_push_calls == []
        assert _IP not in adapter._bulbs  # noqa: SLF001
        assert _IP not in adapter._capabilities  # noqa: SLF001

    async def test_missing_config_does_not_read_mac(self, ctx: _Ctx) -> None:
        await ctx.adapter.get_capabilities(_IP)

        assert ctx.fake_bulbs[_IP].get_mac_calls == 0

    async def test_missing_readback_warns_and_initializes(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        import pywizlight

        bulb = _FakeWizLight(_IP)
        bulb.mac = None
        monkeypatch.setattr(pywizlight, "wizlight", lambda ip: bulb)
        adapter = WizBulbAdapter(_settings(mac="a8bb5006033d"), _RecordingNotifier())

        with caplog.at_level(logging.WARNING):
            await adapter.get_capabilities(_IP)

        assert "identity could not be verified" in caplog.text
        assert len(bulb.start_push_calls) == 1

    async def test_mismatch_can_retry_with_new_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pywizlight

        bulbs = [_FakeWizLight(_IP), _FakeWizLight(_IP)]
        bulbs[0].mac = "001122334455"
        monkeypatch.setattr(pywizlight, "wizlight", lambda ip: bulbs.pop(0))
        adapter = WizBulbAdapter(_settings(mac="a8bb5006033d"), _RecordingNotifier())

        with pytest.raises(WizIdentityError):
            await adapter.get_capabilities(_IP)
        await adapter.get_capabilities(_IP)

        assert len(bulbs) == 0
        assert _IP in adapter._bulbs  # noqa: SLF001


class TestFirstContactConcurrency:
    """First contact is serialized per IP without blocking other bulbs."""

    async def test_same_ip_concurrent_calls_initialize_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pywizlight

        entered = asyncio.Event()
        release = asyncio.Event()
        constructions: list[_FakeWizLight] = []

        class _BlockedBulb(_FakeWizLight):
            async def get_bulbtype(self) -> BulbType:
                entered.set()
                await release.wait()
                return await super().get_bulbtype()

        def _factory(
            ip: str, port: int = 38899, mac: str | None = None
        ) -> _FakeWizLight:
            bulb = _BlockedBulb(ip)
            constructions.append(bulb)
            return bulb

        monkeypatch.setattr(pywizlight, "wizlight", _factory)
        adapter = WizBulbAdapter(_settings(), _RecordingNotifier())
        state_task = asyncio.create_task(adapter.get_state(_IP))
        await entered.wait()
        caps_task = asyncio.create_task(adapter.get_capabilities(_IP))
        await asyncio.sleep(0)
        release.set()

        await asyncio.gather(state_task, caps_task)

        assert len(constructions) == 1
        assert len(constructions[0].start_push_calls) == 1

    async def test_failed_initialization_can_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pywizlight

        constructions: list[_FakeWizLight] = []

        def _factory(
            ip: str, port: int = 38899, mac: str | None = None
        ) -> _FakeWizLight:
            bulb = _FakeWizLight(ip)
            if not constructions:
                bulb.get_bulbtype_exc = WizLightTimeOutError("first attempt")
            constructions.append(bulb)
            return bulb

        monkeypatch.setattr(pywizlight, "wizlight", _factory)
        adapter = WizBulbAdapter(_settings(), _RecordingNotifier())

        with pytest.raises(WizTimeoutError):
            await adapter.get_capabilities(_IP)
        assert constructions[0].closed is True
        assert _IP not in adapter._bulbs  # noqa: SLF001
        assert _IP not in adapter._capabilities  # noqa: SLF001

        await adapter.get_capabilities(_IP)

        assert len(constructions) == 2
        assert len(constructions[1].start_push_calls) == 1

    async def test_different_ips_initialize_concurrently(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pywizlight

        both_entered = asyncio.Event()
        release = asyncio.Event()
        entered: set[str] = set()

        class _BlockedBulb(_FakeWizLight):
            async def get_bulbtype(self) -> BulbType:
                entered.add(self.ip)
                if len(entered) == 2:
                    both_entered.set()
                await release.wait()
                return await super().get_bulbtype()

        monkeypatch.setattr(pywizlight, "wizlight", _BlockedBulb)
        adapter = WizBulbAdapter(_settings(), _RecordingNotifier())
        tasks = [
            asyncio.create_task(adapter.get_capabilities(ip))
            for ip in ("10.0.0.1", "10.0.0.2")
        ]

        await asyncio.wait_for(both_entered.wait(), timeout=1)
        release.set()
        await asyncio.gather(*tasks)

        assert entered == {"10.0.0.1", "10.0.0.2"}


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

    async def test_wizlight_get_state_polls_on_first_call(
        self, ctx: _Ctx, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No push has ever arrived — first call must poll, and warn.

        Push registration having succeeded is what arms the warning
        (cap-fubw); a first call has no push history yet by construction, so
        it is exactly the "push never arrives" case the warning exists for.

        Technique: State Transition Testing — initial state has no push history.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].update_state_result = [_FakeParser(brightness=128)]

        with caplog.at_level(logging.WARNING):
            state = await ctx.adapter.get_state(_IP)

        assert ctx.fake_bulbs[_IP].update_state_calls == 1
        assert state.brightness == 128
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "recent push" in warnings[0].message.lower()

    async def test_wizlight_get_state_parses_rgb_into_hue_saturation(
        self, ctx: _Ctx
    ) -> None:
        """Technique: Round-trip Testing — pure red readback -> known hue/saturation."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].update_state_result = [_FakeParser(rgb=(255.0, 0.0, 0.0))]

        state = await ctx.adapter.get_state(_IP)

        assert state.hue == pytest.approx(0.0, abs=0.01)
        assert state.saturation == pytest.approx(100.0, abs=0.01)

    async def test_wizlight_get_state_ignores_stale_rgb_in_cct_mode(
        self, ctx: _Ctx
    ) -> None:
        """A non-zero colortemp means CCT mode, even with a populated rgb tuple.

        pywizlight's parser can report stale RGB residue from a prior
        colour-mode session alongside a non-zero colortemp; colortemp must
        win, per the CCT-mode detection rule (never ``get_rgb()``).

        Technique: Decision Table — colortemp x rgb populated -> mode.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].update_state_result = [
            _FakeParser(rgb=(255.0, 0.0, 0.0), colortemp=4000)
        ]

        state = await ctx.adapter.get_state(_IP)

        assert state.hue is None
        assert state.saturation is None
        assert state.color_temp_kelvin == 4000

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

    async def test_wizlight_get_state_first_read_uses_pywizlight_cached_heartbeat(
        self, ctx: _Ctx
    ) -> None:
        """A suppressed heartbeat before first read still seeds our cache.

        pywizlight refreshes ``last_push`` before suppressing an unchanged
        callback, then ``updateState()`` returns its own cached parser. The
        adapter must retain its unconditional first read to consume that
        parser rather than indexing an empty cache.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        await ctx.adapter.get_capabilities(_IP)
        fake.state = [_FakeParser(brightness=77)]
        fake.receive_heartbeat()  # unchanged: refreshes pywizlight only

        state = await ctx.adapter.get_state(_IP)

        assert fake.update_state_calls == 1
        assert fake.real_send_calls == 0
        assert state.brightness == 77

    async def test_wizlight_get_state_parses_effect_speed_and_power_draw(
        self, ctx: _Ctx
    ) -> None:
        """Technique: Specification-based — pass-through of speed/power getters."""
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].update_state_result = [_FakeParser(speed=150, power=8.4)]

        state = await ctx.adapter.get_state(_IP)

        assert state.effect_speed == 150
        assert state.power_draw_w == 8.4

    async def test_wizlight_get_state_falls_back_to_polling_when_stale(
        self, ctx: _Ctx
    ) -> None:
        """A push older than both staleness clocks means the next read polls
        for real.

        Technique: Boundary Value Analysis — ``bulb.last_push`` past the
        60 s adapter threshold and pywizlight's own 33 s gate.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        await ctx.adapter.get_capabilities(_IP)
        push_callback = fake.start_push_calls[0]
        push_callback([_FakeParser(brightness=77)])
        fake.last_push = time.monotonic() - 65.0  # push cache now stale
        fake.update_state_result = [_FakeParser(brightness=99)]

        state = await ctx.adapter.get_state(_IP)

        assert fake.update_state_calls == 1
        assert state.brightness == 99

    async def test_wizlight_get_state_warns_on_stale_push_not_first_poll(
        self, ctx: _Ctx, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Warning fires exactly once when a previously-fresh push goes stale.

        Technique: State Transition Testing — received-push then stale-push path.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        await ctx.adapter.get_capabilities(_IP)
        push_callback = fake.start_push_calls[0]
        push_callback([_FakeParser(brightness=77)])  # push received
        fake.last_push = time.monotonic() - 65.0  # push cache now stale
        fake.update_state_result = [_FakeParser(brightness=99)]

        with caplog.at_level(logging.WARNING):
            await ctx.adapter.get_state(_IP)  # stale → poll → warn

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "recent push" in warnings[0].message.lower()


# ---------------------------------------------------------------------------
# get_state — staleness measured against bulb.last_push (cap-dc5y)
# ---------------------------------------------------------------------------


class TestGetStateLivenessProbe:
    """A poll get_state decides on must always be a real network read.

    Before cap-dc5y, ``get_state`` measured staleness against the adapter's
    own state-changing callback record.
    ``pywizlight`` stamps ``bulb.last_push`` on every syncPilot, suppressed
    or not, and gates ``updateState()``'s own network send on that clock
    (``MAX_TIME_BETWEEN_PUSH`` = 33 s). A bulb idling on Wi-Fi keeps
    ``bulb.last_push`` fresh while that record carried no freshness, so the old
    decision could call ``updateState()`` while pywizlight's own gate was
    still shut — zero network I/O, a heartbeat tick that probed nothing.
    """

    async def test_wizlight_get_state_never_polls_while_bulb_keeps_heartbeating(
        self, ctx: _Ctx
    ) -> None:
        """Sustained suppressed heartbeats must never trigger a wasted poll.

        Technique: State Transition Testing — repeated fresh-heartbeat
        state across many ``get_state`` calls, after the first read has
        seeded the cache. Fails today: pre-cap-dc5y, the adapter's callback
        record never advances for a suppressed heartbeat, so every call decided to
        poll and every poll was a no-op.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        await ctx.adapter.get_capabilities(_IP)
        await ctx.adapter.get_state(_IP)  # first read seeds the cache
        calls_after_seed = fake.update_state_calls

        for _ in range(5):
            fake.receive_heartbeat()  # suppressed: no state change
            await ctx.adapter.get_state(_IP)

        assert fake.update_state_calls == calls_after_seed

    async def test_wizlight_get_state_poll_is_a_real_send_once_bulb_goes_silent(
        self, ctx: _Ctx
    ) -> None:
        """A bulb silent past the threshold is polled, and the poll is real.

        Technique: Boundary Value Analysis — ``bulb.last_push`` older than
        both the 60 s adapter threshold and pywizlight's own 33 s gate.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        await ctx.adapter.get_capabilities(_IP)
        fake.last_push = time.monotonic() - 70.0
        fake.update_state_result = [_FakeParser(brightness=99)]

        state = await ctx.adapter.get_state(_IP)

        assert fake.real_send_calls == 1
        assert state.brightness == 99

    async def test_wizlight_get_state_detects_mains_cut_once_heartbeats_stop(
        self, ctx: _Ctx
    ) -> None:
        """Heartbeats stop; the next eligible poll is real and surfaces the
        timeout instead of reporting the bulb healthy from a cache read.

        Technique: State Transition Testing — heartbeating, then silent.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        await ctx.adapter.get_capabilities(_IP)
        await ctx.adapter.get_state(_IP)  # first read seeds the cache
        calls_after_seed = fake.update_state_calls

        fake.receive_heartbeat()
        await ctx.adapter.get_state(_IP)
        assert fake.update_state_calls == calls_after_seed  # still fresh

        fake.last_push = time.monotonic() - 65.0  # mains cut; silent past 60 s
        fake.update_state_exc = WizLightTimeOutError("bulb unreachable")
        real_sends_before_cut = fake.real_send_calls

        with pytest.raises(WizTimeoutError):
            await ctx.adapter.get_state(_IP)

        assert fake.real_send_calls == real_sends_before_cut + 1

    async def test_wizlight_get_state_cadence_unchanged_when_bulb_never_pushes(
        self, ctx: _Ctx
    ) -> None:
        """Ethernet-only host: no push, suppressed or not, ever reaches the
        bulb object, so ``last_push`` never advances past its initial
        sentinel and every call keeps polling for real — the existing
        cadence for a host outside ADR-004's push reach is unchanged.

        Technique: Boundary Value Analysis — the never-pushed sentinel.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        await ctx.adapter.get_capabilities(_IP)
        fake.update_state_result = [_FakeParser(brightness=50)]

        await ctx.adapter.get_state(_IP)
        await ctx.adapter.get_state(_IP)

        assert fake.update_state_calls == 2
        assert fake.real_send_calls == 2


# ---------------------------------------------------------------------------
# Push-health warning — armed by registration, not by arrival (cap-fubw)
# ---------------------------------------------------------------------------


class TestPushHealthWarning:
    """The staleness warning must fire even when push has never arrived.

    Before this fix the warning was armed only by a push that actually
    arrived, so a bulb whose push never works (bridge-NAT, VLAN) polled
    silently forever with no operator-visible diagnostic.
    """

    async def test_wizlight_warns_when_push_registered_but_never_arrives(
        self, ctx: _Ctx, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Registration succeeds, no datagram ever arrives — still warns.

        Technique: Error Guessing — the never-arrives failure mode cap-fubw
        was filed for. Fails before the fix: zero warnings.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)

        with caplog.at_level(logging.WARNING):
            await ctx.adapter.get_state(_IP)

        warnings = [r for r in caplog.records if "recent push" in r.message.lower()]
        assert len(warnings) == 1

    async def test_wizlight_registration_failure_skips_staleness_warning(
        self, ctx: _Ctx, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A raised WizLightError warns once for the registration itself,
        not again for staleness — the operator was already told.

        Technique: Decision Table — registration outcome x warning emitted.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].start_push_exc = WizLightError("boom")

        with caplog.at_level(logging.WARNING):
            await ctx.adapter.get_state(_IP)

        messages = [r.message.lower() for r in caplog.records]
        assert sum("registration failed" in m for m in messages) == 1
        assert sum("recent push" in m for m in messages) == 0

    async def test_wizlight_warns_exactly_once_across_repeated_polls(
        self, ctx: _Ctx, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A push that never arrives still warns only once, not per poll.

        Technique: Equivalence Partitioning — repeated identical polls.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].update_state_result = [_FakeParser(brightness=1)]

        with caplog.at_level(logging.WARNING):
            await ctx.adapter.get_state(_IP)
            await ctx.adapter.get_state(_IP)
            await ctx.adapter.get_state(_IP)

        warnings = [r for r in caplog.records if "recent push" in r.message.lower()]
        assert len(warnings) == 1

    async def test_wizlight_no_warning_while_push_stays_fresh(
        self, ctx: _Ctx, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A push arriving within the threshold polls nothing and warns nothing.

        Technique: Boundary Value Analysis — inside the staleness window.
        Pins that the fix did not change the polling cadence.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        await ctx.adapter.get_capabilities(_IP)  # registers push
        push_callback = fake.start_push_calls[0]
        push_callback([_FakeParser(brightness=77)])  # push arrives, fresh

        with caplog.at_level(logging.WARNING):
            state = await ctx.adapter.get_state(_IP)

        assert fake.update_state_calls == 0
        assert state.brightness == 77
        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# ---------------------------------------------------------------------------
# Push registration retry — start_push's False return is honoured (cap-4rbg)
# ---------------------------------------------------------------------------


class TestPushRegistrationRetry:
    """A failed push registration is diagnosed and retried, not silently
    permanent for the life of the process.
    """

    async def test_wizlight_warns_when_start_push_returns_false(
        self, ctx: _Ctx, caplog: pytest.LogCaptureFixture
    ) -> None:
        """start_push's False return (not an exception) must still warn.

        Technique: Error Guessing — the dropped-return-value bug cap-4rbg
        was filed for. Fails before the fix: zero warnings.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].start_push_result = False

        with caplog.at_level(logging.WARNING):
            await ctx.adapter.get_state(_IP)

        warnings = [
            r for r in caplog.records if "registration failed" in r.message.lower()
        ]
        assert len(warnings) == 1

    async def test_wizlight_retries_registration_once_the_window_elapses(
        self, ctx: _Ctx
    ) -> None:
        """A failed registration is retried once the retry window elapses,
        and the recovered bulb starts pushing normally.

        Technique: State Transition Testing — failed, then recovered.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        fake.start_push_result = False

        await ctx.adapter.get_state(_IP)
        assert len(fake.start_push_calls) == 1

        fake.start_push_result = True
        ctx.adapter._push_retry_at[_IP] = time.monotonic() - 1  # noqa: SLF001

        await ctx.adapter.get_state(_IP)
        assert len(fake.start_push_calls) == 2

        push_callback = fake.start_push_calls[1]
        push_callback([_FakeParser(brightness=42)])

        assert ctx.adapter._state_cache[_IP].brightness == 42  # noqa: SLF001
        assert ctx.notifier.armed == [_NAME]

    async def test_wizlight_retry_is_rate_limited_within_the_window(
        self, ctx: _Ctx
    ) -> None:
        """Several get_state calls inside one retry window cost at most one
        extra registration attempt.

        Technique: Boundary Value Analysis — repeated calls before the
        retry window elapses.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        fake.start_push_result = False
        fake.update_state_result = [_FakeParser(brightness=1)]

        for _ in range(5):
            await ctx.adapter.get_state(_IP)

        assert len(fake.start_push_calls) <= 1

    async def test_wizlight_no_retry_churn_once_registered(self, ctx: _Ctx) -> None:
        """Registration succeeding on the first attempt costs exactly one
        call across many get_state calls — no retry loop on the happy path.

        Technique: Equivalence Partitioning — always-succeeding registration.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.fake_bulbs[_IP].update_state_result = [_FakeParser(brightness=1)]

        for _ in range(5):
            await ctx.adapter.get_state(_IP)

        assert len(ctx.fake_bulbs[_IP].start_push_calls) == 1

    async def test_wizlight_raising_registration_is_also_retried(
        self, ctx: _Ctx
    ) -> None:
        """The raising path keeps its existing warning and is retried too.

        Technique: Equivalence Partitioning — exception vs. False-return
        parity for the retry path.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        fake = ctx.fake_bulbs[_IP]
        fake.start_push_exc = WizLightError("boom")

        await ctx.adapter.get_state(_IP)
        assert len(fake.start_push_calls) == 1

        fake.start_push_exc = None
        ctx.adapter._push_retry_at[_IP] = time.monotonic() - 1  # noqa: SLF001

        await ctx.adapter.get_state(_IP)
        assert len(fake.start_push_calls) == 2
        assert _IP in ctx.adapter._push_registered  # noqa: SLF001


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

    async def test_wizlight_set_state_colour_clears_cached_color_temp(
        self, ctx: _Ctx
    ) -> None:
        """A colour command clears a cached CCT mode instead of leaving it stale.

        Technique: State Transition Testing — CCT mode to RGB mode.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.adapter._state_cache[_IP] = BulbState(  # noqa: SLF001
            state=True,
            brightness=None,
            hue=None,
            saturation=None,
            color_temp_kelvin=2700,
            scene=None,
        )

        await ctx.adapter.set_state(_IP, hue=0.0, saturation=100.0)

        cached = ctx.adapter._state_cache[_IP]  # noqa: SLF001
        assert cached.color_temp_kelvin is None
        assert cached.hue == 0.0
        assert cached.saturation == 100.0

    async def test_wizlight_set_state_false_merges_only_state(self, ctx: _Ctx) -> None:
        """turn_off sends nothing else, so the merge must not fabricate fields.

        Technique: Error Guessing — _send_pilot's off branch sends only
        turn_off(); the cache must not record unsent brightness/colour.
        """
        ctx.fake_bulbs[_IP] = _FakeWizLight(_IP)
        ctx.adapter._state_cache[_IP] = BulbState(  # noqa: SLF001
            state=True,
            brightness=200,
            hue=0.0,
            saturation=100.0,
            color_temp_kelvin=None,
            scene=None,
        )

        await ctx.adapter.set_state(_IP, state=False, brightness=1)

        cached = ctx.adapter._state_cache[_IP]  # noqa: SLF001
        assert cached.state is False
        assert cached.brightness == 200


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

    async def test_wizlight_aexit_clears_all_caches(self, ctx: _Ctx) -> None:
        """All internal caches are empty after __aexit__ — no stale handles remain.

        Technique: State Transition Testing — post-exit state.
        """
        await ctx.adapter.get_capabilities(_IP)
        await ctx.adapter.get_state(_IP)

        async with ctx.adapter:
            pass

        assert ctx.adapter._bulbs == {}  # noqa: SLF001
        assert ctx.adapter._initialization_locks == {}  # noqa: SLF001
        assert ctx.adapter._capabilities == {}  # noqa: SLF001
        assert ctx.adapter._state_cache == {}  # noqa: SLF001
        assert ctx.adapter._push_registered == set()  # noqa: SLF001
        assert ctx.adapter._push_retry_at == {}  # noqa: SLF001
        assert ctx.adapter._warned_stale == set()  # noqa: SLF001

    async def test_wizlight_aexit_closes_remaining_bulbs_after_close_error(
        self, ctx: _Ctx
    ) -> None:
        """A close exception on one bulb does not prevent closing the others.

        Technique: Error Guessing — exception mid-iteration during teardown.
        """
        await ctx.adapter.get_capabilities("10.0.0.1")
        await ctx.adapter.get_capabilities("10.0.0.2")
        ctx.fake_bulbs["10.0.0.1"].async_close_exc = RuntimeError("close failed")

        async with ctx.adapter:
            pass  # __aexit__ should not raise despite the first-bulb error

        assert ctx.fake_bulbs["10.0.0.2"].closed is True


# ---------------------------------------------------------------------------
# Push-driven trigger arming (cosalette ADR-064)
# ---------------------------------------------------------------------------


class TestPushWakesTelemetry:
    """A parsed push arms the matching telemetry entity's local trigger.

    The push callback used to be publication's dead end: it wrote the
    cache and returned, leaving the payload sitting there until the next
    ``interval=`` tick. These tests pin the wake that replaced that wait.
    """

    async def test_wizlight_push_arms_the_configured_entity_name(
        self, ctx: _Ctx
    ) -> None:
        """Technique: Specification-based — the arm uses the bulb's name, not its IP.

        The telemetry entities are named by ``main._bulb_map`` (bulb name),
        so arming by IP would raise ``UnknownEntityError`` at runtime.
        """
        await ctx.adapter.get_capabilities(_IP)
        push_callback = ctx.fake_bulbs[_IP].start_push_calls[0]

        push_callback([_FakeParser(brightness=77)])

        assert ctx.notifier.armed == [_NAME]

    async def test_wizlight_push_arms_after_the_cache_write(self, ctx: _Ctx) -> None:
        """The armed entity must find the *new* state, not the one it replaced.

        Technique: State Transition Testing — ordering of cache write vs. arm.
        """
        seen: list[int | None] = []
        await ctx.adapter.get_capabilities(_IP)
        push_callback = ctx.fake_bulbs[_IP].start_push_calls[0]

        def _record(entity_name: str) -> None:  # noqa: ARG001 — name unused here
            seen.append(ctx.adapter._state_cache[_IP].brightness)  # noqa: SLF001

        ctx.notifier.on_arm = _record
        push_callback([_FakeParser(brightness=77)])

        assert seen == [77]

    async def test_wizlight_unparseable_push_does_not_arm(self, ctx: _Ctx) -> None:
        """No state, no publish-worthy change — nothing to wake for.

        Technique: Error Guessing — empty/None parser list.
        """
        await ctx.adapter.get_capabilities(_IP)
        push_callback = ctx.fake_bulbs[_IP].start_push_calls[0]

        push_callback(None)
        push_callback([])
        push_callback([None])

        assert ctx.notifier.armed == []

    async def test_wizlight_push_for_unconfigured_ip_does_not_arm(
        self, ctx: _Ctx
    ) -> None:
        """An IP outside ``settings.bulbs`` has no telemetry entity to arm.

        Technique: Error Guessing — arming an unmapped IP would raise
        ``UnknownEntityError`` inside a UDP callback.
        """
        await ctx.adapter.get_capabilities(_UNCONFIGURED_IP)
        push_callback = ctx.fake_bulbs[_UNCONFIGURED_IP].start_push_calls[0]

        push_callback([_FakeParser(brightness=77)])

        assert ctx.notifier.armed == []
        assert ctx.adapter._state_cache[_UNCONFIGURED_IP].brightness == 77  # noqa: SLF001

    async def test_wizlight_every_push_arms_once(self, ctx: _Ctx) -> None:
        """Arming is per-push; coalescing is the framework slot's job, not ours.

        Technique: Equivalence Partitioning — burst of pushes.
        """
        await ctx.adapter.get_capabilities(_IP)
        push_callback = ctx.fake_bulbs[_IP].start_push_calls[0]

        for brightness in (10, 20, 30):
            push_callback([_FakeParser(brightness=brightness)])

        assert ctx.notifier.armed == [_NAME] * 3

    def test_wizlight_resolves_through_the_frameworks_adapter_injection(self) -> None:
        """The framework must be able to build this adapter at all.

        Technique: Specification-based — adapter resolution contract.
        ``_call_factory`` injects *every* annotated ``__init__`` parameter,
        so a plain ``float`` default would fail with "no provider is
        registered for type float". ``Annotated[float, Optional()]`` is
        what keeps it out of the plan; this test fails if that is dropped.
        """
        from cosalette._wiring._adapter_lifecycle import (  # noqa: PLC0415
            _build_adapter_providers,
            _call_factory,
        )

        providers = _build_adapter_providers(_settings(), _RecordingNotifier())
        adapter = _call_factory(WizBulbAdapter, providers)

        assert isinstance(adapter, WizBulbAdapter)
        assert adapter._name_by_ip == {_IP: _NAME}  # noqa: SLF001
