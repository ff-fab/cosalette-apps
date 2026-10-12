"""Panel reachability probe for wallpanel-control (app ADR-001).

The root device publishes the saved answers (devices/restore.py) once, then probes the
panel over SSH every ``probe_interval`` seconds and republishes the retained
``display/state`` only when the observed reachability differs from the current answer.
It also resolves the ``observed`` field of an accepted ``system/action/state``:
``confirmed`` once the target (wake: one success; suspend/hibernate: unreachable) is
seen, ``timeout`` after ``action_confirm_timeout``.

One failure is re-probed after ``_RETRY_DELAY``; two consecutive failures count as
unreachable, so a lost packet does not flap the state. A command always wins: the
probe drops its result when a command recorded a newer answer during the probe.
Panel reachability never reaches ``status.devices`` — a sleeping panel is normal.
"""

from __future__ import annotations

import json
import logging

import cosalette
from cosalette import DeviceStore
from pydantic import BaseModel

from wallpanel_control.devices.display import (
    _UNAVAILABLE,
    _DisplayHandlerState,
    _poll_display_state,
)
from wallpanel_control.devices.restore import LastAnswers, publish_saved_answers
from wallpanel_control.devices.system import Observed, SystemActionState
from wallpanel_control.ports import WallpanelPort
from wallpanel_control.settings import WallpanelControlSettings

logger = logging.getLogger(__name__)

DISPLAY_TOPIC = "display/state"
ACTION_TOPIC = "system/action/state"

# Debounce re-probe delay and the probe cadence while an action awaits confirmation.
_RETRY_DELAY = 5.0

_WAKE_TIMEOUT_HINT = (
    "check host networking, WOL_BROADCAST and that WoL is enabled on the panel NIC"
)


class PanelProbe:
    """One probe cycle at a time; holds the reachability and confirmation state."""

    def __init__(
        self,
        ctx: cosalette.DeviceContext,
        wallpanel: WallpanelPort,
        settings: WallpanelControlSettings,
        answers: LastAnswers,
    ) -> None:
        self._ctx = ctx
        self._wallpanel = wallpanel
        self._settings = settings
        self._answers = answers
        self._display = _DisplayHandlerState()
        self._reachable: bool | None = None
        self._action_revision = answers.revision(ACTION_TOPIC)
        self._pending: tuple[SystemActionState, float] | None = None

    @property
    def delay(self) -> float:
        """Seconds until the next cycle: faster while an action is pending."""
        return self._settings.probe_interval if self._pending is None else _RETRY_DELAY

    async def cycle(self) -> None:
        """Probe the panel, then publish what changed."""
        display_revision = self._answers.revision(DISPLAY_TOPIC)
        reachable = await self._observe()
        if reachable != self._reachable:
            logger.info("Wallpanel %s", "reachable" if reachable else "unreachable")
        first, self._reachable = self._reachable is None, reachable
        await self._update_display(reachable, display_revision, first=first)
        await self._resolve_action(reachable)

    async def _observe(self) -> bool:
        if await self._wallpanel.is_reachable():
            return True
        await self._ctx.sleep(_RETRY_DELAY)
        return await self._wallpanel.is_reachable()

    async def _update_display(
        self, reachable: bool, revision: int, *, first: bool
    ) -> None:
        current = self._answers.current(DISPLAY_TOPIC)
        shown = current.get("available") if isinstance(current, dict) else None
        if not first and shown == reachable:
            return
        state = (
            await _poll_display_state(self._wallpanel, self._display)
            if reachable
            else _UNAVAILABLE
        )
        if self._answers.revision(DISPLAY_TOPIC) == revision:
            await self._publish(DISPLAY_TOPIC, state)

    async def _resolve_action(self, reachable: bool) -> None:
        revision = self._answers.revision(ACTION_TOPIC)
        if revision != self._action_revision:
            # A newer acknowledgement replaces the one being tracked.
            self._action_revision = revision
            current = self._answers.current(ACTION_TOPIC)
            self._pending = None
            if isinstance(current, dict) and current.get("observed") == "pending":
                deadline = self._ctx.clock.now() + self._settings.action_confirm_timeout
                self._pending = (SystemActionState.model_validate(current), deadline)
        if self._pending is None:
            return
        ack, deadline = self._pending
        if reachable == (ack.action == "wake"):
            await self._finish(ack, "confirmed")
        elif self._ctx.clock.now() >= deadline:
            hint = f" ({_WAKE_TIMEOUT_HINT})" if ack.action == "wake" else ""
            logger.warning(
                "Wallpanel %s not observed within %.0f s%s",
                ack.action,
                self._settings.action_confirm_timeout,
                hint,
            )
            await self._finish(ack, "timeout")

    async def _finish(self, ack: SystemActionState, observed: Observed) -> None:
        self._pending = None
        await self._publish(ACTION_TOPIC, ack.model_copy(update={"observed": observed}))
        self._action_revision = self._answers.revision(ACTION_TOPIC)

    async def _publish(self, topic: str, state: BaseModel) -> None:
        # ctx.publish skips state_model validation; the payload is a model already.
        self._answers.record(topic, state)
        await self._ctx.publish(
            topic, json.dumps(state.model_dump(mode="json")), retain=True
        )


router = cosalette.Router()


# cosalette routes one root handler per app, so the startup restore and the probe
# share this root device. It keeps the name ``restore_answers``: the name scopes the
# saved answers in the store and names the schema channel.
@router.device(
    discoverable=False,
    triggerable="local",
    summary="Re-publish the saved answers, then probe panel reachability",
)
async def restore_answers(
    ctx: cosalette.DeviceContext,
    store: DeviceStore,
    wallpanel: WallpanelPort,
    settings: WallpanelControlSettings,
    answers: LastAnswers,
    trigger: cosalette.DeviceTrigger,
):
    """Publish the saved answers, then probe every interval or after an action."""
    await publish_saved_answers(ctx, store, answers)
    yield
    if not settings.probe_enabled:
        return
    probe = PanelProbe(ctx, wallpanel, settings, answers)
    while not ctx.shutdown_requested:
        await probe.cycle()
        yield
        if (await trigger.wait(timeout=probe.delay)).is_triggered:
            # Let the acknowledgement publish first; then probe at the fast cadence.
            await ctx.sleep(_RETRY_DELAY)
