"""Entry point for wiz2mqtt."""

from __future__ import annotations

import time
from typing import Annotated, cast

import cosalette
from cosalette import DeviceStore, EntityNotifier, Optional
from cosalette.mqtt import Payload

from wiz2mqtt import __version__, intent, power
from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.adapters.wizlight import WizBulbAdapter
from wiz2mqtt.commands import to_set_state_kwargs
from wiz2mqtt.discovery import cache_capabilities, make_discovery_enrich
from wiz2mqtt.entity import bulb_entity_tick
from wiz2mqtt.errors import WizBridgeError, error_type_map
from wiz2mqtt.models import BulbSetCommand, BulbStateModel, PowerSourceStateModel
from wiz2mqtt.ports import WizBulbPort
from wiz2mqtt.settings import BulbConfig, PowerSourceConfig, Wiz2MqttSettings
from wiz2mqtt.state import SharedState

_TICK_INTERVAL_SECONDS = 60.0
"""Per-bulb heartbeat cadence — the *floor* on publication, not the driver.

State-changing callback pushes reach MQTT immediately (see
``triggerable="local"`` on ``bulb_entity`` below). Suppressed syncPilot
heartbeat packets refresh pywizlight's ``last_push`` clock but do not invoke
that callback or publish state. This interval therefore only guarantees a
periodic re-read for bulbs whose heartbeat traffic has gone quiet. A WiZ bulb
pushes on *change* only, so silence is ambiguous —
"nothing happened" and "the push subscription died" look identical from
here.

Deliberately equal to ``WizBulbAdapter._DEFAULT_PUSH_STALENESS_THRESHOLD``
(``adapters/wizlight.py``): a tick that finds ``bulb.last_push`` older than
that threshold does a real ``updateState()`` poll, so it is a liveness
probe for a bulb that has gone genuinely silent. It is not a probe on a
bulb still sending heartbeats the host can hear — that traffic already
proves liveness, and ``get_state`` skips the poll (cap-dc5y). Changing one
without the other either wastes ticks on a cache that cannot have gone
stale, or lets stale cache entries publish unchallenged. Hardware
verification confirms this fallback in the app ADRs.
"""

app = cosalette.App(
    name="wiz2mqtt",
    version=__version__,
    description="WiZ smart bulb control over MQTT for openHAB and Home Assistant",
    settings_class=Wiz2MqttSettings,
    adapters={WizBulbPort: (WizBulbAdapter, FakeWizBulbAdapter)},
    error_type_map=error_type_map,
)

# cosalette ADR-004 / ADR-059: publish retained Home Assistant MQTT discovery
# `config` payloads on the first successful MQTT connect, built from the app's
# own live, already-expanded registry — so the per-bulb `bulb_entity` names (a
# callable `NameSpec` keyed off `settings.bulbs`) resolve correctly without a
# representative config profile. The entities come from `BulbStateModel` /
# `BulbSetCommand`'s `ha_entities` + `consumer()` metadata (see models.py).
# openHAB has no runtime equivalent; `cosalette schema openhab` (docs/schema.yaml)
# stays the offline path for its Generic MQTT Thing.
#
# The enrich hook narrows each bulb's advertised `light`
# metadata from its DeviceStore-cached capabilities. The cache is populated after
# first contact, so discovery is per-bulb accurate from the *next* connect on;
# the offline `cosalette schema ha-discovery` path keeps the static superset.
app.discovery(enrich=make_discovery_enrich(app))


def _bulb_map(settings: cosalette.Settings) -> dict[str, BulbConfig]:
    """Map configured bulbs to per-bulb command/telemetry registrations."""
    if not isinstance(settings, Wiz2MqttSettings):
        raise TypeError(f"Expected Wiz2MqttSettings, got {type(settings).__name__}")
    return {bulb.name: bulb for bulb in settings.bulbs}


def _power_source_map(settings: cosalette.Settings) -> dict[str, PowerSourceConfig]:
    """Map configured power sources to one telemetry registration each."""
    if not isinstance(settings, Wiz2MqttSettings):
        raise TypeError(f"Expected Wiz2MqttSettings, got {type(settings).__name__}")
    return {source.name: source for source in settings.power_sources}


