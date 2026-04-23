"""Unit tests for gas2mqtt._store_path.

Test Techniques Used:
- Decision Table: explicit override, XDG_STATE_HOME, and default fallback precedence
- Boundary Value Analysis: empty environment variables treated as unset
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gas2mqtt._store_path import resolve_store_path


@pytest.mark.unit
class TestResolveStorePath:
    """Verify XDG state-path precedence rules."""

    def test_explicit_override_wins(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Explicit GAS2MQTT_STATE_FILE wins over XDG_STATE_HOME.

        Technique: Decision Table — highest-priority branch.
        """
        explicit = tmp_path / "explicit.json"
        monkeypatch.setenv("GAS2MQTT_STATE_FILE", str(explicit))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

        result = resolve_store_path()

        assert result == explicit

    def test_xdg_state_home_used_when_explicit_unset(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """XDG_STATE_HOME is used when no explicit override is present.

        Technique: Decision Table — second-priority branch.
        """
        monkeypatch.delenv("GAS2MQTT_STATE_FILE", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

        result = resolve_store_path()

        assert result == tmp_path / "xdg-state" / "gas2mqtt" / "state.json"

    def test_empty_explicit_override_falls_back_to_xdg(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Empty GAS2MQTT_STATE_FILE is treated as unset.

        Technique: Boundary Value Analysis — empty-string env var.
        """
        monkeypatch.setenv("GAS2MQTT_STATE_FILE", "")
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

        result = resolve_store_path()

        assert result == tmp_path / "xdg-state" / "gas2mqtt" / "state.json"

    def test_default_fallback_uses_local_state_home(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Without env overrides, the helper falls back to ~/.local/state.

        Technique: Decision Table — default branch.
        """
        monkeypatch.delenv("GAS2MQTT_STATE_FILE", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = resolve_store_path()

        assert (
            result == tmp_path / "home" / ".local" / "state" / "gas2mqtt" / "state.json"
        )

    def test_empty_xdg_state_home_falls_back_to_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Empty XDG_STATE_HOME is treated as unset.

        Technique: Boundary Value Analysis — empty-string env var.
        """
        monkeypatch.delenv("GAS2MQTT_STATE_FILE", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", "")
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = resolve_store_path()

        assert (
            result == tmp_path / "home" / ".local" / "state" / "gas2mqtt" / "state.json"
        )
