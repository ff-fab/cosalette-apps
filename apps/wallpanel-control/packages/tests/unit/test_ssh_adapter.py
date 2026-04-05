"""Unit tests for adapters/ssh_adapter.py — SshWallpanel SSH adapter.

Test Techniques Used:
- Specification-based Testing: WallpanelPort protocol compliance
- State Transition Testing: Reachable/unreachable via mocked asyncssh
- Error Guessing: Connection failures return None from getters, raise from mutators
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wallpanel_control.adapters.ssh_adapter import SshWallpanel
from wallpanel_control.ports import WallpanelPort

from tests.fixtures.config import make_wallpanel_control_settings


# =============================================================================
# Helpers
# =============================================================================


def _make_adapter(**overrides: object) -> SshWallpanel:
    """Create an SshWallpanel with isolated test settings."""
    settings = make_wallpanel_control_settings(**overrides)
    return SshWallpanel(settings)


def _mock_run_result(stdout: str = "") -> MagicMock:
    """Create a mock SSHCompletedProcess."""
    result = MagicMock()
    result.stdout = stdout
    result.exit_status = 0
    return result


# =============================================================================
# Protocol compliance
# =============================================================================


@pytest.mark.unit
class TestSshWallpanelProtocol:
    """Verify SshWallpanel satisfies WallpanelPort protocol."""

    def test_satisfies_wallpanel_port(self) -> None:
        """SshWallpanel is a structural subtype of WallpanelPort."""
        # Arrange
        adapter = _make_adapter()

        # Act / Assert
        assert isinstance(adapter, WallpanelPort)


# =============================================================================
# Reachable operations (mocked SSH)
# =============================================================================


@pytest.mark.unit
class TestSshWallpanelReachable:
    """Verify adapter behavior with a working SSH connection.

    Technique: Specification-based — commands match legacy bash scripts.
    """

    async def test_get_brightness(self) -> None:
        """get_brightness reads from sysfs and returns int."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=_mock_run_result("500"))
        adapter._conn = mock_conn

        # Act
        result = await adapter.get_brightness()

        # Assert
        assert result == 500

    async def test_get_max_brightness(self) -> None:
        """get_max_brightness reads max_brightness from sysfs."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=_mock_run_result("7812"))
        adapter._conn = mock_conn

        # Act
        result = await adapter.get_max_brightness()

        # Assert
        assert result == 7812

    async def test_set_brightness(self) -> None:
        """set_brightness writes value via tee command."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=_mock_run_result())
        adapter._conn = mock_conn

        # Act
        await adapter.set_brightness(300)

        # Assert
        mock_conn.run.assert_called_once()
        cmd = mock_conn.run.call_args[0][0]
        assert "300" in cmd
        assert "tee" in cmd

    async def test_screen_on(self) -> None:
        """screen_on sends busctl command with PowerSaveMode 0."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=_mock_run_result())
        adapter._conn = mock_conn

        # Act
        await adapter.screen_on()

        # Assert
        cmd = mock_conn.run.call_args[0][0]
        assert "PowerSaveMode" in cmd
        assert cmd.endswith("0")

    async def test_screen_off(self) -> None:
        """screen_off sends busctl command with PowerSaveMode 1."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=_mock_run_result())
        adapter._conn = mock_conn

        # Act
        await adapter.screen_off()

        # Assert
        cmd = mock_conn.run.call_args[0][0]
        assert "PowerSaveMode" in cmd
        assert cmd.endswith("1")

    async def test_get_screen_state_on(self) -> None:
        """get_screen_state returns True when PowerSaveMode is 0."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=_mock_run_result("i 0"))
        adapter._conn = mock_conn

        # Act
        result = await adapter.get_screen_state()

        # Assert
        assert result is True

    async def test_get_screen_state_off(self) -> None:
        """get_screen_state returns False when PowerSaveMode is 1."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=_mock_run_result("i 1"))
        adapter._conn = mock_conn

        # Act
        result = await adapter.get_screen_state()

        # Assert
        assert result is False

    async def test_hibernate(self) -> None:
        """hibernate sends systemctl hibernate."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=_mock_run_result())
        adapter._conn = mock_conn

        # Act
        await adapter.hibernate()

        # Assert
        cmd = mock_conn.run.call_args[0][0]
        assert "systemctl hibernate" in cmd

    async def test_suspend(self) -> None:
        """suspend sends systemctl suspend."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=_mock_run_result())
        adapter._conn = mock_conn

        # Act
        await adapter.suspend()

        # Assert
        cmd = mock_conn.run.call_args[0][0]
        assert "systemctl suspend" in cmd

    async def test_is_reachable_true(self) -> None:
        """is_reachable returns True when connection succeeds."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        adapter._conn = mock_conn

        # Act
        result = await adapter.is_reachable()

        # Assert
        assert result is True


# =============================================================================
# Unreachable operations
# =============================================================================


@pytest.mark.unit
class TestSshWallpanelUnreachable:
    """Verify adapter behavior when SSH connection fails.

    Technique: Error Guessing — connection failures are handled gracefully.
    """

    async def test_get_brightness_returns_none(self) -> None:
        """get_brightness returns None when connection is refused."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(side_effect=ConnectionRefusedError)
        adapter._conn = mock_conn

        # Act
        result = await adapter.get_brightness()

        # Assert
        assert result is None

    async def test_get_screen_state_returns_none(self) -> None:
        """get_screen_state returns None on timeout."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(side_effect=TimeoutError)
        adapter._conn = mock_conn

        # Act
        result = await adapter.get_screen_state()

        # Assert
        assert result is None

    async def test_is_reachable_returns_false_on_refused(self) -> None:
        """is_reachable returns False when connection is refused."""
        # Arrange
        adapter = _make_adapter()
        adapter._conn = None

        with patch(
            "wallpanel_control.adapters.ssh_adapter.asyncssh.connect",
            new_callable=AsyncMock,
            side_effect=ConnectionRefusedError,
        ):
            # Act
            result = await adapter.is_reachable()

        # Assert
        assert result is False

    async def test_is_reachable_returns_false_on_os_error(self) -> None:
        """is_reachable returns False on OSError (network unreachable)."""
        # Arrange
        adapter = _make_adapter()
        adapter._conn = None

        with patch(
            "wallpanel_control.adapters.ssh_adapter.asyncssh.connect",
            new_callable=AsyncMock,
            side_effect=OSError("Network unreachable"),
        ):
            # Act
            result = await adapter.is_reachable()

        # Assert
        assert result is False

    async def test_connection_cleared_on_unreachable(self) -> None:
        """Connection reference is cleared after unreachable error."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(side_effect=ConnectionRefusedError)
        adapter._conn = mock_conn

        # Act
        await adapter.get_brightness()

        # Assert
        assert adapter._conn is None


# =============================================================================
# Context manager
# =============================================================================


@pytest.mark.unit
class TestSshWallpanelContextManager:
    """Verify async context manager lifecycle."""

    async def test_exit_closes_connection(self) -> None:
        """__aexit__ closes the SSH connection."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = MagicMock()
        adapter._conn = mock_conn

        # Act
        await adapter.__aexit__(None, None, None)

        # Assert
        mock_conn.close.assert_called_once()
        assert adapter._conn is None

    async def test_exit_noop_when_no_connection(self) -> None:
        """__aexit__ is a no-op when there is no connection."""
        # Arrange
        adapter = _make_adapter()
        adapter._conn = None

        # Act / Assert (should not raise)
        await adapter.__aexit__(None, None, None)
