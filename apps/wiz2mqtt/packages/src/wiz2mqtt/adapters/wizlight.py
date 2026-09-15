"""Production adapter wrapping ``pywizlight`` via lazy import (ADR-003).

Owns the ``pywizlight`` connection, the push subscription, and the state
cache for every bulb it has been asked about. Bulbs are identified by IP
and connected to lazily on first contact — there is no fixed inventory.

A push does more than refresh the cache: it arms the matching telemetry
entity through the injected :class:`~cosalette.EntityNotifier`, so the
bulb's own UDP notification is what drives publication (cosalette
ADR-064). The ``interval=`` tick in ``wiz2mqtt.main`` degrades to a
heartbeat.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING, Annotated, Any, Self

from cosalette import EntityNotifier, Optional

from wiz2mqtt.colour import (
    clamp_kelvin,
    is_cct_mode,
    rgb_to_hue_saturation,
    validate_scene,
)
from wiz2mqtt.errors import (
    WizBridgeError,
    WizConnectionError,
    WizIdentityError,
    WizTimeoutError,
)
from wiz2mqtt.models import BulbCapabilities, BulbState
from wiz2mqtt.settings import Wiz2MqttSettings

if TYPE_CHECKING:
    from pywizlight.bulb import PilotParser
    from pywizlight.bulblibrary import BulbType

logger = logging.getLogger(__name__)

_DEFAULT_PUSH_STALENESS_THRESHOLD = 60.0
"""Seconds since ``bulb.last_push`` before ``get_state`` falls back to polling.

Measured against ``pywizlight``'s own ``wizlight.last_push`` — stamped on
every syncPilot, suppressed or not — rather than the adapter's own push
cache timestamp. Comparing the same clock ``updateState()`` gates its
short-circuit on (``MAX_TIME_BETWEEN_PUSH`` = 33 s) guarantees that a
decision to poll here always produces a real network read (cap-dc5y): 60 s
exceeds pywizlight's own 33 s gate, so this method never decides to poll
while ``updateState()`` would still short-circuit. A bulb that keeps
heartbeating — suppressed or not — never trips this fallback; only a bulb
that has gone genuinely silent does.
"""

_PUSH_REGISTRATION_RETRY_INTERVAL = 60.0
"""Seconds between re-arm attempts for a bulb whose push registration failed.

