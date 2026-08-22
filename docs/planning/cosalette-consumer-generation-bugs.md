# Bug Report: two defects in HA/openHAB consumer generation

**Status:** **resolved in cosalette 0.6.3** — see
[Resolution](#resolution-cosalette-063) **Raised by:** cosalette-apps, while evaluating
the 0.6.2 upgrade for an eight-app monorepo **Verified against:** cosalette 0.6.2,
installed wheel — `_schema/_consumer_gen.py`, `_schema/_loader_helpers.py`; resolution
re-verified against 0.6.3 **Related upstream work:**
[#377](https://github.com/ff-fab/cosalette/issues/377) (consumer generation
corrections), [#384](https://github.com/ff-fab/cosalette/pull/384) (nested descent)
**Downstream tracking:** beads `cap-bo0` (Bug 1)

Two independent defects in the consumer generators. Both produce output that the target
consumer rejects or silently ignores, and neither surfaces an error during generation.

| #   | Defect                                                           | Introduced |
| --- | ---------------------------------------------------------------- | ---------- |
| 1   | HA component inference ignores channel direction                 | 0.6.1      |
| 2   | Flattened nested property names leak into templates and Item IDs | 0.6.2      |

Both are high severity. Bug 1 makes Home Assistant reject the affected entity outright.
Bug 2 is worse than it first looks: a single nested annotation renders an entire
generated openHAB `.items` file unparsable, taking every unrelated Item in it down too.

Bug 1 was reported during the 0.6.1 evaluation as "Finding 24" of the consumer
integration proposal and is unchanged in 0.6.2. Bug 2 is new: it is a consequence of
#384 making nested properties reachable for the first time.

---

## Bug 1 — HA component inference ignores channel direction

### Symptom

For a `@app.command` entity, cosalette stamps `x-cosalette-archetype: command` on
**both** the `/set` channel (direction `receive`) and the `/state` channel (direction
`send`). Component inference keys on the archetype alone, so the send-only state channel
resolves to a **writable** component — `number`, `select`, `switch`, `text` — while
topic application correctly emits only a `state_topic` for a send channel.

The result is a `number` or `select` config carrying no `command_topic`. Home Assistant
rejects it: a writable entity with no way to write is not a valid discovery payload. The
`_cmd` object_id/unique_id suffix is keyed the same way, so the state entity is also
mislabelled as a command entity.

### Reproduction

Save as `bug1.yaml` and run `cosalette schema ha-discovery bug1.yaml`:

```yaml
asyncapi: 3.0.0
info: { title: bug1, version: 0.1.0 }
channels:
  displaySet:
    address: bug1/display/set
    x-cosalette-app: bug1
    x-cosalette-archetype: command
    messages:
      message:
        payload:
          type: object
          properties:
            brightness_percent:
              anyOf: [{ type: integer, minimum: 0, maximum: 100 }, { type: 'null' }]
  displayState:
    address: bug1/display/state
    x-cosalette-app: bug1
    x-cosalette-archetype: command
    messages:
      message:
        payload:
          type: object
          properties:
            brightness_percent:
              anyOf: [{ type: integer, minimum: 0, maximum: 100 }, { type: 'null' }]
              x-cosalette-consumer: { display_name: Display Brightness, unit: '%' }
operations:
  receiveDisplaySet: { action: receive, channel: { $ref: '#/channels/displaySet' } }
  publishDisplayState: { action: send, channel: { $ref: '#/channels/displayState' } }
```

Observed on 0.6.2:

```text
homeassistant/number/bug1/display_brightness_percent_cmd/config
   state_topic  : bug1/display/state
   command_topic: None            ← writable component, nothing to write to
```

Expected: a read-only component (`sensor`) on the bare object_id
`display_brightness_percent`, because a `send` channel can only observe.

### Root cause

`_schema/_consumer_gen.py:225` — `_infer_component` takes the archetype but never the
channel:

```python
def _infer_component(
    archetype: str | None,
    prop: PropertySchema,
    ha: HaDiscoveryOverrides | None,
) -> str:
```

`_schema/_consumer_gen.py:662` — the call site has `channel` in scope and discards its
direction:

```python
component = _infer_component(channel.archetype, prop, ha)
```

`_schema/_consumer_gen.py:668` — the suffix is keyed the same way:

```python
is_command = channel.archetype == "command" and not consumer.read_only
```

The direction information is already available and already handled correctly elsewhere
in the same module — `_apply_topics_and_templates` (`:356`) branches on
`channel.direction`, as does `_channel_directions` (`:886`). Only component inference
and the suffix are blind to it.

### Suggested fix

Gate the writable branch on direction: a channel with `direction == "send"` can only
observe, so it should take the read-only component path (`sensor` / `binary_sensor`) and
carry no `_cmd` suffix, regardless of archetype. Equivalently, treat
`direction == "send"` exactly as `consumer.read_only` is already treated at
`_consumer_gen.py:234`.

Pass the channel (or its direction) into `_infer_component`, and make the `is_command`
computation at `:668` require `channel.direction in ("receive", "both")`.

### Regression guard worth adding

An invariant test over the generated payloads: no writable component
(`number`/`select`/`switch`/`text`/`light`/`climate`/`cover`) may be emitted without a
`command_topic`. This monorepo carries that assertion in
`apps/wallpanel-control/packages/tests/integration/test_schema_discovery.py` and it is
what caught the bug.

### Note on the 0.6.0 → 0.6.1 history

This is not a plain regression. Under 0.6.0 two bugs cancelled out: the field is
`anyOf: [{type: integer}, {type: 'null'}]`, which 0.6.0 could not unwrap (Finding 6), so
it degraded to `string`, and `("command", "string")` was absent from the component map,
so it fell through to `sensor`. 0.6.1 fixed Finding 6 and filled that map entry, which
correctly resolves the type and thereby exposed the direction-blindness underneath.

### Downstream mitigation currently in place

`apps/wallpanel-control` marks both `DisplayState` fields `read_only=True` in
`consumer()`, which is accurate — they are observations; commands arrive on
`DisplayCommand` over `/set` — and routes them through the Finding 17 path. That
mitigation must stay until this is fixed. It is a workaround, not a fix: it requires
every app author to notice the problem and annotate around it.

---

## Bug 2 — flattened nested property names leak into templates and Item IDs

### Symptom

#384 made nested and array-item properties reachable by flattening their names to
`parent[].child` (array items) and `parent.child` (nested objects). That flattened
**label** is then used verbatim as a **data accessor** in three places, none of which
accept it:

| Output                          | Generated for `events[].title`         |
| ------------------------------- | -------------------------------------- |
| HA `value_template`             | `{{ value_json['events[].title'] }}`   |
| openHAB `transformationPattern` | `JSONPATH:$['events[].title']`         |
| openHAB Item ID                 | `String  Bug2_Birthday_Events[].Title` |

The HA template is a Jinja lookup of a literal key that does not exist, so it renders
`''` and the entity is permanently blank. The JSONPATH selector likewise never matches,
so the openHAB channel never receives a value. The Item ID is outright **invalid
`.items` DSL** — `[`, `]` and `.` are not legal characters in an openHAB Item name.

The third is the most damaging: openHAB parses `.items` files as a unit, so a single
nested annotation makes the **entire generated file** fail to load, taking every
unrelated Item in it down too.

Before 0.6.2 these annotations were inert and produced nothing. The upgrade therefore
turns "no entities" into "broken entities", which is a net regression in observable
behaviour for any app with a nested `consumer()` annotation.

### Reproduction

Save as `bug2.yaml`. Covers both the array-item and nested-object paths:

```yaml
asyncapi: 3.0.0
info: { title: bug2, version: 0.1.0 }
channels:
  calendarState:
    address: bug2/birthday/state
    x-cosalette-app: bug2
    x-cosalette-archetype: telemetry
    messages:
      message:
        payload:
          type: object
          properties:
            events:
              type: array
              items:
                type: object
                properties:
                  title:
                    type: string
                    x-cosalette-consumer: { display_name: Event Title }
            meta:
              type: object
              properties:
                source:
                  type: string
                  x-cosalette-consumer: { display_name: Source }
operations:
  publishCalendarState: { action: send, channel: { $ref: '#/channels/calendarState' } }
```

`cosalette schema ha-discovery bug2.yaml`:

```text
homeassistant/sensor/bug2/birthday_events_title/config -> {{ value_json['events[].title'] }}
homeassistant/sensor/bug2/birthday_meta_source/config  -> {{ value_json['meta.source'] }}
```

`cosalette schema openhab bug2.yaml`:

```text
transformationPattern="JSONPATH:$['events[].title']"
transformationPattern="JSONPATH:$['meta.source']"

String  Bug2_Birthday_Events[].Title  "Event Title [%s]"  (gBug2)  { ... }
String  Bug2_Birthday_Meta.Source     "Source [%s]"       (gBug2)  { ... }
```

Confirmation that the HA template resolves to nothing, against a realistic payload:

```python
>>> from jinja2 import Template
>>> payload = {"events": [{"title": "Anna"}, {"title": "Bo"}]}
>>> Template("{{ value_json['events[].title'] }}").render(value_json=payload)
''
>>> Template("{{ value_json.events[0].title }}").render(value_json=payload)
'Anna'
```

### Root cause

`_schema/_loader_helpers.py:312` — `_expand_property_children` builds the flattened
key:

```python
children[f"{name}[].{sub_name}"] = sub_schema   # :335, array items
...
children[f"{name}.{sub_name}"] = sub_schema     # :342, nested objects
```

That key becomes `PropertySchema.name`, which is a display/identity label. Three
consumers then treat it as a path:

- `_schema/_consumer_gen.py:336` — `_derive_value_template` tests the whole flattened
  name against `_IDENTIFIER_RE`, fails, and falls back to bracket-quoting it as a single
  literal key (`:349-350`).
- `_schema/_consumer_gen.py:205` — `_jsonpath_selector` does the same for openHAB
  (`:222`, `f"$['{escaped}']"`).
- `_schema/_consumer_gen.py:770` — `_openhab_item_id` slugifies `device` but **not**
  `prop_name`:

  ```python
  parts = [app, _slugify(device), prop_name]
  ```

Note that the bracket-quoting in the first two is working as designed — it exists to
stop a property name containing quotes or newlines from corrupting the output. The
defect is that a flattened *path* is being handed to a function whose contract is
"escape this opaque *name*".

### Suggested fix

The three sites need different treatment.

**1. Carry the structural path separately from the display name.** The cleanest fix is
for `_expand_property_children` to record the path segments alongside the flattened name
— e.g. a `path: tuple[str, ...]` and an `is_array_item: bool` on `PropertySchema` —
rather than making callers re-parse `[]` and `.` out of a string. Template and JSONPATH
derivation then build the accessor from the segments:

| Case             | HA `value_template`            | openHAB JSONPATH |
| ---------------- | ------------------------------ | ---------------- |
| `meta.source`    | `{{ value_json.meta.source }}` | `$.meta.source`  |
| `events[].title` | see the design question below  | see below        |

Each segment should still be escaped individually with the existing logic, so a nested
property whose own name is not a simple identifier stays safe.

**2. `_openhab_item_id` must slugify `prop_name`** (`_consumer_gen.py:779`), exactly as
it already slugifies `device`. This is worth fixing independently of the rest: it is a
latent correctness bug for *any* property name that is not a bare identifier, and it is
the one that corrupts the whole `.items` file rather than a single entity.

**3. Design question — what should an array-of-objects produce?** `events[].title` has
no single value: N events yield N titles, and an HA sensor holds one state. Emitting
`value_json.events[0].title` is well-defined but arbitrary. Options, in our order of
preference:

- **Do not emit an entity for an array-item property by default**, and warn — the same
  way 0.6.2 already warns for a `consumer()` block deeper than the loader can reach.
  Emitting nothing was 0.6.1's behaviour and, while it lost the annotation, it was at
  least not wrong.
- Emit an explicitly indexed entity only when the author asks for one, via an
  annotation such as `consumer(..., array_index=0)`.
- Emit `[0]` by default and document it.

The nested-object case (`meta.source`) has no such ambiguity and should simply work.

### Regression guards worth adding

- Every generated `value_template` renders non-empty against a payload instance built
  from the schema. This catches the whole class, not just this instance.
- Every generated openHAB Item ID matches openHAB's identifier grammar
  (`[A-Za-z][A-Za-z0-9_]*`).

### Who is affected today

Any app with a `consumer()` annotation on a nested or array-item property. In this
monorepo that is `caldates2mqtt`, whose `CalendarState.events[]` carries `title` and
`date` annotations: it goes from 0 discovery payloads on 0.6.1 to 4 permanently-blank HA
entities and an unparsable `.items` file on 0.6.2.

---

## Appendix — how this was verified

Both defects were reproduced against the installed 0.6.2 wheel using the two minimal
schemas above, driven through `cosalette schema ha-discovery` and
`cosalette schema openhab`. Root causes were then read off the wheel source; every
`file:line` reference in this document points at cosalette 0.6.2 as published on PyPI
(uploaded 2026-08-12).

For context on the upgrade as a whole: 0.6.2 is otherwise a clean upgrade for this
monorepo. Lint and typecheck pass unchanged across all eight apps, all unit suites pass,
no HA discovery topic is removed for any app (entity identity in Home Assistant is
stable), and openHAB output is byte-identical for seven of eight apps — the exception
being `caldates2mqtt` via Bug 2. The nine findings 0.6.2 set out to close were each
verified as fixed.


---

## Resolution (cosalette 0.6.3)

Shipped as [cosalette#390](https://github.com/ff-fab/cosalette/pull/390), "fix(schema):
correct HA/openHAB consumer generation defects" (upstream epic `cos-ccv6`), with a
self-found follow-up in [#391](https://github.com/ff-fab/cosalette/pull/391). Verified
against the installed 0.6.3 wheel by replaying both reproductions above.

**Bug 1 — fixed.** `_infer_component` now takes the `ChannelSchema` and treats
`direction == "send"` exactly as `read_only`, *before* the `ha.component` override; the
`_cmd` suffix additionally requires `direction in ("receive", "both")`. The `bug1.yaml`
reproduction now yields what was asked for:

```text
homeassistant/sensor/bug1/display_brightness_percent/config
   state_topic  : bug1/display/state
   command_topic: None            ← read-only component, correctly no command topic
```

The `_cmd` mislabelling is gone with it. The `read_only=True` markers on
`wallpanel-control`'s `DisplayState` fields are no longer load-bearing — they remain
accurate as documentation of intent, and output is unchanged either way.

**Bug 2 — fixed.** `PropertySchema` gained `path: tuple[str, ...]` and
`is_array_item: bool`; a shared `_path_segments_to_accessor` helper builds accessors
from the structural segments for both generators, and `_openhab_item_id` now slugifies
`prop_name`. All three symptoms are resolved:

| Output                          | 0.6.3                       |
| ------------------------------- | --------------------------- |
| HA `value_template`             | `{{ value_json.meta.source }}` |
| openHAB `transformationPattern` | `JSONPATH:$.meta.source`    |
| openHAB Item ID                 | `Bug2_Birthday_MetaSource`  |

For the array-of-objects design question, upstream took this document's
first-preference option: array-item properties are skipped and reported rather than
emitted with an arbitrary index. `cosalette schema ha-discovery` now warns —

```text
Warning: consumer() annotations on array-item properties (parent[].child) in
channel(s): birthdayState, garbageState. An array of objects has no single value,
so no discovery entity is generated for them.
```

**Write-path follow-up (#391), not in this report.** Upstream found that the same
flat-key defect existed on the *write* path: `_default_command_template` and
`_openhab_format_before_publish` still built `{"meta.source": <value>}` rather than the
nested envelope the app's own schema validation expects. Both now nest by `prop.path`,
and single-segment paths are byte-identical to before. Verified:

```text
dev_meta_source_cmd -> {"meta": {"source": {{ value | tojson }}}}
dev_flat_cmd        -> {"flat": {{ value | tojson }}}
formatBeforePublish="{\"meta\":{\"level\":%s}}"
```

`cap-bo0` is closed by this release.
