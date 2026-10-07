# Pi Measurement: Cost of the cosalette 0.11.1 Native Health Probe (cap-2ya9)

Instructions for the agent that has access to the Raspberry Pi hosts. You have a shell on
each Pi, Docker, and the deployed containers. You do not have the source repository;
everything you need is on this page.

## Purpose

Bead **cap-2ya9** asks if the monorepo must reinstate a Docker `HEALTHCHECK` now that
cosalette 0.11.1 ships a cheap probe. The decision record is ADR-010. It dropped the
`HEALTHCHECK` for two reasons:

1. **Cost.** The old probe (`<app> health`) started Python and imported the framework and
   the app. On a Raspberry Pi 4 at `cpus: 0.5` one probe took 11 to 13 s when idle and 27
   to 30 s during start-up. Two overlapping probes hit the 30 s timeout.
2. **No consumer.** Nothing reads the Docker health status: no autoheal, no monitoring,
   no `depends_on: service_healthy`.

cosalette 0.11.1 replaces the probe with `cosalette-health`, a native Rust binary of
about 450 KB that the platform wheels install. It reads the health file and does not
start Python. The upstream figure is 1.2 ms wall time on a fast x86_64 desktop. **Your job
is to measure reason 1 again on the Pi hardware.** The maintainer decides reason 2 and
the outcome. You supply the numbers. Do not recommend an option.

## Ground Rules

- **Do not change a deployed container.** Do not restart it, change its configuration or
  edit its files. The script below uses its own throwaway containers, `probe-bench` and
  `probe-hc`, and removes them when it ends.
- **Ask the operator before you run the script on a host that runs production
  services.** The script uses up to 0.5 CPU for about 15 minutes. It also pulls
  `python:3.14-alpine` from Docker Hub and `cosalette==0.11.1` from PyPI.
- **Redact secrets** from everything you return: MQTT credentials, tokens, `.env`
  contents and internal host names other than the Pi model.
- Record a UTC timestamp for each observation. The script prints one for each section.

## Which Hosts

Run the script on each Pi that you can reach, in this order:

1. **Raspberry Pi Zero 2 W.** This is the smallest target host. If its OS is 32-bit, the
   containers run as `armv7l`. If its OS is 64-bit, they run as `aarch64`. Both have a
   native wheel, and the result for each is important.
2. **Raspberry Pi 4.** ADR-010 measured the old probe on this model. Use the same host as
   the earlier probe-cost measurement if you can.
3. Any other Pi model, if you have time.

If a host has no free capacity, or the operator does not agree, skip that host and say
so in the report.

## 1. Preconditions

On each host, check these items and record the output:

```bash
date -u +%FT%TZ
uname -m; getconf LONG_BIT; nproc
tr -d '\0' </proc/device-tree/model; echo
docker version --format '{{.Server.Version}}'
python3 --version            # the script needs python3 on the host (3.9 or newer)
docker ps --format '{{.Names}} {{.Image}} {{.Status}}'
uptime                       # load average before the run
```

If `python3` is missing on the host, stop. Report the problem and do not install
packages on the host.

Run the script only while the load average is low (less than about 0.5 per core). Do
not run it during a deployment, an update or a backup. These make the numbers too noisy.

## 2. Run the Script

Save the script below as `probe-bench.sh` in a temporary directory on the host. Then
run it and keep the full output:

```bash
sh probe-bench.sh 2>&1 | tee "probe-bench-$(tr -d '\0' </proc/device-tree/model | tr ' ' '_')-$(date -u +%Y%m%dT%H%M%SZ).log"
```

It needs about 15 minutes. The longest steps are a 120 s idle baseline and a 300 s
window with a real `HEALTHCHECK`. On a Pi Zero 2, the first `pip install` and the image
pull can add a few minutes.

What the script measures, all at `--cpus 0.5`:

