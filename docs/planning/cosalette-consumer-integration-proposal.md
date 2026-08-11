# Enhancement Proposal: consumer integration overhaul (`_schema/_consumer_gen.py`)

**Status:** proposed — raised upstream, no implementation started
**Raised by:** cosalette-apps, while planning the wiz2mqtt migration (beads epic
`cap-10u`)
**Verified against:** cosalette 0.6.0 (`_schema/_consumer_gen.py`,
`_schema/__init__.py`, `_schema/_loader_helpers.py`, `_schema/_cli.py`,
`_health/_reporter.py`)
**Index:** [wiz2mqtt framework proposals](wiz2mqtt-framework-proposals.md)

## Context

`cosalette schema ha-discovery` and `cosalette schema openhab` turn an AsyncAPI
document into Home Assistant MQTT discovery payloads and openHAB
`.things`/`.items` files. Both read the same `x-cosalette-consumer` annotations
that `cosalette.schema.consumer()` attaches to pydantic fields.

For read-only telemetry — one scalar per field, one direction, one device — they
work. Every app that ships today is that shape.

The next app is not. wiz2mqtt bridges WiZ bulbs: fourteen devices, each with a
state channel and a command channel, carrying booleans, bounded integers,
optionals, an enum and a colour triple. Running the current generators against
that shape produces output that is not merely imperfect but **rejected by both
consumers** — duplicate openHAB Thing UIDs, duplicate Item names, Items bound to
channels that do not exist, HA discovery payloads that overwrite each other on the
broker, and command entities that publish payloads cosalette's own schema
enforcement would reject.

None of it fails loudly. The CLI exits 0 and prints well-formed output. That is
the through-line of every finding below and the reason this belongs in the
framework rather than in a downstream workaround.

### How this document was verified

