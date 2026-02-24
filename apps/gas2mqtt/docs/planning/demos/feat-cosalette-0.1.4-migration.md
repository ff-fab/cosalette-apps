# Adopt cosalette 0.1.4: PT1 filter, init=, eager settings

*2026-02-23T21:31:26Z by Showboat 0.6.0*
<!-- showboat-id: bffbebcd-b3aa-4976-af88-fc7f60e6a198 -->

Upgraded cosalette 0.1.2 → 0.1.4. Replaced custom EwmaFilter with cosalette's Pt1Filter via init= callback. Used eager settings (app.settings) to eliminate model_fields hack. Inlined temperature and magnetometer handlers. Renamed ewma_alpha to smoothing_tau (1200.0s default). Deleted dead code: ewma.py, handler factories, test_ewma.py.

```bash
uv run pytest packages/tests/ -q 2>&1 | grep -oP '\d+ passed'
```

```output
119 passed
```

```bash
grep -c 'Pt1Filter\|init=' packages/src/gas2mqtt/main.py
```

```output
6
```

```bash
grep -c 'app.settings' packages/src/gas2mqtt/main.py && ! grep -q 'model_fields' packages/src/gas2mqtt/main.py && echo 'no model_fields hack'
```

```output
1
no model_fields hack
```

```bash
wc -l packages/src/gas2mqtt/main.py
```

```output
132 packages/src/gas2mqtt/main.py
```
