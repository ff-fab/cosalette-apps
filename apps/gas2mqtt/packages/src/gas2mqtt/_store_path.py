"""Resolve the store file path using XDG Base Directory conventions.

Resolution order:
1. ``GAS2MQTT_STATE_FILE`` env var (explicit override)
2. ``$XDG_STATE_HOME/gas2mqtt/state.json``
3. ``~/.local/state/gas2mqtt/state.json`` (XDG default)

The ``JsonFileStore`` backend auto-creates parent directories on first
save, so no directory pre-creation is needed here.
"""

from __future__ import annotations

import os
from pathlib import Path

_APP_NAME = "gas2mqtt"
_STATE_FILENAME = "state.json"


def resolve_store_path() -> Path:
    """Return the resolved store file path.

    Reads environment variables at call time so tests can
    monkeypatch ``os.environ`` safely.
    """
    # 1. Explicit override
    explicit = os.environ.get("GAS2MQTT_STATE_FILE")
    if explicit:
        return Path(explicit)

    # 2. XDG_STATE_HOME (with standard fallback)
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return Path(xdg_state) / _APP_NAME / _STATE_FILENAME

    # 3. XDG default: ~/.local/state/<app>/state.json
    return Path.home() / ".local" / "state" / _APP_NAME / _STATE_FILENAME
