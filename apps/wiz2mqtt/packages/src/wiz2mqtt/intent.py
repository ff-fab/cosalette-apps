"""Desired-state persistence and the pending-command queue for wiz2mqtt (ADR-008).

Pure domain logic: reads and writes one :class:`DesiredState` per bulb
through the cosalette device store, and the single-slot per-bulb pending
command queue. No cosalette imports — testable as plain Python.
"""

from __future__ import annotations

import dataclasses
import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from wiz2mqtt.commands import off_kwargs
from wiz2mqtt.models import EMPTY_BULB_STATE, BulbState

if TYPE_CHECKING:
    from cosalette import DeviceStore

    from wiz2mqtt.commands import SetStateKwargs
    from wiz2mqtt.power import Belief
    from wiz2mqtt.state import SharedState

logger = logging.getLogger(__name__)

_DESIRED_STATE_KEY = "desired_state"
"""Sub-key under the per-bulb DeviceStore dict, a sibling of discovery.py's
``_CAPABILITIES_KEY`` in the same record."""


@dataclass(frozen=True)
class Appearance:
    """The non-on/off fields of a desired state — mirrors :class:`BulbState`.

    Deliberately excludes ``state`` (carried separately on
    :class:`DesiredState`) and ``power_draw_w`` (telemetry, never intent).
    """

    brightness: int | None
    hue: float | None
    saturation: float | None
    color_temp_kelvin: int | None
    scene: int | None
    speed: int | None


_APPEARANCE_FIELDS = tuple(f.name for f in dataclasses.fields(Appearance))


@dataclass(frozen=True)
class DesiredState:
    """One bulb's desired state: the last intent, from either writer.

    See ADR-008. Never expires (Q24).
    """

    state: Literal["ON", "OFF"]
    appearance: Appearance
    writer: Literal["observation", "command"]
    written_at: float
    """Wall clock, seconds since the epoch — ``time.time()``, not monotonic."""

    def as_bulb_state(self) -> BulbState:
        """Adapt to :class:`BulbState` so :mod:`wiz2mqtt.payload` can render it."""
        return BulbState(
            state=self.state == "ON",
            brightness=self.appearance.brightness,
            hue=self.appearance.hue,
            saturation=self.appearance.saturation,
            color_temp_kelvin=self.appearance.color_temp_kelvin,
            scene=self.appearance.scene,
            effect_speed=self.appearance.speed,
            power_draw_w=None,
        )


def _appearance_from_bulb_state(bulb_state: BulbState) -> Appearance:
    return Appearance(
        brightness=bulb_state.brightness,
        hue=bulb_state.hue,
        saturation=bulb_state.saturation,
        color_temp_kelvin=bulb_state.color_temp_kelvin,
        scene=bulb_state.scene,
        speed=bulb_state.effect_speed,
    )


def desired_state_to_set_state_kwargs(desired: DesiredState) -> SetStateKwargs:
    """Translate a desired state into a ``WizBulbPort.set_state`` write (ADR-008).

    ``OFF`` sends only ``state=False`` — every appearance kwarg stays
    ``None`` regardless of what the stored appearance holds, since a dark
    lamp must not flash its old colour and a WiZ bulb only applies an
    appearance while it is on. ``ON`` sends ``state=True`` and the full
    appearance in the same call, mirroring :meth:`DesiredState.as_bulb_state`.
    """
    if desired.state == "OFF":
        return off_kwargs()
    appearance = desired.appearance
    return {
        "state": True,
        "brightness": appearance.brightness,
        "hue": appearance.hue,
        "saturation": appearance.saturation,
        "color_temp_kelvin": appearance.color_temp_kelvin,
        "scene": appearance.scene,
        "speed": appearance.speed,
    }


def desired_state_to_dict(desired: DesiredState) -> dict[str, Any]:
    """Serialise a desired state to a JSON-storable dict."""
    return {
        "state": desired.state,
        "appearance": dataclasses.asdict(desired.appearance),
        "writer": desired.writer,
        "written_at": desired.written_at,
    }


def _require_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    return value