| Section | What                                                                             | Why                                                         |
| ------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| Setup   | The wheel tag and the file type of `cosalette-health`                            | Confirms that the host got the native binary                |
| 1       | Wall time, CPU and peak RSS of the native probe and of the stdlib fallback, idle | The direct cost of one probe                                |
| 2       | The same while a busy loop uses the full CPU quota of the container              | Replaces the "during start-up" case of ADR-010              |
| 3       | Host wall time, daemon CPU, container CPU and whole-host CPU for each `docker exec` | Docker starts each probe as an exec, and that has a cost of its own |
| 4       | A real `HEALTHCHECK` (interval 2 s) for 300 s                                    | The CPU for each probe, as Docker really runs it            |

The script does not need `cosalette`'s dependencies. It installs the wheel with
`--no-deps`, because the probe uses only the standard library.

```sh
#!/bin/sh
# cap-2ya9: cost of the cosalette 0.11.1 native health probe at cpus 0.5.
# Uses throwaway containers only; touches no deployed container.
set -eu

IMG=python:3.14-alpine
COSALETTE=cosalette==0.11.1
B=probe-bench          # probe cost inside the container
H=probe-hc             # real Docker HEALTHCHECK
WORK=$(mktemp -d)
trap 'docker rm -f $B $H >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT

say() { printf '\n=== %s (%s)\n' "$1" "$(date -u +%FT%TZ)"; }

# --- helper 1: per-run wall, CPU and peak RSS via wait4 (runs inside the container)
cat >"$WORK/bench.py" <<'PY'
import os, statistics, sys, time
n, cmd = int(sys.argv[1]), sys.argv[2:]
walls, cpus, codes = [], [], set()
for _ in range(n):
    t0 = time.perf_counter()
    pid = os.posix_spawnp(cmd[0], cmd, os.environ, file_actions=[(os.POSIX_SPAWN_OPEN, fd, os.devnull, os.O_WRONLY, 0) for fd in (1, 2)])
    _, st, ru = os.wait4(pid, 0)
    walls.append((time.perf_counter() - t0) * 1000)
    cpus.append((ru.ru_utime + ru.ru_stime) * 1000)
    codes.add(os.waitstatus_to_exitcode(st))
    time.sleep(0.2)
def f(xs):
    xs = sorted(xs)
    return f"median {statistics.median(xs):9.1f}  p90 {xs[max(0, int(len(xs) * 0.9) - 1)]:9.1f}  max {xs[-1]:9.1f}"
print(f"{' '.join(cmd)}  runs={n}  exit codes={sorted(codes)}")
print(f"  wall ms: {f(walls)}")
print(f"  cpu  ms: {f(cpus)}")
PY

# --- helper 2: CPU of the Docker daemons on the host (dockerd, containerd, shims, runc)
cat >"$WORK/daemon.py" <<'PY'
import os, subprocess, sys, time
TICK = os.sysconf("SC_CLK_TCK")
def cpu():
    t = 0
    for p in filter(str.isdigit, os.listdir("/proc")):
        try:
            s = open(f"/proc/{p}/stat").read()
        except OSError:
            continue
        if s[s.index("(") + 1 : s.rindex(")")].startswith(("dockerd", "containerd", "runc")):
            t += sum(int(x) for x in s[s.rindex(")") + 2 :].split()[11:15])
    return t * 1000 / TICK
def host():                   # busy CPU of the whole host (all cores), ms
    f = [int(x) for x in open("/proc/stat").readline().split()[1:]]
    return (sum(f[:8]) - f[3] - f[4]) * 1000 / TICK
mode = sys.argv[1]
if mode == "idle":            # daemon and host-wide CPU in ms per second, no extra work
    secs = float(sys.argv[2]); a, h = cpu(), host(); time.sleep(secs)
    print(f"{(cpu() - a) / secs:.2f} {(host() - h) / secs:.2f}")
elif mode == "exec":          # host wall time and daemon CPU per `docker exec`
    n, cmd = int(sys.argv[2]), ["docker", "exec", *sys.argv[3:]]
    walls = []; a, h = cpu(), host(); t0 = time.monotonic()
    for _ in range(n):
        s = time.perf_counter()
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        walls.append((time.perf_counter() - s) * 1000); time.sleep(0.3)
    print(f"{(cpu() - a):.1f} {host() - h:.1f} {time.monotonic() - t0:.1f} " + " ".join(f"{w:.1f}" for w in walls))
PY

daemon_idle() { python3 "$WORK/daemon.py" idle "$1"; }

cg_usec() { docker exec "$1" sh -c 'grep usage_usec /sys/fs/cgroup/cpu.stat | cut -d" " -f2'; }

exec_cost() {  # $1 runs, $2 container, rest: command
  idle=$(daemon_idle 30)
  u0=$(cg_usec "$2")
  out=$(python3 "$WORK/daemon.py" exec "$@")
  u1=$(cg_usec "$2")
  echo "$out" | python3 -c '
import statistics, sys
d_idle, h_idle, n, cg = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
cpu, hst, secs, *w = map(float, sys.stdin.read().split())
w.sort()
print(f"  host wall ms: median {statistics.median(w):.1f}  p90 {w[max(0, int(n * 0.9) - 1)]:.1f}  max {w[-1]:.1f}")
print(f"  daemon CPU ms per exec: {(cpu - d_idle * secs) / n:.1f}  (idle {d_idle:.1f} ms/s subtracted)")
print(f"  container cgroup CPU ms per exec: {cg / 1000 / (n + 1):.1f}")
print(f"  whole-host CPU ms per exec (incl. docker CLI): {(hst - h_idle * secs) / n:.1f}  (idle {h_idle:.1f} ms/s subtracted)")
' $idle "$1" "$((u1 - u0))"
}

say "Host"
uname -m; nproc; { tr -d '\0' </proc/device-tree/model && echo; } 2>/dev/null || echo "no /proc/device-tree/model"
docker version --format 'docker {{.Server.Version}}'
getconf LONG_BIT

say "Setup: $B ($IMG, cpus 0.5, $COSALETTE without dependencies)"
docker rm -f $B $H >/dev/null 2>&1 || true
docker run -d --name $B --cpus 0.5 -e COSALETTE_HEALTH_FILE=/tmp/health.json --entrypoint sh $IMG -c \
  'while :; do printf "{\"status\":\"online\",\"devices\":{},\"written_at\":%s,\"interval\":60.0,\"health_file_version\":1}" "$(date +%s)" >/tmp/health.json.tmp && mv /tmp/health.json.tmp /tmp/health.json; sleep 60; done' >/dev/null
docker exec $B pip install -q --root-user-action=ignore --disable-pip-version-check --no-deps "$COSALETTE"
docker cp "$WORK/bench.py" $B:/bench.py
docker exec $B sh -c 'cat /usr/local/lib/python3.14/site-packages/cosalette-*.dist-info/WHEEL | grep Tag; ls -l /usr/local/bin/cosalette-health; head -c4 /usr/local/bin/cosalette-health | od -c | head -1; cosalette-health; echo "exit=$?"'

say "1. Probe cost inside the container, idle (cpus 0.5)"
docker exec $B python /bench.py 50 cosalette-health
docker exec $B python /bench.py 20 python -m cosalette._health._probe
echo "  peak RSS (busybox time -v, 5 runs):"
docker exec $B sh -c 'for i in 1 2 3 4 5; do /usr/bin/time -v cosalette-health 2>&1 | grep "Maximum resident"; done'
docker exec $B sh -c '/usr/bin/time -v python -m cosalette._health._probe 2>&1 | grep "Maximum resident"'

say "2. Probe cost while a busy loop uses the full 0.5 CPU quota (start-up contention)"
docker exec -d $B python -c 'while True: pass'
sleep 3
docker exec $B python /bench.py 30 cosalette-health
docker exec $B python /bench.py 10 python -m cosalette._health._probe
docker exec $B pkill -f 'while True' || true

say "3. Host-side cost of docker exec (what a probe from outside costs)"
echo "docker exec $B true"
exec_cost 40 $B true
echo "docker exec $B cosalette-health"
exec_cost 40 $B cosalette-health

say "4. Real Docker HEALTHCHECK (interval 2s, 5 min)"
IDLE=$(daemon_idle 120)
echo "  idle (daemon, whole host): $IDLE ms/s, measured over 120 s before $H starts"
docker run -d --name $H --cpus 0.5 -e COSALETTE_HEALTH_FILE=/tmp/health.json --entrypoint sh \
  --health-cmd cosalette-health --health-interval 2s --health-timeout 5s --health-retries 3 $IMG -c \
  'pip install -q --root-user-action=ignore --disable-pip-version-check --no-deps '"$COSALETTE"' && while :; do printf "{\"status\":\"online\",\"devices\":{},\"written_at\":%s,\"interval\":60.0,\"health_file_version\":1}" "$(date +%s)" >/tmp/health.json.tmp && mv /tmp/health.json.tmp /tmp/health.json; sleep 60; done' >/dev/null
until [ "$(docker inspect -f '{{.State.Health.Status}}' $H)" = healthy ]; do sleep 2; done
c0=$(docker exec $H sh -c 'grep usage_usec /sys/fs/cgroup/cpu.stat | cut -d" " -f2')
WITH=$(daemon_idle 300)
c1=$(docker exec $H sh -c 'grep usage_usec /sys/fs/cgroup/cpu.stat | cut -d" " -f2')
echo "  with $H (daemon, whole host): $WITH ms/s over 300 s"
python3 -c "di, hi = '$IDLE'.split(); dw, hw = '$WITH'.split()
print(f'  daemon CPU per probe: {(float(dw) - float(di)) * 2:.1f} ms')
print(f'  whole-host CPU per probe: {(float(hw) - float(hi)) * 2:.1f} ms  (= (with - idle) x 2 s interval)')"
python3 -c "print(f'  container CPU (probes + idle shell): {($c1 - $c0) / 1000 / 300:.2f} ms/s over 300 s')"
echo "  Docker probe durations (Start to End, last 5):"
docker inspect -f '{{json .State.Health.Log}}' $H | python3 -c '
import json, sys, datetime as d
t = lambda s: d.datetime.fromisoformat(s[:26].rstrip("Z") + "+00:00").timestamp()
for e in json.load(sys.stdin):
    ms, code = (t(e["End"]) - t(e["Start"])) * 1000, e["ExitCode"]
    print(f"    {ms:7.1f} ms  exit {code}")
'
docker inspect -f '  status={{.State.Health.Status}} failing_streak={{.State.Health.FailingStreak}}' $H

say "Done"
```

