# API Reference

Auto-generated from source code docstrings using
[mkdocstrings](https://mkdocstrings.github.io/).

---

## Public API

What you need to configure and understand gas2mqtt:

- **[Settings](settings.md)** — `Gas2MqttSettings` and its fields (env vars, defaults,
  validation)
- **[Ports](ports.md)** — `MagnetometerPort` protocol and `MagneticReading` dataclass
- **[Domain](domain.md)** — Schmitt trigger and consumption tracker

## Internals

Implementation details for contributors and deep-dive readers:

- **[Devices](devices.md)** — cosalette device handlers (gas counter, temperature,
  magnetometer)
- **[Adapters](adapters.md)** — Hardware adapter implementations (QMC5883L, fake)
- **[Application](app.md)** — App factory, lifespan, and wiring
