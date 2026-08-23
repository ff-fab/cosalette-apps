"""Production adapter wrapping ``pywizlight`` via lazy import (ADR-003).

Owns the ``pywizlight`` connection, the push subscription, and the state
cache for every bulb it has been asked about. Bulbs are identified by IP
and connected to lazily on first contact — there is no fixed inventory.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

from wiz2mqtt.colour import clamp_kelvin, rgb_to_hue_saturation, validate_scene
from wiz2mqtt.errors import WizBridgeError, WizConnectionError, WizTimeoutError
from wiz2mqtt.models import BulbCapabilities, BulbState

if TYPE_CHECKING:
    from pywizlight.bulb import PilotParser
    from pywizlight.bulblibrary import BulbType

logger = logging.getLogger(__name__)

_DEFAULT_PUSH_STALENESS_THRESHOLD = 60.0
"""Seconds since the last real push before ``get_state`` falls back to polling.

A bulb only pushes on state *changes* — an idle, healthy bulb can go
arbitrarily long without a push. This threshold is a periodic
freshness re-check, not solely a push-failure detector.
"""


class WizBulbAdapter:
    """Production adapter wrapping :mod:`pywizlight`.

    The ``pywizlight`` package is imported *inside methods* rather than at
    module level (ADR-003), matching the convention used by every other
    hardware adapter in this monorepo.
    """

    def __init__(
        self, push_staleness_threshold: float = _DEFAULT_PUSH_STALENESS_THRESHOLD
    ) -> None:
        self._push_staleness_threshold = push_staleness_threshold
        self._bulbs: dict[str, Any] = {}
        self._capabilities: dict[str, BulbCapabilities] = {}
        self._state_cache: dict[str, BulbState] = {}
        self._last_push_at: dict[str, float] = {}
        self._warned_stale: set[str] = set()

    async def _get_bulb(self, ip: str) -> Any:
        """Return the cached bulb for *ip*, connecting on first contact."""
        if ip in self._bulbs:
            return self._bulbs[ip]

        try:
            ipaddress.ip_address(ip)
        except ValueError:
            msg = f"Invalid IP address: {ip!r}"
            raise WizBridgeError(msg) from None

        from pywizlight import wizlight  # noqa: PLC0415 — lazy import by design
        from pywizlight.exceptions import (  # noqa: PLC0415 — lazy import by design
            WizLightConnectionError,
            WizLightError,
            WizLightTimeOutError,
        )

        bulb = wizlight(ip)
        try:
            bulb_type = await bulb.get_bulbtype()
        except WizLightTimeOutError as exc:
            msg = f"Timed out detecting capabilities for bulb {ip}"
            raise WizTimeoutError(msg) from exc
        except WizLightConnectionError as exc:
            msg = f"Connection failed detecting capabilities for bulb {ip}"
            raise WizConnectionError(msg) from exc
        except WizLightError as exc:
            msg = f"pywizlight error detecting capabilities for bulb {ip}: {exc}"
            raise WizBridgeError(msg) from exc

        self._capabilities[ip] = _capabilities_from_bulb_type(bulb_type)
        self._bulbs[ip] = bulb

        # Registration success only means the UDP socket bound, not that
        # packets will ever arrive (bridge-NAT push falls silently into the
        # void) — get_state()'s staleness check is the real health signal.
        try:
            await bulb.start_push(self._make_push_callback(ip))
        except WizLightError:
            logger.warning(
                "Push registration failed for bulb %s; relying on polling", ip
            )

        return bulb

    def _make_push_callback(
        self, ip: str
    ) -> Callable[[list[PilotParser | None] | None], None]:
        def _on_push(parsers: list[PilotParser | None] | None) -> None:
            try:
                state = _parse_state(parsers)
            except Exception:
                logger.exception("Failed to parse push for bulb %s", ip)
                return
            if state is not None:
                self._state_cache[ip] = state
                self._last_push_at[ip] = time.monotonic()

        return _on_push

    async def get_capabilities(self, ip: str) -> BulbCapabilities:
        """Return the bulb's auto-detected capabilities."""
        await self._get_bulb(ip)
        return self._capabilities[ip]

    async def get_state(self, ip: str) -> BulbState:
        """Return the bulb's current state, polling if the push cache is stale."""
        await self._get_bulb(ip)
        last_push = self._last_push_at.get(ip)
        now = time.monotonic()
        if last_push is None or (now - last_push) > self._push_staleness_threshold:
            await self._poll_state(ip)
        return self._state_cache[ip]

    async def _poll_state(self, ip: str) -> None:
        from pywizlight.exceptions import (  # noqa: PLC0415 — lazy import by design
            WizLightConnectionError,
            WizLightError,
            WizLightTimeOutError,
        )

        bulb = self._bulbs[ip]
        try:
            parsers = await bulb.updateState()
        except WizLightTimeOutError as exc:
            msg = f"Timed out polling bulb {ip}"
            raise WizTimeoutError(msg) from exc
        except WizLightConnectionError as exc:
            msg = f"Connection failed polling bulb {ip}"
            raise WizConnectionError(msg) from exc
        except WizLightError as exc:
            msg = f"pywizlight error polling bulb {ip}: {exc}"
            raise WizBridgeError(msg) from exc

        if ip in self._last_push_at and ip not in self._warned_stale:
            logger.warning("No recent push for bulb %s — falling back to polling", ip)
            self._warned_stale.add(ip)

        state = _parse_state(parsers)
        if state is not None:
            self._state_cache[ip] = state
        elif ip not in self._state_cache:
            self._state_cache[ip] = _EMPTY_STATE

    async def set_state(
        self,
        ip: str,
        *,
        state: bool | None = None,
        brightness: int | None = None,
        hue: float | None = None,
        saturation: float | None = None,
        color_temp_kelvin: int | None = None,
        scene: int | None = None,
    ) -> None:
        """Apply a partial state update, clamping/validating against capabilities."""
        if state is None and all(
            v is None for v in (brightness, hue, saturation, color_temp_kelvin, scene)
        ):
            return

        bulb = await self._get_bulb(ip)
        caps = self._capabilities[ip]

        if color_temp_kelvin is not None:
            color_temp_kelvin = clamp_kelvin(color_temp_kelvin, caps)
        if scene is not None:
            validate_scene(scene, caps)

        from pywizlight import PilotBuilder  # noqa: PLC0415 — lazy import by design
        from pywizlight.exceptions import (  # noqa: PLC0415 — lazy import by design
            WizLightConnectionError,
            WizLightError,
            WizLightTimeOutError,
        )

        # No retry loop here — pywizlight already retries internally
        # (TIMEOUT=13s, 6 datagrams); stacking another would compound delays.
        have_colour = hue is not None and saturation is not None
        hucolor = (hue, saturation) if have_colour else None
        try:
            if state is False:
                await bulb.turn_off()
            else:
                pilot = PilotBuilder(
                    brightness=brightness,
                    hucolor=hucolor,
                    colortemp=color_temp_kelvin,
                    scene=scene,
                )
                await bulb.turn_on(pilot)
        except WizLightTimeOutError as exc:
            msg = f"Timed out sending command to bulb {ip}"
            raise WizTimeoutError(msg) from exc
        except WizLightConnectionError as exc:
            msg = f"Connection failed sending command to bulb {ip}"
            raise WizConnectionError(msg) from exc
        except WizLightError as exc:
            msg = f"pywizlight error sending command to bulb {ip}: {exc}"
            raise WizBridgeError(msg) from exc

        # Optimistic merge pending the next authoritative push/poll.
        current = self._state_cache.get(ip, _EMPTY_STATE)
        self._state_cache[ip] = current.replace_non_none(
            state=state,
            brightness=brightness,
            hue=hue,
            saturation=saturation,
            color_temp_kelvin=color_temp_kelvin,
            scene=scene,
        )

    async def health_check(self) -> bool:
        """Always healthy — UDP is connectionless, there is no single link to probe.

        Per-bulb availability is signalled via the domain exceptions raised
        above (wired to ``unavailable_on`` by command/device registrations),
        not this adapter-level health check.
        """
        return True

    async def __aenter__(self) -> Self:
        """Enter async context: no-op — connections are lazy per bulb."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close every bulb connection opened so far, then clear all caches."""
        results = await asyncio.gather(
            *(bulb.async_close() for bulb in self._bulbs.values()),
            return_exceptions=True,
        )
        for ip, result in zip(self._bulbs, results, strict=False):
            if isinstance(result, BaseException):
                logger.warning("Failed to close bulb %s: %s", ip, result)
        self._bulbs.clear()
        self._capabilities.clear()
        self._state_cache.clear()
        self._last_push_at.clear()
        self._warned_stale.clear()