### If the script fails

- **The `Tag:` line in Setup says `py3-none-any`, or `cosalette-health` is not an ELF
  file.** pip did not find a native wheel for this platform. The probe then runs as the
  Python fallback. Report the `Tag:` line and `uname -m`, and continue: sections 1 to 4
  still give useful numbers.
- **`pip install` fails.** Report the error. Do not try to work around it.
- **Section 4 waits for ever at "until ... healthy".** Press Ctrl+C, then run
  `docker inspect -f '{{json .State.Health}}' probe-hc` and report the output. Remove
  the containers with `docker rm -f probe-bench probe-hc`.
- **Any other error.** Report the output up to the error. Run
  `docker rm -f probe-bench probe-hc` to clean up.

## 3. Idle CPU of a Deployed App (observe only)

ADR-010 compared the probe with the idle app. On amd64 the idle app used about 1 s of
CPU per hour. To give the same comparison on the Pi, read the CPU counter of one
deployed cosalette app twice, 10 minutes apart. This only reads a file; it does not
change the container.

```bash
C=airthings2mqtt     # or any other deployed cosalette app; use its container name
docker exec "$C" grep usage_usec /sys/fs/cgroup/cpu.stat; date -u +%FT%TZ
sleep 600
docker exec "$C" grep usage_usec /sys/fs/cgroup/cpu.stat; date -u +%FT%TZ
docker inspect --format '{{.Config.Image}} NanoCpus={{.HostConfig.NanoCpus}}' "$C"
```

