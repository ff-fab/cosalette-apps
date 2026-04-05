"""Unit tests for adapters/fake.py — FakeWallpanel and FakeWol test doubles.

Test Techniques Used:
- State Transition Testing: Reachable/unreachable transitions, hibernate/suspend
- Specification-based Testing: Protocol compliance, default values
- Error Guessing: Mutators fail when unreachable, getters return None
"""

from __future__ import annotations

import pytest

from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol
from wallpanel_control.ports import WallpanelPort, WolPort


# =============================================================================
# FakeWallpanel
# =============================================================================


@pytest.mark.unit
class TestFakeWallpanelProtocol:
    """Verify FakeWallpanel satisfies WallpanelPort protocol."""

    def test_satisfies_wallpanel_port(self) -> None:
        """FakeWallpanel is a structural subtype of WallpanelPort."""
        # Arrange
        fake = FakeWallpanel()

        # Act / Assert
        assert isinstance(fake, WallpanelPort)


@pytest.mark.unit
class TestFakeWallpanelDefaults:
    """Verify default state of FakeWallpanel.

    Technique: Specification-based — constructor defaults match beads spec.
    """

    def test_default_brightness(self) -> None:
        """Default brightness is 0."""
        fake = FakeWallpanel()
        assert fake.brightness == 0

    def test_default_max_brightness(self) -> None:
        """Default max_brightness is 7812."""
        fake = FakeWallpanel()
        assert fake.max_brightness == 7812

    def test_default_screen_state(self) -> None:
        """Default screen_state is True (on)."""
        fake = FakeWallpanel()
        assert fake.screen_state is True

    def test_default_reachable(self) -> None:
        """Default reachable is True."""
        fake = FakeWallpanel()
        assert fake.reachable is True

    def test_default_power_state(self) -> None:
        """Default power_state is 'running'."""
        fake = FakeWallpanel()
        assert fake.power_state == "running"


@pytest.mark.unit
class TestFakeWallpanelReachable:
    """Verify behavior when wallpanel is reachable.

    Technique: State Transition — normal operations in reachable state.
    """

    async def test_set_and_get_brightness(self) -> None:
        """set_brightness updates value returned by get_brightness."""
        # Arrange
        fake = FakeWallpanel()

        # Act
        await fake.set_brightness(500)
        result = await fake.get_brightness()

        # Assert
        assert result == 500

    async def test_get_max_brightness(self) -> None:
        """get_max_brightness returns configured max."""
        # Arrange
        fake = FakeWallpanel(max_brightness=1000)

        # Act
        result = await fake.get_max_brightness()

        # Assert
        assert result == 1000

    async def test_screen_on(self) -> None:
        """screen_on sets screen_state to True."""
        # Arrange
        fake = FakeWallpanel(screen_state=False)

        # Act
        await fake.screen_on()

        # Assert
        assert fake.screen_state is True

    async def test_screen_off(self) -> None:
        """screen_off sets screen_state to False."""
        # Arrange
        fake = FakeWallpanel()

        # Act
        await fake.screen_off()

        # Assert
        assert fake.screen_state is False

    async def test_get_screen_state(self) -> None:
        """get_screen_state returns current screen_state."""
        # Arrange
        fake = FakeWallpanel(screen_state=False)

        # Act
        result = await fake.get_screen_state()

        # Assert
        assert result is False

    async def test_is_reachable(self) -> None:
        """is_reachable returns True when reachable."""
        # Arrange
        fake = FakeWallpanel()

        # Act
        result = await fake.is_reachable()

        # Assert
        assert result is True


@pytest.mark.unit
class TestFakeWallpanelUnreachable:
    """Verify behavior when wallpanel is not reachable.

    Technique: Error Guessing — unreachable state causes getters
    to return None and mutators to raise ConnectionError.
    """

    async def test_get_brightness_returns_none(self) -> None:
        """get_brightness returns None when unreachable."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act
        result = await fake.get_brightness()

        # Assert
        assert result is None

    async def test_get_screen_state_returns_none(self) -> None:
        """get_screen_state returns None when unreachable."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act
        result = await fake.get_screen_state()

        # Assert
        assert result is None

    async def test_set_brightness_raises(self) -> None:
        """set_brightness raises ConnectionError when unreachable."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act / Assert
        with pytest.raises(ConnectionError):
            await fake.set_brightness(100)

    async def test_screen_on_raises(self) -> None:
        """screen_on raises ConnectionError when unreachable."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act / Assert
        with pytest.raises(ConnectionError):
            await fake.screen_on()

    async def test_screen_off_raises(self) -> None:
        """screen_off raises ConnectionError when unreachable."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act / Assert
        with pytest.raises(ConnectionError):
            await fake.screen_off()

    async def test_hibernate_raises(self) -> None:
        """hibernate raises ConnectionError when unreachable."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act / Assert
        with pytest.raises(ConnectionError):
            await fake.hibernate()

    async def test_suspend_raises(self) -> None:
        """suspend raises ConnectionError when unreachable."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act / Assert
        with pytest.raises(ConnectionError):
            await fake.suspend()

    async def test_is_reachable_returns_false(self) -> None:
        """is_reachable returns False when unreachable."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act
        result = await fake.is_reachable()

        # Assert
        assert result is False


