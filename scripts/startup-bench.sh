#!/usr/bin/env bash
# Compare one airthings2mqtt image's startup on Linux with an isolated broker.
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 IMAGE" >&2
    exit 2
fi
command -v docker >/dev/null
command -v mosquitto_sub >/dev/null || {
    echo "Install mosquitto-clients (mosquitto_sub is required)" >&2
    exit 2
}

image=$1
run_id="startup-bench-$$"
broker="${run_id}-broker"
app="${run_id}-app"
port=${STARTUP_BENCH_PORT:-18883}
status_file=$(mktemp)
sub_pid=

cleanup() {
    [[ -z "$sub_pid" ]] || kill "$sub_pid" 2>/dev/null || true
    docker rm -f "$app" "$broker" >/dev/null 2>&1 || true
    rm -f "$status_file"
}
trap cleanup EXIT INT TERM

docker run -d --name "$broker" -p "127.0.0.1:${port}:1883" eclipse-mosquitto:2 >/dev/null
ready=false
for _ in {1..30}; do
    if docker logs "$broker" 2>&1 | grep -q 'Opening ipv4 listen socket'; then
        ready=true
        break
    fi
    sleep 1
done
if [[ "$ready" != true ]]; then
    echo "Mosquitto did not become ready on 127.0.0.1:$port" >&2
    docker logs "$broker" >&2 || true
    exit 1
fi

# Arm the subscriber before starting the app. -C exits on the first status
# heartbeat, and the timestamp brackets startup through that message.
mosquitto_sub -h 127.0.0.1 -p "$port" -t airthings2mqtt/status -C 1 -W 120 \
    >"$status_file" &
sub_pid=$!
sleep 1
started_ns=$(date +%s%N)
docker run -d --name "$app" --cpus 0.5 \
    --network host \
    -e AIRTHINGS2MQTT_MQTT__HOST=127.0.0.1 \
    -e AIRTHINGS2MQTT_MQTT__PORT="$port" \
    -e AIRTHINGS2MQTT_MQTT__PROTOCOL_VERSION=5 \
    -e AIRTHINGS2MQTT_DEVICE_MAC=AA:BB:CC:DD:EE:FF \
    -e AIRTHINGS2MQTT_DEVICE_NAME=airthings \
    -e AIRTHINGS2MQTT_STORE_PATH=/tmp/startup-bench-store.json \
    "$image" --dry-run >/dev/null

if ! wait "$sub_pid"; then
    echo "No status heartbeat received; app logs:" >&2
    docker logs "$app" >&2 || true
    exit 1
fi
sub_pid=
finished_ns=$(date +%s%N)

# Sample cgroup v2 usage and PID 1 RSS immediately after the subscriber returns.
# These are near-heartbeat samples; docker exec cannot sample at the exact
# message timestamp.
metrics=$(docker exec "$app" sh -c \
    'awk "/^usage_usec / {print \$2}" /sys/fs/cgroup/cpu.stat; awk "/^VmRSS:/ {print \$2}" /proc/1/status')
cpu_usec=$(sed -n '1p' <<<"$metrics")
rss_kib=$(sed -n '2p' <<<"$metrics")
elapsed_ms=$(( (finished_ns - started_ns) / 1000000 ))
printf 'image=%s status=%s startup_ms=%s cpu_ms=%s rss_mib=%.1f\n' \
    "$image" "$(tr '\n' ' ' <"$status_file")" "$elapsed_ms" \
    "$((cpu_usec / 1000))" "$(awk -v k="$rss_kib" 'BEGIN {print k / 1024}')"