_EMPTY_STATE = BulbState(
    state=None,
    brightness=None,
    hue=None,
    saturation=None,
    color_temp_kelvin=None,
    scene=None,
)


def _capabilities_from_bulb_type(bulb_type: BulbType) -> BulbCapabilities:
    kelvin_range = bulb_type.kelvin_range
    return BulbCapabilities(
        bulb_class=bulb_type.bulb_type.name,
        color=bulb_type.features.color,
        color_tmp=bulb_type.features.color_tmp,
        effect=bulb_type.features.effect,
        brightness=bulb_type.features.brightness,
        kelvin_min=kelvin_range.min if kelvin_range is not None else None,
        kelvin_max=kelvin_range.max if kelvin_range is not None else None,
    )


def _parse_state(parsers: list[PilotParser | None] | None) -> BulbState | None:
    if not parsers:
        return None
    parser = None
    for p in parsers:
        if p is not None:
            parser = p
            break
    if parser is None:
        return None

    rgb = parser.get_rgb()
    hue = saturation = None
    if rgb is not None:
        r, g, b = rgb
        if r is not None and g is not None and b is not None:
            hue, saturation = rgb_to_hue_saturation(r, g, b)

    return BulbState(
        state=parser.get_state(),
        brightness=parser.get_brightness(),
        hue=hue,
        saturation=saturation,
        color_temp_kelvin=parser.get_colortemp(),
        scene=parser.get_scene_id(),
    )