@pytest.mark.unit
class TestFakeWallpanelPowerTransitions:
    """Verify hibernate/suspend state transitions.

    Technique: State Transition — power commands change both
    power_state and reachability.
    """

    async def test_hibernate_sets_unreachable(self) -> None:
        """hibernate sets reachable=False and power_state='hibernating'."""
        # Arrange
        fake = FakeWallpanel()

        # Act
        await fake.hibernate()

        # Assert
        assert fake.reachable is False
        assert fake.power_state == "hibernating"

    async def test_suspend_sets_unreachable(self) -> None:
        """suspend sets reachable=False and power_state='suspended'."""
        # Arrange
        fake = FakeWallpanel()

        # Act
        await fake.suspend()

        # Assert
        assert fake.reachable is False
        assert fake.power_state == "suspended"

    async def test_hibernate_then_wake_via_set_reachable(self) -> None:
        """set_reachable(True) after hibernate restores reachability."""
        # Arrange
        fake = FakeWallpanel()
        await fake.hibernate()

        # Act
        fake.set_reachable(True)

        # Assert
        assert fake.reachable is True
        assert fake.power_state == "running"


@pytest.mark.unit
class TestFakeWallpanelTestHelpers:
    """Verify test helper methods.

    Technique: Specification-based — helpers bypass reachability.
    """

    def test_set_brightness_state_bypasses_reachability(self) -> None:
        """set_brightness_state sets brightness even when unreachable."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act
        fake.set_brightness_state(999)

        # Assert
        assert fake.brightness == 999


@pytest.mark.unit
class TestFakeWallpanelContextManager:
    """Verify async context manager lifecycle.

    Technique: Specification-based — context manager is no-op for fake.
    """

    async def test_async_context_manager(self) -> None:
        """FakeWallpanel works as async context manager."""
        # Arrange / Act
        async with FakeWallpanel() as fake:
            result = await fake.get_brightness()

        # Assert
        assert result == 0


# =============================================================================
# FakeWol
# =============================================================================


@pytest.mark.unit
class TestFakeWolProtocol:
    """Verify FakeWol satisfies WolPort protocol."""

    def test_satisfies_wol_port(self) -> None:
        """FakeWol is a structural subtype of WolPort."""
        # Arrange
        fake = FakeWol()

        # Act / Assert
        assert isinstance(fake, WolPort)


@pytest.mark.unit
class TestFakeWol:
    """Verify FakeWol records wake() calls.

    Technique: Specification-based — calls list captures arguments.
    """

    async def test_wake_records_call(self) -> None:
        """wake() appends (mac, broadcast) to calls list."""
        # Arrange
        fake = FakeWol()

        # Act
        await fake.wake("AA:BB:CC:DD:EE:FF", "192.168.1.255")

        # Assert
        assert fake.calls == [("AA:BB:CC:DD:EE:FF", "192.168.1.255")]

    async def test_wake_records_multiple_calls(self) -> None:
        """Multiple wake() calls are all recorded in order."""
        # Arrange
        fake = FakeWol()

        # Act
        await fake.wake("11:22:33:44:55:66", "10.0.0.255")
        await fake.wake("AA:BB:CC:DD:EE:FF", "192.168.1.255")

        # Assert
        assert len(fake.calls) == 2
        assert fake.calls[0] == ("11:22:33:44:55:66", "10.0.0.255")
        assert fake.calls[1] == ("AA:BB:CC:DD:EE:FF", "192.168.1.255")

    def test_calls_initially_empty(self) -> None:
        """calls list starts empty."""
        # Arrange
        fake = FakeWol()

        # Act / Assert
        assert fake.calls == []
