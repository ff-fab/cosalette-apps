"""SSH adapter implementing WallpanelPort via asyncssh.

Controls wallpanel brightness (sysfs), screen power (D-Bus/busctl),
and system power (systemctl) over a persistent SSH connection.

Unreachable states (connection refused, timeout) return None from
getters rather than raising — the wallpanel being off is normal.
Unexpected errors (auth failure, permission denied) propagate.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from types import TracebackType
from typing import Self

import asyncssh

from wallpanel_control.settings import WallpanelControlSettings

logger = logging.getLogger(__name__)

# Errors that indicate the wallpanel is simply unreachable (off/hibernating).
_UNREACHABLE_ERRORS = (
    asyncssh.DisconnectError,
    ConnectionRefusedError,
    TimeoutError,
    OSError,
)


class SshWallpanel:
    """WallpanelPort implementation using asyncssh.

    Maintains a persistent SSH connection. If the connection drops,
    it is re-established on the next operation. Unreachable states
    are handled gracefully — getters return None, mutators raise.

    Args:
        settings: Application settings with SSH and hardware config.
    """

    def __init__(self, settings: WallpanelControlSettings) -> None:
        self._settings = settings
        self._conn: asyncssh.SSHClientConnection | None = None

    async def _connect(self) -> asyncssh.SSHClientConnection:
        """Open or reuse the SSH connection.

        Returns:
            Active SSH connection.

        Raises:
            Unreachable errors propagate to caller for handling.
        """
        if self._conn is not None:
            return self._conn

        self._conn = await asyncio.wait_for(
            asyncssh.connect(
                self._settings.ssh_host,
                port=self._settings.ssh_port,
                username=self._settings.ssh_user,
                client_keys=[self._settings.ssh_key_path],
                known_hosts=None,
            ),
            timeout=self._settings.ssh_timeout,
        )
        return self._conn

    async def _run(self, command: str) -> str:
        """Execute a command over SSH and return stdout.

        Args:
            command: Shell command to execute.

        Returns:
            Stripped stdout output.

        Raises:
            asyncssh.ProcessError: If the command exits non-zero.
            Unreachable errors propagate to caller (connection is
            cleared so the next call triggers a fresh connect).
        """
        try:
            conn = await self._connect()
            result = await asyncio.wait_for(
                conn.run(command, check=True),
                timeout=self._settings.ssh_timeout,
            )
            stdout = result.stdout or ""
            return str(stdout).strip()
        except _UNREACHABLE_ERRORS:
            self._conn = None
            raise

    async def _run_or_none(self, command: str) -> str | None:
        """Execute a command, returning None if unreachable.

        Args:
            command: Shell command to execute.

        Returns:
            Stripped stdout, or None if wallpanel is unreachable.
        """
        try:
            return await self._run(command)
        except _UNREACHABLE_ERRORS:
            logger.debug("Wallpanel unreachable during: %s", command)
            self._conn = None
            return None

    def _brightness_path(self) -> str:
        """Return the sysfs brightness file path."""
        return self._settings.backlight_path

    def _max_brightness_path(self) -> str:
        """Derive max_brightness path from brightness path."""
        return self._settings.backlight_path.replace("/brightness", "/max_brightness")

    async def set_brightness(self, value: int) -> None:
        """Set backlight brightness via sysfs echo."""
        path = shlex.quote(self._brightness_path())
        await self._run(f"echo {value} | sudo /usr/bin/tee {path}")

    async def get_brightness(self) -> int | None:
        """Read backlight brightness from sysfs."""
        path = shlex.quote(self._brightness_path())
        output = await self._run_or_none(f"cat {path}")
        if output is None:
            return None
        return int(output)

    async def get_max_brightness(self) -> int:
        """Read max backlight brightness from sysfs."""
        path = shlex.quote(self._max_brightness_path())
        output = await self._run(f"cat {path}")
        return int(output)

    async def screen_on(self) -> None:
        """Turn display on via busctl (Mutter PowerSaveMode=0)."""
        await self._run(
            "busctl --user set-property org.gnome.Mutter.DisplayConfig "
            "/org/gnome/Mutter/DisplayConfig "
            "org.gnome.Mutter.DisplayConfig PowerSaveMode i 0"
        )

    async def screen_off(self) -> None:
        """Turn display off via busctl (Mutter PowerSaveMode=1)."""
        await self._run(
            "busctl --user set-property org.gnome.Mutter.DisplayConfig "
            "/org/gnome/Mutter/DisplayConfig "
            "org.gnome.Mutter.DisplayConfig PowerSaveMode i 1"
        )

    async def get_screen_state(self) -> bool | None:
        """Read display power state via busctl.

        Returns:
            True if on (PowerSaveMode=0), False if off, None if unreachable.
        """
        output = await self._run_or_none(
            "busctl --user get-property org.gnome.Mutter.DisplayConfig "
            "/org/gnome/Mutter/DisplayConfig "
            "org.gnome.Mutter.DisplayConfig PowerSaveMode"
        )
        if output is None:
            return None
        # busctl output format: "i 0" or "i 1"
        return output.strip().endswith("0")

    async def hibernate(self) -> None:
        """Send systemctl hibernate command."""
        await self._run("sudo systemctl hibernate")

    async def suspend(self) -> None:
        """Send systemctl suspend command."""
        await self._run("sudo systemctl suspend")

    async def is_reachable(self) -> bool:
        """Check if wallpanel is reachable via SSH connect."""
        try:
            await self._connect()
        except _UNREACHABLE_ERRORS:
            self._conn = None
            return False
        return True

    async def __aenter__(self) -> Self:
        """Enter async context: establish SSH connection."""
        await self._connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context: close SSH connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