@app.command(
    name=_bulb_map,
    summary="Apply a partial state update to a bulb",
    payload_model=BulbSetCommand,
    # No explicit timeout=: one set_state issues a single pywizlight call
    # already bounded internally (TIMEOUT=13 s, 6 datagrams), and each bulb
    # is its own entity over connectionless UDP — no shared lock, no queuing
    # behind a slow peer. Worst case ~13 s, comfortably inside cosalette's
    # 30 s backstop; a UDP set is idempotent, so a cancel leaves nothing
    # half-written.
)
async def bulb_set(
    cmd: Annotated[BulbSetCommand, Payload()],
    config: BulbConfig,
    port: WizBulbPort,
    state: SharedState,
    ctx: cosalette.DeviceContext,
    notify: EntityNotifier,
    store: Annotated[DeviceStore | None, Optional()] = None,
) -> None:
    """Handle ``wiz2mqtt/{bulb}/set``: partial update, every field optional.

    Mutual exclusion between ``color``/``color_temp``/``effect`` is
    enforced by ``BulbSetCommand``'s own validator, so a conflicting
    payload never reaches this body — the framework rejects it and
    publishes to the bulb's error topic before the handler runs.

    ADR-008/cap-bjw9.6: the desired state is written before any wire
    attempt, so an unreachable bulb still records the intent. A bulb whose
    power source is known off, or that has already crossed the failure
    threshold, is not sent to the wire at all — the command is queued
    instead and the entity is armed to republish the (now updated) desired
    state immediately, without an error. A bulb believed reachable that
    still times out on the wire is queued too, then the timeout still
    surfaces on the error topic as before.
    """
    settings = cast(Wiz2MqttSettings, ctx.settings)
    kwargs = to_set_state_kwargs(cmd)
    now = time.time()
    intent.record_command(state, store, config.name, kwargs, now)

    belief = power.belief_for_bulb(settings, state, config.name)
    unreachable = (
        belief == "off" or state.last_availability.get(config.name) == "offline"
    )
    if unreachable:
        intent.enqueue(state.pending_commands, config.name, kwargs, now)
        notify(config.name)
        return

    try:
        await port.set_state(config.ip, **kwargs)
    except WizBridgeError:
        intent.enqueue(state.pending_commands, config.name, kwargs, now)
        raise


@app.state
def shared_state() -> SharedState:
    """State factory for per-bulb availability/publish debounce."""
    return SharedState()


@app.telemetry(
    name=_bulb_map,
    # bulb_entity_tick deliberately debounces reachability over three failures.
    unavailable_on=None,
    interval=_TICK_INTERVAL_SECONDS,
    # cosalette ADR-064: "local" subscribes no MQTT trigger topic — the only
    # arming path is WizBulbAdapter's push callback calling EntityNotifier.
    # A push therefore publishes through this same handler, with the same
    # OnChange() gating and availability debounce a scheduled tick gets.
    triggerable="local",
    # No min_interval=: OnChange() coalesces burst traffic to the latest state;
    # a throttle would only add latency.
    publish=cosalette.OnChange(),
    summary="Per-bulb state publisher: retained state, availability debounce",
    # state_model validates every publish (cosalette 0.9.0) and types the
    # AsyncAPI `/state` channel so `cosalette schema` can derive HA discovery
    # + openHAB metadata. Every field is Optional and validation dumps with
    # `exclude_none=True`, so `build_state_payload`'s conditional-key wire
    # shape is preserved — absent keys stay omitted, not null-filled.
    state_model=BulbStateModel,
)
async def bulb_entity(
    ctx: cosalette.DeviceContext,
    config: BulbConfig,
    port: WizBulbPort,
    state: SharedState,
    notify: EntityNotifier,
    # Optional() keeps the handler usable when persistence is opted out
    # (store=None); under the default store the framework injects a per-bulb
    # DeviceStore keyed by the bulb name.
    store: Annotated[DeviceStore | None, Optional()] = None,
) -> BulbStateModel | None:
    """Per-configured-bulb telemetry: publish state, debounce availability.

    One instance is registered per ``settings.bulbs`` entry (dict-name
    ``NameSpec``, reusing ``_bulb_map`` — telemetry and command names may
    coexist, unlike device/command). See
    :func:`wiz2mqtt.entity.bulb_entity_tick` for the tick logic.

    Runs on two wakes, indistinguishably: the ``interval=`` heartbeat and
    a local trigger armed by the adapter's push callback.  The tick reads
    the adapter's push cache either way, so no branch on the wake reason
    is needed here.

    The tick builds a conditional-key dict (see
    :func:`wiz2mqtt.payload.build_state_payload`); wrapping it in
    ``BulbStateModel`` keeps the return annotation and ``state_model=``
    in agreement (repo idiom — airthings2mqtt / gas2mqtt) so registration
    emits no ``state_model`` drift warning.
    """
    result = await bulb_entity_tick(ctx, config, port, state, store, notify)
    # Cache detected capabilities for the discovery enrich hook. This is best
    # effort and a no-op until the bulb has been reached.
    if store is not None:
        await cache_capabilities(store, config, port)
    return BulbStateModel.model_validate(result) if result is not None else None


@app.telemetry(
    name=_power_source_map,
    interval=_TICK_INTERVAL_SECONDS,
    # Armed by bulb_entity_tick (any member bulb's answer/failure/boot
    # changes the belief) and by bulb_set (a queued command). No live
    # signal_topic input yet — cap-bjw9.11.
    triggerable="local",
    publish=cosalette.OnChange(),
    # Home Assistant discovery for this entity is cap-bjw9.10, not this
    # task — the payload publishes, but nothing announces it yet.
    discoverable=False,
    summary="Per-source power belief publisher",
    state_model=PowerSourceStateModel,
)
async def power_source_entity(
    ctx: cosalette.DeviceContext, config: PowerSourceConfig, state: SharedState
) -> PowerSourceStateModel:
    """Per-configured-power-source telemetry: publish the belief (ADR-007)."""
    settings = cast(Wiz2MqttSettings, ctx.settings)
    return PowerSourceStateModel.model_validate(
        power.source_payload(settings, config, state)
    )


def main() -> None:
    """CLI entry point."""
    app.run()


if __name__ == "__main__":
    main()