def _require_finite_number(value: object, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{field} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _optional_finite_number(value: object, field: str) -> float | None:
    return None if value is None else _require_finite_number(value, field)


def _optional_int(value: object, field: str) -> int | None:
    """*value* as an int, or ``None`` when it is ``None``."""
    return None if value is None else _require_int(value, field)


def _appearance_from_dict(raw: Any) -> Appearance:
    """Validate and rebuild the stored appearance sub-record."""
    if not isinstance(raw, dict):
        raise TypeError("appearance must be a dict")
    if set(raw) != set(_APPEARANCE_FIELDS):
        raise ValueError("appearance has an invalid shape")

    brightness = _optional_int(raw["brightness"], "appearance.brightness")
    if brightness is not None and not 1 <= brightness <= 255:
        raise ValueError("appearance.brightness must be between 1 and 255")
    color_temp_kelvin = _optional_int(
        raw["color_temp_kelvin"], "appearance.color_temp_kelvin"
    )
    if color_temp_kelvin is not None and color_temp_kelvin <= 0:
        raise ValueError("appearance.color_temp_kelvin must be positive")

    return Appearance(
        brightness=brightness,
        hue=_optional_finite_number(raw["hue"], "appearance.hue"),
        saturation=_optional_finite_number(raw["saturation"], "appearance.saturation"),
        color_temp_kelvin=color_temp_kelvin,
        scene=_optional_int(raw["scene"], "appearance.scene"),
        speed=_optional_int(raw["speed"], "appearance.speed"),
    )


def desired_state_from_dict(raw: dict[Any, Any]) -> DesiredState:
    """Rebuild a desired state from a stored dict.

    Raises ``KeyError``/``TypeError``/``ValueError`` on a malformed record;
    callers guard against it (see :func:`_load_from_device_store`).
    """
    stored_state = raw["state"]
    if stored_state not in ("ON", "OFF"):
        raise ValueError("state must be ON or OFF")
    writer = raw["writer"]
    if writer not in ("observation", "command"):
        raise ValueError("writer must be observation or command")
    return DesiredState(
        state=cast(Literal["ON", "OFF"], stored_state),
        appearance=_appearance_from_dict(raw["appearance"]),
        writer=cast(Literal["observation", "command"], writer),
        written_at=_require_finite_number(raw["written_at"], "written_at"),
    )


def _load_from_device_store(store: DeviceStore) -> DesiredState | None:
    """Return *store*'s persisted desired state, or ``None`` if absent/corrupt.

    *store* is a per-bulb-scoped :class:`~cosalette.DeviceStore` (the same
    scoping :func:`wiz2mqtt.discovery.cache_capabilities` relies on).
    Private: cosalette caches one ``DeviceStore`` per telemetry registration
    for the whole run (loaded once, before the first tick), so a bulb's
    command-side store and telemetry-side store are two separate objects
    that never see each other's writes without a process restart. Every
    caller in this module must go through :func:`resolve_desired_state`
    instead, which keeps :class:`~wiz2mqtt.state.SharedState` as the
    single in-process source of truth and uses the device store only to
    survive a restart.
    """
    raw = store.get(_DESIRED_STATE_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        return desired_state_from_dict(raw)
    except KeyError, TypeError, ValueError, OverflowError:
        return None


def _save(store: DeviceStore, desired: DesiredState) -> None:
    store[_DESIRED_STATE_KEY] = desired_state_to_dict(desired)


def resolve_desired_state(
    state: SharedState, store: DeviceStore | None, name: str
) -> DesiredState | None:
    """Return *name*'s current desired state, or ``None`` if it has none yet.

    Prefers ``state.desired_state`` (in-process, always current). On a cold
    cache — *name*'s first tick since this process started — falls back to
    the persisted device store and populates the cache from it, so a
    restart with a stored intent is picked up exactly once, not reloaded on
    every call.
    """
    generation = state.desired_state_generation.get(name, 0)
    if state.suppressed_desired_state_generation.get(name) == generation:
        return None
    if name in state.desired_state:
        return state.desired_state[name]
    if store is None:
        return None
    desired = _load_from_device_store(store)
    if desired is not None:
        state.desired_state[name] = desired
    return desired


def record_observation(
    state: SharedState,
    store: DeviceStore | None,
    name: str,
    bulb_state: BulbState,
    now: float,
) -> None:
    """Write *bulb_state* as *name*'s new desired state (writer ``"observation"``).

    The caller gates this on the steady phase (ADR-008) — this function
    always writes unconditionally when called. Updates the in-process
    ``SharedState`` cache and, when a store is configured, persists it too.
    """
    if bulb_state.state is None:
        return
    desired = DesiredState(
        state="ON" if bulb_state.state else "OFF",
        appearance=_appearance_from_bulb_state(bulb_state),
        writer="observation",
        written_at=now,
    )
    state.desired_state[name] = desired
    state.suppressed_desired_state_generation.pop(name, None)
    if store is not None:
        _save(store, desired)


def record_command(
    state: SharedState,
    store: DeviceStore | None,
    name: str,
    kwargs: SetStateKwargs,
    now: float,
) -> DesiredState:
    """Merge a partial command onto *name*'s desired state (writer ``"command"``).

    Reuses :meth:`BulbState.apply_command`'s mode-aware colour-mode merge
    instead of duplicating it — a partial command's untouched fields keep
    their previous value, and a complete colour-mode update clears the
    fields of the mode(s) it supersedes. Updates the in-process
    ``SharedState`` cache and, when a store is configured, persists it too.
    """
    state.desired_state_generation[name] = (
        state.desired_state_generation.get(name, 0) + 1
    )
    # A new user command supersedes an exhausted return-path restore.  It must
    # get its own bounded replay budget rather than inheriting stale failures.
    state.restore_retry_cycles.pop(name, None)
    state.restore_retry_at.pop(name, None)
    state.restore_retry_exhausted.discard(name)
    current = resolve_desired_state(state, store, name)
    base = current.as_bulb_state() if current is not None else EMPTY_BULB_STATE
    merged = base.apply_command(
        state=kwargs.get("state"),
        brightness=kwargs.get("brightness"),
        hue=kwargs.get("hue"),
        saturation=kwargs.get("saturation"),
        color_temp_kelvin=kwargs.get("color_temp_kelvin"),
        scene=kwargs.get("scene"),
        effect_speed=kwargs.get("speed"),
    )
    desired = DesiredState(
        state="OFF" if merged.state is False else "ON",
        appearance=_appearance_from_bulb_state(merged),
        writer="command",
        written_at=now,
    )
    state.desired_state[name] = desired
    state.suppressed_desired_state_generation.pop(name, None)
    if store is not None:
        _save(store, desired)
    return desired


# ---------------------------------------------------------------------------
# Pending-command queue (cap-bjw9.6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PendingCommand:
    """The merged queued command for a currently-unreachable bulb."""

    kwargs: SetStateKwargs
    queued_at: float


@dataclass(frozen=True)
class AppliedCommand:
    """The outcome of a bulb's last ADR-008 return-path write."""

    kwargs: SetStateKwargs
    at: float
    """Wall clock, seconds since the epoch."""
    attempts: int
    confirmed: bool


def _pending_as_bulb_state(command: PendingCommand | None) -> BulbState:
    """Adapt a pending command to the state merge model shared with intent."""
    if command is None:
        return EMPTY_BULB_STATE
    kwargs = command.kwargs
    return BulbState(
        state=kwargs.get("state"),
        brightness=kwargs.get("brightness"),
        hue=kwargs.get("hue"),
        saturation=kwargs.get("saturation"),
        color_temp_kelvin=kwargs.get("color_temp_kelvin"),
        scene=kwargs.get("scene"),
        effect_speed=kwargs.get("speed"),
    )


def bulb_state_to_set_state_kwargs(bulb_state: BulbState) -> SetStateKwargs:
    """Translate a bulb state into a complete ``set_state`` write."""
    return {
        "state": bulb_state.state,
        "brightness": bulb_state.brightness,
        "hue": bulb_state.hue,
        "saturation": bulb_state.saturation,
        "color_temp_kelvin": bulb_state.color_temp_kelvin,
        "scene": bulb_state.scene,
        "speed": bulb_state.effect_speed,
    }


def pending_write_kwargs(kwargs: SetStateKwargs) -> SetStateKwargs:
    """Keep queued appearance for a later ON, but never send it with OFF."""
    if kwargs.get("state") is False:
        return off_kwargs()
    return kwargs


def merge_pending(
    existing: PendingCommand | None, kwargs: SetStateKwargs, now: float
) -> PendingCommand:
    """Merge *kwargs* into a pending command with desired-state semantics.

    ``BulbState.apply_command`` owns the colour-mode rules, so a queued
    command and desired state cannot disagree about whether RGB, colour
    temperature, or a scene supersedes the other modes. Each merge refreshes
    the TTL from the newest user intent.
    """
    has_appearance = any(
        kwargs.get(field) is not None
        for field in (
            "brightness",
            "hue",
            "saturation",
            "color_temp_kelvin",
            "scene",
            "speed",
        )
    )
    # WiZ treats an appearance update as a request to show that appearance.
    # Preserve that direct-command behaviour when it supersedes queued OFF.
    state_update = kwargs.get("state")
    if (
        existing is not None
        and existing.kwargs.get("state") is False
        and state_update is None
        and has_appearance
    ):
        state_update = True
    merged = _pending_as_bulb_state(existing).apply_command(
        state=state_update,
        brightness=kwargs.get("brightness"),
        hue=kwargs.get("hue"),
        saturation=kwargs.get("saturation"),
        color_temp_kelvin=kwargs.get("color_temp_kelvin"),
        scene=kwargs.get("scene"),
        effect_speed=kwargs.get("speed"),
    )
    return PendingCommand(kwargs=bulb_state_to_set_state_kwargs(merged), queued_at=now)


def enqueue(
    pending: dict[str, PendingCommand], name: str, kwargs: SetStateKwargs, now: float
) -> None:
    """Merge *kwargs* into *name*'s pending command."""
    pending[name] = merge_pending(pending.get(name), kwargs, now)


def pop_valid(
    pending: dict[str, PendingCommand], name: str, ttl: float, now: float
) -> SetStateKwargs | None:
    """Pop and return *name*'s pending command, or ``None`` if absent/expired.

    *now* is passed in by the caller rather than read internally, so tests
    exercise the TTL with plain floats instead of sleeping.
    """
    command = pending.pop(name, None)
    if command is None:
        return None
    if now - command.queued_at > ttl:
        logger.info("Dropping expired pending command for bulb %s", name)
        return None
    return pending_write_kwargs(command.kwargs)


def queues_for_return(state: SharedState, name: str, belief: Belief | None) -> bool:
    """Whether a command must queue for the return path instead of the wire.

    True when the power source is believed off, the bulb is offline, a queue
    already exists (keeps FIFO order) or the reconnect return path is armed.
    """
    return (
        belief == "off"
        or state.last_availability.get(name) == "offline"
        or name in state.pending_commands
        or state.phase.get(name) == "reconnect"
    )
