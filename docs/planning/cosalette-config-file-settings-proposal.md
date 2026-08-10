# Enhancement Proposal: a native config-file settings source for cosalette

**Status:** proposed — requests an amendment to cosalette ADR-003 plus three CLI/loader
changes **Raised by:** cosalette-apps, while specifying `wiz2mqtt`, a bridge exposing 14
WiZ bulbs as 14 independent MQTT entities (beads epic `cap-10u`, issue `cap-10u.2`)
**Verified against:** cosalette 0.6.0 / pydantic-settings 2.14.2 / Python 3.14
(`_settings/__init__.py`, `_app/__init__.py`, `_cli.py`, `_schema/_cli.py`,
`_schema/_cli_helpers.py`, `_wiring/_resolution_checks.py`, and the pydantic-settings
sources they delegate to)
**Index:** [wiz2mqtt framework proposals](wiz2mqtt-framework-proposals.md)

## Context

cosalette configures applications exclusively through environment variables and `.env`
files, per **ADR-003: Configuration System**. That ADR considered "Option 2: YAML/TOML
configuration files" and rejected it, on three stated grounds: it violates 12-factor,
it requires file mounting in containers, and it creates "two sources of truth if env
vars are also supported". A fourth was listed — "Does not integrate with pydantic's
validation".

The decision has held up well for scalar configuration. It has not held up for
**inventories**: lists of homogeneous entities whose cardinality is a deployment
property. ADR-003 saw this coming and wrote it into its own Negative Consequences:

> Complex nested configurations (like actuator lists) require JSON encoding in env vars,
> which is less readable.

Six months of downstream use later, that sentence describes real committed artifacts.
Three applications in cosalette-apps — a monorepo of eight cosalette bridges, and the
source of this report — already encode an entity inventory as a single-line JSON blob in
an environment variable, because there is no other way to express it:

```dotenv
VELUX2MQTT_COVERS=[{"name":"blind","pin_up":17,"pin_stop":27,"pin_down":22,"travel_duration_up":30,"travel_duration_down":28},{"name":"window",...}]
CALDATES2MQTT_CALENDARS=[{"key":"birthday","url":"https://example.invalid/caldav/birthday","calendar_name":"Birthdays",...}]
JEELINK2MQTT_SENSORS=[{"name":"office","temp_offset":0.0,"humidity_offset":0.0},{"name":"outdoor",...}]
```

The application that triggered this proposal, `wiz2mqtt`, needs an inventory of **14
bulbs**, each carrying `name`, `ip`, an optional `mac` for identity verification, and a
`when_unreachable` policy. Encoded the ADR-003 way, with representative values, that is
a **single-line environment variable of roughly 1.3 kB** — no comments, no per-entity
diff granularity, and no way to review a one-bulb change without reading the whole blob.
Written as TOML it is 14 readable four-line tables.

This proposal does **not** ask cosalette to abandon environment-first configuration. It
asks for a *file source underneath the env source*, with the precedence chain
`env > file > defaults`, so that a config file is a place to put **defaults with
structure** and an environment variable can still override any of them. That precedence
chain is the direct answer to ADR-003's "two sources of truth" objection, and it is
developed in the section on ADR-003 below.

Findings 1–3 are the concrete defects a downstream author hits when they build this
themselves on top of pydantic-settings today — which is possible, and which we did, in
order to write this document. Findings 4–5 are why the fix belongs in the framework.

---

## Finding 1 — a missing config file yields an empty schema and exit 0

`pydantic-settings` skips config files that do not exist, silently, by design:

```python
# pydantic_settings/sources/base.py:216-217, in ConfigFileSourceMixin._read_files
if not file_path.is_file():
    continue
```

Every file-backed source inherits this: `TomlConfigSettingsSource` reads its file in
`__init__` via `self._read_files(...)`
(`pydantic_settings/sources/providers/toml.py:56`), so a missing path produces an empty
dict, every field falls back to its default, and validation passes.

