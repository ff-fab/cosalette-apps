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

"""Unit tests for OptolinkAdapter (serial adapter).

Test Techniques Used:
- Protocol conformance: isinstance check against OptolinkPort
- Monkeypatching: Replace ``_open_session`` with a mock P300 session
- AAA pattern: Arrange-Act-Assert structure throughout
- Error mapping: Verify domain exceptions for transport-level failures
- Concurrency: Verify asyncio.Lock serializes access

Since real serial hardware is unavailable in CI, all I/O is mocked.
The ``_open_session`` private method is patched to yield a
``MockP300Session`` that records reads/writes and returns known byte
sequences.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from vito2mqtt.adapters.serial import OptolinkAdapter
from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.errors import (
    CommandNotWritableError,
    InvalidSignalError,
    OptolinkConnectionError,
    OptolinkTimeoutError,
)
from vito2mqtt.optolink.commands import COMMANDS
from vito2mqtt.optolink.transport import DeviceError
from vito2mqtt.ports import OptolinkPort

from .conftest import MockP300Session, make_open_session_patch

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """OptolinkAdapter must satisfy the OptolinkPort protocol."""

    def test_serial_adapter_isinstance_optolink_port(
        self, vito2mqtt_settings: Vito2MqttSettings
    ) -> None:
        """Structural subtyping — adapter implements all protocol methods.

        Technique: PEP 544 runtime_checkable isinstance check.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        assert isinstance(adapter, OptolinkPort)


# ---------------------------------------------------------------------------
# Signal validation
# ---------------------------------------------------------------------------


