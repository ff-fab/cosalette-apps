"""Unit tests for adapters/ssh_adapter.py — SshWallpanel SSH adapter.

Test Techniques Used:
- Specification-based Testing: WallpanelPort protocol compliance
- State Transition Testing: Reachable/unreachable via mocked asyncssh
- Error Guessing: Connection failures return None from getters, raise from mutators
- Equivalence Partitioning: asyncssh log level default vs explicit setting
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest

from tests.fixtures.config import make_wallpanel_control_settings
from wallpanel_control.adapters.ssh_adapter import SshWallpanel
from wallpanel_control.ports import WallpanelPort, WallpanelSleepPendingError

# =============================================================================
# Helpers
# =============================================================================


def _make_adapter(**overrides: object) -> SshWallpanel:
    """Create an SshWallpanel with isolated test settings."""
    settings = make_wallpanel_control_settings(**overrides)
    return SshWallpanel(settings)


def _mock_conn(*, closed: bool = False) -> AsyncMock:
    """Create a mock SSHClientConnection; is_closed() is synchronous."""
    conn = AsyncMock()
    conn.is_closed = MagicMock(return_value=closed)
    return conn


def _mock_run_result(stdout: str = "") -> MagicMock:
    """Create a mock SSHCompletedProcess."""
    result = MagicMock()
    result.stdout = stdout
    result.exit_status = 0
    return result


# What `sudo systemctl suspend` prints while logind holds an earlier sleep.
_LOGIND_PENDING = (
    "Failed to suspend system via logind: "
    "There's already a shutdown or sleep operation in progress\n"
)


def _process_error(stderr: str) -> asyncssh.ProcessError:
    """Build the error ``conn.run(check=True)`` raises for a non-zero exit."""
    return asyncssh.ProcessError(
        env=None,
        command="sudo systemctl suspend",
        subsystem=None,
        exit_status=1,
        exit_signal=None,
        returncode=1,
        stdout="",
        stderr=stderr,
    )


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
        mock_conn = _mock_conn()
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
        mock_conn = _mock_conn()
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
        mock_conn = _mock_conn()
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
        mock_conn = _mock_conn()
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
        mock_conn = _mock_conn()
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
        mock_conn = _mock_conn()
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
        mock_conn = _mock_conn()
        mock_conn.run = AsyncMock(return_value=_mock_run_result("i 1"))
        adapter._conn = mock_conn

        # Act
        result = await adapter.get_screen_state()

        # Assert
        assert result is False

    @pytest.mark.parametrize(
        "output", ["i 10", "i 20", "error"], ids=["ten", "twenty", "malformed"]
    )
    async def test_get_screen_state_only_treats_exact_i_zero_as_on(
        self, output: str
    ) -> None:
        """Only exact 'i 0' is screen-on; suffix matches are rejected.

        Technique: Boundary Value Analysis — multi-digit busctl values.
        """
        # Arrange
        adapter = _make_adapter()
        mock_conn = _mock_conn()
        mock_conn.run = AsyncMock(return_value=_mock_run_result(output))
        adapter._conn = mock_conn

        # Act
        result = await adapter.get_screen_state()

        # Assert
        assert result is False

    async def test_hibernate(self) -> None:
        """hibernate sends systemctl hibernate."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = _mock_conn()
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
        mock_conn = _mock_conn()
        mock_conn.run = AsyncMock(return_value=_mock_run_result())
        adapter._conn = mock_conn

        # Act
        await adapter.suspend()

        # Assert
        cmd = mock_conn.run.call_args[0][0]
        assert "systemctl suspend" in cmd

    @pytest.mark.parametrize("action", ["suspend", "hibernate"])
    async def test_sleep_pending_raises_sleep_pending_error(self, action: str) -> None:
        """logind's 'operation in progress' refusal maps to the domain error.

        Technique: Error Guessing — a second sleep while gnome-shell's delay
        inhibitor holds the first (adopter report F8).
        """
        # Arrange
        adapter = _make_adapter()
        mock_conn = _mock_conn()
        mock_conn.run = AsyncMock(
            side_effect=[_mock_run_result(), _process_error(_LOGIND_PENDING)]
        )
        adapter._conn = mock_conn

        # Act / Assert
        await getattr(adapter, action)()
        with pytest.raises(WallpanelSleepPendingError, match="in progress"):
            await getattr(adapter, action)()
        assert adapter._conn is mock_conn

    async def test_other_sleep_failure_still_raises_process_error(self) -> None:
        """A systemctl failure that is not a pending sleep keeps propagating.

        Technique: Error Guessing — e.g. sudo refusing the command.
        """
        # Arrange
        adapter = _make_adapter()
        mock_conn = _mock_conn()
        mock_conn.run = AsyncMock(
            side_effect=_process_error("sudo: a password is required")
        )
        adapter._conn = mock_conn

        # Act / Assert
        with pytest.raises(asyncssh.ProcessError):
            await adapter.suspend()

    async def test_different_pending_sleep_action_still_raises_process_error(
        self,
    ) -> None:
        """A generic logind refusal does not prove the pending action matches."""
        adapter = _make_adapter()
        adapter._pending_sleep_action = "suspend"
        mock_conn = _mock_conn()
        mock_conn.run = AsyncMock(side_effect=_process_error(_LOGIND_PENDING))
        adapter._conn = mock_conn

        with pytest.raises(asyncssh.ProcessError):
            await adapter.hibernate()

    async def test_is_reachable_true(self) -> None:
        """is_reachable returns True when connection succeeds."""
        # Arrange
        adapter = _make_adapter()
        mock_conn = _mock_conn()
        adapter._conn = mock_conn

        # Act
        result = await adapter.is_reachable()

        # Assert
        assert result is True

    async def test_connect_passes_known_hosts_to_asyncssh(self) -> None:
        """_connect passes ssh_known_hosts so host-key verification is explicit.

        Technique: Error Guessing — guard against omitting host verification.
        """
        # Arrange
        adapter = _make_adapter()
        mock_conn = _mock_conn()

        with patch(
            "wallpanel_control.adapters.ssh_adapter.asyncssh.connect",
            new_callable=AsyncMock,
            return_value=mock_conn,
        ) as mock_connect:
            # Act
            result = await adapter.is_reachable()

        # Assert
        assert result is True
        assert mock_connect.call_args.kwargs["known_hosts"] == "~/.ssh/known_hosts"

    async def test_connect_enables_ssh_keepalive(self) -> None:
        """_connect asks asyncssh to send keepalives and drop a silent peer.

        Technique: Error Guessing — without keepalive a cached connection to a
        panel that went to sleep stays open and the next command waits the full
        ssh_timeout before failing.
        """
        # Arrange
        adapter = _make_adapter()

        with patch(
            "wallpanel_control.adapters.ssh_adapter.asyncssh.connect",
            new_callable=AsyncMock,
            return_value=_mock_conn(),
        ) as mock_connect:
            # Act
            await adapter.is_reachable()

        # Assert
        kwargs = mock_connect.call_args.kwargs
        assert kwargs["keepalive_interval"] == 15.0
        assert kwargs["keepalive_count_max"] == 3


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
        mock_conn = _mock_conn()
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
        mock_conn = _mock_conn()
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
        mock_conn = _mock_conn()
        mock_conn.run = AsyncMock(side_effect=ConnectionRefusedError)
        adapter._conn = mock_conn

        # Act
        await adapter.get_brightness()

        # Assert
        assert adapter._conn is None


