---
status: Accepted
date: 2026-10-20
impact: moderate
tags: [telemetry, devices, configuration]
---

# ADR-001: Measurement model

## Status

Accepted **Date:** 2026-10-20

## Context

geiger2mqtt turns the pulses of a Geiger-Müller counter board on one GPIO pin into three readings: counts per minute (CPM), the dose rate derived from CPM, and an average dose rate over a longer window. Natural background gives a few pulses per second at most (about 10 to 40 CPM for an SBM-20 tube), and pulse arrival is a Poisson process, so a single minute of counting has a relative error of roughly 1/sqrt(CPM), about 20 % at 25 CPM. The average dose rate exists to smooth that noise.

The readings are published every `publish_interval` seconds (default 30 s), which is shorter than the 60 s CPM window, so consecutive windows overlap. The app also has to say something sensible in the first minutes after a start, when no window has filled yet, and it has to report a tube or board that has stopped producing pulses.

## Decision

Use a buffer of monotonic pulse timestamps for all readings because one source of truth yields an exact CPM for the last 60 s and a true windowed average at any publish interval. CPM counts the pulses in the window `(now - 60 s, now]`; no state is published until 60 s have been counted. The average dose rate counts the pulses in the last `average_window` seconds (default 900 s) and, until that window has filled, divides by the elapsed time instead of the full window, so early averages are not biased low. Dose rate is CPM times `conversion_factor` (default 0.0057 µSv/h per CPM for an SBM-20), a setting because the factor depends on the tube. When no pulse has arrived for `no_pulse_timeout` seconds (default 300 s, 0 disables the check), the handler raises `NoPulseError`, which `unavailable_on` turns into an offline availability; the channel opts out of the freshness watchdog (`stale_after=None`) so a dead tube leaves the app running.

## Decision Drivers

- Exact counts: CPM must be the number of pulses in the last 60 s, independent of the publish interval
- An unbiased average from the first reading on
- Correct behaviour across wall-clock jumps (NTP, DST) on a Raspberry Pi without RTC
- Tube-specific conversion without code changes
- A silent tube must be visible to consumers without restarting the app

## Considered Options

### Option 1: Monotonic timestamp buffer with true windowed average (chosen)

The GPIO callback appends `time.monotonic()` to a buffer trimmed to the average window; each run counts the timestamps in the CPM window and in the average window.

- *Advantages:* CPM and average are exact pulse counts over their windows; Publish interval and windows are independent settings; Immune to wall-clock jumps; Pure functions over a list of floats are trivial to test
- *Disadvantages:* Memory grows with the count rate times the average window (about 600 floats at 40 CPM and 900 s)

### Option 2: Mean of overlapping CPM windows

Keep the last N published CPM values and average them for the long-term dose rate.

- *Advantages:* Small, constant memory
- *Disadvantages:* Overlapping windows count the same pulses several times, so the mean is not a count over the window; The weighting changes whenever the publish interval changes

### Option 3: Wall-clock timestamps

Store `time.time()` per pulse and compare against the current wall clock.

- *Advantages:* Timestamps are human-readable in logs
- *Disadvantages:* An NTP step or a boot without RTC shifts every window, producing bursts or gaps in CPM

### Option 4: Per-pulse stream events

Publish each pulse as an MQTT event and let consumers compute rates.

- *Advantages:* Consumers get the raw data
- *Disadvantages:* Every consumer reimplements the windowing; Up to one MQTT message per pulse instead of one per interval; No Home Assistant sensor without consumer-side logic

## Decision Matrix

| Criterion | Monotonic timestamp buffer with true windowed average | Mean of overlapping CPM windows | Wall-clock timestamps | Per-pulse stream events |
| --- | --- | --- | --- | --- |
| Count accuracy | 5 | 2 | 3 | 4 |
| Robustness to clock changes | 5 | 5 | 1 | 3 |
| Consumer simplicity | 5 | 5 | 5 | 1 |
| Resource use | 4 | 5 | 4 | 2 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Readings are exact counts for their windows, whatever the publish interval
- The first state appears after 60 s with an unbiased average
- Operators set the conversion factor for their tube in `.env`
- A silent tube turns the channel offline and back online when pulses return, without a restart

### Negative

- Nothing is published for the first 60 s after a start or an adapter restart
- Pulse history is lost on restart, so the average refills from zero
- With freshness disabled, a hung handler is detected only by the loop-stall watchdog or a task crash

_2026-10-20_
