# MQTT Topics

geiger2mqtt publishes one state topic for the radiation readings plus the framework's
availability, heartbeat and error topics. All topics start with
`GEIGER2MQTT_MQTT__TOPIC_PREFIX` (default `geiger2mqtt`).

| Topic                              | Direction | Payload                          | Retain | QoS |
| ---------------------------------- | --------- | -------------------------------- | ------ | --- |
| `geiger2mqtt/radiation/state`      | outbound  | Radiation JSON                   | yes    | 1   |
| `geiger2mqtt/radiation/availability` | outbound | `"online"` / `"offline"`        | yes    | 1   |
| `geiger2mqtt/status`               | outbound  | Heartbeat JSON + LWT `"offline"` | yes    | 1   |
| `geiger2mqtt/error`                | outbound  | Error JSON                       | no     | 1   |
| `geiger2mqtt/radiation/error`      | outbound  | Error JSON                       | no     | 1   |

geiger2mqtt subscribes to no topics.

## Radiation state

**Topic:** `geiger2mqtt/radiation/state`

Published every `PUBLISH_INTERVAL` seconds (default 30), even when the values have not
changed. The first message comes 60 seconds after the start.

```json
{ "cpm": 21, "dose_rate": 0.1197, "dose_rate_avg": 0.1123 }
```

| Field           | Type    | Unit  | Description                                              |
| --------------- | ------- | ----- | -------------------------------------------------------- |
| `cpm`           | integer | CPM   | Pulses in the last 60 seconds                            |
| `dose_rate`     | float   | µSv/h | `cpm × CONVERSION_FACTOR`, 4 decimal places              |
| `dose_rate_avg` | float   | µSv/h | Average over `AVERAGE_WINDOW` seconds, 4 decimal places  |

## Availability

**Topic:** `geiger2mqtt/radiation/availability`

`"online"` while readings are published. When no pulse has arrived for
`NO_PULSE_TIMEOUT` seconds (default 300), geiger2mqtt publishes `"offline"`, stops
publishing state and reports `NoPulseError` on the error topics. The next pulse brings
the sensor back `"online"` with the next reading; the app keeps running throughout.
`NO_PULSE_TIMEOUT=0` disables the check.

## Status heartbeat

**Topic:** `geiger2mqtt/status`

A retained JSON heartbeat with the app version, uptime and the status of the
`radiation` entity. On disconnect, the broker publishes the last will `"offline"`.

## Errors

**Topics:** `geiger2mqtt/error` and `geiger2mqtt/radiation/error`

Not retained. The payload carries `error_type`, `message`, `device` and `timestamp`.
Messages are reduced to the exception class name unless
`GEIGER2MQTT_MQTT__ERROR_PUBLISH_VERBOSE=true`. A persisting error is republished as a
reminder (2nd, 4th, 8th, ... failure in the first hour, then hourly).

## Home Assistant discovery

On the first connection, geiger2mqtt publishes retained discovery configs under
`homeassistant/sensor/geiger2mqtt/<object_id>/config`. All three sensors read
`geiger2mqtt/radiation/state` and share the radiation availability topic.

| Entity                     | Object ID                 | Unit  | State class   | Icon              |
| -------------------------- | ------------------------- | ----- | ------------- | ----------------- |
| Counts per minute          | `radiation_cpm`           | CPM   | `measurement` | `mdi:radioactive` |
| Dose rate                  | `radiation_dose_rate`     | µSv/h | `measurement` | `mdi:radioactive` |
| Average dose rate          | `radiation_dose_rate_avg` | µSv/h | `measurement` | `mdi:radioactive` |

Home Assistant has no device class for radiation, so the sensors carry none.
