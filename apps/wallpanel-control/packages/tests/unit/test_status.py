"""Unit tests for devices/status.py — status telemetry handler.

Test Techniques Used:
- Specification-based Testing: StatusState defaults, _status_interval contract,
    create_status_state factory, router registration.
- Branch/Condition Coverage: reachable/unreachable path, max_brightness cached
  vs. uninitialised, None returns from brightness/screen, WallpanelUnreachableError
  during lazy max read.
- State Transition Testing: max_brightness: None → cached on first successful poll.
- Equivalence Partitioning: screen state ON/OFF, percentage values.
- Error Guessing: get_brightness=None, get_screen_state=None, WallpanelUnreachableError
  mid-poll, wrong settings type passed to _status_interval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import TracebackType
from typing import Self

import cosalette
import pytest

from tests.fixtures.config import make_wallpanel_control_settings
from wallpanel_control.adapters.fake import FakeWallpanel
from wallpanel_control.devices.status import (
    StatusState,
    _status_interval,
    create_status_state,
    poll_status,
    router,
)
from wallpanel_control.ports import WallpanelUnreachableError
from wallpanel_control.settings import WallpanelControlSettings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(max_brightness: int | None = None) -> StatusState:
    return StatusState(max_brightness=max_brightness)


def _trigger(*, triggered: bool = False) -> cosalette.TriggerPayload:
    return cosalette.TriggerPayload(is_triggered=triggered)


@dataclass
class _PartiallyUnreachable:
    """WallpanelPort double that reports reachable but returns None from reads.

    Simulates a race condition where the panel goes unreachable after
    is_reachable() returns True.  Used to exercise the None-guard paths.
    """

    brightness_value: int | None = None
    screen_value: bool | None = None
    max_brightness_value: int = 7812
    raise_on_max: bool = False

    async def is_reachable(self) -> bool:
        return True

    async def get_max_brightness(self) -> int:
        if self.raise_on_max:
            msg = "Became unreachable"
            raise WallpanelUnreachableError(msg)
        return self.max_brightness_value

    async def get_brightness(self) -> int | None:
        return self.brightness_value

    async def get_screen_state(self) -> bool | None:
        return self.screen_value

    # remaining protocol methods — unused by status handler
    async def set_brightness(self, value: int) -> None: ...  # noqa: ARG002

    async def screen_on(self) -> None: ...

    async def screen_off(self) -> None: ...

    async def hibernate(self) -> None: ...

    async def suspend(self) -> None: ...

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...


# =============================================================================
# StatusState
# =============================================================================


@pytest.mark.unit
class TestStatusState:
    """Verify StatusState dataclass defaults.

    Technique: Specification-based — constructor defaults match spec.
    """

    def test_max_brightness_defaults_to_none(self) -> None:
        """max_brightness starts as None before any poll."""
        state = StatusState()

        assert state.max_brightness is None

    def test_max_brightness_stored(self) -> None:
        """max_brightness is stored as provided."""
        state = StatusState(max_brightness=7812)

        assert state.max_brightness == 7812


# =============================================================================
# create_status_state
# =============================================================================


@pytest.mark.unit
class TestCreateStatusState:
    """Verify factory returns StatusState with max_brightness=None.

    Technique: Specification-based — eager init is explicitly forbidden.
    """

    def test_returns_status_state_with_none_max_brightness(self) -> None:
        """Factory always returns StatusState(max_brightness=None)."""
        state = create_status_state()

        assert isinstance(state, StatusState)
        assert state.max_brightness is None

    def test_does_not_require_wallpanel(self) -> None:
        """Factory takes no arguments — safe to call at startup without hardware.

        Technique: Error Guessing — startup should succeed even when unreachable.
        """
        state = create_status_state()

        assert state.max_brightness is None


# =============================================================================
# _status_interval
# =============================================================================


@pytest.mark.unit
class TestStatusIntervalHelper:
    """Verify _status_interval extracts poll_interval from correct settings type.

    Technique: Specification-based + Error Guessing.
    """

    def test_returns_poll_interval_from_settings(
        self, wallpanel_settings: WallpanelControlSettings
    ) -> None:
        """Returns WallpanelControlSettings.poll_interval."""
        result = _status_interval(wallpanel_settings)

        assert result == wallpanel_settings.poll_interval

    def test_custom_poll_interval_is_returned(self) -> None:
        """Returns overridden poll_interval value."""
        settings = make_wallpanel_control_settings(poll_interval=42.0)

        assert _status_interval(settings) == 42.0

    def test_raises_type_error_for_wrong_settings_type(self) -> None:
        """Raises TypeError when settings is not WallpanelControlSettings.

        Technique: Error Guessing — guard against mis-wiring.
        """
        with pytest.raises(TypeError, match="WallpanelControlSettings"):
            _status_interval(cosalette.Settings())  # type: ignore[call-arg]


# =============================================================================
# router registration
# =============================================================================


@pytest.mark.unit
class TestRouterRegistration:
    """Verify the router exposes 'status' and is configured correctly.

    Technique: Specification-based — public and semi-private API contract.
    """

    def test_status_in_registered_names(self) -> None:
        """Router has a telemetry handler registered as 'status'."""
        assert "status" in router.registered_names

    def test_init_is_create_status_state(self) -> None:
        """The status registration wires create_status_state as init factory.

        Technique: Specification-based — init= provides DI for handler state.
        """
        reg = next(r for r in router._telemetry if r.name == "status")

        assert reg.init is create_status_state

    def test_triggerable_is_true(self) -> None:
        """The status registration has triggerable=True.

        Note: Uses router._telemetry (semi-private) — no public API exists.
        Technique: Specification-based.
        """
        reg = next(r for r in router._telemetry if r.name == "status")

        assert reg.triggerable is True

    def test_publish_strategy_is_on_change(self) -> None:
        """The status registration uses OnChange publish strategy.

        Note: Uses router._telemetry (semi-private) — no public API exists.
        Technique: Specification-based.
        """
        reg = next(r for r in router._telemetry if r.name == "status")

        assert isinstance(reg.publish_strategy, cosalette.OnChange)


# =============================================================================
# poll_status — reachable
# =============================================================================


@pytest.mark.unit
class TestPollStatusReachable:
    """Verify reachable wallpanel returns available=True with correct values.

    Technique: Equivalence Partitioning — reachable input class.
    """

    async def test_returns_available_true(self, fake_wallpanel: FakeWallpanel) -> None:
        """Reachable wallpanel returns available=True."""
        # Arrange
        fake_wallpanel.brightness = 3906
        state = _state(max_brightness=7812)

        # Act
        result = await poll_status(fake_wallpanel, state, _trigger())

        # Assert
        assert result["available"] is True

    async def test_brightness_percentage_calculated(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Brightness is returned as percentage of max_brightness.

        Technique: Equivalence Partitioning — 50% of 7812.
        """
        # Arrange
        fake_wallpanel.brightness = 3906
        state = _state(max_brightness=7812)

        # Act
        result = await poll_status(fake_wallpanel, state, _trigger())

        # Assert
        assert result["brightness"] == 50

    async def test_screen_on_returned_as_on(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """screen_state=True is returned as 'ON'."""
        # Arrange
        fake_wallpanel.screen_state = True
        state = _state(max_brightness=7812)

        # Act
        result = await poll_status(fake_wallpanel, state, _trigger())

        # Assert
        assert result["screen"] == "ON"

    async def test_screen_off_returned_as_off(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """screen_state=False is returned as 'OFF'.

        Technique: Equivalence Partitioning — screen-off class.
        """
        # Arrange
        fake_wallpanel.screen_state = False
        state = _state(max_brightness=7812)

        # Act
        result = await poll_status(fake_wallpanel, state, _trigger())

        # Assert
        assert result["screen"] == "OFF"


# =============================================================================
# poll_status — unreachable
# =============================================================================


@pytest.mark.unit
class TestPollStatusUnreachable:
    """Verify unreachable wallpanel returns available=False with null values.

    Technique: Equivalence Partitioning — unreachable input class.
    """

    async def test_returns_available_false(self) -> None:
        """Unreachable wallpanel returns available=False."""
        fake = FakeWallpanel(reachable=False)

        result = await poll_status(fake, _state(), _trigger())

        assert result["available"] is False

    async def test_brightness_is_none(self) -> None:
        """Unreachable wallpanel returns brightness=None."""
        fake = FakeWallpanel(reachable=False)

        result = await poll_status(fake, _state(), _trigger())

        assert result["brightness"] is None

    async def test_screen_is_none(self) -> None:
        """Unreachable wallpanel returns screen=None."""
        fake = FakeWallpanel(reachable=False)

        result = await poll_status(fake, _state(), _trigger())

        assert result["screen"] is None


# =============================================================================
# poll_status — lazy max_brightness initialisation
# =============================================================================


@pytest.mark.unit
class TestPollStatusLazyMaxBrightness:
    """Verify max_brightness is read on first poll and cached thereafter.

    Technique: State Transition Testing — max_brightness: None → initialised.
    """

    async def test_max_brightness_populated_on_first_poll(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """state.max_brightness is None before poll and set after first success."""
        # Arrange
        fake_wallpanel.max_brightness = 5000
        state = _state()  # max_brightness=None

        # Act
        await poll_status(fake_wallpanel, state, _trigger())

        # Assert
        assert state.max_brightness == 5000

    async def test_max_brightness_not_re_fetched_on_second_poll(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Cached max_brightness is used on second poll without re-reading hardware.

        Technique: State Transition — value persists across poll boundary.
        """
        # Arrange: pre-initialise to a value different from fake hardware
        state = _state(max_brightness=9999)
        fake_wallpanel.max_brightness = 1234  # would overwrite if re-fetched

        # Act
        await poll_status(fake_wallpanel, state, _trigger())

        # Assert: cached value preserved
        assert state.max_brightness == 9999

    async def test_max_brightness_not_cached_when_unreachable(self) -> None:
        """max_brightness stays None when first poll finds wallpanel unreachable."""
        fake = FakeWallpanel(reachable=False)
        state = _state()

        await poll_status(fake, state, _trigger())

        assert state.max_brightness is None


# =============================================================================
# poll_status — brightness percentage calculation
# =============================================================================


@pytest.mark.unit
class TestPollStatusBrightnessPercentage:
    """Verify brightness percentage calculation with various max values.

    Technique: Boundary Value Analysis + Equivalence Partitioning.
    """

    async def test_100_percent(self, fake_wallpanel: FakeWallpanel) -> None:
        """Full brightness (raw == max) returns 100."""
        fake_wallpanel.brightness = 1000
        state = _state(max_brightness=1000)

        result = await poll_status(fake_wallpanel, state, _trigger())

        assert result["brightness"] == 100

    async def test_0_percent(self, fake_wallpanel: FakeWallpanel) -> None:
        """Zero raw brightness returns 0."""
        fake_wallpanel.brightness = 0
        state = _state(max_brightness=1000)

        result = await poll_status(fake_wallpanel, state, _trigger())

        assert result["brightness"] == 0

    async def test_custom_max_scales_correctly(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Percentage is relative to state.max_brightness, not a constant."""
        fake_wallpanel.brightness = 500
        state = _state(max_brightness=2000)

        result = await poll_status(fake_wallpanel, state, _trigger())

        assert result["brightness"] == 25

    async def test_result_is_rounded(self, fake_wallpanel: FakeWallpanel) -> None:
        """Fractional percentages are rounded to the nearest integer."""
        # 1 / 3 * 100 = 33.33… → 33
        fake_wallpanel.brightness = 1
        state = _state(max_brightness=3)

        result = await poll_status(fake_wallpanel, state, _trigger())

        assert result["brightness"] == round(1 / 3 * 100)

    async def test_max_brightness_zero_returns_unavailable(self) -> None:
        """max_brightness=0 returns unavailable instead of dividing by zero.

        Technique: Boundary Value Analysis — lower boundary of max_brightness.
        """
        fake = _PartiallyUnreachable(
            brightness_value=0,
            screen_value=True,
            max_brightness_value=0,
        )
        state = _state()

        result = await poll_status(fake, state, _trigger())  # type: ignore[arg-type]

        assert result == {"available": False, "brightness": None, "screen": None}


# =============================================================================
# poll_status — None return guards
# =============================================================================


@pytest.mark.unit
class TestPollStatusNoneGuards:
    """Verify None returns from get_brightness/get_screen_state yield unavailable.

    Technique: Error Guessing — race condition mid-poll.
    """

    async def test_get_brightness_none_returns_unavailable(self) -> None:
        """get_brightness() returning None produces the unavailable state dict."""
        fake = _PartiallyUnreachable(brightness_value=None, screen_value=True)

        result = await poll_status(fake, _state(max_brightness=7812), _trigger())  # type: ignore[arg-type]

        assert result == {"available": False, "brightness": None, "screen": None}

    async def test_get_screen_state_none_returns_unavailable(self) -> None:
        """get_screen_state() returning None produces the unavailable state dict."""
        fake = _PartiallyUnreachable(brightness_value=3906, screen_value=None)

        result = await poll_status(fake, _state(max_brightness=7812), _trigger())  # type: ignore[arg-type]

        assert result == {"available": False, "brightness": None, "screen": None}


# =============================================================================
# poll_status — WallpanelUnreachableError during lazy max read
# =============================================================================


@pytest.mark.unit
class TestPollStatusUnreachableErrorDuringMaxRead:
    """Verify WallpanelUnreachableError from get_max_brightness returns unavailable.

    Technique: Error Guessing — panel goes down between is_reachable and max read.
    """

    async def test_unreachable_error_during_max_brightness_returns_unavailable(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """WallpanelUnreachableError from get_max_brightness → unavailable + warning."""
        fake = _PartiallyUnreachable(raise_on_max=True)
        state = _state()  # max_brightness=None — triggers lazy init

        with caplog.at_level(
            logging.WARNING, logger="wallpanel_control.devices.status"
        ):
            result = await poll_status(fake, state, _trigger())  # type: ignore[arg-type]

        assert result == {"available": False, "brightness": None, "screen": None}
        assert any("unreachable" in r.message.lower() for r in caplog.records)

    async def test_max_brightness_not_cached_after_error(self) -> None:
        """state.max_brightness remains None when error prevents initialisation."""
        fake = _PartiallyUnreachable(raise_on_max=True)
        state = _state()

        await poll_status(fake, state, _trigger())  # type: ignore[arg-type]

        assert state.max_brightness is None


# =============================================================================
# poll_status — triggered run
# =============================================================================


@pytest.mark.unit
class TestPollStatusTriggered:
    """Verify triggered run logs a debug message and still returns correct state.

    Technique: Branch/Condition Coverage — is_triggered=True path.
    """

    async def test_triggered_run_logs_debug(
        self,
        fake_wallpanel: FakeWallpanel,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Triggered poll emits a DEBUG log entry."""
        # Arrange
        state = _state(max_brightness=7812)

        with caplog.at_level(logging.DEBUG, logger="wallpanel_control.devices.status"):
            await poll_status(fake_wallpanel, state, _trigger(triggered=True))

        assert any("triggered" in r.message.lower() for r in caplog.records)

    async def test_triggered_run_returns_correct_state(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Triggered poll returns the same state as a scheduled poll."""
        # Arrange
        fake_wallpanel.brightness = 0
        fake_wallpanel.screen_state = True
        state = _state(max_brightness=7812)

        result = await poll_status(fake_wallpanel, state, _trigger(triggered=True))

        assert result["available"] is True
