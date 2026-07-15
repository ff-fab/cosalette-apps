"""Unit tests for gas2mqtt main — telemetry registration and retry configuration.

Test Techniques Used:
- Specification-based: retry and retry_on metadata matches declared configuration
  for all three telemetry handlers (gas_counter, temperature, magnetometer)
- Decision Table: exact retry_on tuple check prevents unintended broadening
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
@pytest.mark.parametrize("handler_name", ["gas_counter", "temperature", "magnetometer"])
class TestHandlerRetryConfig:
    """Verify retry metadata on all three telemetry registrations."""

    def test_retry_count_is_three(self, handler_name: str) -> None:
        """Handler registration has retry=3.

        Technique: Specification-based — verify declared retry configuration.
        """
        from gas2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == handler_name)
        assert reg.retry == 3

    def test_retry_on_is_exactly_oserror_tuple(self, handler_name: str) -> None:
        """Handler retry_on is exactly (OSError,).

        Technique: Specification-based + Decision Table — OSError covers smbus2
        IOError/OSError (IOError is an alias of OSError since PEP 3151 / Python
        3.3). Exact tuple check prevents unintended broadening of retry scope.
        """
        from gas2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == handler_name)
        assert reg.retry_on == (OSError,)
