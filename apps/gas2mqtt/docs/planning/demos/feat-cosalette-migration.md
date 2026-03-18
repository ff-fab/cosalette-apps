# gas2mqtt Migration to cosalette Framework

*2026-02-22T07:31:42Z by Showboat 0.6.0*
<!-- showboat-id: bc29d189-1c23-4680-b63a-f77097b53a67 -->

Full migration of gas2mqtt from a 185-line monolithic legacy script to the cosalette IoT framework. 7 phases: settings/ports/adapters, domain logic (Schmitt trigger, EWMA, consumption tracker), gas counter device, temperature device, debug magnetometer device, app wiring, and docs/deployment.

```bash
uv run pytest packages/tests/ -q --no-header 2>&1 | grep -oP '\d+ passed'
```

```output
101 passed
```

```bash
uv run ruff check packages/src/ packages/tests/ 2>&1 && echo 'Lint: OK'
```

```output
All checks passed!
Lint: OK
```

```bash
uv run mypy packages/src/gas2mqtt/ 2>&1 | tail -1
```

```output
Success: no issues found in 16 source files
```

```bash
find packages/src/gas2mqtt -name '*.py' | sort
```

```output
packages/src/gas2mqtt/adapters/fake.py
packages/src/gas2mqtt/adapters/__init__.py
packages/src/gas2mqtt/adapters/qmc5883l.py
packages/src/gas2mqtt/devices/gas_counter.py
packages/src/gas2mqtt/devices/__init__.py
packages/src/gas2mqtt/devices/magnetometer.py
packages/src/gas2mqtt/devices/temperature.py
packages/src/gas2mqtt/domain/consumption.py
packages/src/gas2mqtt/domain/ewma.py
packages/src/gas2mqtt/domain/__init__.py
packages/src/gas2mqtt/domain/schmitt.py
packages/src/gas2mqtt/__init__.py
packages/src/gas2mqtt/main.py
packages/src/gas2mqtt/ports.py
packages/src/gas2mqtt/settings.py
packages/src/gas2mqtt/_version.py
```