For a scalar setting that is harmless. For an **inventory** it is not, because the
default is an empty list, and an empty inventory is a valid-looking configuration that
registers zero entities. Reproduced against cosalette 0.6.0 with a probe app whose
`bulbs: list[Bulb]` field is fed by a `TomlConfigSettingsSource`:

```console
$ cosalette schema dump --app cfgprobe.main:app --resolve-settings   # config file present
asyncapi: 3.0.0
info: {title: cfgprobe, version: 0.1.0, ...}
channels:
  hallState: {address: cfgprobe/hall/state, ...}
  kitchenState: {address: cfgprobe/kitchen/state, ...}
$ echo $?
0

$ cosalette schema dump --app cfgprobe.main:app --resolve-settings   # config file absent
Dict-name callable returned empty dict for bulb_state
asyncapi: 3.0.0
info: {title: cfgprobe, version: 0.1.0, ...}
$ echo $?
0
```

The second document has **no `channels` key at all**, and the command still succeeds.
The one trace of the problem is a `logger.warning` at
`_wiring/_resolution_checks.py:51`, which

- only fires for ADR-023 dict/list `name=` NameSpecs — an app that feeds the same
  inventory through `@app.on_configure` or plain settings gets no diagnostic whatsoever;
- goes to the logging system, not to the exit code.

The practical consequence is a **silently truncated committed schema**. A regeneration
task of the shape `cosalette schema dump ... > docs/schema.yaml` (which is exactly what
this repository runs) redirects stdout, leaves the warning on stderr, exits 0, and
overwrites the checked-in AsyncAPI artifact with a channel-less stub. Home Assistant
discovery is generated from that artifact, so the failure surfaces later as entities
that quietly stopped existing.

### Correction to the original claim

This was filed as a **parity gap against `--env-file`**. It is not — `--env-file` is
equally silent, and the correction matters for the shape of the fix.

`DotEnvSettingsSource._read_env_files` has the same guard, spelled differently
(`pydantic_settings/sources/providers/dotenv.py:106`):

```python
if env_path.is_file() or env_path.is_fifo():
    dotenv_vars.update(self._read_env_file(env_path))
```

and cosalette does not add an existence check of its own: `--env-file` is declared as a
bare `Path` with no `exists=True` (`_schema/_cli.py:105-113`) and as a bare `str` on the
app CLI (`_cli.py:177-180`). The only `exists=True` constraints in the package are on
*schema* file arguments (`_schema/_cli.py:127`, `:184`, `:242`). Verified:

```console
$ cosalette schema dump --app cfgprobe.main:app --resolve-settings \
    --env-file /path/that/does/not/exist.env
asyncapi: 3.0.0
...channels present...
$ echo $?
0
```

So the real defect is **shared**, and the right rule is narrower and more defensible
than "config files must exist":

> A path the operator **named explicitly** must exist. A path the framework **defaulted
> to** may be absent.

`.env` absent when nobody asked for it is normal. `--env-file prod.env` pointing at
nothing is a typo, and so is `--config-file wiz2mqtt.toml` pointing at nothing.

**Proposed fix:** in the settings loader, distinguish an explicitly supplied path from a
defaulted one and fail with `EXIT_CONFIG_ERROR` (1) on the former:
`Error: config file not found: <path>`. Apply the same rule to `--env-file` — it is the
same one-line check and it closes the same hole. Keep default-path absence silent so no
existing deployment breaks.

---

## Finding 2 — a malformed config file is reported as an import failure

Confirmed exactly as filed, and the mechanism is worth spelling out because it dictates
where the fix has to go.

With a TOML file containing an unclosed array:

```console
$ cosalette schema dump --app cfgprobe.main:app --resolve-settings
Error: Failed to import module 'cfgprobe.main': Unclosed array (at end of document)
$ echo $?
1
```

The message names the wrong subsystem. Nothing is wrong with the module; a config file
is malformed, and the operator is sent to read Python.

### Why it lands there

`App.__init__` eagerly constructs the settings object at **import time**
(`_app/__init__.py:244-247`):

