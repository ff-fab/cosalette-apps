---
status: Accepted
date: 2026-09-18
impact: moderate
tags: [mqtt, configuration, testing, documentation]
---

# ADR-009: MQTT 5 Retained-Message Expiry Posture

## Status

Accepted **Date:** 2026-09-18 | Amended **Date:** 2026-09-18 | Amended **Date:** 2026-09-19

## Context

cosalette 0.10.1 adds opt-in MQTT 5 retained-message expiry (upstream ADR-078). With `mqtt.protocol_version` set to `5`, the client stamps every retained publish and the last will with a `MessageExpiryInterval` (default 86 400 s) and keeps an in-memory ledger of retained topics, which it re-publishes every `message_expiry_interval / 3` (default 8 h). Retained topics that nothing refreshes any more (a renamed entity, a process that never runs again) then expire from the broker without a durable store. The default stays MQTT 3.1.1.

The cost is per deployment. The broker must speak MQTT 5, there is no protocol fallback, and every retained topic is republished with an unchanged payload once per refresh, so a consumer that reacts to message receipt sees a duplicate. This decision covers airthings2mqtt, caldates2mqtt and gas2mqtt (cap-pnjx.3, .4, .5); the remaining six apps follow in their own tasks (cap-pnjx.6 to .11) and extend this record.

Evidence gathered for the three apps: every shipped `compose.yml` bundles `eclipse-mosquitto:2`. Against that image (mosquitto 2.1.2) and the repository's `mosquitto.conf`, a retained MQTT 5 message with a 3 s expiry that nothing refreshed was gone after 8 s, while a topic published through the real cosalette `MqttClient` with the same expiry was still retained, and an MQTT 3.1.1 client connected and retained normally on the same listener. In the tested wiring the apps publish 12 (gas2mqtt), 10 (airthings2mqtt) and 7 (caldates2mqtt, one calendar) retained topics, far below the ledger limits of 1 000 topics and 16 MiB. None of the three sets `force_update` on its Home Assistant entities, so a repeat does not change a sensor state. The repeat is visible only to consumers that trigger on message receipt: an MQTT trigger on caldates2mqtt or airthings2mqtt state, or a pulse-counting rule on gas2mqtt's `gas_counter/state`, which is published only when the trigger flips.

## Decision

Declare MQTT 5 per deployment for airthings2mqtt, caldates2mqtt and gas2mqtt: leave the code default at MQTT 3.1.1 and have each shipped `compose.yml` expose `<PREFIX>_MQTT__PROTOCOL_VERSION` next to the broker host, defaulting to `5` through Compose interpolation for the bundled mosquitto 2 broker, with the fallback and the consumer-visible refresh documented per app.

```yaml
services:
  gas2mqtt:
    environment:
      GAS2MQTT_MQTT__HOST: mosquitto
      GAS2MQTT_MQTT__TLS: ${GAS2MQTT_MQTT__TLS:-false}
      # MQTT 5 retained-message expiry; the bundled mosquitto:2 supports it.
      GAS2MQTT_MQTT__PROTOCOL_VERSION: ${GAS2MQTT_MQTT__PROTOCOL_VERSION:-5}
```

## Decision Drivers

- Post-adoption retained orphans should clear themselves without a persistent store, which only MQTT 5 expiry gives.
- The shipped deployments use one bundled broker (mosquitto 2), so the broker capability is known and was tested rather than assumed.
- An operator with a 3.1.1-only broker needs a one-line fallback, because cosalette has no protocol fallback.
- The posture belongs where the broker host is decided, as ADR-006 already established for TLS.
- The refresh must not change consumer-visible behaviour silently, so its cost has to be tested and documented.
- The wire behaviour is decided by cosalette, so one shared assertion set is cheaper and safer than one per app.

## Considered Options

### Option 1: Keep MQTT 3.1.1

Leave the three apps on the framework default and record that expiry was evaluated and declined.

