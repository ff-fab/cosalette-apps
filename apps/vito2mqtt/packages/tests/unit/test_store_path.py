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

"""Unit tests for _store_path.py — XDG-based store path resolution.

Test Techniques Used:
- Decision Table: Multiple env-var combinations → expected path
- Specification-based: XDG Base Directory compliance
- Equivalence Partitioning: Explicit path / XDG override / default fallback
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vito2mqtt._store_path import resolve_store_path


class TestResolveStorePath:
    """Verify resolve_store_path follows XDG resolution order."""

    def test_explicit_env_var_takes_precedence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """VITO2MQTT_STORE_PATH env var is used verbatim when set.

        Technique: Decision Table — explicit override row.
        """
        monkeypatch.setenv("VITO2MQTT_STORE_PATH", "/custom/path/store.json")

        result = resolve_store_path()

        assert result == Path("/custom/path/store.json")

    def test_xdg_state_home_used_when_no_explicit_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """XDG_STATE_HOME forms the base when no explicit path is set.

        Technique: Decision Table — XDG override row.
        """
        monkeypatch.delenv("VITO2MQTT_STORE_PATH", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg-state")

        result = resolve_store_path()

        assert result == Path("/tmp/xdg-state/vito2mqtt/store.json")

    def test_default_xdg_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to ~/.local/state/vito2mqtt/store.json when no env vars set.

        Technique: Decision Table — default fallback row.
        """
        monkeypatch.delenv("VITO2MQTT_STORE_PATH", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)

        result = resolve_store_path()

        assert result == Path.home() / ".local" / "state" / "vito2mqtt" / "store.json"

    def test_explicit_path_overrides_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """VITO2MQTT_STORE_PATH wins even when XDG_STATE_HOME is also set.

        Technique: Decision Table — both env vars set, explicit wins.
        """
        monkeypatch.setenv("VITO2MQTT_STORE_PATH", "/override/store.json")
        monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg-state")

        result = resolve_store_path()

        assert result == Path("/override/store.json")

    def test_returns_path_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return type must be pathlib.Path regardless of resolution path.

        Technique: Specification-based — return type contract.
        """
        monkeypatch.delenv("VITO2MQTT_STORE_PATH", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)

        result = resolve_store_path()

        assert isinstance(result, Path)

    def test_empty_store_path_env_var_falls_through_to_xdg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty VITO2MQTT_STORE_PATH is treated as unset.

        Technique: Boundary Value Analysis — empty string as edge case.
        """
        monkeypatch.setenv("VITO2MQTT_STORE_PATH", "")
        monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg-state")

        result = resolve_store_path()

        assert result == Path("/tmp/xdg-state/vito2mqtt/store.json")
