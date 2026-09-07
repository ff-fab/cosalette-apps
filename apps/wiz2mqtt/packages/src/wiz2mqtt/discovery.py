"""Runtime HA discovery enrichment: narrow advertised metadata per bulb (cap-3tr).

The static ``_HA_LIGHT_ENTITY`` in :mod:`wiz2mqtt.models` advertises a
wire-format *superset* — every configured bulb is offered ``rgb`` +
``color_temp``, the full effect list, and a 2200-6500 K range — because
``app.discovery()`` publishes on the first MQTT connect, before any bulb has
been contacted (ADR-003, Option A). This module implements **Mechanism B**: the
per-bulb :class:`~cosalette.DeviceStore` caches each bulb's auto-detected
:class:`~wiz2mqtt.models.BulbCapabilities`, and an ``app.discovery(enrich=...)``
hook narrows the advertised ``light`` metadata from that cache.

Because discovery is published once, on connect, and the cache is only populated
*after* a bulb is first reached, the narrowing is **self-healing across a
restart**: the first run of a freshly-onboarded (or retyped) bulb advertises the
superset while it caches what it detected; the next run publishes the accurate,
per-bulb metadata. Capabilities are never declared in config (ADR-003) — the
cache holds derived data that every contact refreshes, so it cannot drift.

Not to be confused with :mod:`wiz2mqtt.discover`, the standalone onboarding CLI.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from wiz2mqtt.errors import WizBridgeError
from wiz2mqtt.models import BulbCapabilities

if TYPE_CHECKING:
    import cosalette
    from cosalette import DeviceStore, Store
    from cosalette.schema import ChannelSchema, HaEnrichHook, PropertySchema

    from wiz2mqtt.ports import WizBulbPort
    from wiz2mqtt.settings import BulbConfig

# Sub-key under the per-bulb DeviceStore dict (which is itself keyed by bulb
# name, so the enrich hook can read it back via ``app.store.load(name)``).
_CAPABILITIES_KEY = "capabilities"

_CAPABILITY_FIELDS = tuple(f.name for f in dataclasses.fields(BulbCapabilities))


def capabilities_to_dict(caps: BulbCapabilities) -> dict[str, Any]:
    """Serialise capabilities to a JSON-storable dict."""
    return dataclasses.asdict(caps)


def capabilities_from_dict(raw: dict[Any, Any]) -> BulbCapabilities:
    """Rebuild capabilities from a stored dict.

    Raises ``KeyError``/``TypeError`` on a malformed record; callers that read
    from an untrusted store guard against it (see :func:`load_cached_capabilities`).
    """
    return BulbCapabilities(**{name: raw[name] for name in _CAPABILITY_FIELDS})


def load_cached_capabilities(store: Store, bulb_name: str) -> BulbCapabilities | None:
    """Return the cached capabilities for *bulb_name*, or ``None`` if absent.

    ``None`` means "not yet detected" (first boot before contact, or a
    corrupt/legacy record) — callers keep the static superset in that case.
    """
    record = store.load(bulb_name)
    if not record:
        return None
    raw = record.get(_CAPABILITIES_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        return capabilities_from_dict(raw)
    except KeyError, TypeError, ValueError:
        return None


async def cache_capabilities(
    store: DeviceStore, config: BulbConfig, port: WizBulbPort
) -> None:
    """Persist *config*'s bulb capabilities into its DeviceStore, if changed.

    A no-op until the bulb has been reached at least once (``get_capabilities``
    raises while unreachable). Writing only on change keeps a retyped bulb
    correct — the next detection overwrites the stale record — without dirtying
    the store every tick.
    """
    try:
        caps = await port.get_capabilities(config.ip)
    except WizBridgeError:
        return
    desired = capabilities_to_dict(caps)
    if store.get(_CAPABILITIES_KEY) != desired:
        store[_CAPABILITIES_KEY] = desired


def narrow_light_discovery(config: dict[str, Any], caps: BulbCapabilities) -> None:
    """Narrow a ``light`` discovery *config* in place to what *caps* supports.

    Home Assistant requires exactly one *primary* colour mode family:
    ``rgb``/``color_temp`` are additive, but a bulb with neither falls back to
    the single ``brightness`` (dimmable white) or ``onoff`` mode. ``color_temp``
    is what gives Kelvin meaning, so the range is dropped without it.
    """
    modes: list[str] = []
    if caps.color:
        modes.append("rgb")
    if caps.color_tmp:
        modes.append("color_temp")
    if not modes:
        modes = ["brightness"] if caps.brightness else ["onoff"]
    config["supported_color_modes"] = modes

    if caps.color_tmp and caps.kelvin_min is not None and caps.kelvin_max is not None:
        config["min_kelvin"] = caps.kelvin_min
        config["max_kelvin"] = caps.kelvin_max
    else:
        config.pop("min_kelvin", None)
        config.pop("max_kelvin", None)

    if not caps.effect:
        config["effect"] = False
        config.pop("effect_list", None)

    if not caps.brightness:
        config["brightness"] = False


def _bulb_name_from_state_topic(state_topic: str | None) -> str | None:
    """Extract the bulb name from a ``<prefix>/<name>/state`` topic.

    The name is always the second-to-last segment, independent of how many
    segments the configurable topic prefix contributes.
    """
    if not state_topic:
        return None
    parts = state_topic.rsplit("/", 2)
    if len(parts) < 2:
        return None
    return parts[-2]


def make_discovery_enrich(app: cosalette.App) -> HaEnrichHook:
    """Build the ``app.discovery(enrich=...)`` hook that narrows per-bulb metadata.

    Reads ``app.store`` lazily at publish time; a missing store or an
    uncached bulb leaves the static superset untouched.
    """

    def _enrich(
        channel: ChannelSchema,  # noqa: ARG001 — hook signature (name via config)
        prop: PropertySchema | None,  # noqa: ARG001 — composite entity: always None
        config: dict[str, Any],
    ) -> None:
        # Only the composite ``light`` entity carries these keys; the number,
        # sensor and bridge entities are left alone.
        if "supported_color_modes" not in config:
            return
        store = app.store
        if store is None:
            return
        name = _bulb_name_from_state_topic(config.get("state_topic"))
        if name is None:
            return
        caps = load_cached_capabilities(store, name)
        if caps is None:
            return
        narrow_light_discovery(config, caps)

    return _enrich
