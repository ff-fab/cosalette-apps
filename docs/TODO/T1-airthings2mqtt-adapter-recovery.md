# T1: airthings2mqtt BLE adapter recovery

| Field   | Value                                                         |
| ------- | ------------------------------------------------------------- |
| Status  | Decided 2026-10-02                                            |
| Trigger | Before any airthings2mqtt adapter-restart or D-Bus write work |
| Gate    | beads `cap-oxdp.7` (epic `cap-oxdp`)                          |

## Problem

An early adopter lost radon data for 11 to 38 hours in three outages (2026-09-24 to
2026-10-02). In one of them the sensor stopped answering and a manual adapter power cycle
did not help. Two app-side gaps remain after the error classification fix (`cap-oxdp.1`):

1. **The restart configuration is dead.** `App(restart_after_failures=5, max_restarts=3)`
   never acts, because cosalette restarts only adapters that are async context managers,
   and `BleakAirthingsReader` is not one. The same check logs
   `Adapter AirthingsReaderPort is health-checkable but not restartable` at every start.
2. **The health check cannot fail on the incidents that occurred.** `health_check()` asks
   BlueZ whether `hci0` is `Powered`. That stayed true through every outage, so it never
   triggers recovery for a deaf radio or a missing sensor.

## Options

| Option                                                                                                      | For                                                     | Against                                                                                                                         |
| ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| A. Declare `restartable = False`, drop the restart knobs                                                    | Honest configuration, no new behaviour                  | cosalette 0.10.x still warns before honouring the flag (upstream F-5)                                                           |
| B. Opt-in reset: toggle `org.bluez.Adapter1.Powered` after N device-not-found errors with zero advertisers | Cheap first escalation the process can do by itself      | Did not help in the incident; disturbs other BLE users on the host; needs a D-Bus policy that allows the write from a non-root UID |
| C. Wait for cosalette data-driven restarts (stale entity triggers the restart path)                          | One mechanism for all apps; no app-specific D-Bus writes | Blocked on an upstream release                                                                                                  |

## Open questions (moot after the resolution below)

- Can the container's D-Bus policy write `Adapter1.Powered` with the read-only system bus
  socket mount and a non-root UID (proposal open question 3)?
- Does option B need the advertiser count from the pre-connect scan (`cap-oxdp.5`) to
  avoid power-cycling an adapter that works and a sensor that has a flat battery?

## Resolution

**Decided 2026-10-02 (gate `cap-oxdp.7` closed).** A non-root user shall not be able to
power-cycle the Bluetooth adapter, and airthings2mqtt is not designed to do so. Option B
is rejected. Inside the app, recovery is reconnect and backoff only: retry, then mark
the entity `offline`. Recovering the adapter is the job of the host and the operator.
Option C stays acceptable only if it restarts the app's adapter object and never the
radio itself.

Follow-ups:

- `cap-oxdp.10`: remove the dead restart knobs and declare the adapter `restartable = False`.
- `cap-oxdp.11`: an operator runbook for host-side adapter recovery.
- `cap-oxdp.12`: record this decision as an app ADR.
