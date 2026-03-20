---
title: Guides
---

# Guides

Practical guides for integrating, deploying, and operating vito2mqtt.

---

## Home Assistant Integration

vito2mqtt publishes telemetry as JSON to MQTT topics that Home Assistant can consume
directly via the [MQTT integration](https://www.home-assistant.io/integrations/mqtt/).

### Temperature sensors

```yaml title="configuration.yaml"
mqtt:
  sensor:
    - name: "Outdoor Temperature"
      state_topic: "vito2mqtt/vitodens200w/outdoor/state"
      value_template: "{{ value_json.outdoor_temperature }}"
      unit_of_measurement: "°C"
      device_class: temperature
      state_class: measurement

    - name: "Hot Water Temperature"
      state_topic: "vito2mqtt/vitodens200w/hot_water/state"
      value_template: "{{ value_json.hot_water_temperature }}"
      unit_of_measurement: "°C"
      device_class: temperature
      state_class: measurement

    - name: "Boiler Temperature"
      state_topic: "vito2mqtt/vitodens200w/burner/state"
      value_template: "{{ value_json.boiler_temperature }}"
      unit_of_measurement: "°C"
      device_class: temperature
      state_class: measurement

    - name: "Exhaust Temperature"
      state_topic: "vito2mqtt/vitodens200w/burner/state"
      value_template: "{{ value_json.exhaust_temperature }}"
      unit_of_measurement: "°C"
      device_class: temperature
      state_class: measurement
```

### Burner statistics

```yaml title="configuration.yaml"
mqtt:
  sensor:
    - name: "Burner Starts"
      state_topic: "vito2mqtt/vitodens200w/burner/state"
      value_template: "{{ value_json.burner_starts }}"
      state_class: total_increasing

    - name: "Burner Hours"
      state_topic: "vito2mqtt/vitodens200w/burner/state"
      value_template: "{{ value_json.burner_hours_stage1 }}"
      unit_of_measurement: "h"
      state_class: total_increasing

    - name: "Burner Modulation"
      state_topic: "vito2mqtt/vitodens200w/burner/state"
      value_template: "{{ value_json.burner_modulation }}"
      unit_of_measurement: "%"

    - name: "Plant Power Output"
      state_topic: "vito2mqtt/vitodens200w/burner/state"
      value_template: "{{ value_json.plant_power_output }}"
      unit_of_measurement: "%"
```

### Hot water setpoint control

```yaml title="configuration.yaml"
mqtt:
  number:
    - name: "Hot Water Setpoint"
      command_topic: "vito2mqtt/vitodens200w/hot_water/set"
      command_template: '{"hot_water_setpoint": {{ value }}}'
      min: 30
      max: 60
      step: 1
      unit_of_measurement: "°C"
      device_class: temperature
```

!!! note "No telemetry feedback for `hot_water_setpoint`"
    The `hot_water_setpoint` signal is not included in the `hot_water` telemetry
    group (which only publishes `hot_water_temperature` and
    `hot_water_outlet_temperature`). It is available via the command interface, but
    its current value is not published in MQTT telemetry, so the HA number entity
    will not show the current boiler value based on telemetry alone. To track the
    current setpoint, you can either read it explicitly using the command interface
    or rely on HA's optimistic mode.

### Error status

```yaml title="configuration.yaml"
mqtt:
  binary_sensor:
    - name: "Boiler Error"
      state_topic: "vito2mqtt/vitodens200w/diagnosis/state"
      value_template: "{{ value_json.error_status }}"
      payload_on: 1
      payload_off: 0
      device_class: problem
```

---

## Docker Deployment

### Docker Compose

```yaml title="docker-compose.yml"
services:
  vito2mqtt:
    image: ghcr.io/ff-fab/vito2mqtt:latest
    restart: unless-stopped
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
    env_file:
      - .env
    environment:
      - VITO2MQTT_SERIAL_PORT=/dev/ttyUSB0
      - VITO2MQTT_MQTT__HOST=mosquitto
    depends_on:
      - mosquitto

  mosquitto:
    image: eclipse-mosquitto:2
    restart: unless-stopped
    ports:
      - "1883:1883"
    volumes:
      - mosquitto-data:/mosquitto/data
      - mosquitto-config:/mosquitto/config

volumes:
  mosquitto-data:
  mosquitto-config:
```

!!! warning "Device permissions"
    The container needs access to the serial device. Ensure the container user has
    read/write permissions on `/dev/ttyUSB0`. You may need to add the user to the
    `dialout` group or use `privileged: true` (not recommended for production).

### Dockerfile (from source)

```dockerfile title="Dockerfile"
FROM python:3.14-slim

RUN pip install uv
WORKDIR /app
COPY . .
RUN uv sync --no-dev

CMD ["uv", "run", "vito2mqtt"]
```

---

## Common Recipes

### Adjusting hot water temperature

Publish a JSON payload to the hot water command topic:

```bash
# Set hot water target to 55°C
mosquitto_pub -h localhost \
  -t 'vito2mqtt/vitodens200w/hot_water/set' \
  -m '{"hot_water_setpoint": 55}'
```

The read-before-write optimization checks the current value first. If the boiler
is already set to 55°C, no write occurs. Use `"__force": true` to write regardless.

### Setting heating schedule timers

Timer signals use the CycleTime (CT) format — 4 on/off slot pairs per day:

```bash
# Set Monday radiator schedule: heat 06:00–08:30 and 17:00–22:00
mosquitto_pub -h localhost \
  -t 'vito2mqtt/vitodens200w/heating_radiator/set' \
  -m '{
    "timer_m1_monday": [
      [[6, 0], [8, 30]],
      [[17, 0], [22, 0]],
      [[null, null], [null, null]],
      [[null, null], [null, null]]
    ]
  }'
```

Unused slots must be `[null, null]`. Each day has exactly 4 pairs of 2 time slots,
where each slot is `[hours, minutes]` with `int` or `null` elements.

### Checking error history

Subscribe to the diagnosis state topic:

```bash
mosquitto_sub -h localhost \
  -t 'vito2mqtt/vitodens200w/diagnosis/state' -v
```

Error history entries (ES type) are returned as objects with `error` and `timestamp`
fields, where `error` is a human-readable description:

```json
{
  "error_status": 0,
  "error_history_1": { "error": "Flame loss during operation", "timestamp": "2026-01-15T14:30:00" },
  "error_history_2": { "error": "Flow sensor fault", "timestamp": "2025-12-03T08:15:00" }
}
```

A value of `0` for `error_status` means no active error.

### Monitoring burner efficiency

Track burner starts and operating hours to assess cycling behavior:

```bash
mosquitto_sub -h localhost \
  -t 'vito2mqtt/vitodens200w/burner/state' -v
```

Key metrics:

- **`burner_starts`** — Total number of burner ignitions. High starts/hour indicates
  short cycling.
- **`burner_hours_stage1`** — Total stage 1 operating hours.
- **`burner_modulation`** — Current modulation percentage (0–100%). Low sustained
  modulation suggests oversized output.
- **`plant_power_output`** — Overall power output percentage.

!!! tip "Efficiency tracking"
    Calculate the average run time per start: `burner_hours_stage1 / burner_starts`.
    Values below 5 minutes suggest the boiler is short-cycling, which reduces
    efficiency and increases wear.

---

## Troubleshooting

### Serial port permission denied

**Symptom:** `PermissionError: [Errno 13] Permission denied: '/dev/ttyUSB0'`

**Fix:** Add your user to the `dialout` group:

```bash
sudo usermod -aG dialout $USER
# Log out and back in for the change to take effect
```

Or set permissions directly (temporary):

```bash
sudo chmod 666 /dev/ttyUSB0
```

### MQTT connection refused

**Symptom:** `ConnectionRefusedError` or timeout when connecting to broker.

**Checklist:**

1. Verify the broker is running: `systemctl status mosquitto`
2. Check `VITO2MQTT_MQTT__HOST` is correct (hostname/IP, not URL)
3. Check `VITO2MQTT_MQTT__PORT` matches the broker's listener port
4. If using authentication, verify `VITO2MQTT_MQTT__USERNAME` and
   `VITO2MQTT_MQTT__PASSWORD`
5. Check firewall rules allow connections on the MQTT port

### P300 protocol timeout

**Symptom:** Timeout errors during Optolink communication.

**Possible causes:**

- **Wrong baud rate** — The Vitodens 200-W uses 4800 baud (default). Ensure
  `VITO2MQTT_SERIAL_BAUD_RATE=4800`.
- **Adapter not connected** — Verify the Optolink adapter is seated correctly on the
  boiler's service port.
- **USB adapter issue** — Try unplugging and reconnecting the USB adapter. Check
  `dmesg | tail` for USB device errors.
- **Multiple readers** — Only one application can use the serial port at a time. Ensure
  no other Optolink software is running.

### No data on MQTT topics

**Symptom:** Subscribed to topics but no messages arrive.

**Checklist:**

1. Verify vito2mqtt is running and connected (check log output)
2. Confirm topic structure: `vito2mqtt/vitodens200w/+/state`
3. Check `VITO2MQTT_DEVICE_ID` matches what you're subscribing to (default:
   `vitodens200w`)
4. Try dry-run mode to isolate serial vs. MQTT issues:
   `uv run vito2mqtt --dry-run`
