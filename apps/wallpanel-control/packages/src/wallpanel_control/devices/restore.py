"""Re-publish the last command answers after a restart.

``display/state`` and ``system/action/state`` are published as the answer to a command
and, on a change only, by the panel probe (app ADR-001). Under MQTT 5 retained expiry
(monorepo ADR-009) nothing refreshes them after a restart, so they would expire and a
later subscriber would get no state. Each command records its answer in
``LastAnswers``, which persists it in the store. The root device (devices/probe.py)
publishes the saved answers again once at startup, before its first probe.

cosalette 0.10 has no startup hook for a command handler, so the root device publishes
through ``ctx.publish``. That channel skips ``state_model`` validation, which is why
``LastAnswers`` stores the already validated wire payload.
"""

from __future__ import annotations

import json
import logging

import cosalette
from cosalette import DeviceStore
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LastAnswers:
    """Last answer of each command, keyed by its state topic below the prefix.

    The panel probe writes through the same record, so each retained topic has one
    current value. ``revision`` counts the records per topic: the probe compares it
    before and after a probe and drops its result when a command answered meanwhile.
    """

    def __init__(self) -> None:
        self._store: DeviceStore | None = None
        self._pending: dict[str, object] = {}
        self._revisions: dict[str, int] = {}

    def record(self, topic: str, answer: BaseModel) -> None:
        """Save *answer*, the payload just published to *topic*."""
        self._record_wire(topic, answer.model_dump(mode="json"))

    def current(self, topic: str) -> object:
        """Return the current answer for *topic*, or ``None`` if there is none yet."""
        if self._store is None:
            return self._pending.get(topic)
        return self._store.get(topic)

    def revision(self, topic: str) -> int:
        """Return how often *topic* was recorded in this process."""
        return self._revisions.get(topic, 0)

    def _record_wire(self, topic: str, wire: object) -> None:
        self._revisions[topic] = self.revision(topic) + 1
        if self._store is None:
            self._pending[topic] = wire
            return
        self._store[topic] = wire
        self._save(self._store)

    def attach(self, store: DeviceStore) -> dict[str, object]:
        """Bind *store* and return the saved answers that no command has replaced."""
        restored = {t: a for t, a in store.items() if t not in self._pending}
        store.update(self._pending)
        self._pending.clear()
        self._store = store
        # A sleep/wake confirmation died with the previous process.
        for topic, answer in restored.items():
            if isinstance(answer, dict) and answer.get("observed") == "pending":
                restored[topic] = {**answer, "observed": None}
                self._record_wire(topic, restored[topic])
        self._save(store)
        return restored

    def is_current(self, topic: str, answer: object) -> bool:
        """Return whether *answer* remains the latest saved value for *topic*."""
        return self._store is not None and self._store.get(topic) == answer

    @staticmethod
    def _save(store: DeviceStore) -> None:
        """Persist the answers; a failing store must not fail a command."""
        try:
            store.save()
        except Exception:
            logger.exception("Failed to save the last answers")


def create_last_answers() -> LastAnswers:
    """Build the shared ``LastAnswers`` for ``app.state``, which needs a factory."""
    return LastAnswers()


async def publish_saved_answers(
    ctx: cosalette.DeviceContext, store: DeviceStore, answers: LastAnswers
) -> None:
    """Publish each saved answer once, retained (the root device calls it first)."""
    for topic, answer in answers.attach(store).items():
        if answers.is_current(topic, answer):
            await ctx.publish(topic, json.dumps(answer), retain=True)
