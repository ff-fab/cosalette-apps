# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Shared fixtures for adapter unit tests.

Provides:
- ``MockP300Session`` — a programmable mock P300 session for serial adapter tests.
- ``vito2mqtt_settings`` — a ``Vito2MqttSettings`` instance with required env vars.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from vito2mqtt.config import Vito2MqttSettings

# ---------------------------------------------------------------------------
# Mock P300 session for serial adapter tests
# ---------------------------------------------------------------------------


class MockP300Session:
    """Fake P300 session that records calls and returns programmable responses.

    Configure :attr:`read` (an :class:`AsyncMock`, e.g. via
    ``read.return_value`` or ``read.side_effect``) to control what
    :meth:`read` returns, and inspect ``write`` calls via the
    :class:`AsyncMock`.
    """

    def __init__(self) -> None:
        self.read = AsyncMock()
        self.write = AsyncMock()

    async def __aenter__(self) -> MockP300Session:
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass


# ---------------------------------------------------------------------------
# Settings fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def vito2mqtt_settings(monkeypatch: pytest.MonkeyPatch) -> Vito2MqttSettings:
    """Construct a ``Vito2MqttSettings`` with required env vars set.

    Provides sensible defaults for adapter tests:
    - ``serial_port``: ``/dev/ttyUSB0``
    - ``serial_baud_rate``: ``4800`` (default)
    - ``signal_language``: ``en`` (default)
    """
    monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyUSB0")
    return Vito2MqttSettings()


@pytest.fixture
def vito2mqtt_settings_de(monkeypatch: pytest.MonkeyPatch) -> Vito2MqttSettings:
    """Settings instance with German language configured."""
    monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyUSB0")
    monkeypatch.setenv("VITO2MQTT_SIGNAL_LANGUAGE", "de")
    return Vito2MqttSettings()


@pytest.fixture
def mock_session() -> MockP300Session:
    """Return a fresh :class:`MockP300Session`."""
    return MockP300Session()


def make_open_session_patch(session: MockP300Session) -> Any:
    """Create an ``_open_session`` replacement that yields *session*.

    Replicates the real ``_open_session``'s error-translation contract:
    ``DeviceError`` → ``OptolinkConnectionError`` and
    ``TimeoutError`` → ``OptolinkTimeoutError``, so tests exercising
    error-mapping through the adapter's public API remain faithful.

    Returns an async context manager factory suitable for use with
    ``monkeypatch.setattr(adapter, '_open_session', ...)``.
    """
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    from vito2mqtt.errors import OptolinkConnectionError, OptolinkTimeoutError
    from vito2mqtt.optolink.transport import DeviceError

    @asynccontextmanager
    async def _fake_open_session() -> AsyncIterator[MockP300Session]:
        try:
            yield session
        except DeviceError as exc:
            msg = f"Device communication error: {exc}"
            raise OptolinkConnectionError(msg) from exc
        except TimeoutError as exc:
            msg = f"Timeout communicating with device: {exc}"
            raise OptolinkTimeoutError(msg) from exc

    return _fake_open_session
