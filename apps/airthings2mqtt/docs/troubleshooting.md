# Troubleshooting

What to do when `airthings2mqtt/airthings/availability` shows `"offline"` or the
heartbeat on `airthings2mqtt/status` reports the sensor `"stale"`. The examples use the default topic prefix
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
   becomes `"stale"` and the availability topic shows `"offline"`.
4. **Tries again at the next poll.** It keeps polling at `POLL_INTERVAL`.
5. **Exits after a long stale period.** If the sensor stays stale for
   `AIRTHINGS2MQTT_EXIT_AFTER_STALE` (5 hours by default), the app exits with code 5 and
   the restart policy starts it again. See [Restarts and Exit Codes](#restarts-and-exit-codes).

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

A container restart only helps when the app itself is stuck, for example when
`airthings2mqtt/status` shows the retained last will `"offline"` while the container is
still running. It does not fix a sensor or adapter fault.

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

## Recognising a Stale or Offline App

MQTT is the health signal. Watch these topics:

| What you see                                          | Meaning                                                              |
| ----------------------------------------------------- | -------------------------------------------------------------------- |
| `airthings2mqtt/airthings/availability` = `"offline"` | A read failed for good, or no read succeeded within `stale_after`    |
| `devices.airthings.status` = `"stale"` in the heartbeat | No read succeeded within `stale_after` (about 62 minutes)          |
| `airthings2mqtt/status` = `"offline"` (plain string)  | The last will: the app died or its event loop has been blocked for about 90 seconds |

```bash
mosquitto_sub -h localhost -v -t 'airthings2mqtt/status' -t 'airthings2mqtt/+/availability'
```

Alert on these in Home Assistant or your monitoring. See
[MQTT Topics](mqtt-topics.md#availability) for the payloads.

The image's Docker `HEALTHCHECK` runs `cosalette-health` every 60 seconds and shows the
same state on the host
([ADR-011](https://github.com/ff-fab/cosalette-apps/blob/main/docs/adr/ADR-011-native-cosalette-health-probe-as-the-default-docker-healthcheck-exit-codes-still-heal.md)).
`docker ps` reports `unhealthy` after three failed probes, when the sensor is stale or
the app has not written its health file for three minutes. Startup gets 60 seconds of
grace; the app starts in about 30 seconds on a Raspberry Pi 4. **An `unhealthy` status
restarts nothing**: Docker only restarts a container whose process exits, so the
recovery comes from the exit codes below.

```bash
docker inspect --format '{{.State.Health.Status}}' <container>
```

---

## Restarts and Exit Codes

Only a process exit makes Docker restart a container; `restart: unless-stopped` then
starts it again. airthings2mqtt exits with a non-zero code when it cannot recover by
itself:

| Exit code | Cause                                                                    |
| --------- | ------------------------------------------------------------------------ |
| `1`       | Startup failed, or a C call held the GIL and blocked the event loop for twice `COSALETTE_LOOP_STALL_TIMEOUT`; the faulthandler backstop exited the process |
| `3`       | An unexpected exception                                                  |
| `4`       | A framework task kept crashing and used up its restart budget            |
| `5`       | The sensor stayed stale for `AIRTHINGS2MQTT_EXIT_AFTER_STALE` seconds (5 hours by default) |
| `6`       | The event loop did not run for `COSALETTE_LOOP_STALL_TIMEOUT` seconds (120 in the shipped `compose.yml`, see below) |

```bash
docker inspect --format '{{.State.ExitCode}} {{.RestartCount}}' <container>
docker compose logs airthings2mqtt | grep CRITICAL
```

**A dead sensor causes one harmless restart about every 6 hours.** The sensor turns
stale about 62 minutes after the last good reading, and the app exits 5 hours after
that. After the restart the count starts again. Each restart shows on MQTT as the last
will `"offline"` and then `"online"`. A restart cannot fix a missing sensor or a radio
fault on the host, so work through the [Operator Runbook](#operator-runbook) when you
see exit code 5 more than once. To turn the exit off, set
`AIRTHINGS2MQTT_EXIT_AFTER_STALE=0`; see [Configuration](configuration.md).

**A blocked event loop exits with code 6.** The last will reports it after about 90
seconds. The shipped `compose.yml` sets `COSALETTE_LOOP_STALL_TIMEOUT` to 120 seconds,
so the app exits with code 6 when its event loop has not run for that long, and the
restart policy starts it again. All Bluetooth and D-Bus calls are asynchronous, so a
healthy app never blocks the loop that long; a slow poll waits without blocking it. To
change the limit, set `COSALETTE_LOOP_STALL_TIMEOUT` in `.env`; to turn the watchdog
off, remove the line from `compose.yml`.

!!! warning "Remove your own health check override"

    Images 0.3.x shipped a `HEALTHCHECK` that ran `airthings2mqtt health`, which
    imported the whole app on every probe. If you copied that `healthcheck:` block, or
    added `healthcheck: {disable: true}`, into your own compose file, remove it. The
    image's probe now runs `cosalette-health`, which only reads the health file.
