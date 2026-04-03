# Configuration

suncast uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
for configuration, giving you three ways to set any value:

1. **CLI flags** — highest priority
2. **Environment variables** — `SUNCAST_` prefix
3. **`.env` file** — loaded from the working directory
4. **Defaults** — built-in sensible values

Higher-priority sources override lower ones. For most deployments, a `.env` file is
all you need. See [`.env.example`](https://github.com/ff-fab/cosalette-apps/blob/main/apps/suncast/.env.example)
for a complete template.

---

## Settings Reference

### Location (Required)

| Setting     | Env Variable         | Default | Description                          |
| ----------- | -------------------- | ------- | ------------------------------------ |
| `latitude`  | `SUNCAST_LATITUDE`   | —       | GPS latitude (−90 to 90)            |
| `longitude` | `SUNCAST_LONGITUDE`  | —       | GPS longitude (−180 to 180)         |
| `timezone`  | `SUNCAST_TIMEZONE`   | —       | IANA timezone (e.g. `Europe/Berlin`) |

!!! warning "All three location settings are required"
    suncast cannot compute sun positions without a valid location. The app will
    refuse to start if any of these are missing.

### Geometry

| Setting         | Env Variable             | Default         | Description                          |
| --------------- | ------------------------ | --------------- | ------------------------------------ |
| `geometry_file` | `SUNCAST_GEOMETRY_FILE`  | `geometry.yaml` | Path to YAML/JSON geometry file      |

### Timing

| Setting         | Env Variable             | Default | Description                           |
| --------------- | ------------------------ | ------- | ------------------------------------- |
| `poll_interval` | `SUNCAST_POLL_INTERVAL`  | `360.0` | Seconds between render cycles (> 0)   |

### Rendering

| Setting           | Env Variable               | Default     | Description                                 |
| ----------------- | -------------------------- | ----------- | ------------------------------------------- |
| `primary_color`   | `SUNCAST_PRIMARY_COLOR`    | `#614c1f`   | Building fill color (dark/outline)          |
| `secondary_color` | `SUNCAST_SECONDARY_COLOR`  | `#b38c3a`   | Building accent color                       |
| `light_color`     | `SUNCAST_LIGHT_COLOR`      | `#f1b023`   | Sun and daylight arc color                  |
| `shadow_color`    | `SUNCAST_SHADOW_COLOR`     | `#0A0A0A`   | Shadow projection color                     |
| `stroke_width`    | `SUNCAST_STROKE_WIDTH`     | `1.0`       | SVG stroke width for building outlines      |
| `sundial_ring`    | `SUNCAST_SUNDIAL_RING`     | `true`      | Show hour markers around the compass dial   |
| `marker_style`    | `SUNCAST_MARKER_STYLE`     | `circle`    | Hour marker style: `circle` or `bar`        |

#### Marker style comparison

<div class="grid" markdown>
![Circle markers](images/generated/marker-circle.svg){ width="250" }
![Bar markers](images/generated/marker-bar.svg){ width="250" }
</div>

Left: `circle` markers (default). Right: `bar` markers.

#### Sundial ring comparison

<div class="grid" markdown>
![Sundial ring enabled](images/generated/sundial-on.svg){ width="250" }
![Sundial ring disabled](images/generated/sundial-off.svg){ width="250" }
</div>

Left: sundial ring enabled (default). Right: sundial ring disabled.

### Output

| Setting       | Env Variable            | Default   | Description                                            |
| ------------- | ----------------------- | --------- | ------------------------------------------------------ |
| `output_path` | `SUNCAST_OUTPUT_PATH`   | `/output` | Directory for SVG/PNG files. `null` to disable         |
| `png_enabled` | `SUNCAST_PNG_ENABLED`   | `false`   | Enable PNG rasterization (requires `suncast[png]`)     |
| `png_width`   | `SUNCAST_PNG_WIDTH`     | `800`     | PNG width in pixels (≥ 1)                              |
| `png_height`  | `SUNCAST_PNG_HEIGHT`    | `800`     | PNG height in pixels (≥ 1)                             |

### HTTP Server

| Setting        | Env Variable            | Default     | Description                    |
| -------------- | ----------------------- | ----------- | ------------------------------ |
| `http_enabled` | `SUNCAST_HTTP_ENABLED`  | `false`     | Enable built-in HTTP server    |
| `http_host`    | `SUNCAST_HTTP_HOST`     | `0.0.0.0`  | HTTP bind address              |
| `http_port`    | `SUNCAST_HTTP_PORT`     | `8080`      | HTTP port (1–65535)            |

!!! tip "HTTP server vs. nginx sidecar"
    The built-in HTTP server is an alternative for non-Docker deployments.
    In Docker, use the nginx sidecar pattern instead — see
    [Getting Started](getting-started.md).

### MQTT (Inherited)

MQTT settings are inherited from cosalette's `Settings` base class. See the
[cosalette docs](https://ff-fab.github.io/cosalette/) for the full reference.
Key settings:

| Setting         | Env Variable               | Default     | Description          |
| --------------- | -------------------------- | ----------- | -------------------- |
| `mqtt.host`     | `SUNCAST_MQTT__HOST`       | `localhost` | MQTT broker hostname |
| `mqtt.port`     | `SUNCAST_MQTT__PORT`       | `1883`      | MQTT broker port     |
| `mqtt.username` | `SUNCAST_MQTT__USERNAME`   | —           | MQTT username        |
| `mqtt.password` | `SUNCAST_MQTT__PASSWORD`   | —           | MQTT password        |

!!! info "Double-underscore delimiter"
    MQTT settings are **nested** inside the settings model. Environment variables
    use `__` (double underscore) to separate nesting levels:

    `SUNCAST_MQTT__HOST` → `settings.mqtt.host`

    This is a
    [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

---

## `.env` Example

Copy the provided template and edit to taste:

```bash
cp .env.example .env
```

```dotenv title=".env.example"
# suncast Configuration
# All settings can be set via environment variables with SUNCAST_ prefix.
# Nested settings use __ delimiter (e.g., SUNCAST_MQTT__HOST).

# --- MQTT Settings (cosalette base) ---
SUNCAST_MQTT__HOST=localhost
SUNCAST_MQTT__PORT=1883
# SUNCAST_MQTT__USERNAME=
# SUNCAST_MQTT__PASSWORD=

# --- Location (required) ---
SUNCAST_LATITUDE=48.1351
SUNCAST_LONGITUDE=11.5820
SUNCAST_TIMEZONE=Europe/Berlin

# --- Geometry ---
# SUNCAST_GEOMETRY_FILE=geometry.yaml

# --- Polling ---
# SUNCAST_POLL_INTERVAL=360.0

# --- Rendering ---
# SUNCAST_PRIMARY_COLOR=#614c1f
# SUNCAST_SECONDARY_COLOR=#b38c3a
# SUNCAST_LIGHT_COLOR=#f1b023
# SUNCAST_SHADOW_COLOR=#0A0A0A
# SUNCAST_STROKE_WIDTH=1.0
# SUNCAST_SUNDIAL_RING=true
# SUNCAST_MARKER_STYLE=circle

# --- Output ---
# SUNCAST_OUTPUT_PATH=/output
# SUNCAST_PNG_ENABLED=false
# SUNCAST_PNG_WIDTH=800
# SUNCAST_PNG_HEIGHT=800

# --- HTTP Server ---
# SUNCAST_HTTP_ENABLED=false
# SUNCAST_HTTP_HOST=0.0.0.0
# SUNCAST_HTTP_PORT=8080
```
