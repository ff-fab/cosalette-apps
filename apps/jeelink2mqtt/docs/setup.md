# Setup

Detailed environment setup — hardware, MQTT broker, configuration, and
home-automation integration.

---

## Hardware Setup

### JeeLink USB Receiver

1. Plug the JeeLink into a USB port.
2. Check which device node the kernel assigned:

    ```bash
    dmesg | grep tty
    ```

    Typical output: `ttyUSB0` or `ttyACM0`.

3. Confirm the device exists:

    ```bash
    ls -l /dev/ttyUSB0
    ```

### Serial Permissions

The device node is usually owned by the `dialout` group.  Add your user:

```bash
sudo usermod -aG dialout $USER
```

!!! warning "Log out and back in"

    Group membership changes require a new login session to take effect.

### LaCrosse TX29DTH-IT Sensors

- Insert batteries and wait ~30 seconds for the first transmission.
- Sensor IDs are **ephemeral** — they change on every battery swap.
  jeelink2mqtt handles this automatically via its registry.

---

## MQTT Broker Setup

A local Mosquitto instance is the simplest option:

```bash
# Debian / Ubuntu
sudo apt install mosquitto mosquitto-clients

# Verify
mosquitto_sub -h localhost -t '$SYS/broker/version' -C 1
```

For authenticated brokers, set the credentials in your `.env`:

```env
JEELINK2MQTT_MQTT__HOST=broker.local
JEELINK2MQTT_MQTT__PORT=1883
JEELINK2MQTT_MQTT__USERNAME=jeelink
JEELINK2MQTT_MQTT__PASSWORD=secret
```

---

## Configuration

jeelink2mqtt reads settings from environment variables prefixed with
`JEELINK2MQTT_`.  A `.env` file in the working directory is loaded
automatically.

### Complete Example

```env
# -- Serial / hardware --
JEELINK2MQTT_SERIAL_PORT=/dev/ttyUSB0
JEELINK2MQTT_BAUD_RATE=57600

# -- MQTT broker (nested with __) --
JEELINK2MQTT_MQTT__HOST=broker.local
JEELINK2MQTT_MQTT__PORT=1883
JEELINK2MQTT_MQTT__USERNAME=jeelink
JEELINK2MQTT_MQTT__PASSWORD=secret

# -- Sensors (JSON array) --
JEELINK2MQTT_SENSORS='[
  {"name": "office", "temp_offset": -0.5, "humidity_offset": 2.0},
  {"name": "outdoor", "staleness_timeout": 900},
  {"name": "bedroom"}
]'

# -- Timing --
JEELINK2MQTT_STALENESS_TIMEOUT_SECONDS=600
JEELINK2MQTT_MEDIAN_FILTER_WINDOW=7
JEELINK2MQTT_HEARTBEAT_INTERVAL_SECONDS=180
```

### Key Conventions

| Convention | Example |
|------------|---------|
| Prefix | `JEELINK2MQTT_` for all settings |
| Nesting delimiter | `__` — e.g. `JEELINK2MQTT_MQTT__HOST` |
| Sensor list | JSON array in `JEELINK2MQTT_SENSORS` |
| Per-sensor overrides | `staleness_timeout` inside each sensor object |

!!! tip "Sensor calibration offsets"

    Place a reference thermometer next to each sensor for 24 hours.  The
    difference becomes your `temp_offset` (positive = sensor reads low,
    negative = sensor reads high).  Same logic for `humidity_offset`.

See [Reference](reference.md) for the full settings table.

---

## Home Automation Integration

### Topic Structure

Each named sensor publishes a retained JSON state message:

**Topic:** `jeelink2mqtt/{sensor_name}/state`

```json
{
  "temperature": 21.3,
  "humidity": 52,
  "low_battery": false,
  "timestamp": "2026-03-04T10:15:00+00:00"
}
```

Availability is published separately as a plain string:

**Topic:** `jeelink2mqtt/{sensor_name}/availability` → `"online"` or `"offline"`

### Home Assistant

```yaml
# configuration.yaml
mqtt:
  sensor:
    - name: "Office Temperature"
      state_topic: "jeelink2mqtt/office/state"
      value_template: "{{ value_json.temperature }}"
      unit_of_measurement: "°C"
      device_class: temperature

    - name: "Office Humidity"
      state_topic: "jeelink2mqtt/office/state"
      value_template: "{{ value_json.humidity }}"
      unit_of_measurement: "%"
      device_class: humidity

    - name: "Office Battery"
      state_topic: "jeelink2mqtt/office/state"
      value_template: "{{ value_json.low_battery }}"
      device_class: battery

  binary_sensor:
    - name: "Office Sensor"
      state_topic: "jeelink2mqtt/office/availability"
      payload_on: "online"
      payload_off: "offline"
      device_class: connectivity
```

### OpenHAB

```java
// jeelink.things
Thing mqtt:topic:office "Office Sensor" (mqtt:broker:local) {
    Channels:
        Type number : temperature [
            stateTopic="jeelink2mqtt/office/state",
            transformationPattern="JSONPATH:$.temperature"
        ]
        Type number : humidity [
            stateTopic="jeelink2mqtt/office/state",
            transformationPattern="JSONPATH:$.humidity"
        ]
}
```

---

## Next Steps

- [User Guide](user-guide.md) — how sensor mapping and commands work
- [Operations](operations.md) — Docker, systemd, monitoring
- [Reference](reference.md) — complete settings and topic reference
