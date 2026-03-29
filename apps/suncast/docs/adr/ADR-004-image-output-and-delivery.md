# ADR-004: Image Output and Delivery

## Status

Accepted **Date:** 2026-03-29

## Context

The existing PoC writes a generated SVG to a static file directory and serves it via
FastAPI's static file mounting. An external Apache server proxies to this endpoint, and
OpenHAB loads the image from that URL for dashboard display.

The new app must support multiple output methods to serve both OpenHAB and Home
Assistant, and accommodate different deployment styles (Docker, bare-metal).

## Decision

Implement **three configurable output methods**, all independently toggleable:

### 1. Filesystem Output (always enabled)

Write the generated image to a configurable path. This is the foundation for all other
delivery methods.

- Setting: `SUNCAST_OUTPUT_PATH` (default: `/output`)
- Files written: `shadow.svg` (always), `shadow.png` (if PNG enabled)
- This path is typically a Docker volume mount shared with a web server sidecar.

### 2. MQTT Publication (always enabled)

Publish image content to MQTT topics:

- `suncast/shadow/state` — JSON payload with sun position data and metadata
- `suncast/shadow/image/svg` — raw SVG content as string payload
- `suncast/shadow/image/png` — raw PNG bytes (if PNG enabled)

Payload on `suncast/shadow/state`:

```json
{
  "sun_azimuth": 185.3,
  "sun_elevation": 42.1,
  "sunrise_azimuth": 83.3,
  "sunset_azimuth": 275.6,
  "is_daylight": true,
  "image_url": "http://suncast.lan/shadow.svg"
}
```

### 3. Embedded HTTP Server (optional, disabled by default)

A lightweight `aiohttp` server for non-Docker deployments where no external web server
is available.

- Setting: `SUNCAST_HTTP_ENABLED` (default: `false`)
- Setting: `SUNCAST_HTTP_PORT` (default: `8080`)
- Serves files from the output path on `/shadow.svg` and `/shadow.png`

### Docker Deployment (recommended)

The recommended production setup uses an `nginx:alpine` sidecar:

```yaml
services:
  suncast:
    image: suncast:latest
    volumes:
      - shadow-output:/output

  shadow-web:
    image: nginx:alpine
    volumes:
      - shadow-output:/usr/share/nginx/html:ro
    ports:
      - '8080:80'

volumes:
  shadow-output:
```

This avoids adding HTTP server code to the app for the primary deployment scenario.

### PNG Support (optional)

- Setting: `SUNCAST_PNG_ENABLED` (default: `false`)
- Uses `cairosvg` or `svglib+reportlab` to rasterize SVG to PNG
- Enables Home Assistant MQTT Camera integration (expects image bytes on topic)
- PNG dimensions configurable: `SUNCAST_PNG_WIDTH`, `SUNCAST_PNG_HEIGHT`

### Night Behavior

The app runs 24/7 with the same update interval. When the sun is below the horizon:

- Shadow polygons are not rendered
- The sundial, sun azimuth indicator, and day/night arc are still shown
- The visualization acts as a clock showing the sun's position on its daily path

## Decision Drivers

- Docker-first: sidecar pattern avoids embedding HTTP server for most users
- Flexibility: MQTT enables both OpenHAB and Home Assistant consumption
- Simplicity: filesystem output is the lowest-common-denominator
- Optional PNG: enables native HA MQTT Camera integration

## Considered Options

1. **MQTT only** — simplest, but harder for dashboard image display
2. **Filesystem + MQTT** — covers most cases, needs external web server
3. **Filesystem + MQTT + optional HTTP** — maximum flexibility
4. **Embedded HTTP only** — like the legacy service, but misses MQTT benefits

## Decision Matrix

| Criterion             | MQTT only | FS + MQTT | FS + MQTT + HTTP | HTTP only |
| --------------------- | --------- | --------- | ---------------- | --------- |
| Docker simplicity     | 4         | 5         | 5                | 3         |
| Dashboard integration | 2         | 4         | 5                | 4         |
| Non-Docker support    | 3         | 3         | 5                | 4         |
| Implementation cost   | 5         | 4         | 3                | 4         |
| Multi-consumer        | 5         | 5         | 5                | 2         |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Docker sidecar pattern keeps the app focused on its core responsibility
- MQTT enables real-time updates for any consumer
- Filesystem output works universally regardless of deployment method
- Optional HTTP server covers non-Docker users without forcing it on Docker users
- Optional PNG enables native Home Assistant camera entity

### Negative

- Three output methods increase configuration surface
- PNG rendering adds an optional dependency (`cairosvg` or similar)
- Nginx sidecar adds a container to docker-compose (minimal overhead)

_2026-03-29_
