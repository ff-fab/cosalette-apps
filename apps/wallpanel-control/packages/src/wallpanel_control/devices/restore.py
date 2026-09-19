"""Re-publish the last command answers after a restart.

``display/state`` and ``system/action/state`` are published only as the answer to a
command. Under MQTT 5 retained expiry (monorepo ADR-009) nothing refreshes them after a
restart, so they would expire and a later subscriber would get no state. Each command
records its answer in ``LastAnswers``, which persists it in the store. A root device
publishes the saved answers again once at startup.

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
    """Last answer of each command, keyed by its state topic below the prefix."""

    def __init__(self) -> None:
        self._store: DeviceStore | None = None
        self._pending: dict[str, object] = {}

    def record(self, topic: str, answer: BaseModel) -> None:
        """Save *answer*, the payload that a command just published to *topic*."""
        wire = answer.model_dump(mode="json")
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


router = cosalette.Router()


@router.device(
    discoverable=False,
    summary="Re-publish the last display and system action answers at startup",
)
async def restore_answers(
    ctx: cosalette.DeviceContext,
    store: DeviceStore,
    answers: LastAnswers,
):
    """Publish each saved answer once, retained, then end."""
    for topic, answer in answers.attach(store).items():
        if answers.is_current(topic, answer):
            await ctx.publish(topic, json.dumps(answer), retain=True)
    yield