- *Advantages:* No behaviour change for any running deployment.; No dependency on broker MQTT 5 support.
- *Disadvantages:* Retained orphans from renamed or removed entities stay on the broker forever unless a durable store cleans them.; Leaves the upstream safety net unused although the bundled broker supports it.

### Option 2: Pin MQTT 5 in application code

Set `protocol_version="5"` in each app's settings so every process uses MQTT 5 regardless of deployment.

- *Advantages:* Expiry is on for every process, including ones started without the compose file.; No compose or documentation wiring per app.
- *Disadvantages:* A deployment on a 3.1.1-only broker cannot connect and has no configuration-level fallback.; Repeats the invisible code-level pin that ADR-006 removed for TLS.

### Option 3: Declare MQTT 5 per deployment (chosen)

Keep the code default and expose `<PREFIX>_MQTT__PROTOCOL_VERSION` in each compose file, defaulting to `5` for the bundled broker, with the operator contract documented per app.

- *Advantages:* The posture is stated next to the broker host, where an operator can see and change it.; Bundled deployments get expiry by default; any other broker uses `3.1.1` with one setting.; Bare processes, tests and tools keep the unchanged MQTT 3.1.1 behaviour.; Matches the ADR-006 pattern, so one cross-app test guards both declarations.
- *Disadvantages:* A deployment that copies neither compose file nor the setting stays on MQTT 3.1.1 without expiry.; An existing compose deployment that points at a 3.1.1-only broker must add the fallback before upgrading.; Consumers that trigger on message receipt see one repeat per refresh.

## Decision Matrix

| Criterion | Keep MQTT 3.1.1 | Pin MQTT 5 in application code | Declare MQTT 5 per deployment |
| --- | --- | --- | --- |
| Orphan cleanup without a durable store | 1 | 5 | 4 |
| Operator control over the protocol | 3 | 1 | 5 |
| Runtime behaviour preserved on upgrade | 5 | 1 | 3 |
| Deploy-time visibility of the posture | 2 | 1 | 5 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Retained topics that nothing refreshes any more expire from the broker within 24 hours by default.
- The protocol is one line in `.env` or the Compose environment, next to the TLS setting from ADR-006.
- A shared broker double drives the real cosalette `MqttClient` in each app's integration tests, so the expiry property, the once-per-window refresh and the absence of any expiry under 3.1.1 are regression-tested.
- A cross-app unit test guards the compose declaration, the resolved defaults and the bundled broker version.

### Negative

- Every retained topic of the three apps is republished with an unchanged payload every 8 hours, which a consumer that triggers on message receipt sees as a duplicate.
- An outage longer than the expiry interval lets the retained topics expire until the next publish.
- Retained topics published before the switch never expire and need a manual clear.
- The real-broker check was run once by hand against `eclipse-mosquitto:2`; CI exercises a broker double, not a broker.

## Amendment (2026-09-18) — Additive

**Rationale:** cap-pnjx.6, .7 and .8 apply the same posture to jeelink2mqtt, suncast and velux2mqtt. The record needs their evidence and the three consumer-visible differences the first three apps did not have.

### Additional Sub-Decision: Extension to jeelink2mqtt, suncast and velux2mqtt

Declare MQTT 5 per deployment for jeelink2mqtt, suncast and velux2mqtt (cap-pnjx.6, .7, .8) exactly as for the first three apps: the code default stays MQTT 3.1.1, and each shipped `compose.yml` and `.env.example` defaults `<PREFIX>_MQTT__PROTOCOL_VERSION` to `5` for the bundled mosquitto 2 broker. The cross-app test `test_mqtt5_expiry_defaults.py` and a per-app `test_mqtt5_expiry.py` built on `mqtt5_broker` and `mqtt5_contract` guard the declaration and the wire behaviour.

