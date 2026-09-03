---
status: Accepted
date: 2026-09-03
impact: high
tags: [mqtt, security, configuration, architecture]
---

# ADR-006: MQTT Transport Security Posture

## Status

Accepted **Date:** 2026-09-03

## Context

cosalette 0.7.0 flipped `MqttSettings.tls` from `False` to `True` (upstream ADR-062), driven by security-audit finding F-CU1 (CWE-1188/319): plaintext MQTT credentials on non-local brokers. The flip is unconditional — upstream explicitly declines to exempt loopback, on the grounds that a pydantic default cannot vary by another field's value.

The cosalette 0.8.0 migration (commit 42a5d55) absorbed that flip by declaring a private `_MqttSettings(cosalette.MqttSettings)` subclass in each of the nine apps, redeclaring `tls: bool = False`, and binding it as the `mqtt` field. The nine blocks are byte-identical apart from the env prefix named in the docstring — roughly 150 lines of duplication. That was a deliberate backward-compatibility measure to keep the upgrade from silently starting a TLS handshake no broker could answer, and it explicitly deferred the posture question rather than answering it.

Three facts make the deferral untenable as a permanent state. First, the pin is **invisible at deploy time**: it lives in application code, so an operator who configures a TLS-capable broker has no signal that a code-level default is overriding their intent. Second, its rationale is duplicated across nine identical docstrings, each of which must be re-read and re-verified at every cosalette upgrade. Third, the only repository-level written record of the posture lives in the body of `.github/instructions/cosalette.instructions.md`, which `cosalette ai init --force` overwrites wholesale.

The pinned behaviour is covered — `packages/tests/unit/test_mqtt_tls_defaults.py` asserts it across all nine apps — but it asserts a code-level default. Nothing asserts that a deployment states its own posture, which is the property that actually determines what happens on the wire.

On the infrastructure side, every `mosquitto.conf` in the repository is the same minimal plaintext configuration (`listener 1883`, `allow_anonymous true`) with no TLS listener anywhere — no `8883`, `cafile`, or `certfile` directive exists in the repo. Meanwhile all nine `compose.yml` files point their app at `MQTT__HOST: mosquitto`, a Docker service name rather than loopback, which means cosalette's `_log_transport_posture()` defense-in-depth check has been emitting a plaintext-transport warning on every connect since the 0.8.0 upgrade landed.

Deployment is exclusively via the shipped compose files; there are no bare-metal or systemd installations to coordinate.

## Decision

Treat MQTT transport security as a per-deployment setting rather than a per-app code default: remove the nine `_MqttSettings` subclasses, inherit cosalette's TLS-on default, and have each shipped deployment configuration expose `<PREFIX>_MQTT__TLS` alongside the broker host it depends on, defaulting it to `false` via Compose interpolation for the bundled plaintext broker. The posture for every current deployment remains plaintext, but it is now stated in configuration where an operator can see and change it.

```yaml
services:
  gas2mqtt:
    environment:
      GAS2MQTT_MQTT__HOST: mosquitto
      # Broker terminates plaintext MQTT; see docs/adr/ADR-006.
      GAS2MQTT_MQTT__TLS: ${GAS2MQTT_MQTT__TLS:-false}
```

## Decision Drivers

- The posture must be visible where it is decided — at deploy time, next to the broker host — not buried in an application-code default.
- No broker in this repository terminates TLS: every mosquitto.conf is a plaintext listener on 1883, so enabling TLS is broker work (certificates, a TLS listener, a CA distributed to nine containers), not an application flag.
- Upstream ADR-062 made TLS-on the default for a real finding (F-CU1, CWE-1188/319); silently opting out of it in perpetuity, in code, is a position this repository should state rather than inherit by accident.
- The existing cross-app regression test asserts a code-level default; it should instead assert the deployment declaration that actually determines the posture and keeps the opt-in path visible.
- Nine byte-identical 16-line subclasses must each be re-verified at every cosalette upgrade.
- Settings precedence (init > env > dotenv > config_file > secrets > defaults) already supports per-deployment declaration without any code-level subclass.

## Considered Options

### Option 1: Keep the per-app _MqttSettings pin

Retain the nine subclasses introduced by the 0.8.0 migration and document the rationale in their docstrings, treating plaintext-on-trusted-LAN as a settled repository position expressed in code.