The idle CPU in seconds per hour is `(second - first) / 1e6 * 6`. If the file is
missing, the host uses cgroup v1. In that case, report this and skip the section.

## 4. Report

Return one block for each host. Attach the full log of the script. Fill in this table
from the log:

| Item                                                        | Value |
| ----------------------------------------------------------- | ----- |
| Pi model, `uname -m`, `getconf LONG_BIT`, Docker version    |       |
| Wheel `Tag:` and size of `cosalette-health`                 |       |
| 1. Native probe, idle: median and p90 wall ms, median CPU ms |       |
| 1. Native probe: peak RSS (KiB)                             |       |
| 1. Fallback probe, idle: median wall ms, median CPU ms      |       |
| 2. Native probe, busy: median and max wall ms               |       |
| 2. Fallback probe, busy: median and max wall ms             |       |
| 3. `docker exec true`: host wall ms, daemon, container and whole-host CPU ms |  |
| 3. `docker exec cosalette-health`: same                     |       |
| 4. Idle and with `HEALTHCHECK`: daemon and whole-host ms/s  |       |
| 4. Daemon and whole-host CPU per probe (ms)                 |       |
| 4. Container CPU ms/s, Docker probe durations (ms)          |       |
| 4. Final health status and failing streak                   |       |
| Idle app CPU (s per hour), from section 3                   |       |
| Load average before and after the run                       |       |

