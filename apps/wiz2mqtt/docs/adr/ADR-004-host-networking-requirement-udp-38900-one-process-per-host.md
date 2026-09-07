---
status: Accepted
date: 2026-09-06
impact: low
tags: [packaging, architecture, lifecycle, mqtt]
---

# ADR-004: Host Networking Requirement (UDP 38900, One Process Per Host)

## Status

Accepted **Date:** 2026-09-06

## Context

wiz2mqtt's low-latency state publication depends on WiZ bulb *push* notifications: after `bulb.start_push(callback)`, the bulb sends an unsolicited UDP datagram to the subscriber whenever its state changes. pywizlight's push manager binds a single fixed local port for this — `LISTEN_PORT = 38900` (`pywizlight.push_manager`) — and the bulb sends its push to the source address of the registration datagram.

Two consequences fall out of that:

1. **The push datagram must be able to reach the process.** Inside a bridge-networked container the bulb sees the container's NAT address; the return datagram lands on the host and is dropped. pywizlight fails this silently — `start_push` reports success once the socket binds, and the app quietly degrades to polling. wiz2mqtt's adapter comments already note this (`adapters/wizlight.py`).
2. **Port 38900 is a singleton.** Only one process per network namespace can bind it. A second wiz2mqtt process (or anything else using pywizlight's push manager) on the same host gets `Port 38900 is in use` and no push.

The heartbeat tick (60 s) and the push-staleness threshold (60 s) are the deliberate fallback: without push, wiz2mqtt still works, just at poll latency. But the whole point of the rewrite (cap-10u.21, ADR-005) was to publish on the push, so a deployment that cannot receive one has lost the feature it was built for.

## Decision

Require `network_mode: host` (or an equivalent host-network deployment) for wiz2mqtt, and document that exactly one wiz2mqtt process may run per host because pywizlight's push listener binds the fixed singleton UDP port 38900. Ship `compose.yml` with host networking, and treat 'push silently degraded to polling' as a deployment misconfiguration to be caught by the cap-10u.19 real-bulb verification, not a supported mode.

## Decision Drivers

- WiZ push datagrams are addressed to the source of the registration packet, so NAT between the bulb and the process breaks push with no error
- pywizlight binds one fixed port (38900) for all push traffic — it is not configurable and not per-bulb
- pywizlight reports push-subscription success as soon as the socket binds, so a broken return path is invisible without a real bulb test
- Event-driven publication is the reason the app exists (ADR-005); a deployment that cannot receive a push has regressed to the pre-rewrite behaviour
- A single documented constraint (host net, one process) is cheaper to operate than a configurable port-forwarding scheme that still cannot fix the NAT source-address problem

## Considered Options

### Option 1: Require host networking, one process per host (chosen)

wiz2mqtt runs in the host network namespace. `compose.yml` sets `network_mode: host`. Documentation states the UDP 38900 singleton constraint and that a second instance on the same host will not get push.

- *Advantages:* Push datagrams reach the process with no NAT translation, so the feature works as designed; Matches how pywizlight itself expects to be deployed; No per-bulb port mapping to maintain as the inventory grows; Simple, single-sentence operational rule
- *Disadvantages:* The container shares the host's network stack — no port isolation, and the MQTT client and any future HTTP surface bind host ports directly; Only one wiz2mqtt per host; multi-tenant or multi-subnet setups need one host (or namespace) each; `network_mode: host` behaves differently on Docker Desktop / macOS, so local dev on those platforms cannot fully exercise push

### Option 2: Bridge networking with explicit UDP port publishing

Keep the container on a bridge network and publish UDP 38900 (and the discovery/response ports) back to the container with `-p 38900:38900/udp`.

- *Advantages:* Preserves container network isolation; Multiple containers could in principle coexist if each mapped a different host port
- *Disadvantages:* Does not actually fix push: the bulb still addresses the datagram to the container's NAT source address, which the port publish does not rewrite; pywizlight's port is fixed at 38900, so a different host port does not reach the listener anyway; Gives the appearance of a working setup while silently polling — the worst failure mode; More moving parts (port maps, firewall rules) for a configuration that cannot work

## Consequences

### Positive

- The shipped `compose.yml` works out of the box for the push path on Linux hosts
- The 'one wiz2mqtt per host' rule is stated up front rather than discovered via a confusing `Port 38900 is in use` log line
- No per-bulb or per-instance port-mapping configuration to keep in sync with the inventory
- cap-10u.19 has a concrete misconfiguration to test for: push present vs silently degraded to polling

### Negative

- wiz2mqtt cannot share a host network namespace with a second instance or another pywizlight-push consumer
- Host networking weakens container isolation and is not fully faithful on Docker Desktop / macOS, limiting local push testing there
- Operators on non-host orchestration (some Kubernetes CNIs, restrictive PaaS) must arrange host-network access explicitly or accept poll-only latency

_2026-09-06_
