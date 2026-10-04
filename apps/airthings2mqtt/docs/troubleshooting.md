# Troubleshooting

What to do when `airthings2mqtt/airthings/availability` shows `"offline"` or the
container reports `unhealthy`. The examples use the default topic prefix
(`airthings2mqtt`) and device name (`airthings`).

---

## What the App Does

Each poll scans for the sensor's advertisement, connects and reads it. When that
fails, airthings2mqtt:

1. **Retries with backoff.** Connection failures and timeouts are retried up to three
   times within the same poll. A read failure (`ble_read`) is not retried.
2. **Marks the sensor offline.** When the retries run out, or a read fails, it
   publishes a retained `"offline"` on the availability topic and the error on
   `airthings2mqtt/airthings/error`. The next successful read publishes `"online"`.
3. **Reports staleness.** If no read succeeds for the derived `stale_after` window
   (about 62 minutes with the defaults), the device status in `airthings2mqtt/status`
   becomes `"stale"` and the container health check fails.
4. **Tries again at the next poll.** It keeps polling at `POLL_INTERVAL`. Nothing
   else changes.

The `error_type` says which step failed:

| `error_type`           | What it tells you                                            |
| ---------------------- | ------------------------------------------------------------ |
| `ble_device_not_found` | The scan did not see the sensor's advertisement             |
| `ble_connection`       | The connection failed, or BlueZ, D-Bus or the adapter refused |
| `ble_timeout`          | The connection or read took longer than allowed            |
| `ble_read`             | Connected, but a characteristic was missing or undecodable |

A `ble_device_not_found` message also says how many other advertisers the scan saw.
Zero suggests the adapter is not receiving anything; a non-zero count suggests the
adapter works and this sensor is not advertising or is out of range. Treat both as
hints, not a diagnosis.

