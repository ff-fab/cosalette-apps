# cosalette Framework Enhancement: Default Store Path Resolution

**Date:** 2026-07-12
**Author:** caldates2mqtt / airthings2mqtt maintainer
**Status:** Proposal — awaiting framework review and implementation
**Context:** Follows cosalette 0.5.0 (ADR-048 retained-topic cleanup, opt-in via `store=`)
**Tracked by:** (beads issue to be filed)

---

## Executive Summary

cosalette 0.5.0 ships ADR-048: on first MQTT connect the framework diffs current
entities against a persisted snapshot and clears orphaned retained topics. The feature
is correct and well-designed, but its activation requires every app author to (a) pick
a store path, (b) write or copy a `resolve_store_path()` helper, (c) add `store=` to
`App(...)`, (d) wire `MemoryStore()` into test fixtures, and (e) add a volume env
override in `compose.yml`. This is four to five files touched per app for a cleanup
behavior the framework should own unconditionally.

**This proposal asks the framework to derive a default store path from the app name
using XDG conventions and an env override, so retained-topic cleanup works correctly
for every app by default — with zero app-side wiring.**

---

## Problem Statement

### The framework publishes retained topics; it should also clean them up

`cosalette.App` publishes `{app}/{entity}/availability` and `{app}/{entity}/state` as
retained MQTT messages on the app's behalf. When an entity is removed from config and
the app restarts, those topics persist on the broker indefinitely. ADR-048 resolves
this, but activating it requires apps to opt in with an explicit store. The opt-in
model places the **deployment concern** (store path, volume mount) on app authors to
access a **framework-level invariant** (retained topics match current entities). The
invariant should hold by default.

### The current workaround is copy-pasted boilerplate

Every app that wants cleanup currently must:

1. Write `resolve_store_path()` (30–40 lines) — identical or near-identical across apps
2. Call `JsonFileStore(resolve_store_path())` in `App(...)`
3. Add `<APP>_STORE_PATH=/app/data/store.json` to `compose.yml`
4. Inject `MemoryStore()` in integration test fixtures to avoid filesystem I/O

The boilerplate in `vito2mqtt`, `gas2mqtt`, and `jeelink2mqtt` is already diverging
slightly (env var names, fallback paths, docstrings). This will worsen as more apps
adopt the feature.

### Scope of the problem

Of the eight apps in this monorepo, three already configure `store=` for app-specific
reasons (gas2mqtt, jeelink2mqtt, vito2mqtt). Five do not (airthings2mqtt, caldates2mqtt,
suncast, velux2mqtt, wallpanel-control). Of the five store-less apps:

- **caldates2mqtt**: directly hit by the orphaned retained-topic bug in production
  (smoke test 2026-07-11 — `caldates2mqtt/birthday/availability` left retained after
  `contact_birthdays` calendar was removed).
- **airthings2mqtt**: single-entity app; same risk if the device key is ever renamed or
  the app is decommissioned.
- **suncast, velux2mqtt, wallpanel-control**: lower risk today but not immune.

---

## Proposed Solution

### Framework-owned default path resolution

If `store=` is omitted from `App(...)`, the framework **automatically** resolves and
creates a `JsonFileStore` using the following precedence:

```
1. <APP_NAME_UPPER>_STORE_PATH   (env var — explicit operator override)
2. $XDG_STATE_HOME/<app_name>/store.json
3. ~/.local/state/<app_name>/store.json   (XDG default)
```

`<app_name>` is the `name=` string passed to `App(...)`, with spaces/hyphens
normalised to underscores. The env var mirrors the convention already established by
`vito2mqtt` (`VITO2MQTT_STORE_PATH`) and `gas2mqtt`.

`JsonFileStore` already auto-creates parent directories on first write — no directory
pre-creation is needed.

### Explicit `store=None` to opt out

If the app explicitly passes `store=None`, the framework skips default resolution and
runs without a store (current no-op behaviour). Opt-out is always available; the
change is only to the default.

### Explicit `store=<any Store>` still works

Explicit `store=JsonFileStore(...)` or `store=SqliteStore(...)` takes precedence and
is used as-is. Apps that already wire a store (gas2mqtt, jeelink2mqtt, vito2mqtt)
are **unaffected**.

### Resulting API surface

