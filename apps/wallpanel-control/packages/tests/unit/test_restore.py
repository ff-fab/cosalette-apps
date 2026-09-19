"""Unit tests for devices/restore.py — persisted last answers.

Test Techniques Used:
- State Transition: LastAnswers before and after ``attach``.
- Branch/Condition Coverage: a pending answer replaces a saved one; a save failure.
- Specification-based Testing: the saved payload is the wire payload (no nulls).
"""

from __future__ import annotations

import pytest
from cosalette import DeviceStore, MemoryStore

from wallpanel_control.devices.display import DisplayState
from wallpanel_control.devices.restore import LastAnswers
from wallpanel_control.devices.system import SystemActionState


def _attached(backend: MemoryStore) -> DeviceStore:
    store = DeviceStore(backend, "restore_answers")
    store.load()
    return store


@pytest.mark.unit
class TestLastAnswers:
    """Verify record/attach persist and return the wire payload."""

    def test_recorded_answer_survives_a_new_instance(self) -> None:
        """A second LastAnswers on the same backend restores the saved answer."""
        backend = MemoryStore()
        first = LastAnswers()
        first.attach(_attached(backend))
        first.record(
            "display/state",
            DisplayState(available=True, state="on", brightness_percent=40),
        )

        second = LastAnswers()
        restored = second.attach(_attached(backend))

        assert restored == {
            "display/state": {
                "available": True,
                "state": "on",
                "brightness_percent": 40,
            }
        }

    def test_saved_payload_omits_null_fields(self) -> None:
        """The wire payload of an unavailable display has no null values."""
        backend = MemoryStore()
        answers = LastAnswers()
        answers.attach(_attached(backend))
        answers.record(
            "display/state",
            DisplayState(available=False, state=None, brightness_percent=None),
        )

        assert backend.load("restore_answers") == {
            "display/state": {"available": False}
        }

    def test_answer_recorded_before_attach_replaces_the_saved_one(self) -> None:
        """A command that runs before attach wins over the saved answer."""
        backend = MemoryStore()
        old = LastAnswers()
        old.attach(_attached(backend))
        old.record(
            "system/action/state", SystemActionState(accepted=True, action="wake")
        )

        fresh = LastAnswers()
        fresh.record(
            "system/action/state", SystemActionState(accepted=False, action="suspend")
        )
        restored = fresh.attach(_attached(backend))

        assert restored == {}
        assert backend.load("restore_answers") == {
            "system/action/state": {"accepted": False, "action": "suspend"}
        }

    def test_saved_answer_is_not_current_after_a_newer_answer(self) -> None:
        """A command during replay prevents an older saved answer from publishing.

        Technique: State Transition -- a newer record supersedes the startup snapshot.
        """
        backend = MemoryStore()
        answers = LastAnswers()
        answers.attach(_attached(backend))
        answers.record(
            "display/state",
            DisplayState(available=True, state="on", brightness_percent=40),
        )
        old_answer = {"available": True, "state": "on", "brightness_percent": 40}

        answers.record(
            "display/state",
            DisplayState(available=True, state="off", brightness_percent=40),
        )

        assert not answers.is_current("display/state", old_answer)

    def test_save_failure_is_logged_not_raised(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failing store must not turn an answered command into an error."""

        class _BrokenBackend(MemoryStore):
            def save(self, key: str, data: dict[str, object]) -> None:
                raise OSError("disk full")

        answers = LastAnswers()
        answers.attach(_attached(_BrokenBackend()))

        answers.record(
            "system/action/state", SystemActionState(accepted=True, action="wake")
        )

        assert "Failed to save the last answers" in caplog.text
