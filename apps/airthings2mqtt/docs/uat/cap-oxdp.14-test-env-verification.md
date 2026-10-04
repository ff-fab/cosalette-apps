# Test-Environment Verification: airthings2mqtt 0.3.0 (cap-oxdp.14)

Instructions for the agent that runs in the test environment. You have the Docker host,
the deployed container, its logs and the MQTT broker, and perhaps Home Assistant. You do
not have the source repository; everything you need is on this page.

## Purpose

Bead **cap-oxdp.14** asks one question: is the container health probe fast enough on a
Raspberry Pi?

PR #323 raised the `HEALTHCHECK` timeout from 10 s to 30 s. Its evidence came from
amd64: the probe `airthings2mqtt health` imports the whole app, which took 1 s at
2 CPU, 4 s at 0.5 CPU and 41 s at 0.1 CPU. A Pi core is several times slower, so 30 s
may still be too short. That is inferred, not measured. Your job is to measure it.

**Acceptance criteria of cap-oxdp.14**, quoted from the bead:

| ID   | Criterion                                                                      |
| ---- | ------------------------------------------------------------------------------ |
| AC-1 | With `cpus: 0.5`, `time docker exec <container> airthings2mqtt health` is well under 30 s |
| AC-2 | `.State.Health.Status` turns `healthy` within `start_period` (180 s)           |
| AC-3 | `.State.Health.Status` stays `healthy` across a poll                           |

If one fails, the maintainer either raises the timeout or asks cosalette upstream for a
lighter probe. You do not decide that; you supply the numbers.