```python
# Before (0.5.0 — explicit wiring required):
app = cosalette.App(
    name="caldates2mqtt",
    ...
    store=JsonFileStore(resolve_store_path()),   # must be added by app author
)

# After (proposed 0.5.x — zero wiring):
app = cosalette.App(
    name="caldates2mqtt",
    ...
    # store= omitted → framework resolves CALDATES2MQTT_STORE_PATH
    #                   or ~/.local/state/caldates2mqtt/store.json
)

# Opt out when cleanup is genuinely unwanted:
app = cosalette.App(
    name="caldates2mqtt",
    ...
    store=None,   # explicit opt-out; no default applied
)
```

---

## Path Resolution Algorithm (Detailed)

The framework should implement a function equivalent to the following inside
`cosalette._app` (not in app code):

```python
import os
from pathlib import Path

def _resolve_default_store_path(app_name: str) -> Path:
    """Derive the default store file path for *app_name*.

    Resolution order:
    1. ``<APP_NAME_UPPER>_STORE_PATH`` env var (operator override).
    2. ``$XDG_STATE_HOME/<app_name>/store.json``
    3. ``~/.local/state/<app_name>/store.json``

    ``<APP_NAME_UPPER>`` is derived by upper-casing and replacing hyphens and
    spaces with underscores: ``caldates2mqtt`` → ``CALDATES2MQTT``.

    The returned path is not guaranteed to exist; ``JsonFileStore`` creates
    parent directories on first save.
    """
    safe_name = app_name.upper().replace("-", "_").replace(" ", "_")
    env_key = f"{safe_name}_STORE_PATH"

    # 1. Explicit operator override
    explicit = os.environ.get(env_key)
    if explicit:
        return Path(explicit)

    # 2. XDG_STATE_HOME (set by desktop environments or operators)
    xdg_state = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return base / app_name / "store.json"
```

And applied in `App.__init__`:

```python
# Inside App.__init__, after the store= parameter is received:
_UNSET = object()

def __init__(self, ..., store: Store | Callable[..., Store] | None | _UNSET = _UNSET, ...):
    if store is _UNSET:
        # Default resolution — never fails; runtime write errors surface on first save
        resolved_path = _resolve_default_store_path(self.name)
        self._store = JsonFileStore(resolved_path)
        self._store_is_default = True
    else:
        self._store = store   # None, a Store instance, or a factory callable
        self._store_is_default = False
```

The `_UNSET` sentinel distinguishes "caller omitted store=" from "caller passed
store=None" without changing the external type signature of the parameter (it remains
`Store | Callable | None` in the public API — the `_UNSET` default is an
implementation detail).

---

## Test Ergonomics

### Integration tests — inject MemoryStore explicitly

Existing integration tests that wire the app with `build_integration_app()` or
`AppHarness` should pass `store=MemoryStore()` explicitly. This keeps tests fast
(no filesystem I/O), hermetic (no shared state between test runs), and explicit about
what they test.

```python
# In conftest.py (integration tests):
from cosalette import MemoryStore

def build_integration_app(fake_reader, calendars, *, store=None):
    app = cosalette.App(
        name="caldates2mqtt-test",
        ...
        store=store or MemoryStore(),   # explicit; avoids default path resolution
    )
    ...
```

### Unit tests that test the default path resolution itself

```python
def test_default_store_path_uses_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CALDATES2MQTT_STORE_PATH", str(tmp_path / "store.json"))
    app = cosalette.App(name="caldates2mqtt", ...)
    assert app._store._path == tmp_path / "store.json"

def test_default_store_path_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("CALDATES2MQTT_STORE_PATH", raising=False)
    app = cosalette.App(name="caldates2mqtt", ...)
    assert app._store._path == tmp_path / "caldates2mqtt" / "store.json"

def test_explicit_none_disables_store(monkeypatch):
    app = cosalette.App(name="caldates2mqtt", ..., store=None)
    assert app._store is None
```

### No automatic test-environment detection in framework code

The framework should **not** try to detect `"pytest" in sys.modules` or
`os.environ.get("PYTEST_CURRENT_TEST")` to choose a MemoryStore default. That kind
of environment coupling belongs in application/fixture code, not in library code
(see: "Hexagonal Architecture — infrastructure concerns at the boundary").

---

## Container Deployment

No compose.yml change is needed if:

- The container image sets `WORKDIR /app`, creates `/app/data`, and declares
  `VOLUME /app/data` in the Dockerfile, AND
- The compose service sets `<APP_NAME_UPPER>_STORE_PATH=/app/data/store.json`.

This is exactly what airthings2mqtt and caldates2mqtt already do for the volume mount.
The only addition is one env var line in `compose.yml`:

```yaml
# compose.yml (airthings2mqtt or caldates2mqtt) — no structural change
environment:
  - AIRTHINGS2MQTT_STORE_PATH=/app/data/store.json   # ← only new line
```

