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
D-Bus writes; only the host's D-Bus/BlueZ policy does. The full rationale is in
[ADR-003](adr/ADR-003-no-adapter-power-cycling-bluetooth-adapter-recovery-is-host-side.md).

---

## Operator Runbook

Work through these steps on the host, in order.

### 1. Check the Sensor

Is the sensor advertising, and is the signal usable?

```bash
bluetoothctl scan on    # wait for the sensor's MAC to appear, then:
bluetoothctl scan off
```

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

## Container Health Check

The image sets `COSALETTE_HEALTH_FILE=/tmp/airthings2mqtt-health.json` and checks it
with `airthings2mqtt health` every 60 seconds, starting 180 seconds after the container
starts. The check fails when:

- the health file is missing or older than three heartbeat intervals, so the event loop
  has stalled; or
- the device status is `"stale"`, so no reading succeeded within `stale_after`.

```bash
docker inspect --format '{{.State.Health.Status}}' <container>
docker compose exec airthings2mqtt airthings2mqtt health
```

A single failed read does not make the container unhealthy. To include it, append
`--fail-on stale --fail-on error` to the `healthcheck.test` in `compose.yml`. Repeat
the flag: `--fail-on error` on its own replaces the default `stale` instead of adding to
it.

!!! warning "Docker does not restart unhealthy containers"

    `restart: unless-stopped` only restarts a container whose process has exited. An
    `unhealthy` status is reported and nothing more. To act on it, run a watchdog
    such as [autoheal](https://github.com/willfarrell/docker-autoheal), or alert on
    it from your monitoring. A restart cannot fix a missing sensor, so alert first and
    automate restarts only for a stalled app.
