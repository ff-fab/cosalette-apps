"""Unit tests for ports.py — WallpanelPort and WolPort protocol definitions.

Test Techniques Used:
- Structural Subtyping Verification: Compliant classes satisfy protocol isinstance checks
- Specification-based Testing: Protocols are runtime_checkable with expected method set
"""

from __future__ import annotations

from types import TracebackType
from typing import Self

import pytest

from wallpanel_control.ports import WallpanelPort, WolPort


# =============================================================================
# Compliant test doubles
# =============================================================================


class FakeWallpanel:
    """Minimal compliant implementation of WallpanelPort for testing."""

    async def set_brightness(self, value: int) -> None:
        pass

    async def get_brightness(self) -> int | None:
        return 100

    async def get_max_brightness(self) -> int:
        return 255

    async def screen_on(self) -> None:
        pass

    async def screen_off(self) -> None:
        pass

    async def get_screen_state(self) -> bool | None:
        return True

    async def hibernate(self) -> None:
        pass

    async def suspend(self) -> None:
        pass

    async def is_reachable(self) -> bool:
        return True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class FakeWol:
    """Minimal compliant implementation of WolPort for testing."""

    async def wake(self, mac: str, broadcast: str) -> None:
        pass


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.unit
class TestWallpanelPort:
    """Verify WallpanelPort protocol definition and structural subtyping.

    Technique: Structural Subtyping Verification — a compliant fake
    satisfies the protocol via isinstance check.
    """

    def test_protocol_is_runtime_checkable(self) -> None:
        """WallpanelPort is decorated with @runtime_checkable."""
        assert hasattr(WallpanelPort, "__protocol_attrs__")

    def test_fake_wallpanel_satisfies_protocol(self) -> None:
        """FakeWallpanel implements all methods required by WallpanelPort."""
        # Arrange
        fake = FakeWallpanel()

        # Act / Assert
        assert isinstance(fake, WallpanelPort)

    def test_empty_class_does_not_satisfy_protocol(self) -> None:
        """A class missing protocol methods fails the isinstance check."""

        class Empty:
            pass

        # Arrange
        obj = Empty()

        # Act / Assert
        assert not isinstance(obj, WallpanelPort)


@pytest.mark.unit
class TestWolPort:
    """Verify WolPort protocol definition and structural subtyping.

    Technique: Structural Subtyping Verification — a compliant fake
    satisfies the protocol via isinstance check.
    """

    def test_protocol_is_runtime_checkable(self) -> None:
        """WolPort is decorated with @runtime_checkable."""
        assert hasattr(WolPort, "__protocol_attrs__")

    def test_fake_wol_satisfies_protocol(self) -> None:
        """FakeWol implements all methods required by WolPort."""
        # Arrange
        fake = FakeWol()

        # Act / Assert
        assert isinstance(fake, WolPort)

    def test_empty_class_does_not_satisfy_protocol(self) -> None:
        """A class missing protocol methods fails the isinstance check."""

        class Empty:
            pass

        # Arrange
        obj = Empty()

        # Act / Assert
        assert not isinstance(obj, WolPort)
