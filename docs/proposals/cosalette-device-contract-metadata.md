# FEP-003: Contract Metadata for `@app.device()` and `add_device()`

**Status:** Proposed
**Cosalette target:** 0.3.7 or 0.4.0
**Triggered by:** PR #111 — cosalette 0.3.6 migration across cosalette-apps

---

## Problem

cosalette 0.3.6 introduced contract metadata kwargs on `@app.telemetry()` and
`@app.command()`:

```python
app.telemetry("gas_counter",
    summary="...",
    state_model=GasCounterState,
    behavior=["..."],
    effects=["..."],
)
app.command("consumption",
    summary="...",
    payload_model=dict,
    effects=["..."],
)
```

`@app.device()` and `app.add_device()` have no equivalent support. Their current
signatures are:

```python
def device(
    self,
    name: str | None = None,
    *,
    init: Callable[..., Any] | None = None,
    enabled: EnabledSpec = True,
) -> Callable[..., Any]: ...

def add_device(
    self,
    name: str,
    func: Callable[..., Awaitable[None]],
    *,
    init: Callable[..., Any] | None = None,
    enabled: bool = True,
    is_root: bool = False,
) -> None: ...
```

When this PR added `summary=` to device registrations in jeelink2mqtt and velux2mqtt,
both `ty` typecheck and runtime `TypeError` failures resulted, because the kwargs do not
exist on the method.

Concretely, these two calls currently cause CI failures:

```python
# jeelink2mqtt/receiver.py
@app.device(
    summary="JeeLink LaCrosse serial receiver: read sensor frames and publish state"
)
async def receiver(ctx, jeelink, store, settings): ...

# velux2mqtt/main.py
app.add_device(
    "cover",
    _cover_device,
    summary=f"Velux cover {_cover_cfg.name}: open/close/stop control",
)
```

---

## Evaluation: Should `@app.device()` have contract metadata?

### What `@app.device()` represents

`@app.device()` is the **C&C device** registration type — it runs as a concurrent
async task, owns the full device loop (open adapter, read frames, publish state, handle
commands via `ctx.on_command`). It is the most _complex_ of the three registration
archetypes. A device often does the work of multiple telemetry + command registrations
combined.

### The coherence argument

All three archetypes register a named device that appears in `cosalette manifest` output
and in the AsyncAPI schema. The manifest already exposes `name` for all three types. The
asymmetry in contract metadata creates:

| Registration | `summary` | `behavior` | `effects` | `state_model` | `payload_model` |
|---|---|---|---|---|---|
| `@app.telemetry()` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `@app.command()` | ✅ | ✅ | ✅ | ✅ | ✅ |
| **`@app.device()`** | ❌ | ❌ | ❌ | ❌ | ❌ |

This is directly observable in real apps:

- **jeelink2mqtt** `receiver` device: complex async serial loop, re-publishes per-sensor
  state, handles `mapping` commands via `ctx.on_command`. There is no way to document
  this in the manifest today.
- **velux2mqtt** `cover` devices: created dynamically per cover config via `add_device()`.
  Each has a unique name and behavior description but no metadata surface.

**Verdict: yes**, contract metadata on `@app.device()` is expected for coherence. The
device archetype is arguably _more_ in need of documentation than the simpler archetypes,
given its complexity.

---

## Proposed API changes

### `@app.device()` — add `summary`, `behavior`, `effects`

```python
def device(
    self,
    name: str | None = None,
    *,
    init: Callable[..., Any] | None = None,
    enabled: EnabledSpec = True,
    # --- new in FEP-003 ---
    summary: str | None = None,
    behavior: list[str] | None = None,
    effects: list[str] | None = None,
) -> Callable[..., Any]: ...
```

### `app.add_device()` — same additions

```python
def add_device(
    self,
    name: str,
    func: Callable[..., Awaitable[None]],
    *,
    init: Callable[..., Any] | None = None,
    enabled: bool = True,
    is_root: bool = False,
    # --- new in FEP-003 ---
    summary: str | None = None,
    behavior: list[str] | None = None,
    effects: list[str] | None = None,
) -> None: ...
```

### Why not `state_model` and `payload_model` on `@app.device()`?

`state_model` and `payload_model` are meaningless at the device level because:

- A device handler returns `None` (it publishes via `ctx.publish_state()` directly,
  not via a return value). There is no single state dict type to reference.
- A device receives commands via `ctx.on_command(handler)`, which has its own per-command
  routing. The payload type belongs to individual command handlers, not the device loop.

These two fields should remain absent from `@app.device()`.

### Manifest and schema impact

The `cosalette manifest` output and `cosalette schema init` should include the new
metadata in device channel descriptions, following the same pattern already implemented
for telemetry and command channels:

```yaml
# AsyncAPI channel produced by schema init
channels:
  receiverState:
    address: jeelink2mqtt/state
    x-cosalette-archetype: device
    x-cosalette-summary: "JeeLink LaCrosse serial receiver: ..."
    x-cosalette-behavior:
      - "Open serial port, read LaCrosse frames"
      - "Dispatch per-sensor state via publish_state()"
    x-cosalette-effects:
      - "Publishes to jeelink2mqtt/{sensor_name}/state"
```

---

## Migration path for cosalette-apps

Once cosalette ships FEP-003, the migration in PR #111 is straightforward:

1. Bump `cosalette>=0.3.7` (or target version) in all `pyproject.toml`
2. The existing `summary=` usages in jeelink2mqtt and velux2mqtt become valid
3. No further code changes required — the PR already anticipates the new API

The failing `typecheck` and `test` jobs in PR #111 (jeelink2mqtt, velux2mqtt) will
resolve automatically once the framework version is updated.

---

## Affected files in cosalette-apps (waiting on framework)

| File | Change | Status |
|---|---|---|
| `apps/jeelink2mqtt/packages/src/jeelink2mqtt/receiver.py` | `@app.device(summary=...)` | blocked on FEP-003 |
| `apps/velux2mqtt/packages/src/velux2mqtt/main.py` | `app.add_device(..., summary=...)` | blocked on FEP-003 |

---

## Non-blocking CI failures in PR #111

The `airthings2mqtt / lint`, `vito2mqtt / lint`, and `caldates2mqtt / lint` failures in
CI are devcontainer startup errors (HTTP 500) — infrastructure flakiness, not code
issues. They are unrelated to this proposal.

The `gas2mqtt / typecheck` failure is a separate typing issue: the lifespan function
annotates `settings: Gas2MqttSettings = ctx.settings` but `AppContext.settings` returns
the base `Settings` type. This requires either a `cast()` or a typed `AppContext` generic
— tracked separately from this proposal.