``_get_bulb`` only ever attempts registration once per bulb's lifetime, so a
transient failure (port 38900 momentarily in use, no source IP yet) would
otherwise degrade that bulb to polling for the rest of the process even
after the underlying condition clears (cap-4rbg). ``get_state`` retries at
this cadence instead, bounded so a genuinely misconfigured host is not
spammed with connection attempts.
"""


class WizBulbAdapter:
    """Production adapter wrapping :mod:`pywizlight`.

    The ``pywizlight`` package is imported *inside methods* rather than at
    module level (ADR-003), matching the convention used by every other
    hardware adapter in this monorepo.
    """

    def __init__(
        self,
        settings: Wiz2MqttSettings,
        notify: EntityNotifier,
        # Annotated[..., Optional()] keeps this out of the DI resolution:
        # a bare ``float`` puts the parameter in the injection plan, where
        # it fails with "no provider is registered for type float".
        push_staleness_threshold: Annotated[float, Optional()] = (
            _DEFAULT_PUSH_STALENESS_THRESHOLD
        ),
    ) -> None:
        self._push_staleness_threshold = push_staleness_threshold
        self._notify = notify
        # Total and injective: Wiz2MqttSettings._bulbs_unique guarantees both
        # names and IPs are unique, and the telemetry entity names come from
        # the same list (main._bulb_map).
        self._name_by_ip = {bulb.ip: bulb.name for bulb in settings.bulbs}
        self._expected_mac_by_ip = {
            bulb.ip: bulb.mac for bulb in settings.bulbs if bulb.mac is not None
        }
        self._bulbs: dict[str, Any] = {}
        self._initialization_locks: dict[str, asyncio.Lock] = {}
        self._capabilities: dict[str, BulbCapabilities] = {}
        self._state_cache: dict[str, BulbState] = {}
        # ips whose push registration has succeeded (bulb.start_push()
        # returned True) — arms the staleness warning below regardless of
        # whether a datagram has ever actually arrived (cap-fubw).
        self._push_registered: set[str] = set()
        # ip -> monotonic time of the next allowed re-arm attempt, for ips
        # whose registration failed (cap-4rbg).
        self._push_retry_at: dict[str, float] = {}
        self._warned_stale: set[str] = set()

    async def _get_bulb(self, ip: str) -> Any:
        """Return the cached bulb for *ip*, connecting on first contact."""
        if ip in self._bulbs:
            return self._bulbs[ip]

        lock = self._initialization_locks.setdefault(ip, asyncio.Lock())
        async with lock:
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
                try:
                    bulb_type = await bulb.get_bulbtype()
                except WizLightTimeOutError as exc:
                    msg = f"Timed out detecting capabilities for bulb {ip}"
                    raise WizTimeoutError(msg) from exc
                except WizLightConnectionError as exc:
                    msg = f"Connection failed detecting capabilities for bulb {ip}"
                    raise WizConnectionError(msg) from exc
                except WizLightError as exc:
                    msg = (
                        f"pywizlight error detecting capabilities for bulb {ip}: {exc}"
                    )
                    raise WizBridgeError(msg) from exc

                expected_mac = self._expected_mac_by_ip.get(ip)
                if expected_mac is not None:
                    try:
                        reported_mac = await bulb.getMac()
                    except WizLightTimeOutError as exc:
                        msg = f"Timed out reading identity for bulb {ip}"
                        raise WizTimeoutError(msg) from exc
                    except WizLightConnectionError as exc:
                        msg = f"Connection failed reading identity for bulb {ip}"
                        raise WizConnectionError(msg) from exc
                    except WizLightError as exc:
                        msg = f"pywizlight error reading identity for bulb {ip}: {exc}"
                        raise WizBridgeError(msg) from exc

                    if reported_mac is None:
                        logger.warning(
                            "Bulb %s did not report a MAC; "
                            "identity could not be verified",
                            ip,
                        )
                    else:
                        normalized_mac = (
                            reported_mac.lower().replace(":", "").replace("-", "")
                        )
                        if normalized_mac != expected_mac:
                            logger.error(
                                "Bulb identity mismatch at %s: expected MAC %s, got %s",
                                ip,
                                expected_mac,
                                normalized_mac,
                            )
                            msg = f"Bulb identity mismatch at {ip}"
                            raise WizIdentityError(msg)

                capabilities = _capabilities_from_bulb_type(bulb_type)

                # Registration success only means the UDP socket bound, not that
                # packets will ever arrive (bridge-NAT push falls silently into the
                # void) — get_state()'s staleness check is the real health signal.
                # start_push() signals listener-startup failure by returning
                # False, not by raising, so the return value is checked too
                # (cap-4rbg): a dropped return silently left the operator with
                # no diagnostic and no retry.
                await self._register_push(ip, bulb)

                self._capabilities[ip] = capabilities
                self._bulbs[ip] = bulb
                return bulb
            except BaseException:
                try:
                    await bulb.async_close()
                except BaseException:
                    logger.warning(
                        "Failed to close rejected bulb %s", ip, exc_info=True
                    )
                raise

    async def _register_push(
        self, ip: str, bulb: Any, *, is_retry: bool = False
    ) -> None:
        """Attempt push registration, recording the outcome for get_state.

        ``bulb.start_push()`` reports the common listener-startup failure
        (port 38900 already bound, or no source IP yet) by returning
        ``False``, not by raising — treat that the same as a raised
        ``WizLightError``: log once, and leave ``ip`` out of
        ``_push_registered`` so ``get_state`` retries later.
        """
        from pywizlight.exceptions import (  # noqa: PLC0415 — lazy import by design
            WizLightError,
        )

        try:
            registered = await bulb.start_push(self._make_push_callback(ip))
        except WizLightError:
            registered = False

        if registered:
            self._push_registered.add(ip)
            self._push_retry_at.pop(ip, None)
            if is_retry:
                logger.info("Push registration recovered for bulb %s", ip)
        else:
            logger.warning(
                "Push registration failed for bulb %s; relying on polling", ip
            )
            self._push_retry_at[ip] = (
                time.monotonic() + _PUSH_REGISTRATION_RETRY_INTERVAL
            )

    async def _maybe_retry_push_registration(self, ip: str, bulb: Any) -> None:
        """Re-arm push for a bulb whose registration has not yet succeeded.

        Rate-limited by ``_push_retry_at`` so a genuinely misconfigured host
        is retried at most once per ``_PUSH_REGISTRATION_RETRY_INTERVAL``,
        not on every ``get_state`` call (cap-4rbg).
        """
        if ip in self._push_registered:
            return
        retry_at = self._push_retry_at.get(ip)
        if retry_at is not None and time.monotonic() < retry_at:
            return
        await self._register_push(ip, bulb, is_retry=True)

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
                self._wake(ip)

        return _on_push

    def _wake(self, ip: str) -> None:
        """Arm *ip*'s telemetry entity so the fresh cache publishes now.

        A no-op for an IP outside ``settings.bulbs``: nothing registered a
        telemetry entity for it, so there is no slot to arm.  Arming is
        coalescing and thread-safe, so a burst of pushes collapses into one
        out-of-cycle run and an off-loop callback is marshalled for us.
        """
        name = self._name_by_ip.get(ip)
        if name is not None:
            self._notify(name)

    async def get_capabilities(self, ip: str) -> BulbCapabilities:
        """Return the bulb's auto-detected capabilities."""
        await self._get_bulb(ip)
        return self._capabilities[ip]

    async def get_state(self, ip: str) -> BulbState:
        """Return the bulb's current state, polling if the push cache is stale.

        Staleness is measured against ``bulb.last_push``, not the adapter's
        own state-changing push record. The two diverge because pywizlight
        stamps ``bulb.last_push`` on every syncPilot it receives, suppressed
        or not. Deciding from the adapter's own record could call
        ``_poll_state`` while ``updateState()`` still short-circuits on its
        own fresher clock, performing zero network I/O (cap-dc5y).

        A first read always calls ``updateState()`` regardless of
        ``bulb.last_push``: a suppressed heartbeat can stamp it fresh in the
        window between connecting and this call, before ``_state_cache``
        holds anything to return. In that case pywizlight returns its cached
        parser without sending a network request, and this method populates
        the adapter cache from it.
        """
        bulb = await self._get_bulb(ip)
        await self._maybe_retry_push_registration(ip, bulb)
        now = time.monotonic()
        if ip not in self._state_cache or (
            (now - bulb.last_push) > self._push_staleness_threshold
        ):
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

        # Keyed on registration succeeding, not on a push ever having arrived:
        # a bulb whose push never works (bridge-NAT, VLAN) must warn too, not
        # just one that worked and then went stale (cap-fubw).
        if ip in self._push_registered and ip not in self._warned_stale:
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
        speed: int | None = None,
    ) -> None:
        """Apply a partial state update, clamping/validating against capabilities."""
        if state is None and all(
            v is None
            for v in (brightness, hue, saturation, color_temp_kelvin, scene, speed)
        ):
            return

        bulb = await self._get_bulb(ip)
        caps = self._capabilities[ip]

        if color_temp_kelvin is not None:
            color_temp_kelvin = clamp_kelvin(color_temp_kelvin, caps)
        if scene is not None:
            validate_scene(scene, caps)

        have_colour = hue is not None and saturation is not None
        hucolor = (hue, saturation) if have_colour else None
        await self._send_pilot(
            ip,
            bulb,
            state=state,
            brightness=brightness,
            hucolor=hucolor,
            color_temp_kelvin=color_temp_kelvin,
            scene=scene,
            speed=speed,
        )

        # Optimistic merge pending the next authoritative push/poll.
        # _send_pilot only sends turn_off() when state is False — merge just
        # that field rather than the unsent brightness/colour fields.
        current = self._state_cache.get(ip, _EMPTY_STATE)
        if state is False:
            self._state_cache[ip] = current.apply_command(state=False)
        else:
            self._state_cache[ip] = current.apply_command(
                state=state,
                brightness=brightness,
                hue=hue,
                saturation=saturation,
                color_temp_kelvin=color_temp_kelvin,
                scene=scene,
                effect_speed=speed,
            )

    async def _send_pilot(
        self,
        ip: str,
        bulb: Any,
        *,
        state: bool | None,
        brightness: int | None,
        hucolor: tuple[float, float] | None,
        color_temp_kelvin: int | None,
        scene: int | None,
        speed: int | None,
    ) -> None:
        """Send turn_off/turn_on, wrapping pywizlight's exceptions at the boundary.

        No retry loop here — pywizlight already retries internally
        (TIMEOUT=13s, 6 datagrams); stacking another would compound delays.
        """
        from pywizlight import PilotBuilder  # noqa: PLC0415 — lazy import by design
        from pywizlight.exceptions import (  # noqa: PLC0415 — lazy import by design
            WizLightConnectionError,
            WizLightError,
            WizLightTimeOutError,
        )

        try:
            if state is False:
                await bulb.turn_off()
            else:
                pilot = PilotBuilder(
                    brightness=brightness,
                    hucolor=hucolor,
                    colortemp=color_temp_kelvin,
                    scene=scene,
                    speed=speed,
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
        self._initialization_locks.clear()
        self._capabilities.clear()
        self._state_cache.clear()
        self._push_registered.clear()
        self._push_retry_at.clear()
        self._warned_stale.clear()


_EMPTY_STATE = BulbState(
    state=None,
    brightness=None,
    hue=None,
    saturation=None,
    color_temp_kelvin=None,
    scene=None,
    effect_speed=None,
    power_draw_w=None,
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
    parser = next((p for p in parsers if p is not None), None)
    if parser is None:
        return None

    color_temp_kelvin = parser.get_colortemp()
    hue, saturation = _hue_saturation_from_parser(parser, color_temp_kelvin)

    return BulbState(
        state=parser.get_state(),
        brightness=parser.get_brightness(),
        hue=hue,
        saturation=saturation,
        color_temp_kelvin=color_temp_kelvin,
        scene=parser.get_scene_id(),
        effect_speed=parser.get_speed(),
        power_draw_w=parser.get_power(),
    )


def _hue_saturation_from_parser(
    parser: PilotParser, color_temp_kelvin: int | None
) -> tuple[float | None, float | None]:
    """Derive (hue, saturation) from the parser's RGB readback, CCT-gated.

    CCT mode is detected from colortemp, never from ``get_rgb()``: the
    parser can report both a non-zero colortemp *and* a fully-populated RGB
    tuple at once — stale RGB residue from a prior colour-mode session.
    """
    if is_cct_mode(color_temp_kelvin):
        return None, None
    rgb = parser.get_rgb()
    if rgb is None:
        return None, None
    r, g, b = rgb
    if r is None or g is None or b is None:
        return None, None
    cold_white = parser.get_cold_white() or 0
    return rgb_to_hue_saturation(r, g, b, cold_white)