```python
try:
    self._settings: Settings | None = settings_class()
except ValidationError:
    self._settings = None
```

That is the whole story. Because settings are built while `main.py` is being imported,
the TOML parse happens inside `importlib.import_module` at `_schema/_cli_helpers.py:91`,
and `TOMLDecodeError` is not a `ValidationError`, so it escapes the guard on line 246
and is caught by the broad handler two frames out:

```python
# _schema/_cli_helpers.py:98-103
except Exception as exc:
    typer.echo(f"Error: Failed to import module '{module_path}': {exc}", err=True)
    raise typer.Exit(EXIT_CONFIG_ERROR) from exc
```

There are **four** narrow guards in the settings path, not three, and the one that
actually loses is the import-time one:

| # | Location                    | Catches           | Outcome                                    |
| - | --------------------------- | ----------------- | ------------------------------------------ |
| 1 | `_app/__init__.py:246`      | `ValidationError` | **escaped** — this is where the error is   |
| 2 | `_cli.py:208`               | `ValidationError` | never reached (import already failed)      |
| 3 | `_cli_helpers.py:206`       | `ValidationError` | never reached                              |
| 4 | `_cli_helpers.py:248`       | `ValueError`      | never reached                              |

Two consequences follow that an implementer needs to know:

- **The CLI flag arrives too late to matter.** `--env-file` is applied by *re-building*
  settings after import (`_cli.py:207`, `_cli_helpers.py:205`:
  `app._settings_class(_env_file=env_file)`). The import-time construction on
  `_app/__init__.py:245` always uses the **default** paths. A `--config-file` flag added
  naively would therefore still be preceded by a load of the default config file, and a
  malformed default file would break the import before the flag could redirect anything.
- **Do not fix this by widening guard 4 to `ValueError`.** `tomllib.TOMLDecodeError`
  *is* a `ValueError` subclass, but `yaml.YAMLError` is **not** (verified: MRO is
  `YAMLError → Exception`). Widening to `ValueError` fixes TOML and leaves YAML — the
  format this proposal puts behind an extra — reported as an import failure forever.

The runtime path is worse than the tooling path. `python -m myapp.main --version` with
the same malformed file produces a raw uncaught `TOMLDecodeError` traceback and exit 1,
because the failure happens during module import, before Typer has parsed a single
argument.

**Proposed fix:**

1. Wrap config-file (and `.env`) source construction in a cosalette-owned exception —
   `SettingsLoadError`, carrying the offending path — raised for **any** parse failure,
   not a specific decoder's type.
2. Catch it alongside `ValidationError` at `_app/__init__.py:246`, `_cli.py:208`, and
   `_cli_helpers.py:206`, and report
   `Error: could not load configuration file '<path>': <detail>` with
   `EXIT_CONFIG_ERROR`.
3. Preferably also make `App.__init__`'s eager settings construction lazy, so that
   import-time work does not depend on files the CLI is about to override. That is a
   larger change and this proposal does not require it — but until it happens, any
   `--config-file` flag is a partial fix by construction, because the default file is
   read before the flag is seen.

---

## Finding 3 — no way to point tooling at a config file

Confirmed. cosalette 0.6.0 has **no config-file support of any kind**:

```console
$ grep -rn -e config_file -e toml_file -e yaml_file \
      -e TomlConfig -e YamlConfig -e JsonConfig --include='*.py' .../site-packages/cosalette/
$ echo $?
1        # no matches
```

`cosalette schema dump --help` offers exactly three options besides `--help`: `--app`,
`--resolve-settings`, `--env-file`. Same for `schema check` and `schema init`
(`_schema/_cli.py:248`, `:298`, `:328`).

This is the finding that makes the other two block a downstream application rather than
merely annoy it. cosalette **ADR-051** established that schema generation for apps with
settings-derived entity names must resolve settings first, and shipped
`--resolve-settings` / `--env-file` on `schema dump` (2026-08-05), extended to
`schema check` and `schema init` in the 2026-08-08 amendment. Its Negative Consequences
say so plainly:

