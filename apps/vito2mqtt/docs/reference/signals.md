---
title: MQTT Signal Reference
---

# MQTT Signal Reference

Complete reference of the 88 signals exposed by vito2mqtt over MQTT. These exposed
signals are organized into 7 domain groups, each published as a JSON object to its
own MQTT topic. An additional internal command (`system_time`) exists in the
registry but is not exposed via these topics.

---

## Topic Layout

Topics follow the domain-grouped layout defined in
[ADR-002](../adr/ADR-002-mqtt-topic-layout.md):

```
vito2mqtt/{device_id}/{group}/state    # Telemetry (read-only, JSON)
vito2mqtt/{device_id}/{group}/set      # Commands (writable, JSON)
```

With the default `device_id` of `vitodens200w`, example topics:

```
vito2mqtt/vitodens200w/outdoor/state
vito2mqtt/vitodens200w/hot_water/state
vito2mqtt/vitodens200w/hot_water/set
vito2mqtt/vitodens200w/burner/state
vito2mqtt/vitodens200w/heating_radiator/state
vito2mqtt/vitodens200w/heating_radiator/set
vito2mqtt/vitodens200w/heating_floor/state
vito2mqtt/vitodens200w/heating_floor/set
vito2mqtt/vitodens200w/system/state
vito2mqtt/vitodens200w/system/set
vito2mqtt/vitodens200w/diagnosis/state
```

---

## Signal Groups

### Outdoor (3 telemetry signals)

Topic: `vito2mqtt/{device_id}/outdoor/state`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `outdoor_temperature` | `0x0800` | IS10 | READ | Current outdoor temperature (°C, ÷10) |
| `outdoor_temperature_lowpass` | `0x5525` | IS10 | READ | Low-pass filtered outdoor temperature (°C) |
| `outdoor_temperature_damped` | `0x5527` | IS10 | READ | Damped outdoor temperature (°C) |

---

### Hot Water (2 telemetry + 9 command signals)

Telemetry topic: `vito2mqtt/{device_id}/hot_water/state`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `hot_water_temperature` | `0x0804` | IS10 | READ | Current hot water temperature (°C) |
| `hot_water_outlet_temperature` | `0x0814` | IS10 | READ | Hot water outlet temperature (°C) |

Command topic: `vito2mqtt/{device_id}/hot_water/set`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `hot_water_setpoint` | `0x6300` | IUNON | READ_WRITE | Target hot water temperature (°C) |
| `hot_water_pump_overrun` | `0x6762` | IUNON | READ_WRITE | Pump overrun time (seconds) |
| `timer_hw_monday` | `0x2100` | CT | READ_WRITE | Monday hot water schedule |
| `timer_hw_tuesday` | `0x2108` | CT | READ_WRITE | Tuesday hot water schedule |
| `timer_hw_wednesday` | `0x2110` | CT | READ_WRITE | Wednesday hot water schedule |
| `timer_hw_thursday` | `0x2118` | CT | READ_WRITE | Thursday hot water schedule |
| `timer_hw_friday` | `0x2120` | CT | READ_WRITE | Friday hot water schedule |
| `timer_hw_saturday` | `0x2128` | CT | READ_WRITE | Saturday hot water schedule |
| `timer_hw_sunday` | `0x2130` | CT | READ_WRITE | Sunday hot water schedule |

---

### Burner (8 telemetry signals)

Topic: `vito2mqtt/{device_id}/burner/state`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `boiler_temperature` | `0x0802` | IS10 | READ | Current boiler water temperature (°C) |
| `boiler_temperature_lowpass` | `0x0810` | IS10 | READ | Low-pass filtered boiler temperature (°C) |
| `boiler_temperature_setpoint` | `0x555A` | IS10 | READ | Target boiler temperature (°C) |
| `exhaust_temperature` | `0x0808` | IS10 | READ | Exhaust gas temperature (°C) |
| `burner_modulation` | `0x55D3` | IUNON | READ | Current burner modulation (%) |
| `burner_starts` | `0x088A` | IUNON | READ | Total burner start count |
| `burner_hours_stage1` | `0x08A7` | IU3600 | READ | Stage 1 operating hours |
| `plant_power_output` | `0xA38F` | PR3 | READ | Current power output (%) |

