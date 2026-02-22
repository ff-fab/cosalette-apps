"""Unit tests for state storage adapters.

Test Techniques Used:
- Specification-based Testing: Verify adapters satisfy StateStoragePort contract
- Boundary Value Analysis: Missing file, missing key, corrupted data
- Error Guessing: Corrupted JSON, atomic write cleanup
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gas2mqtt.adapters.fake import FakeStorage, NullStorage
from gas2mqtt.adapters.json_storage import JsonFileStorage


@pytest.mark.unit
class TestJsonFileStorage:
    """Verify JsonFileStorage satisfies StateStoragePort protocol.

    Technique: Specification-based — contract compliance and edge cases.
    """

    def test_load_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        """load() returns None when the backing file does not exist."""
        # Arrange
        storage = JsonFileStorage(tmp_path / "nonexistent.json")

        # Act
        result = storage.load("gas_counter")

        # Assert
        assert result is None

    def test_save_creates_file_and_directories(self, tmp_path: Path) -> None:
        """save() creates parent directories and the JSON file."""
        # Arrange
        path = tmp_path / "subdir" / "nested" / "state.json"
        storage = JsonFileStorage(path)

        # Act
        storage.save("gas_counter", {"counter": 42})

        # Assert
        assert path.exists()
        assert path.parent.is_dir()

    def test_save_then_load_roundtrip(self, tmp_path: Path) -> None:
        """Data survives a save/load roundtrip unchanged."""
        # Arrange
        path = tmp_path / "state.json"
        storage = JsonFileStorage(path)
        state = {"counter": 42, "consumption_m3": 123.45}

        # Act
        storage.save("gas_counter", state)
        result = storage.load("gas_counter")

        # Assert
        assert result == state

    def test_save_preserves_other_keys(self, tmp_path: Path) -> None:
        """Saving key B does not clobber existing key A."""
        # Arrange
        path = tmp_path / "state.json"
        storage = JsonFileStorage(path)
        storage.save("device_a", {"value": 1})

        # Act
        storage.save("device_b", {"value": 2})

        # Assert
        assert storage.load("device_a") == {"value": 1}
        assert storage.load("device_b") == {"value": 2}

    def test_load_returns_none_for_missing_key(self, tmp_path: Path) -> None:
        """load() returns None when the file exists but the key is absent."""
        # Arrange
        path = tmp_path / "state.json"
        storage = JsonFileStorage(path)
        storage.save("other_device", {"value": 99})

        # Act
        result = storage.load("gas_counter")

        # Assert
        assert result is None

    def test_load_returns_none_on_corrupted_file(self, tmp_path: Path) -> None:
        """load() returns None and logs a warning when JSON is invalid.

        Technique: Error Guessing — corrupted file should not crash.
        """
        # Arrange
        path = tmp_path / "state.json"
        path.write_text("NOT VALID JSON {{{", encoding="utf-8")
        storage = JsonFileStorage(path)

        # Act
        result = storage.load("gas_counter")

        # Assert
        assert result is None

    def test_save_overwrites_corrupted_file(self, tmp_path: Path) -> None:
        """save() starts fresh when existing file is corrupted.

        Technique: Error Guessing — recovery from corruption.
        """
        # Arrange
        path = tmp_path / "state.json"
        path.write_text("CORRUPT", encoding="utf-8")
        storage = JsonFileStorage(path)

        # Act
        storage.save("gas_counter", {"counter": 1})

        # Assert
        result = storage.load("gas_counter")
        assert result == {"counter": 1}

    def test_atomic_write_uses_replace(self, tmp_path: Path) -> None:
        """After save(), no .tmp file remains — atomic rename cleans up.

        Technique: Boundary Value Analysis — verifying implementation detail
        that prevents data loss.
        """
        # Arrange
        path = tmp_path / "state.json"
        storage = JsonFileStorage(path)

        # Act
        storage.save("gas_counter", {"counter": 42})

        # Assert
        tmp_file = path.with_suffix(".tmp")
        assert not tmp_file.exists()
        assert path.exists()


@pytest.mark.unit
class TestNullStorage:
    """Verify NullStorage is a silent no-op.

    Technique: Specification-based — contract compliance for the null adapter.
    """

    def test_load_always_returns_none(self) -> None:
        """load() returns None regardless of key."""
        # Arrange
        storage = NullStorage()

        # Act & Assert
        assert storage.load("gas_counter") is None
        assert storage.load("any_key") is None

    def test_save_does_not_raise(self) -> None:
        """save() completes without error or side effects."""
        # Arrange
        storage = NullStorage()

        # Act & Assert — no exception raised
        storage.save("gas_counter", {"counter": 42})


@pytest.mark.unit
class TestFakeStorage:
    """Verify FakeStorage stores state in memory for testing.

    Technique: Specification-based — contract compliance for the test double.
    """

    def test_load_returns_none_when_empty(self) -> None:
        """load() returns None on a fresh FakeStorage."""
        # Arrange
        storage = FakeStorage()

        # Act
        result = storage.load("gas_counter")

        # Assert
        assert result is None

    def test_save_then_load_roundtrip(self) -> None:
        """Data survives a save/load roundtrip."""
        # Arrange
        storage = FakeStorage()
        state = {"counter": 42, "consumption_m3": 123.45}

        # Act
        storage.save("gas_counter", state)
        result = storage.load("gas_counter")

        # Assert
        assert result == state

    def test_save_overwrites_previous_value(self) -> None:
        """Saving the same key replaces the previous value."""
        # Arrange
        storage = FakeStorage()
        storage.save("gas_counter", {"counter": 1})

        # Act
        storage.save("gas_counter", {"counter": 2})

        # Assert
        assert storage.load("gas_counter") == {"counter": 2}

    def test_independent_keys(self) -> None:
        """Different keys do not interfere with each other."""
        # Arrange
        storage = FakeStorage()

        # Act
        storage.save("device_a", {"value": 10})
        storage.save("device_b", {"value": 20})

        # Assert
        assert storage.load("device_a") == {"value": 10}
        assert storage.load("device_b") == {"value": 20}

    def test_save_isolates_from_caller_mutation(self) -> None:
        """Mutating the dict after save() does not affect stored state.

        Technique: Error Guessing — preventing reference-sharing bugs
        that would cause tests to pass but production (JsonFileStorage)
        to behave differently.
        """
        # Arrange
        storage = FakeStorage()
        data: dict[str, object] = {"counter": 42}

        # Act
        storage.save("gas_counter", data)
        data["counter"] = 999  # Mutate original

        # Assert — stored value is unaffected
        assert storage.load("gas_counter") == {"counter": 42}

    def test_load_isolates_from_caller_mutation(self) -> None:
        """Mutating the loaded dict does not affect the stored state.

        Technique: Error Guessing — load() returns a copy, not the
        internal reference.
        """
        # Arrange
        storage = FakeStorage()
        storage.save("gas_counter", {"counter": 42})

        # Act
        loaded = storage.load("gas_counter")
        assert loaded is not None
        loaded["counter"] = 999  # Mutate the loaded copy

        # Assert — re-loading returns the original value
        assert storage.load("gas_counter") == {"counter": 42}
