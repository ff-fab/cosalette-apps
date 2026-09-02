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
