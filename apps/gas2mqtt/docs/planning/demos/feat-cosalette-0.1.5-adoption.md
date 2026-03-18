# Adopt cosalette 0.1.5: declarative main.py

*2026-02-27T19:37:39Z by Showboat 0.6.1*
<!-- showboat-id: c228543c-a2a6-4ba6-95fa-d61ddfc27688 -->

Migrated gas2mqtt to cosalette 0.1.5 with a fully declarative main.py:

- Adapter lifecycle: __aenter__/__aexit__ on adapters; Settings DI in constructors
- Direct registration: app.add_device() and app.add_telemetry() replace create_app() factory
- Store persistence: cosalette Store/DeviceStore replaces custom JsonFileStorage
- Declarative adapters: adapters= dict on App constructor
- All three device handlers extracted to separate files under devices/

```bash
cat packages/src/gas2mqtt/main.py
```

```output
"""gas2mqtt application entry point.

Wires the cosalette App with all devices, adapters, and settings.
The module-level ``app`` object is the entry point for the CLI:
``gas2mqtt`` runs ``app.run()``.
"""

from __future__ import annotations

import cosalette
from cosalette import OnChange

from gas2mqtt import __version__
from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.adapters.qmc5883l import Qmc5883lAdapter
from gas2mqtt.devices.gas_counter import gas_counter
from gas2mqtt.devices.magnetometer import magnetometer
from gas2mqtt.devices.temperature import make_pt1, temperature
from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings

# --- Settings & store ---

settings = Gas2MqttSettings()

_store: cosalette.Store = (
    cosalette.JsonFileStore(settings.state_file)
    if settings.state_file is not None
    else cosalette.NullStore()
)

# --- App creation ---

app = cosalette.App(
    name="gas2mqtt",
    version=__version__,
    description="Domestic gas meter reader via QMC5883L magnetometer",
    settings_class=Gas2MqttSettings,
    store=_store,
    adapters={
        MagnetometerPort: (Qmc5883lAdapter, FakeMagnetometer),
    },
)
"""Module-level app instance — entry point for the CLI."""

# --- Device registration ---

app.add_device("gas_counter", gas_counter)

app.add_telemetry(
    "temperature",
    temperature,
    interval=settings.temperature_interval,
    publish=OnChange(threshold={"temperature": 0.05}),
    init=make_pt1,
)

app.add_telemetry(
    "magnetometer",
    magnetometer,
    interval=settings.poll_interval,
    enabled=settings.enable_debug_device,
)
```

```bash
ls packages/src/gas2mqtt/devices/*.py
```

```output
packages/src/gas2mqtt/devices/gas_counter.py
packages/src/gas2mqtt/devices/__init__.py
packages/src/gas2mqtt/devices/magnetometer.py
packages/src/gas2mqtt/devices/temperature.py
```

```bash
uv run pytest packages/tests/ -q --tb=no 2>&1 | grep -oP '\d+ passed'
```

```output
99 passed
```

```bash
wc -l packages/src/gas2mqtt/main.py
```

```output
63 packages/src/gas2mqtt/main.py
```