Also report anything unusual: a probe that failed, a large `max` value, a high idle
daemon rate, or a throttled CPU (`vcgencmd get_throttled`, if available).

## Reference: amd64 Results

The maintainer ran the same script on amd64. Use these numbers only to check that your
results are plausible. Do not compare the hosts in your report.

Host: x86_64, 6 cores (WSL2 devcontainer), Docker 29.8.0, all containers at `--cpus 0.5`,
2026-10-07. Wheel tag `cp314-abi3-musllinux_1_2_x86_64`, `cosalette-health` is an ELF
file of 459,680 bytes.

| Item                                                     | amd64                                    |
| -------------------------------------------------------- | ---------------------------------------- |
| 1. Native probe, idle: wall ms (median, p90), CPU ms     | 0.9, 2.2; 0.5                            |
| 1. Native probe: peak RSS                                | about 780 KiB                            |
| 1. Fallback probe, idle: wall ms, CPU ms                 | 101; 77                                  |
| 2. Native probe, busy: wall ms (median, max)             | 0.6, 2.1                                 |
| 2. Fallback probe, busy: wall ms (median, max)           | 312, 402                                 |
| 3. `docker exec true`: host wall ms, daemon CPU ms       | 138; 60                                  |
| 3. Container cgroup CPU ms per exec                      | 29 (for `true` and for the probe)        |
| 4. Daemon CPU per probe, Docker probe durations          | 69 ms; 94 to 257 ms                      |
| 4. Final health status                                   | `healthy`, failing streak 0              |

On this host the whole-host counter was noisy (190 to 240 ms/s when idle), so its value
for each probe (56 to 128 ms) is only approximate. On a quiet Pi it is more useful.

For comparison, the old probe of ADR-010 (`airthings2mqtt health`, image 0.3.0) on the
same host: 3.6 s wall time, 1.83 s CPU and 54 MiB peak RSS for each run. With cosalette
0.11.1 the Typer probes still cost 0.48 s CPU (`cosalette health`) and 0.54 to 0.88 s CPU
(`airthings2mqtt health`, `suncast health`).