The same release also changes the user, the capabilities, the radon payload and the
state file. Section [Release smoke checks](#4-release-smoke-checks) covers those
briefly. No further UAT is planned before the release, so anything you find there
becomes a bug-fix bead after the release. It does not block it.

## Ground Rules

- **Observe only.** Do not change configuration, restart containers or edit files
  unless a step says so. Steps marked **DISRUPTIVE (optional)** need the operator's
  consent first; skip them if you do not have it.
- **Redact secrets** from everything you return: MQTT usernames and passwords, tokens,
  Home Assistant URLs with credentials, and `.env` contents. Also shorten the sensor's
  Bluetooth MAC to its last two octets (`**:AB:CD`); the app already does this in its
  own logs.
- Record a UTC timestamp for every observation (`date -u +%FT%TZ`).

## 1. Setup

Set these shell variables once. Adjust the broker options to the test broker; keep
credentials out of anything you paste into the report.

```bash
C=$(docker ps -q --filter name=airthings2mqtt)   # must print exactly one ID
docker ps --filter name=airthings2mqtt --format '{{.ID}} {{.Names}} {{.Image}} {{.Status}}'
MQTT="-h localhost -p 1883"                       # add -u/-P if the broker needs them
P=airthings2mqtt                                  # AIRTHINGS2MQTT_MQTT__TOPIC_PREFIX, if changed
D=airthings                                       # AIRTHINGS2MQTT_DEVICE_NAME, if changed
```

If more than one container matches (a multi-device setup), run the checks once per
container and report each separately.

## 2. Confirm the Deployed Version

The release is **0.3.0** (Release Please may pick a different number; use what it
published). Images are `ghcr.io/ff-fab/airthings2mqtt:<version>` and `:latest`.

```bash
docker inspect --format '{{.Config.Image}} {{.Image}}' "$C"        # tag and local image ID
docker image inspect --format '{{json .RepoDigests}}' "$(docker inspect --format '{{.Image}}' "$C")"
docker exec "$C" airthings2mqtt --version                           # expect: airthings2mqtt v0.3.0
mosquitto_sub $MQTT -t "$P/status" -C 1 -W 10 | jq '{status, version}'   # expect version "0.3.0"
```

Record the host as well, since the bead is about Pi speed:

```bash
uname -m; nproc; cat /proc/device-tree/model 2>/dev/null; echo
docker version --format '{{.Server.Version}}'
docker inspect --format 'NanoCpus={{.HostConfig.NanoCpus}} CpuQuota={{.HostConfig.CpuQuota}} CpuPeriod={{.HostConfig.CpuPeriod}}' "$C"
```

`NanoCpus=500000000` means `cpus: 0.5`. **AC-1 assumes that limit.** If the container
runs without a CPU limit, say so prominently in the report, and run the optional limited
measurement in [section 3.4](#34-disruptive-optional-measure-at-cpus-05).

## 3. Health Probe (cap-oxdp.14)

The probe settings in both the image and the shipped `compose.yml` are
`interval 60s, timeout 30s, start_period 180s, retries 3`, running
`airthings2mqtt health`. The probe reads `/tmp/airthings2mqtt-health.json` (set by
`COSALETTE_HEALTH_FILE`) and prints `healthy (health file Ns old)` on success, or
`unhealthy: <reason>` with exit code 1. By default it fails only when the file is too
old or the device status is `stale`.

Confirm the effective settings first; the test deployment may override them:

```bash
docker inspect --format '{{json .Config.Healthcheck}}' "$C" | jq
```

`Interval`, `Timeout` and `StartPeriod` are in nanoseconds (60 s = `60000000000`).

### 3.1 Time to healthy after start (AC-2)

Docker keeps the last five probe results with start and end times. Read them together
with the container start time:

```bash
docker inspect --format '{{.State.StartedAt}}' "$C"
docker inspect --format '{{json .State.Health}}' "$C" | jq
```

Report the time from `StartedAt` to the `End` of the first probe with `ExitCode 0`. If
the container has run long enough that the first probes are gone from the log, poll it
right after the next start instead. Run this immediately after the deployment starts
the container, while the status is still `starting`:

```bash
start=$(date +%s)
while :; do
  s=$(docker inspect --format '{{.State.Health.Status}}' "$C")
  echo "$(date -u +%FT%TZ) +$(( $(date +%s) - start ))s $s"
  [ "$s" = healthy ] && break
  [ $(( $(date +%s) - start )) -gt 400 ] && echo "TIMEOUT" && break
  sleep 5
done
```

Pass: `healthy` within 180 s of `StartedAt`. Note that the first probe runs only after
the first 60 s interval, so values between about 60 s and 180 s are normal. The PR test
on core-02 stayed `starting` for about 185 s, which is what this bead is about.

If you missed the start, the only way to repeat it is a restart: see
[section 3.4](#34-disruptive-optional-measure-at-cpus-05).

### 3.2 Probe duration (AC-1)

Run the probe by hand ten times, at least 10 s apart, and record each wall-clock time:

```bash
for i in $(seq 1 10); do
  printf '%s run %02d: ' "$(date -u +%FT%TZ)" "$i"
  { /usr/bin/time -f '%e s' docker exec "$C" airthings2mqtt health; } 2>&1 | tr '\n' ' '
  echo
  sleep 10
done
```

If `/usr/bin/time` is missing, use the shell keyword: `time docker exec "$C" airthings2mqtt health`.

Also derive the durations Docker itself measured, from the probe log:

```bash
docker inspect --format '{{json .State.Health.Log}}' "$C" \
  | jq -r '.[] | "\(.Start) exit=\(.ExitCode) \(.Output|gsub("\n";" "))"'
```

Compute `End - Start` for each entry and report them. Report min, median and max of all
durations. Pass: max well under 30 s. As a guide, flag anything above 15 s (half the
timeout), and report any probe whose output mentions a timeout.

While the probes run, note the host load (`uptime`) and container CPU
(`docker stats --no-stream "$C"`), because a busy Pi slows the import.

### 3.3 Stays healthy across a poll (AC-3)

The app reads the sensor every `AIRTHINGS2MQTT_POLL_INTERVAL` seconds (default 1500 s,
25 minutes). A BLE read uses CPU at the same time as the probe, so the probe must stay
fast across one. Sample every minute for at least **two poll intervals** (about 60
minutes with the default), so at least one poll falls inside the window:

```bash
for i in $(seq 1 60); do
  echo "$(date -u +%FT%TZ) $(docker inspect --format '{{.State.Health.Status}} streak={{.State.Health.FailingStreak}}' "$C")"
  sleep 60
done | tee /tmp/airthings2mqtt-health-samples.txt
```

In parallel, record the polls from the log so you can line them up with the samples:

```bash
docker logs --since 70m -t "$C" 2>&1 | grep -E 'Airthings read ok|error|Error|unhealthy'
```

Each successful poll logs `Airthings read ok: mac=**:<last octets> rssi=... protocol=...
temperature=... humidity=... radon_24h_avg=... radon_long_term_avg=...`.

Pass: every sample is `healthy` with `streak=0`, and at least one `Airthings read ok`
line falls inside the window. Then keep a lighter watch for **24 hours** (one sample
every 15 minutes) to catch a probe that fails only occasionally: the probe also turns
unhealthy when the device becomes `stale` (no successful read for about 62 minutes with
default settings), which a single hour cannot rule out.

### 3.4 DISRUPTIVE (optional): measure at `cpus: 0.5`

Only with operator consent, and only if section 2 showed no 0.5 CPU limit or you
missed the start in 3.1. Restarting costs one missed poll at most.

```bash
docker update --cpus 0.5 "$C"        # temporary; reverted by the next compose up
docker restart "$C"
```

Then repeat 3.1 and 3.2 immediately. Record that the limit was set by you, and restore
the previous state afterwards (`docker update --cpus 0 "$C"` removes the limit, or
re-run the deployment's `docker compose up -d`).

## 4. Release Smoke Checks

Short checks of the other changes in 0.3.0. Run them once after deployment, unless
noted.

### 4.1 Dedicated user and hardening

0.3.0 runs as UID/GID **10001** (0.2.x used 1000), adds no capabilities and sets
`no-new-privileges`. The host needs an account for UID 10001, or D-Bus refuses the
connection and every poll fails.

```bash
docker exec "$C" id                                   # expect uid=10001 gid=10001
getent passwd 10001; getent group 10001               # host: expect one entry each
docker inspect --format '{{.HostConfig.CapAdd}} {{.HostConfig.SecurityOpt}}' "$C"
# expect: [] [no-new-privileges:true]   (a custom compose file may differ: record it)
docker exec "$C" grep -E '^Cap(Eff|Bnd)' /proc/1/status   # CapEff must be all zeros
```

If the host has the optional BlueZ write policy at
`/etc/dbus-1/system.d/airthings2mqtt-bluez.conf`, check it denies writes and allows
reads. Both commands are harmless: the write uses a wrong value type, so BlueZ rejects
it even without the policy.

```bash
ls -l /etc/dbus-1/system.d/airthings2mqtt-bluez.conf
docker exec "$C" dbus-send --system --print-reply --dest=org.bluez /org/bluez/hci0 \
    org.freedesktop.DBus.Properties.Set \
    string:org.bluez.Adapter1 string:Powered variant:string:probe
# with policy: org.freedesktop.DBus.Error.AccessDenied ; without: InvalidSignature
docker exec "$C" dbus-send --system --print-reply --dest=org.bluez /org/bluez/hci0 \
    org.freedesktop.DBus.Properties.Get string:org.bluez.Adapter1 string:Powered
# expect: variant boolean true
```

### 4.2 Startup log and state file

```bash
docker logs -t "$C" 2>&1 | head -100
docker logs -t "$C" 2>&1 | grep -E 'MQTT connected to|Airthings read ok|Permission denied|Corrupt or unreadable store file|non-object JSON|Overwriting|Traceback|ERROR|WARNING'
docker exec "$C" ls -ln /app/data                     # expect owner 10001 10001
docker exec "$C" cat /app/data/store.json | jq '.airthings.reset_tracker'
```

Expected: `MQTT connected to ...`, then `Airthings read ok: ...` within the first poll.
No `Permission denied` (an upgraded volume still owned by UID 1000 causes it), no
traceback, no store warnings.

After the first successful read, `reset_tracker` holds `last_lta` (the last long-term
average), `reset_at`, `lta_before_reset` and `reset_count`. On an upgrade from 0.2.x it
appears only after the first read; `reset_at` stays `null` and `reset_count` stays `0`
unless a reset was detected. The top-level key is the device name (`airthings` by
default).

### 4.3 MQTT payloads

```bash
mosquitto_sub $MQTT -v -F '%I retained=%r %t %p' -W 15 \
  -t "$P/$D/state" -t "$P/$D/availability" -t "$P/status"
```

Retained messages arrive at once (`retained=1`); later ones come with each poll and
heartbeat. Check `$P/$D/state` has all eight keys:

| Field                 | Expect                                                         |
| --------------------- | -------------------------------------------------------------- |
| `temperature`         | number, °C                                                     |
| `humidity`            | number, %                                                      |
| `radon_24h_avg`       | integer, or `null` while `warming_up` or for a garbled frame   |
| `radon_long_term_avg` | integer, or `null` under the same rules                        |
| `last_read`           | ISO 8601 UTC, within one poll interval of now                  |
| `rssi`                | integer dBm, or `null`                                         |
| `measurement_state`   | `ok` normally; `warming_up` or `provisional` after a reset     |
| `sensor_reset_at`     | `null`, or ISO 8601 UTC of the last detected reset             |

`$P/$D/availability` must be `online`, and `$P/status` must show `"status": "online"`
and `devices.airthings.status` `"ok"`.

A radon value of `0` together with the other radon value `0` must **never** appear on
the state topic; the app publishes `null` instead. A radon value above 16383 must never
appear either. Either one is a finding.

During the 24-hour watch, also log errors (not retained, so subscribe continuously):

```bash
mosquitto_sub $MQTT -v -F '%I %t %p' -t "$P/error" -t "$P/$D/error" | tee /tmp/airthings2mqtt-errors.txt
```

Record each `error_type` (`ble_device_not_found`, `ble_connection`, `ble_timeout` or
`ble_read`) with its count. Occasional retried BLE errors are normal; `availability`
turning `offline` is worth reporting with its timestamps. Check that no error `message`
contains a full Bluetooth MAC.

### 4.4 Home Assistant (if available)

```bash
mosquitto_sub $MQTT -v -t 'homeassistant/#' -W 10 | grep -i airthings
```

The device should expose: temperature, humidity, **Radon (24h avg)**, **Radon
(long-term avg)**, and four diagnostic entities: **Last read** (timestamp), **Signal
strength** (dBm), **Measurement state** (enum with options `warming_up`, `provisional`,
`ok`) and **Sensor reset** (timestamp). In the Home Assistant UI, check that
Measurement state shows a value, Sensor reset shows *unknown* (no reset detected) or a
time, and that no entity is *unavailable* while `availability` is `online`. A radon
entity shows *unknown*, not `0`, while the sensor warms up.

### 4.5 Sensor reset lifecycle (only if a reset happens)

A battery change makes the sensor forget its radon averages and report `0/0` until it
has new ones. The app then publishes radon as `null` with `warming_up`, then the values
as `provisional` for `AIRTHINGS2MQTT_LTA_SETTLE_DAYS` days (default 30), then `ok`. It
logs once, at `INFO`:

```text
Airthings sensor reset detected (battery change or power loss): long-term average <old> -> <new>; radon is withheld while the sensor reports 0/0
```

and `sensor_reset_at` plus `reset_tracker.reset_count` change. A restart must not log
the same reset again.

**DISRUPTIVE (optional):** to test this, take the batteries out of the sensor for a
minute and put them back. Only with operator consent: the sensor loses its long-term
radon history for good, and the 24-hour average takes about a day to return. Watch
`$P/$D/state` and the log for the first hours, then once a day. Do **not** corrupt the
state file to test validation; that path is covered by unit tests.

## 5. Report Template

Return the report as Markdown, filled in. Keep raw excerpts short (a few lines each) and
redacted.

```markdown
# cap-oxdp.14 test-environment report

- Reporter / date (UTC):
- Host: model, arch, nproc, Docker version:
- Container: name, image tag, image ID, RepoDigest:
- `airthings2mqtt --version`: ; status `version`:
- CPU limit (NanoCpus / CpuQuota): ; set by me in 3.4? yes/no
- Effective healthcheck (interval/timeout/start_period/retries):
- Poll interval (if not default):

## cap-oxdp.14

| AC   | Result (pass/fail/not run) | Observed                                   |
| ---- | -------------------------- | ------------------------------------------ |
| AC-1 |                            | probe min/median/max s, n runs, host load  |
| AC-2 |                            | StartedAt, first healthy at, delta s       |
| AC-3 |                            | samples, unhealthy count, polls in window  |

Probe durations (s):
Health.Log excerpt:

## Release smoke checks

| Check                          | Result | Observed |
| ------------------------------ | ------ | -------- |
| 4.1 UID 10001, host account    |        |          |
| 4.1 CapAdd / SecurityOpt / CapEff |     |          |
| 4.1 BlueZ policy (if installed)|        |          |
| 4.2 startup log clean          |        |          |
| 4.2 store.json owner, reset_tracker |   |          |
| 4.3 state payload, 8 keys      |        |          |
| 4.3 no 0/0 radon, no >16383    |        |          |
| 4.3 availability / status      |        |          |
| 4.3 errors over 24 h           |        | counts per error_type |
| 4.4 Home Assistant entities    |        |          |
| 4.5 sensor reset (if any)      |        |          |

## Findings

One block per finding, see below.

## Anomalies and notes

Anything odd that is not clearly a finding.
```

## 6. Findings

A finding is any of:

- an acceptance criterion of cap-oxdp.14 that fails, or a probe slower than 15 s;
- `.State.Health.Status` `unhealthy`, or a probe that times out;
- a payload, log line or entity that contradicts sections 4.1 to 4.5;
- a traceback, an unexpected `ERROR` or `WARNING`, or a full MAC in a log or error
  payload.

For each finding report: a one-line title, the time (UTC), what you expected, what you
saw, the exact command, a redacted output or log excerpt, and whether it repeats. Note
anything you changed in the environment before it happened.

Findings become bug-fix beads after the release; they do not block it. A failed AC of
cap-oxdp.14 is an input to the maintainer's decision (raise the timeout or a lighter
upstream probe), so report the numbers rather than a recommendation.
