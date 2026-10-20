---
status: Accepted
date: 2026-10-20
impact: moderate
tags: [devices, dependencies, packaging, security]
---

# ADR-002: GPIO backend

## Status

Accepted **Date:** 2026-10-20

## Context

geiger2mqtt counts falling edges on one GPIO pin of a Raspberry Pi, from a Pi Zero 2 W up to a Pi 5. Every app in this monorepo ships from the same `python:3.14-alpine` base image as a non-root user. The kernel exposes GPIO through the character device `/dev/gpiochip0`; the older `/dev/gpiomem` register mapping does not exist for the RP1 I/O controller of the Pi 5.

lgpio, the backend gpiozero recommends for current Raspberry Pi OS, publishes no wheels for CPython 3.14 or for musl (Alpine), so it must be built from source. Its sdist bundles the lg C library and SWIG bindings that predate SWIG 4.3 and the C23 default of GCC 15. lgpio also writes notification FIFOs to its working directory, which is not writable for the container user.

## Decision

Use gpiozero with the lgpio pin factory for pulse counting because it talks to the GPIO character device, which works on every Raspberry Pi model including the Pi 5 and needs no privileged access. The Dockerfile builds the locked, hash-checked lgpio sdist in a separate Alpine stage with `PYPI=1` (bundled lg sources, no system liblgpio), `swig<4.3` from PyPI and `CFLAGS="-std=gnu17 -Wno-error=incompatible-pointer-types"`; the root `pyproject.toml` applies the same settings to `uv sync`. The runtime image sets `GPIOZERO_PIN_FACTORY=lgpio` and `LG_WD=/tmp`, and the build fails if `import lgpio, gpiozero.pins.lgpio` fails. Compose passes only `/dev/gpiochip0` and adds the host's gpio group by numeric GID (`GEIGER2MQTT_GPIO_GID`, default 997), because the Alpine image has no gpio group by name.

## Decision Drivers

- Support for every Raspberry Pi model in use, including the Pi 5
- No privileged container and no `/dev/gpiomem` or `/dev/mem` access
- One base image (`python:3.14-alpine`) for every app in the monorepo
- Reproducible builds from the locked dependency graph
- Fail at build time, not on the device, if the native extension is broken

## Considered Options

### Option 1: gpiozero with lgpio built from source on Alpine (chosen)

gpiozero's `DigitalInputDevice` on the lgpio pin factory; lgpio compiled in a builder stage from the locked sdist.

- *Advantages:* Uses the GPIO character device on all models including the Pi 5; Only one device node is passed into the container; Stays on the shared Alpine base image; gpiozero's edge callbacks fit the pulse buffer directly
- *Disadvantages:* A source build with three workarounds (PYPI=1, swig<4.3, CFLAGS) that may need revisiting on lgpio or toolchain upgrades; The builder stage adds build time on CI

### Option 2: RPi.GPIO

The classic register-level GPIO library.

- *Advantages:* Widely documented, simple edge-detection API
- *Disadvantages:* Needs `/dev/gpiomem`; Does not support the Pi 5

### Option 3: gpiozero NativeFactory

gpiozero's pure-Python pin factory without a native backend.

- *Advantages:* No native extension to build
- *Disadvantages:* Marked experimental by gpiozero; Uses sysfs for edge detection and needs `/dev/gpiomem`

### Option 4: Debian slim image with prebuilt lgpio wheels

Switch this app to a Debian-based Python 3.12 image, for which lgpio publishes wheels.

- *Advantages:* No source build
- *Disadvantages:* Breaks the single base image and Python version shared by every app; Larger image

## Decision Matrix

| Criterion | gpiozero with lgpio built from source on Alpine | RPi.GPIO | gpiozero NativeFactory | Debian slim image with prebuilt lgpio wheels |
| --- | --- | --- | --- | --- |
| Hardware coverage (Pi Zero 2 W to Pi 5) | 5 | 2 | 2 | 5 |
| Container privileges | 5 | 3 | 2 | 5 |
| Monorepo consistency | 5 | 4 | 5 | 1 |
| Build simplicity | 2 | 3 | 5 | 4 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- The same image runs on every Raspberry Pi model without privileged mode
- A broken lgpio build fails the image build instead of the first start on a device
- Dev machines and `--dry-run` never import gpiozero, because the adapter imports it lazily

### Negative

- The source build depends on workarounds that an lgpio, SWIG or GCC upgrade may break
- Operators must check the host's gpio GID (`getent group gpio`) when it is not 997
- Importing lgpio creates notification FIFOs in the working directory, so `LG_WD` must point to a writable directory

_2026-10-20_
