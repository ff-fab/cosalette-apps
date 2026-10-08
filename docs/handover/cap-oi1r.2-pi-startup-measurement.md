# Pi startup measurement: cosalette lazy exports

This handover compares the airthings2mqtt image before and after the cosalette
lazy-export change. It uses the app's `--dry-run` reader, a throwaway local
Mosquitto broker, and a 0.5 CPU quota. No sensor or production broker is needed.

## Run on the Raspberry Pi

Requirements: Linux Docker host, Docker access, and `mosquitto_sub` from
`mosquitto-clients`. The script uses host networking for the app and binds its
temporary broker to `127.0.0.1:18883`; stop any service already using that port
or choose another with `STARTUP_BENCH_PORT`.

From the repository root, pull the published baseline and fetch PR #331's head.
The abbreviated commit must still be `97ee932` (cosalette 0.11.2); the check
prevents silently benchmarking a later PR revision. The archive gives Docker an
isolated source tree without checking out or changing another worktree:

```sh
docker pull ghcr.io/ff-fab/airthings2mqtt:0.3.1
git fetch origin refs/pull/331/head
candidate=$(git rev-parse FETCH_HEAD)
test "${candidate:0:7}" = 97ee932 || {
  echo "PR #331 head changed; expected 97ee932, got $candidate" >&2
  exit 1
}
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT
git archive "$candidate" | tar -x -C "$build_dir"
docker build -f "$build_dir/apps/airthings2mqtt/Dockerfile" \
  -t airthings2mqtt:cosalette-0.11.2 "$build_dir"
for image in ghcr.io/ff-fab/airthings2mqtt:0.3.1 airthings2mqtt:cosalette-0.11.2; do
  for run in 1 2 3; do
    scripts/startup-bench.sh "$image"
  done
done
```

The script starts Mosquitto, waits for its listener, arms a subscriber on
`airthings2mqtt/status`, then starts the app with `--dry-run`. It reports elapsed
milliseconds from app container start to the first status heartbeat, cumulative
container CPU milliseconds from cgroup v2 `usage_usec`, and PID 1 `VmRSS` in
MiB. The elapsed timer stops immediately after the subscriber captures the first
status message. CPU and RSS are read in the following `docker exec`, so they are
near-startup samples taken just after that capture, not values from the exact
message timestamp. The subscriber times out after 120 seconds. The script
removes both containers on exit. The elapsed time includes MQTT connection and
is measured on the same host for both images.

The result is an operational comparison, not a controlled microbenchmark: CPU
temperature, background load, broker startup, and run order can affect it. Keep
the host, power supply, Docker version, broker port, and run conditions the same;
alternate image order on repeated rounds if investigating small differences.

## Recorded results

Raspberry Pi 4 B Rev 1.2 (aarch64), Debian 13, Docker 29.8.1, cgroup v2;
three runs per image, `--cpus 0.5`, local throwaway Mosquitto. The baseline was
the published 0.3.1 image, cross-checked against a local build. The 0.3.2 image
was not published at measurement time, so the candidate was built from source
commit `97ee932` (release-please head on `dff6285`, cosalette 0.11.2):

| Image | First status | CPU sample near status | RSS sample near status |
|---|---:|---:|---:|
| airthings2mqtt 0.3.1 (cosalette 0.11.0, post-#326) | 4785 ms | 2360 ms | 55.7 MiB |
| airthings2mqtt 0.3.2 (cosalette 0.11.2) | 3818 ms | 1888 ms | 48.8 MiB |

These are the recorded representative values; retain individual run output
alongside any future comparison. The earlier amd64 dry-run reference (three
runs, same CPU quota) was 2645 vs 2367 ms to first status, 681 vs 554 ms CPU,
and 55.3 vs 48.3 MiB VmRSS. The Pi result is the completion evidence for
`cap-oi1r.2`; the amd64 numbers are a separate reference, not a substitute for
the Pi measurement.
