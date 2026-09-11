# wiz2mqtt

WiZ smart bulb control over MQTT for openHAB and Home Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

Built on the [cosalette](https://github.com/ff-fab/cosalette) IoT framework, currently
on the 0.9.6 release.

## Home Assistant Discovery

**Wired up.** `wiz2mqtt.main` calls `app.discovery()` (monorepo
[ADR-004](../../docs/adr/ADR-004-runtime-home-assistant-discovery-adoption.md)), so on
the first successful MQTT connect the app publishes retained
`homeassistant/<component>/wiz2mqtt/.../config` payloads generated from its own live,
already-expanded registry. Nothing to configure in Home Assistant — each configured bulb
appears automatically as one device. Removing a bulb from `wiz2mqtt.toml` clears its
retained discovery topics on the next start.

Each `[[bulbs]]` entry becomes one HA **device** carrying three entities, all reading
the one retained `wiz2mqtt/{name}/state` payload:

| Entity       | HA component            | Key fields                                                                                                                       | Topics                                                       |
| ------------ | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Light        | `light`, `schema: json` | `brightness`, `supported_color_modes: [color_temp, rgb]`, `effect` + 38-scene `effect_list`, `min_kelvin`/`max_kelvin` 2200–6500 | state `wiz2mqtt/{name}/state`, command `wiz2mqtt/{name}/set` |
| Effect speed | `number`                | `min` 10, `max` 200, `step` 1, `command_template` `{"effect_speed": {{ value }}}`                                                | state `wiz2mqtt/{name}/state`, command `wiz2mqtt/{name}/set` |
| Power        | `sensor`                | `device_class: power`, `unit_of_measurement: W`, `state_class: measurement`                                                      | state `wiz2mqtt/{name}/state` (read-only)                    |

One bridge-level `binary_sensor` (`device_class: connectivity`, state topic
`wiz2mqtt/status`) is published once for the whole app.

The `light` discovery metadata is a **static wire-format superset** — every bulb
advertises `color_temp` + `rgb` and the full scene list regardless of its actual class.
Runtime capability auto-detection still governs which commands the adapter forwards, so
a control that a given bulb lacks is a no-op, never a mis-routed command. Per-bulb
capability-filtered discovery metadata is deferred (`cap-3tr`; see
[ADR-003](docs/adr/ADR-003-toml-inventory-as-the-configuration-boundary.md)).

Because `app.discovery()` reads the runtime registry rather than the checked-in
`docs/schema.yaml`, bulb names are always correct without a representative `.env.schema`
profile. `docs/schema.yaml` and `task wiz2mqtt:schema:check` stay as the openHAB
(`cosalette schema openhab`) and drift-gate path; `task wiz2mqtt:schema:ha-discovery`
remains available for offline inspection of the same payloads. See
`packages/tests/integration/test_schema_discovery.py`.

## Onboarding

The bulb inventory lives in `wiz2mqtt.toml` (copy `wiz2mqtt.example.toml`). Each
`[[bulbs]]` entry needs a `name` and an `ip`; `mac` is optional and only verified
against the bulb's own report on first contact (`ip` is the identity —
[ADR-002](docs/adr/ADR-002-ip-address-as-bulb-identity.md)).

To find bulbs on the LAN, run the bundled `wiz2mqtt-discover` helper. It UDP-broadcasts
for WiZ bulbs and prints paste-ready `[[bulbs]]` blocks (placeholder names to rename):

```console
$ wiz2mqtt-discover --wait 5 > discovered.toml   # progress goes to stderr, TOML to stdout
```

The helper is an onboarding aid only — it is deliberately **not** wired into the daemon,
which addresses bulbs by their configured `ip`. Because the daemon never re-discovers,
pin each bulb's address with a static DHCP reservation. `--broadcast` targets a specific
subnet; `--timeout` caps total run time (pywizlight discovery can otherwise hang).

## Deployment

**Host networking is mandatory.** wiz2mqtt publishes bulb state the instant a bulb
_pushes_ a change over UDP, and a WiZ bulb addresses that push datagram to the source
address of the registration packet. Behind Docker's bridge NAT the bulb sees the
container's translated address, the return datagram lands on the host and is dropped,
and pywizlight reports the subscription as healthy anyway — so the app silently degrades
to poll-latency. The shipped `compose.yml` therefore runs the service with
`network_mode: host` (wiz2mqtt
[ADR-004](docs/adr/ADR-004-host-networking-requirement-udp-38900-one-process-per-host.md)
— distinct from the unrelated monorepo `docs/adr/ADR-004`).

Two operational constraints follow:

- **One wiz2mqtt per host.** pywizlight's push listener binds a single fixed port, UDP
  `38900`, that is not configurable. A second wiz2mqtt (or any other pywizlight-push
  consumer) in the same network namespace fails with `Port 38900 is in use` and gets no
  push.
- **The broker is reached over host loopback.** Because the container shares the host
  network namespace, it cannot resolve the Compose service name `mosquitto`. The bundled
  broker publishes on `127.0.0.1:1883`, so the service connects with
  `WIZ2MQTT_MQTT__HOST=localhost`. Point this at your own broker's host address for an
  external broker.

`network_mode: host` is a Linux-host feature; on Docker Desktop / macOS it does not
share the real host stack, so push cannot be exercised there — use a Linux host for a
faithful deployment.

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for setup instructions, common commands,
project structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