The heartbeat entry `devices.airthings` adds `consecutive_failures`, `last_error`,
`failing_since` and `last_success_at`. See [MQTT Topics](mqtt-topics.md#status-heartbeat).

---

## What the App Does Not Do

**airthings2mqtt never power-cycles or resets the Bluetooth adapter.** It does not
write any adapter property over D-Bus. Its health check only reads
`Adapter1.Powered`. Recovering the radio is the host's job:

- The adapter is shared. Toggling it disconnects every other BLE client on the host.
- A manual power cycle did not help in the outage that prompted this decision.
- The container runs as a non-root user and should not need permission to change the
  host's Bluetooth state.

This is a rule about what the app's code does, not a host security guarantee. The
read-only `/var/run/dbus` mount and the non-root user do not, by themselves, block
D-Bus writes; only the host's D-Bus/BlueZ policy does. To enforce the rule, install the
opt-in policy in [Host Setup](host-setup.md#optional-deny-bluez-property-writes). The
full rationale is in
[ADR-003](adr/ADR-003-no-adapter-power-cycling-bluetooth-adapter-recovery-is-host-side.md).

---

## Operator Runbook

Work through these steps on the host, in order.

### 1. Check the Sensor

Is the sensor advertising, and is the signal usable?

```bash
bluetoothctl --timeout 30 scan on
```

The timed scan stays active for 30 seconds. `bluetoothctl scan on` without an
interactive session can exit immediately on some BlueZ versions.

- **Not listed:** replace the batteries, move the sensor or the host closer, and make
  sure no other client (for example the Airthings phone app) is holding a connection.
- **Listed with a weak RSSI** (around -90 dBm or below): reduce the distance or
  obstructions. The `rssi` field in the state payload shows the trend over time.

### 2. Check the Adapter

```bash
bluetoothctl show       # expect "Powered: yes"
systemctl status bluetooth
journalctl -u bluetooth --since "1 hour ago"
```

If the scan in step 1 saw no advertisers at all, or BlueZ logs errors, restart the
Bluetooth stack as root:

```bash
sudo systemctl restart bluetooth
```

If that does not help, reset the adapter itself (also as root), or reboot the host:

```bash
sudo bluetoothctl power off && sudo bluetoothctl power on
```

The app needs no restart: it reconnects at the next poll. To skip the wait, trigger a
re-read:

```bash
mosquitto_pub -h localhost -t "airthings2mqtt/airthings/set" -n
```

If the logs show D-Bus connection failures, or `Permission denied` for
`/app/data/store.json`, after an upgrade from 0.2.x, the host account or the data
ownership step is missing. See [Host Setup](host-setup.md#container-user-uid-10001).

### 3. Restart the Container

A container restart only helps when the app itself is stuck, which the health check
reports as a stale health file. It does not fix a sensor or adapter fault.

```bash
docker compose restart airthings2mqtt
```

---

## Replacing the Batteries

A battery change resets the sensor: it forgets its radon averages and computes them from
scratch.

1. Replace the batteries. The app needs no restart: it reads the sensor again at the
   next poll once the sensor advertises.
2. Check that the sensor advertises. `bluetoothctl --timeout 20 scan on` on the host
   should list its address within about 20 seconds. Right after power-up the sensor can
   advertise without a name, so look for the address.
3. Expect `measurement_state: "warming_up"` and `null` for both radon fields until the
   sensor has computed its first 24-hour average. After that, expect `"provisional"`
   for `LTA_SETTLE_DAYS` days (30 by default), then `"ok"`. See
   [Measurement state](mqtt-topics.md#measurement-state).
4. The long-term average starts again from zero. `sensor_reset_at` in the state payload
   records when the app detected the reset. The value before the reset is in the `INFO`
   log line (`Airthings sensor reset detected ...: long-term average 113 -> 0`) and in
   the store as `reset_tracker.lta_before_reset`.

If the app was not running for the whole warm-up, it still detects the reset when the
long-term average has fallen below a quarter of its previous value (at least 20 Bq/m³).

---

## Container Health Check

The image sets `COSALETTE_HEALTH_FILE=/tmp/airthings2mqtt-health.json` and checks it
with `airthings2mqtt health`. During the 180-second start period, Docker 25 and later
probes every `start_interval` (5 seconds by default) and does not count failures. The
container turns `healthy` at the first successful probe, about 35 seconds after start on
a Raspberry Pi 4 with `cpus: 0.5`. From then on Docker probes every 60 seconds. The
check fails when:

- the health file is missing or older than three heartbeat intervals, so the event loop
  has stalled; or
- the device status is `"stale"`, so no reading succeeded within `stale_after`.

```bash
docker inspect --format '{{.State.Health.Status}}' <container>
docker compose exec airthings2mqtt airthings2mqtt health
```

Each probe starts a new Python interpreter and imports the framework and the app. On a
Raspberry Pi 4 with `cpus: 0.5`, images up to 0.3.0 took 11 to 13 seconds per probe,
because they shipped without precompiled bytecode. Later images include it, so the probe
is faster. The timeout of 30 seconds leaves room for both. If `.State.Health.Status`
stays `starting`, or turns `unhealthy`, while the `exec` above prints `healthy`, time
the probe with `time docker compose exec airthings2mqtt airthings2mqtt health`. If it
takes close to the timeout, raise `healthcheck.timeout`.

!!! caution "Do not probe by hand while Docker probes"

    A manual `docker exec ... airthings2mqtt health` runs in the container and shares
    its CPU quota with Docker's own probe. If the two overlap, both take about twice
    as long, and Docker can record a timeout. Check `.State.Health.Log` for the time
    of the last probe and run the manual one between two scheduled probes.

A single failed read does not make the container unhealthy. To include it, append
`--fail-on stale --fail-on error` to the `healthcheck.test` in `compose.yml`. Repeat
the flag: `--fail-on error` on its own replaces the default `stale` instead of adding to
it.

!!! danger "The health check needs image 0.3.0 or later"

    Older images have no `health` command. There, `airthings2mqtt health` starts a
    second instance of the app. With a fixed `MQTT__CLIENT_ID` it uses the same client
    ID, and the two instances keep disconnecting each other. Upgrade the image before you add the `healthcheck` block. See
    [Host Setup](host-setup.md#health-check-needs-030-or-later).

!!! warning "Docker does not restart unhealthy containers"

    `restart: unless-stopped` only restarts a container whose process has exited. An
    `unhealthy` status is reported and nothing more. To act on it, run a watchdog
    such as [autoheal](https://github.com/willfarrell/docker-autoheal), or alert on
    it from your monitoring. A restart cannot fix a missing sensor, so alert first and
    automate restarts only for a stalled app.