# =============================================================================
# asyncssh log level
# =============================================================================


@pytest.fixture
def asyncssh_logger() -> Iterator[logging.Logger]:
    """The asyncssh logger, with its level restored after the test."""
    ssh_logger = logging.getLogger("asyncssh")
    level = ssh_logger.level
    yield ssh_logger
    ssh_logger.setLevel(level)


@pytest.mark.unit
class TestSshWallpanelLogLevel:
    """asyncssh logs several INFO lines per command; the adapter quiets them."""

    def test_default_suppresses_asyncssh_info(
        self, asyncssh_logger: logging.Logger
    ) -> None:
        """A default adapter sets asyncssh to WARNING, so INFO is not emitted."""
        # Arrange
        asyncssh_logger.setLevel(logging.NOTSET)

        # Act
        _make_adapter()

        # Assert
        assert asyncssh_logger.level == logging.WARNING
        assert not asyncssh_logger.isEnabledFor(logging.INFO)

    def test_setting_lowers_the_asyncssh_level(
        self, asyncssh_logger: logging.Logger
    ) -> None:
        """ssh_log_level=DEBUG lets asyncssh debug output through."""
        # Act
        _make_adapter(ssh_log_level="DEBUG")

        # Assert
        assert asyncssh_logger.level == logging.DEBUG


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

    async def test_enter_does_not_connect(self) -> None:
        """__aenter__ is a no-op: does not call _connect or asyncssh.connect.

        cosalette enters adapter context managers at bootstrap. The wallpanel
        may be off or hibernating at that point — connecting eagerly would
        cause startup failure in a normal operating state.

        Technique: Error Guessing — guard against eager-connect regression.
        """
        # Arrange
        adapter = _make_adapter()

        with patch(
            "wallpanel_control.adapters.ssh_adapter.asyncssh.connect",
            new_callable=AsyncMock,
        ) as mock_connect:
            # Act
            result = await adapter.__aenter__()

        # Assert
        mock_connect.assert_not_called()
        assert adapter._conn is None
        assert result is adapter


@pytest.mark.unit
class TestSshWallpanelClosedConnection:
    """A connection the panel closed must not stay cached forever."""

    async def test_closed_connection_is_replaced(self) -> None:
        """A cached but closed connection is dropped and a fresh one opened.

        Technique: State Transition — the panel reboots, asyncssh marks the
        cached connection closed, and the next command must reconnect instead
        of failing with ChannelOpenError on every call until a restart.
        """
        # Arrange
        adapter = _make_adapter()
        stale = _mock_conn(closed=True)
        fresh = _mock_conn()
        fresh.run = AsyncMock(return_value=_mock_run_result("500"))
        adapter._conn = stale

        with patch(
            "wallpanel_control.adapters.ssh_adapter.asyncssh.connect",
            new_callable=AsyncMock,
            return_value=fresh,
        ) as mock_connect:
            # Act
            result = await adapter.get_brightness()

        # Assert
        assert result == 500
        mock_connect.assert_awaited_once()
        stale.run.assert_not_called()
        assert adapter._conn is fresh