Evidence: all three ship the same `mosquitto.conf` and `eclipse-mosquitto:2` as the first three apps. Against that image (mosquitto 2.1.2), a retained MQTT 5 message with a 3 s expiry that nothing refreshed was gone after 8 s, while a 3 s topic and a 300 kB topic published through the real cosalette `MqttClient` were still retained, and an MQTT 3.1.1 client connected on the same listener. In the tested wiring the apps publish 14 (jeelink2mqtt, after one frame and one mapping snapshot), 5 (suncast) and 10 (velux2mqtt, two covers) retained topics, far below the ledger limits. None sets `force_update`, so a repeat does not change a sensor state.

### Additional Sub-Decision: Consumer-visible differences of the three apps

**jeelink2mqtt:** `{sensor}/state` is already re-published every `heartbeat_interval_seconds` (180 s), so its refresh is negligible. `mapping/state` is published only when a mapping changes, so its refresh is a real repeat. A repeat carries the original `timestamp` and `last_seen`, so a freshness check on those fields is not fooled.

**suncast:** the retained payloads are the SVG and the optional base64 PNG, the largest of any app. The image is replaced every `poll_interval` (360 s), so the refresh is invisible to a dashboard. A retained publish that would push the refresh ledger past 16 MiB raises, and suncast logs a warning and skips that image; the default SVG is about 5 kB. suncast publishes no Home Assistant discovery (`discoverable=False`), so its contract test sets `has_discovery = False`.

**velux2mqtt:** a repeat of a cover state never moves a blind, because velux2mqtt acts only on the `set` topics, which are neither retained nor refreshed. An automation that triggers on receipt of `{cover}/state` runs once more per refresh. `calibrate/result` is published once and refreshed only while the process runs, so after a restart it expires within the expiry interval; the operator must copy the values into `VELUX2MQTT_COVERS` when a calibration ends.

### Additional Negative Consequences

- jeelink2mqtt, suncast and velux2mqtt republish every retained topic with an unchanged payload every 8 hours, which a consumer that triggers on message receipt sees as a duplicate.
- A velux2mqtt calibration result that is not copied into the cover configuration is lost within 24 hours of a restart.
- The real-broker check for these three apps drove the cosalette `MqttClient` directly against `eclipse-mosquitto:2`; CI still exercises the broker double, not a broker.

## Amendment (2026-09-18) — Additive

**Rationale:** cap-pnjx.9, .10 and .11 apply the same posture to vito2mqtt, wallpanel-control and wiz2mqtt, the last three apps of the epic. wallpanel-control differs from every earlier app: its state topics exist only after a command, so the record needs the consequence for a restart.

### Additional Sub-Decision: Extension to vito2mqtt, wallpanel-control and wiz2mqtt

Declare MQTT 5 per deployment for vito2mqtt, wallpanel-control and wiz2mqtt (cap-pnjx.9, .10, .11) exactly as for the first six apps: the code default stays MQTT 3.1.1, and each shipped `compose.yml` and `.env.example` defaults `<PREFIX>_MQTT__PROTOCOL_VERSION` to `5` for the bundled mosquitto 2 broker. The cross-app test `test_mqtt5_expiry_defaults.py` and a per-app `test_mqtt5_expiry.py` built on `mqtt5_broker` and `mqtt5_contract` guard the declaration and the wire behaviour. With these three, all nine apps of the epic follow this posture.

Evidence: all three ship the same `mosquitto.conf` and `eclipse-mosquitto:2` as the first six apps. Against that image (mosquitto 2.1.2), run once per app with that app's own `mosquitto.conf`, a retained MQTT 5 message with a 3 s expiry that nothing refreshed was gone after 8 s, a topic published through the real cosalette `MqttClient` with the same expiry was still retained, and an MQTT 3.1.1 client connected and retained normally on the same listener. In the tested wiring the apps publish 41 (vito2mqtt), 9 (wallpanel-control, after one display command and one system action) and 12 (wiz2mqtt, one bulb and one power source) retained topics, far below the ledger limits of 1 000 topics and 16 MiB; wiz2mqtt adds five or fewer per bulb. None of the three sets `force_update` on its Home Assistant entities, so a repeat does not change an entity state. The shared broker double gains `deliver`, which queues an inbound message, so a test can send a command through the real client.

