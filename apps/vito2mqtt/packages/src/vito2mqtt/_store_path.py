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

"""Resolve the store file path using XDG Base Directory conventions.

Resolution order:
1. ``VITO2MQTT_STORE_PATH`` env var (explicit override)
2. ``$XDG_STATE_HOME/vito2mqtt/store.json``
3. ``~/.local/state/vito2mqtt/store.json`` (XDG default)

The ``JsonFileStore`` backend auto-creates parent directories on first
save, so no directory pre-creation is needed here.
"""

from __future__ import annotations

import os
from pathlib import Path

_APP_NAME = "vito2mqtt"
_STORE_FILENAME = "store.json"


def resolve_store_path() -> Path:
    """Return the resolved store file path.

    Reads environment variables at call time so tests can
    monkeypatch ``os.environ`` safely.
    """
    # 1. Explicit override
    explicit = os.environ.get("VITO2MQTT_STORE_PATH")
    if explicit:
        return Path(explicit)

    # 2. XDG_STATE_HOME (with standard fallback)
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return Path(xdg_state) / _APP_NAME / _STORE_FILENAME

    # 3. XDG default: ~/.local/state/<app>/store.json
    return Path.home() / ".local" / "state" / _APP_NAME / _STORE_FILENAME
