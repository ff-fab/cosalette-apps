"""Dry-run pulse counter producing Poisson-distributed pulses.

Pulses arrive with exponential inter-arrival times at about 20 CPM, the
background level of an SBM-20 tube. They are generated lazily up to the
current clock time whenever the port is queried, so an injected clock drives
the fake deterministically in tests.
"""

from __future__ import annotations

import random
import time
from types import TracebackType
from typing import Self, override

from geiger2mqtt.adapters._buffer import Clock, PulseBuffer
from geiger2mqtt.settings import Geiger2MqttSettings

BACKGROUND_CPM = 20.0


class FakePulseCounter(PulseBuffer):
    """PulseCounterPort test double with a seeded Poisson pulse source."""

    def __init__(
        self,
        settings: Geiger2MqttSettings,
        clock: Clock = time.monotonic,
        seed: int | None = None,
        cpm: float = BACKGROUND_CPM,
    ) -> None:
        super().__init__(retention=settings.average_window, clock=clock)
        self._rng = random.Random(seed)  # simulation, not crypto
        self._rate = cpm / 60.0
        self._next = self.started_at + self._rng.expovariate(self._rate)

    @override
    def snapshot(self, since: float) -> list[float]:
        self._generate()
        return super().snapshot(since)

    @override
    def last_pulse(self) -> float | None:
        self._generate()
        return super().last_pulse()

    def _generate(self) -> None:
        now = self.now()
        while self._next <= now:
            self._record_at(self._next)
            self._next += self._rng.expovariate(self._rate)

    async def __aenter__(self) -> Self:
        self.reset()
        self._next = self.started_at + self._rng.expovariate(self._rate)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None