---

### Heating Radiator / M1 (7 telemetry + 13 command signals)

The M1 heating circuit controls traditional radiators.

Telemetry topic: `vito2mqtt/{device_id}/heating_radiator/state`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `flow_temperature_m1` | `0x2900` | IS10 | READ | Flow temperature, radiator circuit (°C) |
| `flow_temperature_setpoint_m1` | `0x2544` | IS10 | READ | Flow temperature setpoint, radiator circuit (°C) |
| `pump_status_m1` | `0x7663` | IUNON | READ | Radiator circuit pump status |
| `frost_warning_m1` | `0x2500` | IUNON | READ | Frost warning flag, radiator circuit |
| `frost_limit_m1` | `0x27A3` | IUNON | READ | Frost limit temperature, radiator circuit (°C) |
| `operating_mode_m1` | `0x2301` | BA | READ | Operating mode, radiator circuit |
| `operating_mode_economy_m1` | `0x2302` | BA | READ | Economy mode, radiator circuit |

Command topic: `vito2mqtt/{device_id}/heating_radiator/set`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `heating_curve_gradient_m1` | `0x27D3` | IS10 | READ_WRITE | Heating curve gradient, radiator circuit |
| `heating_curve_level_m1` | `0x27D4` | IUNON | READ_WRITE | Heating curve level, radiator circuit |
| `room_temperature_setpoint_m1` | `0x2306` | IUNON | READ_WRITE | Room temperature setpoint, radiator circuit (°C) |
| `room_temperature_setpoint_economy_m1` | `0x2307` | IUNON | READ_WRITE | Economy room temperature setpoint, radiator circuit (°C) |
| `room_temperature_setpoint_party_m1` | `0x2308` | IUNON | READ_WRITE | Party mode room temperature setpoint, radiator circuit (°C) |
| `operating_mode_party_m1` | `0x2303` | BA | READ_WRITE | Party mode toggle, radiator circuit |
| `timer_m1_monday` | `0x2000` | CT | READ_WRITE | Monday heating schedule, radiator circuit |
| `timer_m1_tuesday` | `0x2008` | CT | READ_WRITE | Tuesday heating schedule, radiator circuit |
| `timer_m1_wednesday` | `0x2010` | CT | READ_WRITE | Wednesday heating schedule, radiator circuit |
| `timer_m1_thursday` | `0x2018` | CT | READ_WRITE | Thursday heating schedule, radiator circuit |
| `timer_m1_friday` | `0x2020` | CT | READ_WRITE | Friday heating schedule, radiator circuit |
| `timer_m1_saturday` | `0x2028` | CT | READ_WRITE | Saturday heating schedule, radiator circuit |
| `timer_m1_sunday` | `0x2030` | CT | READ_WRITE | Sunday heating schedule, radiator circuit |

---

### Heating Floor / M2 (8 telemetry + 13 command signals)

The M2 heating circuit controls underfloor heating.

Telemetry topic: `vito2mqtt/{device_id}/heating_floor/state`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `flow_temperature_m2` | `0x3900` | IS10 | READ | Flow temperature, floor heating circuit (°C) |
| `flow_temperature_setpoint_m2` | `0x3544` | IS10 | READ | Flow temperature setpoint, floor heating circuit (°C) |
| `pump_status_m2` | `0x7665` | RT | READ | Floor heating circuit pump status |
| `pump_speed_m2` | `0x7665` | PR2 | READ | Floor heating circuit pump speed (%) |
| `frost_warning_m2` | `0x3500` | IUNON | READ | Frost warning flag, floor heating circuit |
| `frost_limit_m2` | `0x37A3` | IUNON | READ | Frost limit temperature, floor heating circuit (°C) |
| `operating_mode_m2` | `0x3301` | BA | READ | Operating mode, floor heating circuit |
| `operating_mode_economy_m2` | `0x3302` | BA | READ | Economy mode, floor heating circuit |