- *Advantages:* Zero migration risk — runtime behaviour is unchanged for every deployment, including any not using the shipped compose files.; The opt-in path already works: an operator can still set the env var to enable TLS.; No configuration files need to change.
- *Disadvantages:* The posture stays invisible at deploy time, which is the substance of the original complaint.; The record stays duplicated across nine docstrings that must be re-verified at each upgrade.; An operator who later terminates TLS on the broker has no signal that a code default is fighting their configuration.; Leaves roughly 150 lines of duplicated compatibility scaffolding in the source tree indefinitely.

### Option 2: Adopt the upstream TLS-on default

Remove the subclasses and let cosalette's `tls=True` default take effect, requiring operators to stand up TLS on the broker and to opt out explicitly where they cannot.

- *Advantages:* Secure by default, fully aligned with upstream ADR-062 and finding F-CU1.; Removes the duplicated scaffolding.; Any future deployment inherits the safe posture without needing to remember a setting.
- *Disadvantages:* Breaks all nine apps immediately: there is no TLS endpoint anywhere in the repository to connect to, so the apps fail to connect and nothing becomes more secure.; Requires broker infrastructure work — certificates, a TLS listener, CA distribution to nine containers — before it can be adopted at all.; Converts a documentation problem into an outage.

### Option 3: Declare MQTT__TLS per deployment (chosen)

Remove the subclasses so the `mqtt` field is inherited from `cosalette.Settings` with its TLS-on default, and expose `<PREFIX>_MQTT__TLS` in each shipped deployment configuration adjacent to the broker host setting that establishes the topology, defaulting it to `false` for the bundled plaintext broker.

- *Advantages:* The posture is stated in configuration, visible to whoever deploys the app, next to the broker host it depends on.; Runtime behaviour is unchanged on day one for every compose-based deployment.; Removes roughly 150 lines of duplicated scaffolding and the per-upgrade re-verification burden.; Enabling TLS later becomes a one-line `.env` or Compose-override change rather than a source-code edit.; Keeps a single repository-wide record in this ADR rather than nine docstring copies.
- *Disadvantages:* Any deployment that does not use the shipped compose files must add the setting before upgrading or it will fail to connect.; The effective posture is still plaintext, so finding F-CU1 remains unaddressed in substance until the broker gains a TLS listener.; Each new app must remember to declare the setting; the inherited default will not do it for them.

## Decision Matrix

| Criterion | Keep the per-app _MqttSettings pin | Adopt the upstream TLS-on default | Declare MQTT__TLS per deployment |
| --- | --- | --- | --- |
| Deploy-time visibility of the posture | 1 | 4 | 5 |
| Runtime behaviour preserved on upgrade | 5 | 1 | 4 |
| Alignment with upstream ADR-062 | 1 | 5 | 4 |
| Maintenance cost across nine apps | 2 | 5 | 4 |
| Broker infrastructure work required | 5 | 1 | 5 |
| Cost of enabling TLS later | 2 | 5 | 5 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- The transport posture is declared in each deployment's configuration, adjacent to the broker host, where an operator changing the broker will see it.
- Roughly 150 lines of duplicated compatibility scaffolding are removed from the source tree, along with the obligation to re-verify nine identical subclasses at each cosalette upgrade.
- Enabling TLS becomes a one-line `.env` or Compose-override change per deployment plus broker work, with no source edit.
- The repository-wide record lives in this ADR rather than in an agent-instructions file that `cosalette ai init --force` overwrites.
- The cross-app regression test now asserts that every shipped compose file declares the posture on the app service and defaults it to `false`, so deleting the declaration or masking TLS opt-in fails CI rather than surfacing as a failed broker connection.

### Negative

- The effective posture remains plaintext MQTT, so upstream finding F-CU1 (CWE-1188/319) is documented rather than remediated; credentials and payloads stay readable to anything on the broker's network segment.
- Any deployment not using the shipped compose files must still set `<PREFIX>_MQTT__TLS=false` before upgrading, or the app will inherit `tls=True` and fail to connect. Deployment is currently compose-only, which bounds this risk to future installations.
- Each new app must declare the setting in its deployment configuration; the inherited default will not supply it.
- cosalette's `_log_transport_posture()` check continues to warn on every connect, since all nine apps target a non-loopback broker host over plaintext.

_2026-09-03_