Every finding was reproduced against an installed cosalette 0.6.0 wheel, not read
off the source. The probe schema is reproduced in full in
[Appendix A](#appendix-a-reproduction-schema); the two commands are:

```bash
cosalette schema ha-discovery probe.yaml
cosalette schema openhab probe.yaml
```

Claims from the originating issue that did not reproduce, or reproduced with a
different mechanism than claimed, are marked as such. The verdict column in the
[summary table](#summary) distinguishes **confirmed**, **corrected** and **newly
found**.

---

## Part 1 — Entity identity

The generators build identifiers from `(app, device, property)`. Direction is not
part of the tuple, and `device` is extracted incorrectly. Everything in this part
follows from those two facts.

### Finding 1 — openHAB Thing blocks are emitted per channel, keyed per device

`generate_things()` (`_consumer_gen.py:360-368`) loops over channels and calls
`_thing_block()` once per channel, but `_openhab_thing_uid()`
(`_consumer_gen.py:278-280`) keys the UID on `(app, device)` only:

```python
def _openhab_thing_uid(broker_uid: str, app: str, device: str) -> str:
    """Build a Thing UID: ``mqtt:topic:<broker>:<app>_<device>``."""
    return f"mqtt:topic:{broker_uid}:{_slugify(app)}_{_slugify(device)}"
```

A device with a state channel and a command channel therefore yields two Thing
blocks carrying the **same UID**. Verified output for a single bulb with
`wiz2mqtt/desk/state` and `wiz2mqtt/desk/set`:

```java
Thing mqtt:topic:broker:wiz2mqtt_desk "wiz2mqtt desk" (mqtt:broker:broker) {
    Channels:
        Type number : brightness_cmd "Brightness" [ commandTopic="wiz2mqtt/desk/set", ... ]
        ...
}

Thing mqtt:topic:broker:wiz2mqtt_desk "wiz2mqtt desk" (mqtt:broker:broker) {
    Channels:
        Type number : brightness "Brightness" [ stateTopic="wiz2mqtt/desk/state", ... ]
        ...
}
```

openHAB's DSL parser does not merge these. Fourteen bulbs produce twenty-eight
Thing blocks for fourteen UIDs.

**Fix:** group channels by resolved device before emitting, and emit one Thing per
device containing the union of its channels. This is a precondition for Findings 2
and 3 — they cannot be fixed while a Thing is a per-channel artifact.

### Finding 2 — Items link to `:<prop>`, but receive channels are named `<prop>_cmd`

`_openhab_channel_uid()` (`_consumer_gen.py:283-286`) appends the bare slugified
property name:

```python
def _openhab_channel_uid(broker_uid: str, app: str, device: str, prop_name: str) -> str:
    thing = _openhab_thing_uid(broker_uid, app, device)
    return f"{thing}:{_slugify(prop_name)}"
```

`_thing_block()` names the receive-direction channel `<prop>_cmd`
(`_consumer_gen.py:424-431`). The two never agree. There are two distinct failure
modes, and the second is worse than the issue that raised this originally
described:

1. **Property exists only on the command channel** — the link is dangling.
   Verified: `String Wiz2Mqtt_Desk_Scene ... { channel="mqtt:topic:broker:wiz2mqtt_desk:scene" }`
   while the only generated channel is `scene_cmd`. openHAB logs a link error.
2. **Property exists on both channels** — the link resolves, to the **state**
   channel. Verified for `brightness`, `state`, `hsb`, `color_temp_kelvin`. The
   Item shows the right value and silently discards every command. No error is
   logged anywhere.

Case 2 is the one that will cost a user an afternoon.

**Fix:** derive both sides from one function. Once Finding 3 gives Items a
direction-aware identity, a command Item links to `<prop>_cmd` and a state Item to
`<prop>`, and the two names come from the same helper.

### Finding 3 — Item IDs carry no direction, producing duplicate definitions

`_openhab_item_id()` (`_consumer_gen.py:289-292`) takes `(app, device, prop_name)`.
Verified `.items` output for the single-bulb probe:

```java
Number  Wiz2Mqtt_Desk_Brightness  "Brightness [%s]"  (gWiz2Mqtt)  { channel="...:brightness" }
String  Wiz2Mqtt_Desk_ColorTempKelvin  "Colour Temperature [%s K]"  (gWiz2Mqtt)  { ... }
Color   Wiz2Mqtt_Desk_Hsb  "HSB [%s]"  (gWiz2Mqtt)  { ... }
Switch  Wiz2Mqtt_Desk_State  "Desk Lamp [%s]"  (gWiz2Mqtt)  { ... }
Number  Wiz2Mqtt_Desk_Brightness  "Brightness [%s]"  (gWiz2Mqtt)  { channel="...:brightness" }
String  Wiz2Mqtt_Desk_ColorTempKelvin  "Colour Temperature [%s K]"  (gWiz2Mqtt)  { ... }
Color   Wiz2Mqtt_Desk_Hsb  "HSB [%s]"  (gWiz2Mqtt)  { ... }
Switch  Wiz2Mqtt_Desk_State  "Desk Lamp [%s]"  (gWiz2Mqtt)  { ... }
```

Four Items defined twice in one file. openHAB rejects duplicate Item names on
load.

**Correction to the original report:** the duplicates were described as having
"conflicting types". In the common case they are same-typed, as above, which is
still a load error. Conflicting types arise only when the two channels' payload
models differ for the same field name (for instance `int` on the command side and
`int | None` on the state side, which Finding 6 downgrades to `String`) — real, but
the secondary case.

**Fix:** make direction part of the Item identity, e.g. `Wiz2Mqtt_Desk_Brightness`
and `Wiz2Mqtt_Desk_Brightness_Cmd`.

### Finding 4 — HA `object_id`, `unique_id` and discovery topic are all direction-blind

`_build_payload()` (`_consumer_gen.py:213-217`):

```python
object_id = _slugify(f"{device_name}_{prop.name}")
node_id = _slugify(app)
unique_id = f"cosalette_{_slugify(app)}_{object_id}"

topic = f"{self.discovery_prefix}/{component}/{node_id}/{object_id}/config"
```

Only `component` distinguishes a state entity from a command entity, and only when
the inferred component happens to differ. Verified against the probe (12 payloads
in one run):

```
total payloads: 12
distinct topics: 10
DUP x2 homeassistant/sensor/wiz2mqtt/desk_color_temp_kelvin/config
DUP x2 homeassistant/sensor/wiz2mqtt/desk_hsb/config

unique_id collisions:
DUP x2 cosalette_wiz2mqtt_desk_brightness
DUP x2 cosalette_wiz2mqtt_desk_color_temp_kelvin
DUP x2 cosalette_wiz2mqtt_desk_hsb
DUP x2 cosalette_wiz2mqtt_desk_state
```

The two `homeassistant/sensor/wiz2mqtt/desk_color_temp_kelvin/config` payloads are
not merely similar; they are the same retained topic. Publishing this list in order
means the command payload is overwritten by the state payload and the command entity
ceases to exist — a silent, order-dependent loss of half the entity set.

**Fix:** direction (or, better, the channel identity) belongs in `object_id` and
`unique_id`. The topic follows.

### Finding 5 — device extraction hardcodes `parts[1]`, ignoring routers, sub-entities and nested devices

The originating issue described this as "router identity taken from the payload
field rather than the topic segment". **Corrected:** nothing reads a payload field.
The actual defect is that `_consumer_gen` carries its own device extractor
(`_consumer_gen.py:95-100`):

```python
def _device_name_from_address(address: str) -> str:
    """Extract device segment from ``app/device/suffix`` address."""
    parts = address.split("/")
    if len(parts) >= 2:
        return parts[1]
    return parts[0]
```

`parts[1]` is correct only for a flat three-segment address. It is wrong for every
address cosalette itself generates with more structure:

| Feature      | Topic shape                        | Correct device     | `parts[1]` yields |
| ------------ | ---------------------------------- | ------------------ | ----------------- |
| Router       | `{app}/{router}/{device}/state`    | `{router}/{device}`| `{router}`        |
| Sub-entity   | `{app}/{device}/{sub}/state`       | `{device}/{sub}`   | `{device}`        |
| Nested       | `{app}/{room}/{device}/state`      | `{room}/{device}`  | `{room}`          |

Verified: `wiz2mqtt/livingroom/ceiling/state` produced
`Thing mqtt:topic:broker:wiz2mqtt_livingroom` and HA `object_id: livingroom_brightness`.
Every device under one router prefix collapses into a single Thing and a single
`object_id` namespace, at which point Findings 3 and 4 apply between *different
devices*.

What makes this a clean fix: **the correct implementation already exists twenty
lines away**, in `_schema/__init__.py:299-315`:

```python
def _device_name_from_archetype(channel: ChannelSchema) -> str | None:
    parts = channel.address.split("/")
    if len(parts) == 3:
        return parts[1]                    # app/device/suffix  →  "device"
    if len(parts) > 3:
        return "/".join(parts[1:-1])       # app/device/sub/suffix  →  "device/sub"
    return None
```

`_extract_device_names()` uses it; the consumer generators do not. Two extractors
for one concept, and the generators picked the wrong one.

**Fix:** delete `_device_name_from_address` and route both generators through the
shared extractor, honouring `{deviceName}` template parameters via
`_device_name_from_template()` as well. Note that a device name containing `/`
needs slugifying before it reaches `_openhab_item_id()`, which currently
title-cases its input and would emit an illegal Item name.

---

## Part 2 — Type inference

### Finding 6 — `anyOf: [T, null]` has no top-level `type`, so every optional field degrades

Both generators read the type with `prop.json_schema.get("type", "string")`
(`_consumer_gen.py:87`, `:261`, `:297`). Pydantic emits optionals as a composition
with no top-level `type` — verified against the installed pydantic:

```python
class M(pydantic.BaseModel):
    kelvin: int | None = None
```

```json
"kelvin": { "anyOf": [ { "type": "integer" }, { "type": "null" } ], "default": null }
```

The `.get(..., "string")` default therefore fires for **every optional field in
every cosalette app**. Verified consequence, comparing two command fields that
differ only by optionality:

| Field                          | Python type  | Generated topic                                            |
| ------------------------------ | ------------ | ---------------------------------------------------------- |
| `brightness`                   | `int`        | `homeassistant/number/wiz2mqtt/desk_brightness/config`      |
| `color_temp_kelvin`            | `int \| None`| `homeassistant/sensor/wiz2mqtt/desk_color_temp_kelvin/config` |

A writable number silently becomes a read-only sensor. On the openHAB side the
same field becomes `Type string` / `String` instead of `number` / `Number`.

**Fix:** resolve the effective type before lookup — unwrap `anyOf`/`oneOf` by
discarding `null` variants and taking the remaining type when exactly one remains.
`_collect_properties()` already establishes the precedent of walking composition
keywords.

### Finding 7 — `array` is in no lookup table and `items` is never inspected

`_HA_COMPONENT_MAP` (`_consumer_gen.py:30-42`), `_OPENHAB_TYPE_MAP`
(`:242-249`), `_openhab_item_type()` (`:252-264`) and `_openhab_channel_type()`
(`:295-300`) between them handle `number`, `integer`, `boolean` and `string`.
`array` falls through to `sensor` / `String` / `string`, and the `items` subschema
is never read.

Verified: `rgb: list[int]` produced
`homeassistant/sensor/wiz2mqtt/desk_rgb/config` with
`"value_template": "{{ value_json.rgb }}"`, which renders the Python repr
`[255, 0, 0]` into HA as a string.

**Fix:** at minimum recognise `array` and emit a `value_template` that joins the
elements (`{{ value_json.rgb | join(',') }}`), which is what both HA's
`rgb_state_topic` and openHAB's `color` channel expect. See Finding 21 for the
general mechanism.

### Finding 8 — openHAB switch channels get no `on=` / `off=`, so boolean items stay `UNDEF`

`_thing_block()` (`_consumer_gen.py:417-431`) emits only `stateTopic` /
`commandTopic` and `transformationPattern`. Verified:

```java
Type switch : state "Desk Lamp" [
    stateTopic="wiz2mqtt/desk/state",
    transformationPattern="JSONPATH:$.state"
]
```

The JSONPATH extracts `true` / `false`; the openHAB MQTT switch channel defaults to
`ON` / `OFF`; nothing matches and the Item never leaves `UNDEF`. The channel needs
`on="true", off="false"`.

**Fix:** covered by Finding 21 — this is one instance of "channel parameters cannot
be expressed".

### Finding 9 — openHAB *item* type is overridable, *channel* type is not

`_openhab_item_type()` (`_consumer_gen.py:252-264`) honours
`x-cosalette-openhab.item_type`. `_openhab_channel_type()` (`:295-300`) does not
— it reads `json_schema` and nothing else:

```python
def _openhab_channel_type(prop: PropertySchema) -> str:
    json_type = prop.json_schema.get("type", "string")
    return {"number": "number", "integer": "number", "boolean": "switch"}.get(
        json_type, "string"
    )
```

Verified with `item_type: Color` on an `hsb` array field — the generator produced a
`Color` Item bound to a `string` channel:

```java
Type string : hsb "HSB" [ stateTopic="wiz2mqtt/desk/state", transformationPattern="JSONPATH:$.hsb" ]
Color  Wiz2Mqtt_Desk_Hsb  "HSB [%s]"  (gWiz2Mqtt)  { channel="mqtt:topic:broker:wiz2mqtt_desk:hsb" }
```

This is exactly wiz2mqtt's driving requirement, and the one override the framework
already offers is the half that does not help.

**Fix:** Finding 21.

### Finding 10 — the HA `component` override redirects the topic and emits none of the component's keys

`_infer_component()` (`_consumer_gen.py:78-92`) returns
`x-cosalette-ha-discovery.component` verbatim, which changes the discovery topic at
`:217`. `_build_payload()` (`:201-234`) then emits the same six keys regardless.
Verified with `component: light`:

```json
{
  "topic": "homeassistant/light/wiz2mqtt/bedside_state/config",
  "config": {
    "name": "Bedside Lamp",
    "unique_id": "cosalette_wiz2mqtt_bedside_state",
    "object_id": "bedside_state",
    "state_topic": "wiz2mqtt/bedside/state",
    "value_template": "{{ value_json.state }}",
    "device": { "identifiers": ["cosalette_wiz2mqtt"], "name": "wiz2mqtt", "manufacturer": "cosalette" }
  }
}
```

HA's MQTT light platform requires `command_topic`; `value_template` is not one of
its keys (the light platform uses `state_value_template`). The config is rejected
outright. The override moves the payload to the right topic and guarantees it will
be thrown away.

**Fix:** the component override must select a *payload builder*, not just a topic
segment. See [The overhaul](#the-overhaul).

---

## Part 3 — Neither generator can write a JSON envelope

This part is **newly found**. It is, for wiz2mqtt, the single most consequential
gap, and it did not appear in the originating issue.

### Finding 11 — HA command entities publish a bare scalar to a channel that expects JSON

`_apply_topics_and_templates()` (`_consumer_gen.py:111-135`) sets `command_topic`
for receive-direction channels but only sets `command_template` when the author
supplied one:

```python
if channel.direction in ("receive", "both"):
    config["command_topic"] = channel.address
...
if ha and ha.command_template and "command_topic" in config:
    config["command_template"] = ha.command_template
```

Verified — every generated command entity, with no `command_template`:

```json
{ "topic": "homeassistant/number/wiz2mqtt/desk_brightness/config",
  "config": { "name": "Brightness", "command_topic": "wiz2mqtt/desk/set", ... } }
```

Without a template HA publishes the raw value, so moving the HA slider publishes
`128` to `wiz2mqtt/desk/set`. cosalette's own typed handler contract expects
`{"brightness": 128}` and will raise `PayloadValidationError`; with
`x-cosalette-enforcement.on_publish` the framework rejects it explicitly.

The generator reads a JSON envelope perfectly well — `value_template` is derived
from the property name at `:126-131`. It simply never learned to write one, even
though the information required is identical.

**Fix:** default `command_template` to `{"<prop>": {{ value }}}` (JSON-quoted for
string-typed properties), by symmetry with the auto-derived `value_template`.
Composite entities (Finding 20) need the multi-key form.

### Finding 12 — openHAB command channels apply an inbound-only transform outbound

`_thing_block()` (`_consumer_gen.py:424-431`) emits the same
`transformationPattern` for the receive branch as for the send branch:

```java
Type number : brightness_cmd "Brightness" [
    commandTopic="wiz2mqtt/desk/set",
    transformationPattern="JSONPATH:$.brightness"
]
```

In the openHAB MQTT binding `transformationPattern` applies to *incoming* state;
outgoing values need `transformationPatternOut` or `formatBeforePublish`. And
JSONPATH is an extraction language — it cannot construct `{"brightness": 128}` in
either direction. The generated channel publishes the bare value, exactly as in
Finding 11, plus a transform that is inert.

**Fix:** emit `formatBeforePublish="{\"brightness\":%s}"` on command channels (or
`transformationPatternOut` for the composite case) and drop the inbound-only
`transformationPattern` from them.

Findings 11 and 12 are one root cause on two surfaces: **the generators model a
channel as a bag of independent scalars, but cosalette's wire format is a single
JSON object per channel.** Any fix that addresses one and not the other leaves half
the apps broken.

---

## Part 4 — Information the schema already carries and the generators discard

### Finding 13 — `_CONSUMER_FIELD_MAP` whitelists four keys with no passthrough

`_consumer_gen.py:139-144`:

```python
_CONSUMER_FIELD_MAP: dict[str, str] = {
    "device_class": "device_class",
    "unit": "unit_of_measurement",
    "state_class": "state_class",
    "icon": "icon",
}
```

`_apply_consumer_fields()` (`:147-159`) copies those four plus `expire_after`.
There is no escape hatch. Home Assistant MQTT discovery has on the order of a
hundred platform keys; four are reachable. Concretely, none of the keys wiz2mqtt
needs can be expressed at all: `schema: json`, `supported_color_modes`,
`brightness`, `color_temp_kelvin`, `min_kelvin`, `max_kelvin`, `effect`,
`effect_list`, `optimistic`, `retain`.

The whitelist is also the reason Finding 10 cannot be worked around downstream:
an author who sets `component: light` has no way to supply the keys a light needs.

**Fix:** keep the curated, typo-checked keys as the ergonomic front door, and add
an explicit passthrough (`extra: {...}` under `x-cosalette-ha-discovery`) merged
last. The lesson from a previous proposal against this framework applies here too —
an allowlist cannot anticipate the next consumer key, so unknown keys should be
author property by default.

### Finding 14 — JSON Schema constraints survive parsing and are then ignored

`_build_property_schema()` (`_loader_helpers.py:184-186`) deliberately preserves
everything that is not a cosalette extension:

```python
clean_schema = {
    k: v for k, v in prop_schema.items() if not k.startswith("x-cosalette-")
}
```

So `minimum`, `maximum`, `multipleOf`, `enum` and `maxLength` are all sitting in
`prop.json_schema`. Nothing in `_consumer_gen.py` reads any of them except `enum`,
and only for its presence (`:89`). Verified: `Field(ge=0, le=255)` produces
`"minimum": 0, "maximum": 255` in the schema, and the generated HA `number` entity
carries neither — it is the payload shown in Finding 11, because `_build_payload()`
emits the same six keys whatever the constraint set says.

HA's MQTT number platform defaults to `min: 1`, `max: 100`, `step: 1`. A 0–255
brightness control is therefore clamped to 1–100 and cannot express its own
range — from a schema that states the range explicitly. The openHAB `number`
channel likewise supports `min` / `max` / `step` and gets none.

**Fix:** map `minimum`/`maximum`/`multipleOf` to `min`/`max`/`step` on both sides.
Zero new annotation surface; the data is already there.

### Finding 15 — `select` entities are emitted without `options`

`_infer_component()` (`_consumer_gen.py:89-90`) promotes a command-side string with
an `enum` to `select`:

```python
if archetype == "command" and json_type == "string" and "enum" in prop.json_schema:
    return "select"
```

`_build_payload()` never emits `options`. Verified:

```json
{ "topic": "homeassistant/select/wiz2mqtt/desk_scene/config",
  "config": { "name": "Scene", "unique_id": "...", "object_id": "desk_scene",
              "command_topic": "wiz2mqtt/desk/set" } }
```

`options` is required by HA's MQTT select platform. Every `select` this generator
has ever produced is an invalid config. This is the only branch in
`_infer_component()` that inspects the JSON Schema beyond its type, and it inspects
it only to reach a component it cannot then populate.

**Fix:** emit `options` from `enum`. Same one-line source as Finding 14.

### Finding 16 — nested and `$ref`-ed properties are inert

`_collect_properties()` (`_loader_helpers.py:205-241`) merges `properties` across
`oneOf` / `anyOf` / `allOf`. It never descends into an array's `items`, never
descends into a property's own `properties`, and never resolves `$ref`.

Verified in a shipped app: `caldates2mqtt` annotates
`components.schemas.CalendarEvent.title` and `.date` with `x-cosalette-consumer`,
reached from a top-level `events` property of `type: array` whose `items` is a
`$ref`. `cosalette schema ha-discovery docs/schema.yaml` returns `[]`. The
annotations are syntactically valid, typo-checked by `ConsumerMeta`, and have no
effect.

This was noted in passing in the PR that fixed the velux2mqtt phantom entity
(below) and is confirmed here.

**Fix:** resolve `$ref` against `components.schemas` and descend one level into
object properties and array items, with the flattened name (`events[].title`)
available to the templating in Finding 20.

### Finding 17 — `read_only` is parsed, typo-checked, documented, and ignored

`read_only` is a first-class field of `ConsumerMetadata` (`_schema/__init__.py:53`),
a key of the `ConsumerMeta` TypedDict that gives `consumer()` its static checking
(`:73`), parsed by `_build_consumer_metadata()` (`_loader_helpers.py:144`), and
listed in `cosalette ai help consumer`. `grep -rn read_only` finds no reference in
`_consumer_gen.py`.

Verified — a boolean command field annotated `read_only: true` still becomes a
writable switch:

```json
{ "topic": "homeassistant/switch/probe2/dev_locked/config",
  "config": { "name": "Locked", "command_topic": "probe2/dev/set", ... } }
```

**Fix:** honour it — force the read-only component (`binary_sensor` / `sensor`) and
drop `command_topic`; on openHAB, skip the `_cmd` channel. Or remove the key. The
current state is worse than either, because the static checker actively confirms
the author spelled it right.

---

## Part 5 — Availability

### Finding 18 — discovery emits no availability keys, though the runtime publishes them

Grepping the whole installed package for `availability_topic`, `payload_available`,
`payload_not_available` and `availability_mode` returns **zero** occurrences.
Verified across every real app's generated payloads — for instance velux2mqtt's:

```json
{ "name": "Cover Position", "unique_id": "cosalette_velux2mqtt_blind_position",
  "object_id": "blind_position", "state_topic": "velux2mqtt/blind/state",
  "value_template": "{{ value_json.position }}", "unit_of_measurement": "%",
  "state_class": "measurement", "device": { ... } }
```

Meanwhile the framework maintains exactly the topic HA wants.
`_health/_reporter.py:203-210`:

```python
def _availability_topic(self, device: str) -> str:
    if device in self._root_devices:
        return f"{self.topic_prefix}/availability"
    return f"{self.topic_prefix}/{device}/availability"
```

published retained at QoS 1 with `"online"` / `"offline"`, driven by
`unavailable_on=`, `ctx.mark_unavailable()`, the LWT, and reconnect
re-announcement. The values already match HA's `payload_available` /
`payload_not_available` defaults. HA entities generated by cosalette nevertheless
never go unavailable: a bridge whose device has been offline for a week shows its
last retained reading as current.

Note that the availability topic is a runtime convention, not an AsyncAPI channel —
none of the shipped schemas contain one. The generator must derive it from the same
ADR-012 rule the reporter uses, which is another argument for the shared device
extractor in Finding 5.

**Fix:** emit `availability_topic` (device-scoped, falling back to the app root),
`payload_available`, `payload_not_available`, and `availability_mode: all` when
both device and app-level topics apply.

### Finding 19 — one HA device per app, so physical devices are not modelled

`_build_payload()` (`_consumer_gen.py:228-232`):

```python
config["device"] = {
    "identifiers": [f"cosalette_{_slugify(app)}"],
    "name": app,
    "manufacturer": "cosalette",
}
```

Verified across the whole probe: all twelve entities, spanning four distinct
bulbs, carry `identifiers: ["cosalette_wiz2mqtt"]`. Fourteen physical bulbs become
one HA device with a flat list of entities.

Two knock-on effects, both verified:

- HA prefixes entity names with the device name, so velux2mqtt's real output ships
  two entities both displayed as *velux2mqtt Cover Position* — one for the blind,
  one for the window, indistinguishable in the UI.
- Per-device availability (Finding 18) has nowhere to attach, because HA's
  device-level availability follows the device block.

`SchemaRegistry` already carries `app_version` (`_schema/__init__.py:197`) and
`device_names`, so the ingredients for a proper per-device block exist.

**Fix:** emit one device per resolved device, `identifiers:
[cosalette_<app>_<device>]`, `name: <device>`, `via_device: cosalette_<app>`, with
a bridge device for the app itself. Add the `origin` block
(`{name: <app>, sw_version: <app_version>}`) while touching this code — it is free
and HA surfaces it in diagnostics.

---

## Part 6 — Extensibility and delivery

### Finding 20 — one property, one entity, with no composite mapping

`_payloads_for_channel()` (`_consumer_gen.py:190-199`) iterates properties and
emits one payload each. There is no way to say "these five JSON fields are one
entity".

This is what blocks every rich consumer entity, not just wiz2mqtt's. An HA MQTT
`light` with `schema: json` is one entity over `state`, `brightness`, `color_temp`
and `color`. A `climate` entity is one entity over half a dozen fields. A `cover`
with position is two. All of them are currently expressible only as a scatter of
sensors.

**Fix:** allow a channel-level annotation that names an entity and maps consumer
keys to properties, e.g.

```yaml
x-cosalette-ha-discovery:
  entities:
    - component: light
      name: Desk Lamp
      schema: json
      brightness: true
      supported_color_modes: [color_temp, hs]
      state_value_template: '{{ value_json.state }}'
```

with the field-level form retained for the simple case.

### Finding 21 — openHAB channel type and channel parameters cannot be annotated

`OpenHabOverrides` (`_schema/__init__.py:143-149`) exposes `item_type`, `label`,
`groups` and `tags`. The channel side — its type and its parameters — is entirely
inferred.

This single gap causes Findings 8, 9 and 14 on the openHAB side. Adding
`channel_type` and a free-form `channel_params` mapping resolves all three at once:

```yaml
x-cosalette-openhab:
  item_type: Color
  channel_type: color
  channel_params: { colorMode: HSB }
```

```yaml
x-cosalette-openhab:
  channel_type: switch
  channel_params: { on: 'true', off: 'false' }
```

```yaml
x-cosalette-openhab:
  channel_type: dimmer
  channel_params: { min: 0, max: 255, step: 1 }
```

That is the openHAB half of wiz2mqtt's requirement — a native `Color` item over the
`hsb` field — expressed in three lines.

### Finding 22 — no typed producer for `x-cosalette-ha-discovery` or `x-cosalette-openhab`

`cosalette.schema` exports `consumer`, `temperature`, `percent`, `ConsumerMeta` and
`X_COSALETTE_CONSUMER`. `consumer()` (`_schema/__init__.py:76-96`) gives authors a
typo-checked keyword surface backed by the `ConsumerMeta` TypedDict, with a
drift-guard test keeping it in parity with the reader.

The two override extensions get none of that. An author wanting `component: light`
or `item_type: Color` hand-writes an untyped dict into `json_schema_extra`, with no
static check, no drift guard, and no discoverability. Given Findings 10, 13 and 21
all expand these two extensions substantially, they need the same treatment before
they grow.

**Fix:** add `ha_discovery(**HaDiscoveryMeta)` and `openhab(**OpenHabMeta)`
producers alongside `consumer()`, sharing the same TypedDict-parity pattern, and a
merge helper so a single field can carry all three.

### Finding 23 — discovery is offline-only, with no runtime publication and no hook

`cosalette schema ha-discovery` (`_schema/_cli.py:380-408`) ends in `typer.echo`.
So does `cosalette schema openhab` (`:411-440`). Nothing in the package publishes
either artifact — grepping for `homeassistant`, `HaDiscoveryGenerator` and
`OpenHabGenerator` outside `_schema/` returns nothing.

Everything downstream follows from that. Because generation happens against a
checked-in YAML file and never against the running app, the two can diverge and
nothing notices. In this repository that divergence has already shipped twice:

**Evidence 1 — velux2mqtt phantom entity.** velux2mqtt registers covers with a
callable `name=` keyed on user configuration. The static pipeline could not see the
per-deployment names and collapsed them into one channel named after the Python
handler's qualname, so `ha-discovery` emitted a payload with
`state_topic: velux2mqtt/cover_device/state` — a topic no runtime publish ever
uses — while the real per-cover topics got no discovery at all. The payload was
well-formed and would have been shipped to HA as-is; it would have appeared as a
permanently unavailable entity. It survived review because the app's discovery test
asserted payload *shape*, which was correct.

**Evidence 2 — the cross-check that had to be invented six times.** The follow-up
work added, to each app independently, a test that runs the real app under its
integration harness and asserts that every generated `state_topic` appears in the
topics actually published:

```python
await run_app_briefly(harness)

published_topics = {topic for topic, *_ in harness.mqtt.published}
for payload in ha_payloads:
    state_topic = payload["config"]["state_topic"]
    assert state_topic in published_topics, (
        f"state_topic {state_topic!r} was never published at "
        f"runtime; published topics: {sorted(published_topics)}"
    )
```

Six of this repository's eight apps now carry a `test_schema_discovery.py`; five of
those carry this runtime cross-check (the sixth asserts zero payloads, for a
separate reason). None of it would exist if the generator ran against the live
registry.

**Evidence 3 — silence when nothing is annotated.** `jeelink2mqtt` and `suncast`
have zero `x-cosalette-consumer` annotations, and `task jeelink2mqtt:schema:ha-discovery`
prints `[]` and exits 0. An app can be fully wired, pass `schema:check`, and ship no
discovery at all without any signal. `caldates2mqtt` prints `[]` too, but for the
entirely different reason in Finding 16 — the CLI cannot distinguish "nothing to
publish" from "your annotations are unreachable".

**Fix, in three parts:**

1. **Publish at runtime.** An opt-in `app.discovery(...)` that publishes retained
   discovery payloads on connect, generated from the live registry after the
   configure/expand lifecycle, and clears them on entity removal (the retained
   cleanup machinery for orphaned `state`/`availability` topics already exists and
   should extend to `config` topics).
2. **Enrichment hook.** A callback receiving `(channel, prop, config)` before
   publication, so an app can add what the schema cannot express — the escape hatch
   that makes the rest survivable while it matures.
3. **Report, don't shrug.** `ha-discovery` should exit non-zero, or at least warn on
   stderr, when a registry has consumer-visible channels but produces no payloads,
   and should say when annotations were found in unreachable positions.

Part 1 also dissolves the velux2mqtt failure class entirely: at runtime the callable
`name=` has already expanded, so the phantom topic cannot be constructed.

---

## The overhaul

The findings collapse into five changes. Ordered by what unblocks what:

**1. Resolve identity once.** One helper produces
`(app, device, channel, direction, property)` for both generators, using the
existing `_device_name_from_archetype` / `_device_name_from_template` logic
(Finding 5). Every downstream ID — HA `object_id`, `unique_id`, discovery topic,
openHAB Thing UID, channel UID, Item ID — derives from that tuple, and the same
helper is used on both the Thing side and the Item side so they cannot disagree
(Findings 1–4). Group channels by device before emitting, so a device is the unit
of output rather than a channel.

**2. Resolve type once.** A `resolve_json_type(prop)` that unwraps
`anyOf`/`oneOf` around `null` (Finding 6), recognises `array` and reads `items`
(Finding 7), and returns the constraint set (`minimum`, `maximum`, `multipleOf`,
`enum`) alongside the type (Findings 14, 15). Both generators consume it. Fill the
`("command", "string")` gap in `_HA_COMPONENT_MAP` with `text`, which currently
falls through to `sensor` — verified: a writable string command yields
`homeassistant/sensor/probe2/dev_label/config` carrying a `command_topic` and no
`state_topic`, invalid on two counts.

**3. Learn to write the envelope.** Default `command_template` on the HA side
(Finding 11) and `formatBeforePublish` on the openHAB side (Finding 12), derived
from the property name exactly as `value_template` already is. Without this,
*every* command entity either generator has ever produced is wrong on the wire.

**4. Make the annotation surface open and typed.** `channel_type` +
`channel_params` for openHAB (Finding 21); an `extra` passthrough for HA
(Finding 13); component-aware payload builders so `component: light` produces a
light (Finding 10); composite entity mapping (Finding 20); `$ref` and nested
resolution (Finding 16); `read_only` honoured (Finding 17); typed producers for all
of it (Finding 22). Filter emitted keys by the target platform while doing so —
verified that a `binary_sensor` currently ships `unit_of_measurement` and
`state_class`, neither of which that platform accepts, because
`_apply_consumer_fields` copies without regard to where the entity landed.

**5. Publish from the live registry.** Runtime discovery with an enrichment hook
and availability keys (Findings 18, 19, 23), replacing offline-only generation as
the primary path. Keep the CLI for inspection and diffing.

Changes 1–3 are corrections with no new annotation surface — they can ship first and
would fix every app currently in production. Changes 4 and 5 are the additive
capability wiz2mqtt needs.

### Worked example: what wiz2mqtt needs to be expressible

One WiZ bulb, one state channel, one command channel. Home Assistant should see a
single `light` entity using the JSON schema; openHAB should see a native `Color`
item over the `hsb` field, which HA ignores. Both from one annotated model:

```python
class BulbState(pydantic.BaseModel):
    state: Annotated[bool, Field(json_schema_extra=consumer(display_name="Desk Lamp"))]
    brightness: Annotated[int, Field(ge=0, le=255, json_schema_extra=consumer(...))]
    color_temp_kelvin: Annotated[int | None, Field(ge=2200, le=6500, ...)]
    hsb: Annotated[
        list[int],
        Field(json_schema_extra=openhab(item_type="Color", channel_type="color",
                                        channel_params={"colorMode": "HSB"})),
    ]
```

Against 0.6.0 this yields: five scattered HA entities of which two collide on the
discovery topic and none is a light; an openHAB `Color` item bound to a `string`
channel; a brightness control clamped to 1–100; the optional colour temperature
downgraded to a read-only sensor; and every command entity publishing a bare
scalar the app rejects.

The requirement is modest — **an extra JSON key that one consumer uses natively and
the other ignores** — and it maps onto Findings 20 and 21 exactly. It is the reason
those two are the headline asks rather than the individually more severe bugs in
Parts 1–3.

---

## Summary

| #   | Finding                                                       | Verdict     | Impact                                                    |
| --- | ------------------------------------------------------------- | ----------- | --------------------------------------------------------- |
| 1   | openHAB Thing emitted per channel, keyed per device            | confirmed   | Duplicate Thing UIDs; 2 blocks per bidirectional device    |
| 2   | Items link `:<prop>`, receive channels named `<prop>_cmd`      | confirmed   | Dangling link, or silent bind to the read-only channel     |
| 3   | Item IDs have no direction component                           | confirmed¹  | Duplicate Item definitions; openHAB rejects the file       |
| 4   | HA `object_id` / `unique_id` / topic direction-blind           | confirmed   | Retained discovery topics overwrite each other            |
| 5   | Device extraction hardcodes `parts[1]`                         | corrected²  | Routers, sub-entities, nested devices all collapse         |
| 6   | `anyOf: [T, null]` has no top-level `type`                     | confirmed   | Every optional field degrades to string/sensor             |
| 7   | `array` unhandled, `items` never inspected                     | confirmed   | Lists render as Python reprs                               |
| 8   | No `on=` / `off=` on openHAB switch channels                   | confirmed   | JSON booleans leave the Item `UNDEF`                       |
| 9   | Channel type has no override path                              | confirmed   | `Color` item bound to a `string` channel                   |
| 10  | HA `component` override emits no component keys                | confirmed   | `component: light` produces a config HA rejects            |
| 11  | No default HA `command_template`                               | newly found | Commands publish bare scalars; app rejects the payload     |
| 12  | openHAB commands use inbound-only `transformationPattern`      | newly found | Same, plus an inert transform                              |
| 13  | `_CONSUMER_FIELD_MAP` whitelists four keys                     | confirmed   | Most HA config unreachable, statically or dynamically      |
| 14  | `minimum` / `maximum` / `multipleOf` discarded                 | newly found | HA `number` clamps 0–255 to its 1–100 default              |
| 15  | `select` emitted without `options`                             | newly found | Every generated `select` is an invalid config              |
| 16  | Nested / `$ref` properties never walked                        | newly found³ | Valid annotations silently produce no entity              |
| 17  | `read_only` parsed, typo-checked, ignored                      | newly found | Read-only fields become writable entities                  |
| 18  | No availability keys at all                                    | confirmed   | HA entities never go unavailable                           |
| 19  | One HA device per app                                          | confirmed   | Physical devices unmodelled; duplicate display names       |
| 20  | One property, one entity — no composite mapping                | confirmed   | `light` / `climate` / `cover` inexpressible                |
| 21  | openHAB channel type and params not annotatable                | confirmed   | Root cause of 8, 9 and openHAB-side 14                     |
| 22  | No typed producer for the two override extensions              | confirmed   | Untyped dicts, no drift guard, no discoverability          |
| 23  | Discovery offline-only, no runtime publication, no hook        | confirmed   | Static output silently diverges from runtime               |

¹ Confirmed, with the "conflicting types" characterisation corrected — the common
case is same-typed duplicates, which openHAB still rejects.
² The defect is real; the mechanism is not what was reported. It is naive `parts[1]`
extraction in a duplicate helper, not a payload field, and the correct
implementation already exists in the same package.
³ Reported in passing in the velux2mqtt fix; verified here against a shipped app.

Findings 11, 12, 14, 15, 16 and 17 were not in the originating report. All six are
cases where the generator produces confidently wrong output rather than incomplete
output, which is why they went unnoticed.

Every claim in the originating report reproduced against 0.6.0; nothing was dropped
as unreproducible. The two that reproduced differently are footnoted above.

## What cosalette-apps is doing

- **No downstream workaround for Findings 1–19.** They are framework defects with
  no local fix that would not amount to reimplementing the generator.
- **wiz2mqtt's migration is gated on Findings 20, 21 and 23.** A gate task blocks
  the app's consumer-integration work until this ships upstream. Until then wiz2mqtt
  will hand-publish its HA discovery payloads, and that hand-written code is the
  reference implementation for what Finding 20 should generate.
- **The runtime cross-check stays.** Even once Finding 23 lands, the test asserting
  that every `state_topic` is really published is cheap and catches a class of error
  no generator change can rule out. It should ideally move into
  `cosalette.testing` as a shared assertion rather than being reimplemented per app.
- **`cap-egy` (jeelink2mqtt annotations) is deliberately not blocked on this.**
  Adding `consumer()` metadata is useful regardless.

**One request on the shape of the fix.** Findings 13 and 21 are both about
extensibility, and both would be defeated by a fix that adds a longer allowlist. The
consumer surfaces of Home Assistant and openHAB change faster than a framework
release cycle, and a curated key set will always trail them. The curated,
typo-checked keys are genuinely valuable as the front door — but there needs to be a
back door beside them that passes arbitrary keys through untouched. Without it, the
next app hits the same wall from a slightly different angle.

---

## Appendix A — reproduction schema

Both probe schemas below reproduce every finding in Parts 1–5 against cosalette
0.6.0 with `cosalette schema ha-discovery <file>` and `cosalette schema openhab
<file>`.

```yaml
asyncapi: 3.0.0
info: { title: wiz2mqtt, version: 0.1.0 }
channels:
  bulbState:
    address: wiz2mqtt/desk/state
    x-cosalette-app: wiz2mqtt
    x-cosalette-archetype: device
    messages:
      message:
        payload:
          type: object
          properties:
            state: { type: boolean, x-cosalette-consumer: { display_name: Desk Lamp } }
            brightness:
              { type: integer, minimum: 0, maximum: 255,
                x-cosalette-consumer: { display_name: Brightness } }
            color_temp_kelvin:
              anyOf: [{ type: integer }, { type: 'null' }]
              x-cosalette-consumer: { display_name: Colour Temperature, unit: K }
            rgb:
              { type: array, items: { type: integer },
                x-cosalette-consumer: { display_name: RGB } }
            hsb:
              type: array
              items: { type: integer }
              x-cosalette-consumer: { display_name: HSB }
              x-cosalette-openhab: { item_type: Color }
  bulbSet:
    address: wiz2mqtt/desk/set
    x-cosalette-app: wiz2mqtt
    x-cosalette-archetype: command
    messages:
      message:
        payload:
          type: object
          properties:
            state: { type: boolean, x-cosalette-consumer: { display_name: Desk Lamp } }
            brightness:
              { type: integer, minimum: 0, maximum: 255,
                x-cosalette-consumer: { display_name: Brightness } }
            color_temp_kelvin:
              anyOf: [{ type: integer }, { type: 'null' }]
              x-cosalette-consumer: { display_name: Colour Temperature, unit: K }
            scene:
              { type: string, enum: [ocean, romance, party],
                x-cosalette-consumer: { display_name: Scene } }
            hsb:
              type: array
              items: { type: integer }
              x-cosalette-consumer: { display_name: HSB }
              x-cosalette-openhab: { item_type: Color }
  bulbLight: # Finding 10 — component override
    address: wiz2mqtt/bedside/state
    x-cosalette-app: wiz2mqtt
    x-cosalette-archetype: device
    messages:
      message:
        payload:
          type: object
          properties:
            state:
              type: boolean
              x-cosalette-consumer: { display_name: Bedside Lamp }
              x-cosalette-ha-discovery: { component: light }
  routedBulb: # Finding 5 — nested / router-prefixed address
    address: wiz2mqtt/livingroom/ceiling/state
    x-cosalette-app: wiz2mqtt
    x-cosalette-archetype: device
    messages:
      message:
        payload:
          type: object
          properties:
            brightness:
              { type: integer, x-cosalette-consumer: { display_name: Ceiling Brightness } }
operations:
  publishBulbState: { action: send, channel: { $ref: '#/channels/bulbState' } }
  receiveBulbSet: { action: receive, channel: { $ref: '#/channels/bulbSet' } }
  publishBulbLight: { action: send, channel: { $ref: '#/channels/bulbLight' } }
  publishRoutedBulb: { action: send, channel: { $ref: '#/channels/routedBulb' } }
```

A second, smaller probe covers Finding 17 (`read_only`), the missing
`("command", "string")` map entry, and cross-platform key copying:

```yaml
asyncapi: 3.0.0
info: { title: probe2, version: 0.1.0 }
channels:
  cmd:
    address: probe2/dev/set
    x-cosalette-app: probe2
    x-cosalette-archetype: command
    messages:
      message:
        payload:
          type: object
          properties:
            label:
              { type: string, x-cosalette-consumer: { display_name: Free Text Label } }
            locked:
              { type: boolean,
                x-cosalette-consumer: { display_name: Locked, read_only: true } }
  tel:
    address: probe2/dev/state
    x-cosalette-app: probe2
    x-cosalette-archetype: telemetry
    messages:
      message:
        payload:
          type: object
          properties:
            motion:
              type: boolean
              x-cosalette-consumer:
                { display_name: Motion, unit: '%', state_class: measurement,
                  device_class: motion }
operations:
  recvCmd: { action: receive, channel: { $ref: '#/channels/cmd' } }
  sendTel: { action: send, channel: { $ref: '#/channels/tel' } }
```

Its full HA output — three entities, all three invalid:

```
homeassistant/sensor/probe2/dev_label/config
    command_topic on a sensor, no state_topic          → overhaul step 2
homeassistant/switch/probe2/dev_locked/config
    writable despite read_only: true                   → Finding 17
homeassistant/binary_sensor/probe2/dev_motion/config
    carries unit_of_measurement and state_class        → overhaul step 4
```
