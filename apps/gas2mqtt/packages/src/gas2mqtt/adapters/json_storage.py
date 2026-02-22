"""JSON file adapter for StateStoragePort.

Stores all device state in a single JSON file, keyed by device name.
Uses atomic write (write-to-temp + replace) to prevent corruption
from power loss or crashes mid-write.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class JsonFileStorage:
    """Persists device state as a JSON file.

    The file contains a single JSON object where keys are device names
    and values are state dicts. Example::

        {"gas_counter": {"counter": 42, "consumption_m3": 123.45}}

    Thread safety: Not thread-safe. Designed for single-process use
    (one gas2mqtt instance).
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self, key: str) -> dict[str, object] | None:
        """Load state for the given key from the JSON file.

        Returns None if the file doesn't exist, the key is missing,
        or the file is corrupted (logs a warning on corruption).
        """
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data.get(key)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load state from %s: %s", self._path, exc)
            return None

    def save(self, key: str, data: dict[str, object]) -> None:
        """Save state for the given key using atomic write.

        Reads the existing file (if any), updates the key, and writes
        back atomically via write-to-temp + replace.

        Creates parent directories if they don't exist.
        """
        # Read existing state (or start fresh)
        existing: dict[str, object] = {}
        if self._path.exists():
            try:
                existing = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Corrupted state file %s, starting fresh: %s", self._path, exc
                )

        existing[key] = data

        # Atomic write: temp file + replace
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
            tmp_path.replace(self._path)
        except OSError:
            logger.exception("Failed to save state to %s", self._path)
            # Clean up temp file if it exists
            tmp_path.unlink(missing_ok=True)
