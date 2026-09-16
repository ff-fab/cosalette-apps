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

from wiz2mqtt.models import BulbState

if TYPE_CHECKING:
    from cosalette import DeviceStore

    from wiz2mqtt.commands import SetStateKwargs
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
    appearance_raw = raw["appearance"]
    if not isinstance(appearance_raw, dict):
        raise TypeError("appearance must be a dict")
    if set(appearance_raw) != set(_APPEARANCE_FIELDS):
        raise ValueError("appearance has an invalid shape")

    brightness = appearance_raw["brightness"]
    if brightness is not None:
        brightness = _require_int(brightness, "appearance.brightness")
        if not 1 <= brightness <= 255:
            raise ValueError("appearance.brightness must be between 1 and 255")
    color_temp_kelvin = appearance_raw["color_temp_kelvin"]
    if color_temp_kelvin is not None:
        color_temp_kelvin = _require_int(
            color_temp_kelvin, "appearance.color_temp_kelvin"
        )
        if color_temp_kelvin <= 0:
            raise ValueError("appearance.color_temp_kelvin must be positive")

    appearance = Appearance(
        brightness=brightness,
        hue=_optional_finite_number(appearance_raw["hue"], "appearance.hue"),
        saturation=_optional_finite_number(
            appearance_raw["saturation"], "appearance.saturation"
        ),
        color_temp_kelvin=color_temp_kelvin,
        scene=(
            None
            if appearance_raw["scene"] is None
            else _require_int(appearance_raw["scene"], "appearance.scene")
        ),
        speed=(
            None
            if appearance_raw["speed"] is None
            else _require_int(appearance_raw["speed"], "appearance.speed")
        ),
    )
    return DesiredState(
        state=cast(Literal["ON", "OFF"], stored_state),
        appearance=appearance,
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
    current = resolve_desired_state(state, store, name)
    base = current.as_bulb_state() if current is not None else _EMPTY_BULB_STATE
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
    if store is not None:
        _save(store, desired)
    return desired


_EMPTY_BULB_STATE = BulbState(
    state=None,
    brightness=None,
    hue=None,
    saturation=None,
    color_temp_kelvin=None,
    scene=None,
    effect_speed=None,
    power_draw_w=None,
)


# ---------------------------------------------------------------------------
# Pending-command queue (cap-bjw9.6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PendingCommand:
    """A queued command for a currently-unreachable bulb."""

    kwargs: SetStateKwargs
    queued_at: float


def enqueue(
    pending: dict[str, PendingCommand], name: str, kwargs: SetStateKwargs, now: float
) -> None:
    """Queue *kwargs* for *name*, replacing any older pending command."""
    pending[name] = PendingCommand(kwargs=kwargs, queued_at=now)


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
    return command.kwargs
