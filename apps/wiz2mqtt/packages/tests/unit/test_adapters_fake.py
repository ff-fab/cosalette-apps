"""Unit tests for adapters/fake.py — FakeWizBulbAdapter.

Test Techniques Used:
- Specification-based: Default capabilities/state without prior injection
- State Transition Testing: Partial set_state merges onto existing state
- Error Guessing: fail_next raises once then clears
- Sociable Unit Tests: Exercised entirely through the WizBulbPort surface
"""

from __future__ import annotations

import pytest
from cosalette import EntityNotifier

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.errors import WizTimeoutError
from wiz2mqtt.models import BulbCapabilities, BulbState
from wiz2mqtt.settings import Wiz2MqttSettings

_IP = "10.0.0.42"
_NAME = "office"


@pytest.fixture
def fake() -> FakeWizBulbAdapter:
    return FakeWizBulbAdapter()


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    """Unseen bulbs get sensible defaults without prior injection."""

    async def test_fake_get_capabilities_defaults_to_full_featured_rgb(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — default capability shape."""
        caps = await fake.get_capabilities(_IP)
        assert caps.bulb_class == "RGB"
        assert caps.color is True

    async def test_fake_get_state_defaults_to_off_and_unset(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — default state shape."""
        state = await fake.get_state(_IP)
        assert state.state is False
        assert state.brightness is None


# ---------------------------------------------------------------------------
# Partial updates
# ---------------------------------------------------------------------------


class TestSetState:
    """set_state merges only the given fields onto existing state."""

    async def test_fake_set_state_merges_partial_update(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """A brightness-only update leaves other fields untouched.

        Technique: State Transition Testing — sequential partial updates.
        """
        await fake.set_state(_IP, state=True, brightness=128)
        await fake.set_state(_IP, hue=200.0, saturation=50.0)

        state = await fake.get_state(_IP)
        assert state.state is True
        assert state.brightness == 128
        assert state.hue == 200.0
        assert state.saturation == 50.0

    async def test_fake_set_state_false_is_not_treated_as_unset(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """``state=False`` must apply, not be filtered out like ``None``.

        Technique: Error Guessing — False is falsy but not None.
        """
        await fake.set_state(_IP, state=True)
        await fake.set_state(_IP, state=False)

        state = await fake.get_state(_IP)
        assert state.state is False

    async def test_fake_set_state_colour_clears_color_temp(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """A colour command clears a cached CCT mode, pinned to the real adapter.

        Technique: State Transition Testing — CCT mode to RGB mode.
        """
        await fake.set_state(_IP, state=True, color_temp_kelvin=2700)
        await fake.set_state(_IP, hue=0.0, saturation=100.0)

        state = await fake.get_state(_IP)
        assert state.color_temp_kelvin is None
        assert state.hue == 0.0
        assert state.saturation == 100.0

    async def test_fake_set_state_false_merges_only_state(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """``state=False`` must not fabricate unsent brightness/colour fields.

        Technique: Error Guessing — pinned to the real adapter's off branch.
        """
        await fake.set_state(_IP, state=True, brightness=200, hue=0.0, saturation=100.0)
        await fake.set_state(_IP, state=False, brightness=1)

        state = await fake.get_state(_IP)
        assert state.state is False
        assert state.brightness == 200


# ---------------------------------------------------------------------------
# Test-injection helpers
# ---------------------------------------------------------------------------


class TestInjectionHelpers:
    """inject_capabilities/inject_push/fail_next drive test scenarios."""

    async def test_fake_inject_capabilities_overrides_default(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — seeded capability override."""
        fake.inject_capabilities(
            _IP,
            BulbCapabilities(
                bulb_class="TW",
                color=False,
                color_tmp=True,
                effect=True,
                brightness=True,
                kelvin_min=2700,
                kelvin_max=6500,
            ),
        )
        caps = await fake.get_capabilities(_IP)
        assert caps.bulb_class == "TW"
        assert caps.color is False

    async def test_fake_inject_push_overwrites_cached_state_directly(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Simulates a push arriving out-of-band from any set_state call.

        Technique: Specification-based — push-simulation helper contract.
        """
        pushed = BulbState(
            state=True,
            brightness=255,
            hue=10.0,
            saturation=90.0,
            color_temp_kelvin=None,
            scene=None,
        )
        fake.inject_push(_IP, pushed)
        assert await fake.get_state(_IP) == pushed

    async def test_fake_fail_next_raises_once_then_clears(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """fail_next primes exactly one failure, then normal behaviour resumes.

        Technique: Error Guessing — one-shot failure injection for
        exercising future unavailable_on wiring.
        """
        fake.fail_next(_IP, WizTimeoutError("simulated timeout"))

        with pytest.raises(WizTimeoutError):
            await fake.get_state(_IP)

        # Second call succeeds — the primed failure was consumed.
        state = await fake.get_state(_IP)
        assert state.state is False


# ---------------------------------------------------------------------------
# HealthCheckable / lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """health_check and async context manager methods are no-ops that succeed."""

    async def test_fake_health_check_always_true(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — fake has no connection to break."""
        assert await fake.health_check() is True

    async def test_fake_async_context_manager_roundtrip(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — __aenter__/__aexit__ contract."""
        async with fake as entered:
            assert entered is fake


# ---------------------------------------------------------------------------
# Push-driven trigger arming (cosalette ADR-064)
# ---------------------------------------------------------------------------


class _RecordingNotifier(EntityNotifier):
    """An ``EntityNotifier`` that records names instead of arming real slots."""

    def __init__(self) -> None:
        super().__init__()
        self.armed: list[str] = []

    def __call__(self, entity_name: str) -> None:
        self.armed.append(entity_name)


def _settings() -> Wiz2MqttSettings:
    """Isolated settings with exactly one bulb, ``office`` at ``_IP``."""
    return Wiz2MqttSettings(
        bulbs=[{"name": _NAME, "ip": _IP}],  # type: ignore[list-item]
        _env_file=None,  # type: ignore[call-arg]
        _config_file=None,  # type: ignore[call-arg]
    )


class TestInjectPushArmsTrigger:
    """``inject_push`` mirrors the production push: cache write, then wake.

    Without this the fake silently loses the event-driven path, and every
    ``--dry-run`` or integration run would fall back to the ``interval=``
    heartbeat while appearing to pass.
    """

    async def test_fake_inject_push_arms_the_configured_entity_name(self) -> None:
        """Technique: Specification-based — arm by bulb name, not IP."""
        notifier = _RecordingNotifier()
        fake = FakeWizBulbAdapter(_settings(), notifier)

        fake.inject_push(_IP, await fake.get_state(_IP))

        assert notifier.armed == [_NAME]

    async def test_fake_bind_restores_injection_for_a_prebuilt_fake(self) -> None:
        """Technique: State Transition Testing — unbound then bound.

        The integration harness registers a pre-built fake through a
        closure, which bypasses constructor injection entirely.
        """
        notifier = _RecordingNotifier()
        fake = FakeWizBulbAdapter()
        state = await fake.get_state(_IP)

        fake.inject_push(_IP, state)  # unbound — nothing to arm
        assert notifier.armed == []

        fake.bind(_settings(), notifier)
        fake.inject_push(_IP, state)

        assert notifier.armed == [_NAME]

    async def test_fake_inject_push_for_unconfigured_ip_does_not_arm(self) -> None:
        """Technique: Error Guessing — no entity exists for an unmapped IP."""
        notifier = _RecordingNotifier()
        fake = FakeWizBulbAdapter(_settings(), notifier)
        state = await fake.get_state(_IP)

        fake.inject_push("10.0.0.99", state)

        assert notifier.armed == []
        assert (await fake.get_state("10.0.0.99")) == state


# ---------------------------------------------------------------------------
# set_unreachable (ADR-008 / cap-bjw9.2)
# ---------------------------------------------------------------------------


class TestSetUnreachable:
    """set_unreachable makes a specific bulb behave as unreachable."""

    async def test_get_state_raises_while_unreachable(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: State Transition Testing — reachable to unreachable."""
        fake.set_unreachable(_IP, True)

        with pytest.raises(WizTimeoutError):
            await fake.get_state(_IP)

    async def test_get_state_call_count_still_increments_while_unreachable(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — the attempt still counts."""
        fake.set_unreachable(_IP, True)

        with pytest.raises(WizTimeoutError):
            await fake.get_state(_IP)

        assert fake.get_state_call_count == 1

    async def test_set_state_raises_while_unreachable(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Equivalence Partitioning — both read and write paths."""
        fake.set_unreachable(_IP, True)

        with pytest.raises(WizTimeoutError):
            await fake.set_state(_IP, state=True)

    async def test_clearing_unreachable_restores_normal_behaviour(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: State Transition Testing — unreachable back to reachable."""
        fake.set_unreachable(_IP, True)
        fake.set_unreachable(_IP, False)

        state = await fake.get_state(_IP)
        assert state.state is False

    async def test_unreachable_is_per_bulb(self, fake: FakeWizBulbAdapter) -> None:
        """Technique: Equivalence Partitioning — an untouched bulb is unaffected."""
        fake.set_unreachable(_IP, True)

        other = await fake.get_state("10.0.0.99")
        assert other.state is False

    async def test_always_fail_is_a_shortcut_for_every_bulb(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — always_fail kept as a global shim."""
        fake.always_fail = True

        with pytest.raises(WizTimeoutError):
            await fake.get_state(_IP)
        with pytest.raises(WizTimeoutError):
            await fake.get_state("10.0.0.99")


# ---------------------------------------------------------------------------
# boot / register_boot_callback (ADR-008 / cap-bjw9.2)
# ---------------------------------------------------------------------------


class TestBoot:
    """boot() simulates a bulb power-cycling into its default state."""

    @staticmethod
    def _boot_state(*, state: bool, brightness: int | None) -> BulbState:
        return BulbState(
            state=state,
            brightness=brightness,
            hue=None,
            saturation=None,
            color_temp_kelvin=None,
            scene=None,
        )

    async def test_boot_clears_unreachable(self, fake: FakeWizBulbAdapter) -> None:
        """Technique: State Transition Testing."""
        fake.set_unreachable(_IP, True)

        fake.boot(_IP, self._boot_state(state=True, brightness=255))

        state = await fake.get_state(_IP)
        assert state.state is True
        assert state.brightness == 255

    async def test_boot_replaces_cached_state(self, fake: FakeWizBulbAdapter) -> None:
        """Technique: Specification-based — boot state wins over any prior state."""
        await fake.set_state(_IP, state=True, brightness=1)

        fake.boot(_IP, self._boot_state(state=False, brightness=None))

        state = await fake.get_state(_IP)
        assert state.state is False
        assert state.brightness is None

    async def test_boot_fires_the_registered_callback_exactly_once_with_ip(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — firstBeat-equivalent boot event."""
        calls: list[str] = []
        fake.register_boot_callback(calls.append)

        fake.boot(_IP, self._boot_state(state=True, brightness=100))

        assert calls == [_IP]

    async def test_boot_without_a_registered_callback_does_not_raise(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Error Guessing — no callback registered is a valid state."""
        fake.boot(_IP, self._boot_state(state=True, brightness=100))  # must not raise


# ---------------------------------------------------------------------------
# refuse_writes (ADR-008 / cap-bjw9.2)
# ---------------------------------------------------------------------------


class TestRefuseWrites:
    """refuse_writes drives the three-retry rule: N writes are silently dropped."""

    async def test_refused_writes_leave_cached_state_unchanged(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Boundary Value Analysis — exactly at the refused count."""
        fake.refuse_writes(_IP, 2)

        await fake.set_state(_IP, state=True, brightness=200)
        await fake.set_state(_IP, state=True, brightness=201)

        state = await fake.get_state(_IP)
        assert state.state is False
        assert state.brightness is None

    async def test_call_after_refused_count_changes_state(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Boundary Value Analysis — first call past the boundary."""
        fake.refuse_writes(_IP, 2)

        await fake.set_state(_IP, state=True, brightness=200)
        await fake.set_state(_IP, state=True, brightness=201)
        await fake.set_state(_IP, state=True, brightness=202)

        state = await fake.get_state(_IP)
        assert state.state is True
        assert state.brightness == 202

    async def test_refused_writes_do_not_raise(self, fake: FakeWizBulbAdapter) -> None:
        """Technique: Specification-based — refused writes 'succeed on the wire'."""
        fake.refuse_writes(_IP, 1)

        await fake.set_state(_IP, state=True)  # must not raise


# ---------------------------------------------------------------------------
# set_state_calls (ADR-008 / cap-bjw9.2)
# ---------------------------------------------------------------------------


class TestSetStateCalls:
    """set_state_calls logs every call, in order, with its kwargs."""

    async def test_records_calls_in_order_with_kwargs(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — order and payload fidelity."""
        await fake.set_state(_IP, state=False)
        await fake.set_state(_IP, state=True, brightness=128)

        assert fake.set_state_calls[0][0] == _IP
        assert fake.set_state_calls[0][1]["state"] is False
        assert fake.set_state_calls[1][1]["state"] is True
        assert fake.set_state_calls[1][1]["brightness"] == 128

    async def test_records_calls_even_when_refused(
        self, fake: FakeWizBulbAdapter
    ) -> None:
        """Technique: Error Guessing — a refused write is still a logged attempt."""
        fake.refuse_writes(_IP, 1)

        await fake.set_state(_IP, state=True)

        assert len(fake.set_state_calls) == 1
