"""Thread-safe store of pulse timestamps shared by both adapters."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from geiger2mqtt.domain.radiation import CPM_WINDOW

Clock = Callable[[], float]


class PulseBuffer:
    """Records pulse timestamps and prunes those older than the longest window.

    ``record`` may run on a foreign thread (gpiozero calls back from lgpio's
    thread), so every access to the deque holds a lock.
    """

    def __init__(self, retention: float, clock: Clock = time.monotonic) -> None:
        self._retention = max(CPM_WINDOW, retention)
        self._clock = clock
        self._pulses: deque[float] = deque()
        self._last: float | None = None
        self._lock = threading.Lock()
        self._started_at = clock()

    @property
    def started_at(self) -> float:
        return self._started_at

    def now(self) -> float:
        return self._clock()

    def reset(self) -> None:
        """Forget all pulses and restart the clock at the current time."""
        with self._lock:
            self._pulses.clear()
            self._last = None
            self._started_at = self._clock()

    def record(self) -> None:
        """Store a pulse at the current clock time."""
        self._record_at(self._clock())

    def _record_at(self, t: float) -> None:
        with self._lock:
            self._pulses.append(t)
            self._last = t
            self._prune(t)

    def snapshot(self, since: float) -> list[float]:
        with self._lock:
            self._prune(self._clock())
            return [t for t in self._pulses if t > since]

    def last_pulse(self) -> float | None:
        """Latest pulse, kept even after pruning drops it from the window."""
        with self._lock:
            return self._last

    def _prune(self, now: float) -> None:
        cutoff = now - self._retention
        while self._pulses and self._pulses[0] <= cutoff:
            self._pulses.popleft()