class TestSignalValidation:
    """Validate signal name and access mode checks."""

    async def test_read_signal_unknown_name_raises_invalid_signal(
        self, vito2mqtt_settings: Vito2MqttSettings
    ) -> None:
        """Unknown signal name raises InvalidSignalError.

        Technique: Boundary — signal not in COMMANDS registry.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        with pytest.raises(InvalidSignalError, match="Unknown signal"):
            await adapter.read_signal("nonexistent_signal")

    async def test_write_signal_unknown_name_raises_invalid_signal(
        self, vito2mqtt_settings: Vito2MqttSettings
    ) -> None:
        """Unknown signal name on write raises InvalidSignalError."""
        adapter = OptolinkAdapter(vito2mqtt_settings)
        with pytest.raises(InvalidSignalError, match="Unknown signal"):
            await adapter.write_signal("nonexistent_signal", 42)

    async def test_write_signal_read_only_raises_not_writable(
        self, vito2mqtt_settings: Vito2MqttSettings
    ) -> None:
        """Writing a READ-only signal raises CommandNotWritableError.

        ``outdoor_temperature`` is AccessMode.READ — writing must fail.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        with pytest.raises(CommandNotWritableError, match="read-only"):
            await adapter.write_signal("outdoor_temperature", 20.0)

    async def test_read_signal_write_only_raises_invalid_signal(
        self, vito2mqtt_settings: Vito2MqttSettings
    ) -> None:
        """Reading a WRITE-only signal raises InvalidSignalError.

        ``system_time`` is AccessMode.WRITE — reading must fail.

        Technique: Error Guessing — write-only guard on read path.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        with pytest.raises(InvalidSignalError, match="write-only"):
            await adapter.read_signal("system_time")


# ---------------------------------------------------------------------------
# Read signal integration (mocked session)
# ---------------------------------------------------------------------------


class TestReadSignal:
    """Verify read_signal decodes raw bytes from the session correctly."""

    async def test_read_signal_decodes_is10_temperature(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """Read outdoor_temperature (IS10) — raw bytes 0xCB00 → 20.3°C.

        IS10 divides the little-endian signed int by 10:
            0xCB = 203 → 203 / 10 = 20.3
        """
        # Arrange
        adapter = OptolinkAdapter(vito2mqtt_settings)
        adapter._open_session = make_open_session_patch(mock_session)  # type: ignore[assignment]
        mock_session.read.return_value = b"\xcb\x00"

        # Act
        result = await adapter.read_signal("outdoor_temperature")

        # Assert
        cmd = COMMANDS["outdoor_temperature"]
        mock_session.read.assert_awaited_once_with(cmd.address, cmd.length)
        assert result == pytest.approx(20.3)

    async def test_read_signal_decodes_iunon(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """Read burner_modulation (IUNON, 1 byte) — 0x37 → 55."""
        adapter = OptolinkAdapter(vito2mqtt_settings)
        adapter._open_session = make_open_session_patch(mock_session)  # type: ignore[assignment]
        mock_session.read.return_value = b"\x37"

        result = await adapter.read_signal("burner_modulation")

        assert result == 55

    async def test_read_signal_decodes_rt(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """Read internal_pump_status (RT) — 0x01 → ReturnStatus.ON."""
        from vito2mqtt.optolink.codec import ReturnStatus

        adapter = OptolinkAdapter(vito2mqtt_settings)
        adapter._open_session = make_open_session_patch(mock_session)  # type: ignore[assignment]
        mock_session.read.return_value = b"\x01"

        result = await adapter.read_signal("internal_pump_status")

        assert result == ReturnStatus.ON


# ---------------------------------------------------------------------------
# Write signal integration (mocked session)
# ---------------------------------------------------------------------------


class TestWriteSignal:
    """Verify write_signal encodes and sends data to the session."""

    async def test_write_signal_encodes_iunon(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """Write hot_water_setpoint (IUNON, 1 byte) — 50 → 0x32.

        IUNON encodes as unsigned little-endian: 50 → b'\\x32'
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        adapter._open_session = make_open_session_patch(mock_session)  # type: ignore[assignment]

        await adapter.write_signal("hot_water_setpoint", 50)

        cmd = COMMANDS["hot_water_setpoint"]
        mock_session.write.assert_awaited_once_with(cmd.address, b"\x32")

    async def test_write_signal_encodes_is10(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """Write heating_curve_gradient_m1 (IS10, 1 byte) — 1.4 → 0x0E.

        IS10 encodes as signed little-endian × 10: 1.4 × 10 = 14 → 0x0E
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        adapter._open_session = make_open_session_patch(mock_session)  # type: ignore[assignment]

        await adapter.write_signal("heating_curve_gradient_m1", 1.4)

        cmd = COMMANDS["heating_curve_gradient_m1"]
        mock_session.write.assert_awaited_once_with(cmd.address, b"\x0e")


# ---------------------------------------------------------------------------
# Batch read
# ---------------------------------------------------------------------------


class TestReadSignals:
    """Verify read_signals returns a dict of decoded values."""

    async def test_read_signals_returns_dict_of_values(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """Batch read returns {name: decoded_value} for each signal."""
        adapter = OptolinkAdapter(vito2mqtt_settings)
        adapter._open_session = make_open_session_patch(mock_session)  # type: ignore[assignment]

        # outdoor_temperature (IS10, 2 bytes) and burner_modulation (IUNON, 1 byte)
        mock_session.read.side_effect = [b"\xcb\x00", b"\x37"]

        result = await adapter.read_signals(
            ["outdoor_temperature", "burner_modulation"]
        )

        assert result == {
            "outdoor_temperature": pytest.approx(20.3),
            "burner_modulation": 55,
        }

    async def test_read_signals_single_session_for_batch(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """Only one session is opened for the entire batch.

        Technique: Wrap ``_open_session`` to count invocations.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        call_count = 0
        original_patch = make_open_session_patch(mock_session)

        from collections.abc import AsyncIterator
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _counting_open() -> AsyncIterator[MockP300Session]:
            nonlocal call_count
            call_count += 1
            async with original_patch() as s:
                yield s

        adapter._open_session = _counting_open  # type: ignore[assignment]
        mock_session.read.side_effect = [b"\xcb\x00", b"\x37"]

        await adapter.read_signals(["outdoor_temperature", "burner_modulation"])

        assert call_count == 1

    async def test_read_signals_validates_all_before_io(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """An unknown signal name rejects the whole batch before any I/O.

        Technique: Verify ``_open_session`` is never entered when
        validation fails.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        session_opened = False
        original_patch = make_open_session_patch(mock_session)

        from collections.abc import AsyncIterator
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _tracking_open() -> AsyncIterator[MockP300Session]:
            nonlocal session_opened
            session_opened = True
            async with original_patch() as s:
                yield s

        adapter._open_session = _tracking_open  # type: ignore[assignment]

        with pytest.raises(InvalidSignalError, match="Unknown signal"):
            await adapter.read_signals(["outdoor_temperature", "nonexistent_signal"])

        assert not session_opened

    async def test_read_signals_write_only_rejected_before_io(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """A write-only signal in the batch rejects before any I/O.

        Technique: Same tracking wrapper — session must not be opened.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        session_opened = False
        original_patch = make_open_session_patch(mock_session)

        from collections.abc import AsyncIterator
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _tracking_open() -> AsyncIterator[MockP300Session]:
            nonlocal session_opened
            session_opened = True
            async with original_patch() as s:
                yield s

        adapter._open_session = _tracking_open  # type: ignore[assignment]

        with pytest.raises(InvalidSignalError, match="write-only"):
            await adapter.read_signals(["outdoor_temperature", "system_time"])

        assert not session_opened

    async def test_read_signals_empty_returns_empty_dict(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """Empty names list returns ``{}`` without opening any session."""
        adapter = OptolinkAdapter(vito2mqtt_settings)
        session_opened = False
        original_patch = make_open_session_patch(mock_session)

        from collections.abc import AsyncIterator
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _tracking_open() -> AsyncIterator[MockP300Session]:
            nonlocal session_opened
            session_opened = True
            async with original_patch() as s:
                yield s

        adapter._open_session = _tracking_open  # type: ignore[assignment]

        result = await adapter.read_signals([])

        assert result == {}
        assert not session_opened

    async def test_read_signals_mid_batch_error_propagates(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """A DeviceError mid-batch propagates as OptolinkConnectionError.

        First signal succeeds, second raises ``DeviceError`` — the
        adapter's error-translation contract maps it to
        ``OptolinkConnectionError``.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        adapter._open_session = make_open_session_patch(mock_session)  # type: ignore[assignment]
        mock_session.read.side_effect = [
            b"\xcb\x00",
            DeviceError("handshake failed"),
        ]

        with pytest.raises(OptolinkConnectionError, match="Device communication"):
            await adapter.read_signals(["outdoor_temperature", "burner_modulation"])


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


class TestErrorMapping:
    """Verify transport-level errors are mapped to domain exceptions."""

    async def test_device_error_maps_to_connection_error(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """DeviceError from session.read → OptolinkConnectionError.

        The adapter wraps DeviceError from the P300 transport layer.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        adapter._open_session = make_open_session_patch(mock_session)  # type: ignore[assignment]
        mock_session.read.side_effect = DeviceError("handshake failed")

        with pytest.raises(OptolinkConnectionError, match="Device communication"):
            await adapter.read_signal("outdoor_temperature")

    async def test_timeout_error_maps_to_optolink_timeout(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """TimeoutError from session.read → OptolinkTimeoutError."""
        adapter = OptolinkAdapter(vito2mqtt_settings)
        adapter._open_session = make_open_session_patch(mock_session)  # type: ignore[assignment]
        mock_session.read.side_effect = TimeoutError("timed out")

        with pytest.raises(OptolinkTimeoutError, match="Timeout"):
            await adapter.read_signal("outdoor_temperature")

    async def test_os_error_on_connection_maps_to_connection_error(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OSError when opening serial port → OptolinkConnectionError.

        Simulates the serial port being unavailable by patching the
        lazy ``serial_asyncio`` import to raise OSError.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)

        # Patch the import to simulate serial_asyncio raising OSError
        async def _broken_open(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("No such device")

        import types

        fake_module = types.ModuleType("serial_asyncio")
        fake_module.open_serial_connection = _broken_open  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "serial_asyncio", fake_module)

        with pytest.raises(OptolinkConnectionError, match="Failed to open"):
            await adapter.read_signal("outdoor_temperature")


# ---------------------------------------------------------------------------
# Lock serialization
# ---------------------------------------------------------------------------


class TestLockSerialization:
    """Verify the asyncio.Lock serializes concurrent access."""

    async def test_concurrent_reads_are_serialized(
        self,
        vito2mqtt_settings: Vito2MqttSettings,
        mock_session: MockP300Session,
    ) -> None:
        """Two concurrent read_signal calls must not overlap.

        We verify by tracking the order of lock acquisition using
        side effects that record timestamps.
        """
        adapter = OptolinkAdapter(vito2mqtt_settings)
        adapter._open_session = make_open_session_patch(mock_session)  # type: ignore[assignment]

        call_order: list[int] = []

        async def _slow_read(address: int, length: int) -> bytes:
            call_order.append(1)
            await asyncio.sleep(0.01)
            call_order.append(2)
            return b"\xcb\x00"

        mock_session.read.side_effect = _slow_read

        # Launch two reads concurrently
        results = await asyncio.gather(
            adapter.read_signal("outdoor_temperature"),
            adapter.read_signal("outdoor_temperature"),
        )

        # If serialized, the pattern should be [1, 2, 1, 2] (not [1, 1, 2, 2])
        assert call_order == [1, 2, 1, 2]
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Async context manager
# ---------------------------------------------------------------------------


class TestAsyncContextManager:
    """Verify __aenter__/__aexit__ work correctly."""

    async def test_context_manager_returns_self(
        self, vito2mqtt_settings: Vito2MqttSettings
    ) -> None:
        """async with adapter returns the adapter itself (no-op lifecycle)."""
        adapter = OptolinkAdapter(vito2mqtt_settings)
        async with adapter as ctx:
            assert ctx is adapter