Command topic: `vito2mqtt/{device_id}/heating_floor/set`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `heating_curve_gradient_m2` | `0x37D3` | IS10 | READ_WRITE | Heating curve gradient, floor heating circuit |
| `heating_curve_level_m2` | `0x37D4` | IUNON | READ_WRITE | Heating curve level, floor heating circuit |
| `room_temperature_setpoint_m2` | `0x3306` | IUNON | READ_WRITE | Room temperature setpoint, floor heating circuit (°C) |
| `room_temperature_setpoint_economy_m2` | `0x3307` | IUNON | READ_WRITE | Economy room temperature setpoint, floor heating circuit (°C) |
| `room_temperature_setpoint_party_m2` | `0x3308` | IUNON | READ_WRITE | Party mode room temperature setpoint, floor heating circuit (°C) |
| `operating_mode_party_m2` | `0x3303` | BA | READ_WRITE | Party mode toggle, floor heating circuit |
| `timer_m2_monday` | `0x3000` | CT | READ_WRITE | Monday heating schedule, floor heating circuit |
| `timer_m2_tuesday` | `0x3008` | CT | READ_WRITE | Tuesday heating schedule, floor heating circuit |
| `timer_m2_wednesday` | `0x3010` | CT | READ_WRITE | Wednesday heating schedule, floor heating circuit |
| `timer_m2_thursday` | `0x3018` | CT | READ_WRITE | Thursday heating schedule, floor heating circuit |
| `timer_m2_friday` | `0x3020` | CT | READ_WRITE | Friday heating schedule, floor heating circuit |
| `timer_m2_saturday` | `0x3028` | CT | READ_WRITE | Saturday heating schedule, floor heating circuit |
| `timer_m2_sunday` | `0x3030` | CT | READ_WRITE | Sunday heating schedule, floor heating circuit |

---

### System (7 telemetry + 7 command signals)

Telemetry topic: `vito2mqtt/{device_id}/system/state`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `storage_temperature_lowpass` | `0x0812` | IS10 | READ | Low-pass filtered storage temperature (°C) |
| `internal_pump_status` | `0x7660` | RT | READ | Internal pump on/off status |
| `internal_pump_speed` | `0x7660` | PR2 | READ | Internal pump speed (%) |
| `storage_charge_pump_status` | `0x6513` | RT | READ | Storage charge pump on/off status |
| `circulation_pump_status` | `0x6515` | RT | READ | Circulation pump on/off status |
| `switch_valve_status` | `0x0A10` | USV | READ | Switch valve position |
| `flow_temperature_setpoint_m3` | `0x4544` | IS10 | READ | Flow temperature setpoint, M3 circuit (°C) |

Command topic: `vito2mqtt/{device_id}/system/set`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `timer_cp_monday` | `0x2200` | CT | READ_WRITE | Monday circulation pump schedule |
| `timer_cp_tuesday` | `0x2208` | CT | READ_WRITE | Tuesday circulation pump schedule |
| `timer_cp_wednesday` | `0x2210` | CT | READ_WRITE | Wednesday circulation pump schedule |
| `timer_cp_thursday` | `0x2218` | CT | READ_WRITE | Thursday circulation pump schedule |
| `timer_cp_friday` | `0x2220` | CT | READ_WRITE | Friday circulation pump schedule |
| `timer_cp_saturday` | `0x2228` | CT | READ_WRITE | Saturday circulation pump schedule |
| `timer_cp_sunday` | `0x2230` | CT | READ_WRITE | Sunday circulation pump schedule |

---

### Diagnosis (11 telemetry signals)

Topic: `vito2mqtt/{device_id}/diagnosis/state`

| Signal Name | Address | Type | Access | Description |
|-------------|---------|------|--------|-------------|
| `error_status` | `0x0A82` | RT | READ | Current error status (0 = OK) |
| `error_history_1` | `0x7507` | ES | READ | Most recent error entry |
| `error_history_2` | `0x7510` | ES | READ | 2nd error history entry |
| `error_history_3` | `0x7519` | ES | READ | 3rd error history entry |
| `error_history_4` | `0x7522` | ES | READ | 4th error history entry |
| `error_history_5` | `0x752B` | ES | READ | 5th error history entry |
| `error_history_6` | `0x7534` | ES | READ | 6th error history entry |
| `error_history_7` | `0x753D` | ES | READ | 7th error history entry |
| `error_history_8` | `0x7546` | ES | READ | 8th error history entry |
| `error_history_9` | `0x754F` | ES | READ | 9th error history entry |
| `error_history_10` | `0x7558` | ES | READ | 10th (oldest) error history entry |

