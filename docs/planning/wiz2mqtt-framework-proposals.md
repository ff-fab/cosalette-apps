# Index: wiz2mqtt framework proposals

**Status:** phase 0 of beads epic `cap-10u` — all three documents filed **Raised by:**
cosalette-apps, while planning the wiz2mqtt migration **Verified against:** cosalette
0.6.0

Specifying `wiz2mqtt` — a bridge exposing 14 WiZ bulbs as 14 independent MQTT entities —
surfaced three framework-level problems. None of them has a downstream fix worth
building, so **all three are upstream asks against cosalette**, not work items in this
repository. Phase 0 of the epic is writing them down; the build phase does not start
until they land.

| Document                                                                            | Kind        | Gate task   | Downstream work it blocks                            |
| ----------------------------------------------------------------------------------- | ----------- | ----------- | ---------------------------------------------------- |
| [Config-file settings source](cosalette-config-file-settings-proposal.md) (`cap-10u.2`) | enhancement | `cap-10u.5` | `cap-10u.8` scaffold, `cap-10u.17` task template     |
| [Consumer integration overhaul](cosalette-consumer-integration-proposal.md) (`cap-10u.3`) | enhancement | `cap-10u.6` | `cap-10u.8` scaffold, `cap-10u.14` consumer integration |
| [Command dispatch bug](cosalette-command-dispatch-bug.md) (`cap-10u.1`)             | bug         | `cap-10u.7` | nothing                                              |

Each document is consumed by exactly one gate task, which closes when a cosalette
release carrying the fix is on PyPI and the app's pin can be bumped. Per AGENTS.md the
gate tasks hold no decision logic — the documents do.

## Dependency order

**The two enhancements block the build outright.** `cap-10u.5` and `cap-10u.6` both
block `cap-10u.8` (scaffold the app), so no wiz2mqtt code is written until they close.
They are independent of each other and may land upstream in either order:

- the config-file source decides how 14 bulbs are _declared_, and the entity set is
  derived from that inventory — so the settings shape has to exist before the app does;
- the consumer overhaul decides how those entities reach Home Assistant and openHAB, and
  against 0.6.0 both generators produce output their own consumers reject for any device
  carrying a state channel and a command channel — which is every bulb.

**The dispatch bug blocks nothing downstream, and is still the one that decides whether
the app ships.** `cap-10u.7` has no `blocks` edges: the handlers, the entity model and
the tests can all be written against the current framework, and they will be. What the
defect costs is production viability — one bulb switched off at the wall stalls commands
for the other thirteen, while the app keeps publishing `status: "online"` and reporting
itself healthy. An app that behaves that way cannot go in front of a household, so
`cap-10u.7` gates **deployment** rather than construction.

If the upstream fix lands narrower than proposed — an opt-in flag, or a timeout without
per-entity dispatch — the gate stays open and the 14-bulb configuration is reassessed
rather than shipped.