> CI environments will need to provide a representative settings profile or env file for
> `schema dump` to succeed.

The mechanism ADR-051 provides for supplying that profile is `--env-file`. An
application whose entity set lives in a config file has **no equivalent** — it cannot
name a profile, so the committed schema depends on whatever config file happens to sit
in the working directory. Combined with Finding 1, a CI machine without that file
regenerates an empty schema and exits 0.

**Proposed fix:** add `--config-file` everywhere `--env-file` already exists —
`schema dump`, `schema check`, `schema init`, and the app CLI built by `build_cli`
(`_cli.py:177`) — with the same "only meaningful with `--resolve-settings`" semantics on
the schema commands. Accepting the option more than once (merging in order) is a
worthwhile extra: `ConfigFileSourceMixin._read_files` already takes a sequence and has a
`deep_merge` flag (`pydantic_settings/sources/base.py:202`).

*Adjacent, out of scope, noted for completeness:* `cosalette manifest` accepts neither
`--resolve-settings` nor `--env-file`, so it already cannot introspect a
settings-derived app. Whatever shape `--config-file` takes, `manifest` is the natural
next command to receive both.

---

## Finding 4 — pydantic-settings offers no runtime kwarg to plumb a path through

This is why `--config-file` is a framework change rather than a three-line CLI addition,
and it was not in the original report.

`--env-file` is trivial to implement today because `BaseSettings.__init__` accepts a
private runtime kwarg for it (`pydantic_settings/main.py:186`), which cosalette passes
straight through:

```python
settings = app._settings_class(_env_file=env_file)   # _cli.py:207, _cli_helpers.py:205
```

The `__init__` signature (`pydantic_settings/main.py:180-210`) has `_env_file`,
`_env_file_encoding`, `_secrets_dir` and a long list of `_cli_*` kwargs — and **no**
`_toml_file`, `_yaml_file`, or `_config_file`. A config file's path is only reachable
through `model_config` (read at class-definition time) or through
`settings_customise_sources`, where the source object is constructed.

So cosalette has to own the source construction. It is well placed to: it already owns
the base `Settings` class and its `model_config` (`_settings/__init__.py:286-291`).

**Proposed shape** (sketch, not a mandate):

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        config_file=None,          # new: str | Path | Sequence[Path] | None
        extra="ignore",
    )

    def __init__(self, *args, _config_file=None, **kwargs): ...   # runtime override

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                   dotenv_settings, file_secret_settings):
        return (init_settings, env_settings, dotenv_settings,
                _ConfigFileSource(settings_cls),      # format dispatch + fail-loud
                file_secret_settings)
```

Defining `settings_customise_sources` once on the base class is what makes this worth
doing upstream: downstream apps then declare `config_file="myapp.toml"` in their
`SettingsConfigDict` and get the whole behaviour — precedence, fail-loud, format
dispatch, CLI override — with no boilerplate and, importantly, **identically across
apps**, which is the point of a framework.

---

## Finding 5 — TOML in core costs nothing; YAML is already an optional dependency

cosalette's metadata pins `Requires-Python: >=3.14`, so **`tomllib` is in the standard
library**. A TOML source adds zero dependencies to core, in a framework whose core
dependency list is deliberately six packages long (`aiomqtt`, `orjson`, `packaging`,
`pydantic`, `pydantic-settings`, `typer`).

YAML is heavier and genuinely optional — and cosalette already treats it that way:
`pyyaml>=6.0` ships under the existing `schema` extra. The proposal is to keep that
asymmetry rather than smooth it over: **TOML in core, YAML behind an extra**, with the
missing-dependency path producing the same friendly hint cosalette already emits for
PyYAML at `_schema/_cli.py:60-68` and `_schema/_cli_helpers.py:50-56`:

```text
Error: PyYAML is required to read '<path>'.