### Additional Sub-Decision: Consumer-visible differences of the three apps

**vito2mqtt:** every group publishes with `OnChange()`, so a stable group was silent for hours and now repeats once per refresh, while an expired retained topic would otherwise have been lost after 24 h of stable values. The refresh also keeps the group topics alive across a long stable period. A repeat never drives the boiler: vito2mqtt writes only on the `{group}/set` topics, which are neither retained nor refreshed. After a restart every group publishes again at startup.

**wallpanel-control:** `display/state` and `system/action/state` are published only as the answer to a command; nothing polls the panel. The refresh replays the last answer while the process runs, and it never re-reads the panel. After a restart nothing refreshes the old answers, so they expire within 24 h and a subscriber that connects later gets no state until the next command. A deployment that needs the Home Assistant light to keep its last known state across restarts sets `WALLPANEL_CONTROL_MQTT__PROTOCOL_VERSION=3.1.1`; this is the one place where the posture removes state that MQTT 3.1.1 kept. A repeat of `system/action/state` never runs an action, because the app acts only on the `/set` topics.

**wiz2mqtt:** bulb and power source state use `OnChange()` and push wakes, so the refresh is a real repeat. A repeat never moves a bulb: wiz2mqtt sends to a bulb only on the `set` topics, and it restores the desired state when a bulb returns to reachability, not on an MQTT message. The desired state and the capability cache live in the store file, so expiry never touches them. The power source `signal_topic` is reserved and unsubscribed; when it is subscribed, the relay that owns it publishes it, so it stays outside the ledger.

### Additional Negative Consequences

- vito2mqtt, wallpanel-control and wiz2mqtt republish every retained topic with an unchanged payload every 8 hours, which a consumer that triggers on message receipt sees as a duplicate.
- After a restart, wallpanel-control's display and system action answers expire within 24 hours unless a command replaces them, so a subscriber that connects later has no state.
- The real-broker check for these three apps drove the cosalette `MqttClient` directly against `eclipse-mosquitto:2`; CI still exercises the broker double, not a broker.

## Amendment (2026-09-19) — Additive

**Rationale:** cap-rj7j removes the one place where the posture lost state that MQTT 3.1.1 kept: wallpanel-control now re-publishes its last command answers at startup.

### Additional Sub-Decision: wallpanel-control restores its last command answers at startup

This supersedes the wallpanel-control restart consequence of the 2026-09-18 amendment. Each command handler records its answer (`display/state`, `system/action/state`) in a `LastAnswers` object, which saves the wire payload in the cosalette store. A root device, `restore_answers`, publishes the saved answers once, retained, after each start. Then the refresh of the MQTT client keeps them alive, as for any other retained topic. A command that runs before the device attaches wins over the saved answer. cosalette 0.10 has no startup hook for a command handler, so the device publishes with `ctx.publish`, which skips `state_model` validation; the saved payload is therefore the already validated wire payload. The shipped `compose.yml` sets `WALLPANEL_CONTROL_STORE_PATH=/app/data/store.json` on the existing `wallpanel_control-data` volume, because the default store path is not persistent in a container. The restored answer is the last answer, not a new reading: the app does not read the panel again, so the panel state can differ if someone changed it by hand while the app was down. `WALLPANEL_CONTROL_MQTT__PROTOCOL_VERSION=3.1.1` is no longer needed to keep the state across restarts.

### Additional Negative Consequences

- wallpanel-control publishes through `ctx.publish` at startup, which skips `state_model` validation, until cosalette offers a startup hook for command handlers.
- A wallpanel-control deployment that does not persist `WALLPANEL_CONTROL_STORE_PATH` still loses its answers on a restart, as before.