Apps that do NOT set this env var will write to the XDG path inside the container
(`~/.local/state/<app_name>/store.json`), which is typically ephemeral. The env var
override into `/app/data` is the correct production deployment — but the framework
default still works correctly without it (cleanup runs from an ephemeral store on the
same boot cycle, which still handles same-restart entity removal).

---

## Impact on Existing Store-Wired Apps

| App | Current `store=` | After this change |
|-----|------------------|-------------------|
| gas2mqtt | `store=_make_store()` | Unchanged — explicit store takes precedence |
| jeelink2mqtt | `store=JsonFileStore(Path("data")/...)` | Unchanged |
| vito2mqtt | `store=JsonFileStore(resolve_store_path())` | Unchanged |
| airthings2mqtt | not configured | Gets framework default → set env var in compose |
| caldates2mqtt | not configured | Gets framework default → set env var in compose |
| suncast | not configured | Gets framework default → entity cleanup works |
| velux2mqtt | not configured | Gets framework default |
| wallpanel-control | not configured | Gets framework default |

Existing store-wired apps can **optionally** remove their `resolve_store_path()`
helper and `store=` wiring after this lands, letting the framework handle it.
That simplification is advisory, not required.

---

## What This Does NOT Change

- **`store=` API** — unchanged; explicit store values are still accepted and preferred.
- **ADR-048 semantics** — the cleanup logic itself is unchanged; this proposal only
  affects when the store becomes non-None.
- **Store backend choice** — `JsonFileStore` is used as the default. Apps that need
  `SqliteStore` (or a custom backend) continue to pass it explicitly.
- **App-specific store usage** — apps using the store for their own data (sensor
  caching, reading history) should continue to wire it explicitly for clarity.
- **`MemoryStore` in tests** — test fixtures should still pass `store=MemoryStore()`
  explicitly; the framework does not change test behaviour.

---

## Migration Path After Framework Implements This

1. **Bump `cosalette` to the releasing version.**
2. **Remove `resolve_store_path()` helper** from apps that only wired it for cleanup.
3. **Remove `store=JsonFileStore(resolve_store_path())`** from `App(...)` in those apps.
4. **Add `<APP_NAME_UPPER>_STORE_PATH=/app/data/store.json`** to `compose.yml` for
   container-persistent store location.
5. **Update integration test fixtures** to pass `store=MemoryStore()` explicitly
   (or keep passing it — no breakage either way).

Total diff per app that removes boilerplate: approximately −50 lines
(`_store_path.py` helper gone, `store=` call gone, import gone).

---

## Open Questions for the Framework Maintainer

1. **`_UNSET` sentinel vs overloaded signature**: the proposal uses an internal
   sentinel to distinguish "omitted" from `None`. Is a cleaner alternative to model
   this as `store: Store | Callable | None = _DEFAULT` where `_DEFAULT` is an
   exported framework constant that apps can reference explicitly to opt back into
   default resolution after passing `None`?

2. **Startup warning for ephemeral store**: should the framework log a `WARNING` when
   the default store path resolves inside a container to a path that looks ephemeral
   (e.g., not under a known writable volume)? This would guide operators to set the
   env var without making the path mandatory.

3. **`MemoryStore` as test-only default**: is it worth the framework inspecting
   `sys.modules` for pytest and defaulting to `MemoryStore()`? The proposal recommends
   against it (§ Test Ergonomics), but the framework maintainer may have a different
   opinion given how often integration tests need this.

4. **Shared store path prefix**: some apps use `XDG_STATE_HOME/<app_name>/store.json`
   (proposed here) while the existing apps use `XDG_STATE_HOME/<app_name>/store.json`
   via their own helpers. The convention is consistent; confirming it as canonical would
   allow the boilerplate removal migration.

5. **SqliteStore as default**: for apps with many entities or high write frequency,
   `JsonFileStore` (full-file rewrite on each save) may eventually become a concern.
   Should the framework default be configurable at import time
   (e.g. `cosalette.set_default_store_backend(SqliteStore)`)?

---

## Summary

The framework currently asks app authors to own a store path for a cleanup behavior
the framework should own unconditionally. This proposal closes that gap by:

- Resolving a default store path from the app name (XDG + env override) when `store=`
  is omitted.
- Keeping explicit `store=None` as an opt-out with no change to the existing API.
- Leaving all existing store-wired apps unaffected.
- Eliminating four to five files of identical boilerplate per new adopter.
- Making retained-topic cleanup a zero-config invariant rather than an opt-in feature.