Hint: Install with: pip install cosalette[config-yaml]
```

Whether that extra is new (`config-yaml`) or folded into the existing `schema` extra is
a packaging judgement call for the maintainer; this document has no stake in it.

Format dispatch on the file suffix (`.toml` → `tomllib`; `.yaml`/`.yml` → PyYAML;
optionally `.json` → stdlib `json`) is the least surprising rule and needs no extra
configuration key.

---

## The precedence chain

`env > file > defaults`, with secrets in the environment only.

Concretely, source order `(init, env, dotenv, config_file, file_secret)` — earlier
sources win in pydantic-settings. Verified end to end on cosalette 0.6.0:

```console
# TOML declares bulbs; env declares bulbs -> env wins outright
$ CFGPROBE_BULBS='[{"name":"envwins","ip":"9.9.9.9"}]' python -c '...'
bulbs: [('envwins', '9.9.9.9')]

# TOML sets mqtt.host and mqtt.port; env overrides only mqtt.port -> partial merge
$ CFGPROBE_MQTT__PORT=8883 python -c '...'
mqtt.host = broker.from.toml | mqtt.port = 8883
```

The second case is the important one: nested models merge **per field** across the two
sources, so a config file can carry structure while an environment variable overrides
one leaf of it. Nothing in cosalette needs to implement that — `env_nested_delimiter`
already does it.

**Secrets stay in the environment.** Config files get mounted, templated, shared and
code-reviewed; `SecretStr` fields should not. The precedence chain already makes
this safe rather than merely conventional — any value in a file is overridable by an env
var, so a secret that leaked into a file can always be superseded without editing it. A
warning when a `SecretStr` field resolves from the config-file source would be a
welcome addition, but this proposal deliberately does not ask for a hard failure: the
line between "secret" and "credential-shaped string" is not the framework's to draw.

---

## What this asks of ADR-003

An **amendment**, not a reversal. ADR-003's Decision — pydantic-settings with
`BaseSettings`, `env_nested_delimiter="__"`, `SecretStr` for credentials — is untouched
and correct. What changes is the corollary that file sources are excluded, recorded in
its rejection of Option 2. Taking that rejection's four stated disadvantages in turn:

**"Does not fit the Docker/container convention of env-based config (12-factor
violation)."** Under `env > file > defaults` the file is a *default provider*, not a
configuration authority. A container that mounts no file and sets environment variables
behaves **exactly** as it does today, byte for byte. 12-factor's actual requirement is
that config be environment-overridable and not baked into the image; a mounted,
env-overridable inventory file satisfies it. It is also worth noting that the same
convention already accepts `.env` files, which are equally files and equally mounted.

**"Requires file mounting in containers."** Only for applications that choose to use
one. Nothing here is mandatory: `config_file` defaults to `None` and every existing app
keeps working with no change. `wiz2mqtt` would mount one file; the other eight apps in
cosalette-apps would mount none.

**"Two sources of truth if env vars are also supported."** This is the objection with
real force, and precedence is the answer to it. Two sources are only two *truths* if the
resolution order between them is undefined. A strict, documented, single-direction chain
makes exactly one of them authoritative at any point: the environment, always, with the
file supplying values the environment did not. That is the same relationship `.env`
already has to the real environment today — ADR-003 shipped a two-source configuration
system on day one, and nobody experiences `.env` as a competing truth.

**"Does not integrate with pydantic's validation."** This one is simply no longer true.
It was written on 2026-02-14; pydantic-settings now ships `TomlConfigSettingsSource`,
`YamlConfigSettingsSource` and `JsonConfigSettingsSource` as first-class sources whose
values traverse the identical validation pipeline. Verified: the probe app's
`list[Bulb]` field is parsed, coerced and validated from TOML by the same machinery that
handles env vars, and ADR-003's own headline benefits — type safety, `SecretStr`,
cross-field validators — apply unchanged.

Against that, ADR-003's Negative Consequences already concede the cost this proposal
removes: "complex nested configurations ... require JSON encoding in env vars, which is
less readable". Its own decision matrix scores both YAML/TOML and pydantic-settings **5**
on nesting support — but pydantic-settings earns that 5 precisely by JSON-encoding into
an env var, which is the readability cost the same ADR concedes two sections later. This
proposal keeps the 5 and removes the cost. The evidence that the concession was accurate
is three committed `.env.schema` files in cosalette-apps, each a single-line JSON
inventory, and a fourth application that cannot reasonably be written that way at all.

Suggested amendment text, in ADR-003's own idiom:

> **Amendment (Option 2 revisited).** Structured config files are admitted as a
> *subordinate* settings source, not as an alternative to environment variables.
> Precedence is fixed at `env > file > defaults`; secrets remain environment-only; the
> feature is opt-in per application via `config_file=` and defaults to disabled. The
> "two sources of truth" objection is answered by the precedence chain, and the "does
> not integrate with pydantic's validation" objection is obsolete as of
> pydantic-settings' first-class file sources.

---

## Summary

| # | Finding                                     | Impact                                              | Suggested fix                                              |
| - | ------------------------------------------- | --------------------------------------------------- | ---------------------------------------------------------- |
| 1 | Missing config file → empty schema, exit 0  | Silently truncates the committed AsyncAPI artifact  | Fail loudly on an explicitly named path; same for `--env-file` |
| 2 | Malformed file → "Failed to import module"  | Names the wrong subsystem; raw traceback at runtime | `SettingsLoadError` caught beside `ValidationError`         |
| 3 | No `--config-file` anywhere                 | ADR-051 profile selection impossible for such apps  | Add it to `dump`/`check`/`init` and `build_cli`            |
| 4 | No pydantic-settings runtime kwarg          | `--config-file` cannot mirror `--env-file`'s one-liner | cosalette owns the source via base-class sources hook    |
| 5 | TOML is stdlib; PyYAML already an extra     | —                                                   | TOML in core, YAML behind an extra, dispatch on suffix     |

Findings 1–3 are the blocking set. Finding 4 constrains how they are implemented, and
Finding 5 is the argument that the core half is cheap.

Ordered by value if the work has to be split: **3** (unblocks profile selection), then
**1** (stops silent artifact truncation), then **2** (makes the error message honest).

## What cosalette-apps is doing

Waiting. `wiz2mqtt` is gated on this landing upstream and **no downstream workaround is
being built** — the gate is tracked as a first-class blocker (`cap-10u.5`) on the whole
application.

That deserves justification, because the workaround is real: a downstream app can add
`settings_customise_sources` returning a `TomlConfigSettingsSource` in about fifteen
lines, and the probe app used to verify this document does exactly that and works. What
it cannot do is:

- select a config-file profile for `schema dump` / `schema check` (Finding 3), so the
  committed schema would depend on whichever file happens to be on the developer's disk;
- avoid regenerating an empty schema on any machine lacking that file (Finding 1);
- produce an honest error message when the file is malformed (Finding 2).

Those are properties of the framework's CLI and loader, not of the application. Building
the workaround would buy a working app and three permanent traps, one of which silently
corrupts a checked-in artifact that Home Assistant discovery is generated from.

When the feature lands, this repository will:

- give `wiz2mqtt` a `wiz2mqtt.toml` holding **only** the bulb inventory, with a
  validator rejecting every other top-level key. Everything else stays in `.env`; all
  secrets stay in the environment (`cap-10u.9`).
- commit `wiz2mqtt.toml.example` and a separate `wiz2mqtt.toml.schema` profile, and
  gitignore the real file — the same split the existing `.env` / `.env.schema` pattern
  uses.
- add `SCHEMA_CONFIG_FILE` to its reusable per-app task template, mirroring the existing
  `SCHEMA_ENV_FILE` variable that already drives `--resolve-settings --env-file` for the
  three ADR-051 apps (`cap-10u.17`).

**One request on the shape of the fix.** The fail-loud rule in Finding 1 is worth more
than the feature it guards. If `--config-file` ships without it, every config-file app
in this repository inherits a regeneration path that turns a missing file into a
successful, empty, committed schema — and that failure is invisible until entities go
missing in Home Assistant weeks later. Of the three blocking findings, that is the one
we would least like to see deferred to a follow-up.
