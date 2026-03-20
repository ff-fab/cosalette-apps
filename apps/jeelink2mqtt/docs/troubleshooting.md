# Troubleshooting

Common issues, symptoms, and resolutions.  Start with the symptom you're
seeing and follow the fix.

---

!!! danger "Serial port permission denied"

    **Symptom:** `PermissionError: [Errno 13] Permission denied: '/dev/ttyUSB0'`

    **Fix:**

    ```bash
    sudo usermod -aG dialout $USER
    ```

    Log out and back in for the group change to take effect.  Verify with:

    ```bash
    groups | grep dialout
    ```

---

!!! warning "No sensor data appearing"

    **Symptom:** MQTT topics are empty or only `mapping/state` publishes.

    **Checklist:**

    1. **Check the raw channel** — subscribe to `jeelink2mqtt/raw/state`.
       If frames appear here but not on named topics, the issue is in sensor
       mapping — see the auto-adopt section below.

    2. **Verify serial port** — confirm the device exists and matches config:

        ```bash
        ls -l /dev/ttyUSB0
        dmesg | grep tty
        ```

    3. **Check baud rate** — must be `57600` (the JeeLink default).

    4. **Check sensor batteries** — LaCrosse sensors don't transmit when
       batteries are dead.

    5. **Try dry-run mode** — `jeelink2mqtt --dry-run` confirms the rest of
       the pipeline works.

---

!!! warning "Sensor not auto-adopting"

    **Symptom:** New sensor ID appears in `raw/state` but no named sensor
    picks it up.

    **Cause:** Multiple configured sensors are stale.  Auto-adopt requires
    **exactly one** stale sensor to avoid ambiguous assignment.

    **Fix:**

    1. List unknown IDs:

        ```bash
        mosquitto_pub -h localhost -t 'jeelink2mqtt/mapping/set' \
          -m '{"command": "list_unknown"}'
        ```

    2. Subscribe to see the response:

        ```bash
        mosquitto_sub -h localhost -t 'jeelink2mqtt/mapping/state' -C 1
        ```

    3. Manually assign each sensor:

        ```bash
        mosquitto_pub -h localhost -t 'jeelink2mqtt/mapping/set' \
          -m '{"command": "assign", "sensor_name": "office", "sensor_id": 42}'
        ```

    See [User Guide → Multi-Battery Failure](user-guide.md#multi-battery-failure)
    for the full workflow.

---

!!! danger "Mapping conflict error"

    **Symptom:** Assign command returns `{"error": "Sensor ID 42 is already mapped to 'outdoor'..."}`

    **Cause:** The sensor ID is already assigned to a different sensor name.

    **Fix:** Reset the conflicting mapping first, then reassign:

    ```bash
    # Remove the existing mapping
    mosquitto_pub -h localhost -t 'jeelink2mqtt/mapping/set' \
      -m '{"command": "reset", "sensor_name": "outdoor"}'

    # Now assign to the intended sensor
    mosquitto_pub -h localhost -t 'jeelink2mqtt/mapping/set' \
      -m '{"command": "assign", "sensor_name": "office", "sensor_id": 42}'
    ```

---

!!! warning "Sensor shows offline (stale)"

    **Symptom:** `jeelink2mqtt/{sensor}/availability` shows `"offline"`.

    **Cause:** No reading received within the staleness timeout (default:
    600 seconds / 10 minutes).

    **Checklist:**

    - **Batteries** — check and replace if `low_battery` was `true` before
      the sensor went offline.
    - **Distance** — the sensor may be too far from the JeeLink receiver.
      LaCrosse 868 MHz has ~100 m open-air range, less through walls.
    - **Interference** — other 868 MHz devices can cause collisions.
    - **Staleness timeout** — if the sensor transmits infrequently, increase
      the per-sensor `staleness_timeout`:

        ```env
        JEELINK2MQTT_SENSORS='[{"name": "outdoor", "staleness_timeout": 900}]'
        ```

---

!!! note "MQTT connection issues"

    **Symptom:** Application starts but no messages appear on the broker.

    **Checklist:**

    1. **Broker running?**

        ```bash
        systemctl status mosquitto
        ```

    2. **Host and port correct?**

        ```env
        JEELINK2MQTT_MQTT__HOST=localhost
        JEELINK2MQTT_MQTT__PORT=1883
        ```

    3. **Authentication** — if the broker requires credentials:

        ```env
        JEELINK2MQTT_MQTT__USERNAME=jeelink
        JEELINK2MQTT_MQTT__PASSWORD=secret
        ```

    4. **Network** — verify connectivity from the jeelink2mqtt host:

        ```bash
        mosquitto_pub -h broker.local -t test -m hello
        ```

---

!!! note "Readings seem wrong"

    **Symptom:** Temperature or humidity values are consistently off.

    **Fix:** Use calibration offsets.  Compare the raw reading (from
    `jeelink2mqtt/raw/state`) against a reference instrument and set
    offsets accordingly:

    ```env
    JEELINK2MQTT_SENSORS='[{"name": "office", "temp_offset": -0.5, "humidity_offset": 2.0}]'
    ```

    Also check:

    - **Median filter window** — a very large window (e.g. 21) smooths
      aggressively and can delay real changes.  Default of 7 is a good
      balance.
    - **Sensor placement** — avoid direct sunlight, heat sources, or
      enclosures that trap heat.

---

!!! warning "Data not persisting across restarts"

    **Symptom:** Sensor mappings are lost after restarting jeelink2mqtt.

    **Checklist:**

    - **Directory exists and is writable:**

        ```bash
        ls -la data/
        ```

    - **Docker volume mounted:**

        ```yaml
        volumes:
          - jeelink-data:/app/data
        ```

    - **File present after running:**

        ```bash
        cat data/jeelink2mqtt.json
        ```

    If the file is empty or missing, check that the application has write
    permissions to the `data/` directory.

---

## Still Stuck?

1. Run with debug logging: `jeelink2mqtt --log-level DEBUG`
2. Check the raw channel: `mosquitto_sub -h localhost -t 'jeelink2mqtt/raw/state' -v`
3. Check mapping state: `mosquitto_sub -h localhost -t 'jeelink2mqtt/mapping/state' -v`
4. [Open an issue](https://github.com/ff-fab/cosalette-apps/issues) with the debug log output.