---

## Signal Totals Summary

| Group | Telemetry | Commands | Total |
|-------|-----------|----------|-------|
| Outdoor | 3 | — | 3 |
| Hot Water | 2 | 9 | 11 |
| Burner | 8 | — | 8 |
| Heating Radiator (M1) | 7 | 13 | 20 |
| Heating Floor (M2) | 8 | 13 | 21 |
| System | 7 | 7 | 14 |
| Diagnosis | 11 | — | 11 |
| **Total** | **46** | **42** | **88** |

!!! note "89 vs 88"
    The command registry contains 89 entries total. The `system_time` command
    (`0x088E`, type TI, WRITE-only) is used internally and not exposed through
    telemetry or command groups.

---

## Type Code Reference

| Code | Name | Description | Unit |
|------|------|-------------|------|
| IS10 | Signed fixed-point ÷10 | Signed 16-bit integer divided by 10. Used for temperature values. | °C |
| IUNON | Unsigned integer | Unsigned integer with no scaling. Used for counts, setpoints, status flags. | varies |
| IU3600 | Unsigned ÷3600 | Unsigned integer divided by 3600. Converts seconds to hours. | hours |
| PR2 | Second byte unsigned | Extracts the second byte as an unsigned percentage. Used for pump/fan speed. | % |
| PR3 | First byte ÷2 | Extracts the first byte and divides by 2. Used for power output percentage. | % |
| BA | Betriebsart | Operating mode enum. Labels are language-configurable (DE/EN) per ADR-006. | enum |
| USV | Umschaltventil | Switch valve state enum. Labels are language-configurable (DE/EN). | enum |
| ES | Fehlerspeicher | Error history entry: error code + BCD-packed timestamp. | `[label, datetime]` |
| RT | ReturnStatus | Boolean/status flag as IntEnum: 0=OFF, 1=ON, 3=UNKNOWN, 0xAA=ERROR. | 0/1 |
| CT | CycleTime | Weekly timer schedule with 4 on/off time slot pairs per day. | schedule |
| TI | SystemTime | BCD-packed date/time (8 bytes). Used for system clock sync. | datetime |

---

## Command Payloads

### Writing values

To write values, publish a JSON object to the group's `/set` topic:

```bash
# Set hot water target temperature to 55°C
mosquitto_pub -h localhost \
  -t 'vito2mqtt/vitodens200w/hot_water/set' \
  -m '{"hot_water_setpoint": 55}'
```

Multiple signals can be set in a single message:

```bash
# Set both room setpoint and economy setpoint for the radiator circuit
mosquitto_pub -h localhost \
  -t 'vito2mqtt/vitodens200w/heating_radiator/set' \
  -m '{"room_temperature_setpoint_m1": 21, "room_temperature_setpoint_economy_m1": 18}'
```

### Read-before-write optimization

For READ_WRITE signals, vito2mqtt reads the current value from the boiler before
writing. If the desired value matches the current value, the write is **skipped**.
This reduces serial bus traffic and avoids unnecessary EEPROM wear on the boiler
controller.

### The `__force` meta-key

To bypass the read-before-write comparison and write unconditionally, include the
`__force` key set to `true`:

```json
{
  "hot_water_setpoint": 55,
  "__force": true
}
```

!!! warning "Use `__force` sparingly"
    Forcing writes bypasses the EEPROM wear protection. Only use this when you need
    to guarantee a write regardless of current state — e.g., after a boiler reset or
    when debugging.

### Timer schedule format (CT type)

Timer schedules use the CycleTime format with 4 on/off slot pairs per day:

```json
{
  "timer_hw_monday": [
    ["06:00", "08:00"],
    ["17:00", "22:00"],
    ["00:00", "00:00"],
    ["00:00", "00:00"]
  ]
}
```

Each slot is a `[start, end]` pair in `"HH:MM"` format. Unused slots should be set
to `["00:00", "00:00"]`.
