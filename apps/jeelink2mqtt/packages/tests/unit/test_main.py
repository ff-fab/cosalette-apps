"""Unit tests for main.py — command handler invariant guards.

Test Techniques Used:
- Error Guessing: inject the (None, None) impossible return value from
  _parse_or_error to verify the defensive RuntimeError is raised for both
  mapping_assign and mapping_reset command handlers.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from jeelink2mqtt.main import _PARSE_OR_ERROR_IMPOSSIBLE


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_store() -> MagicMock:
    return MagicMock()


def _make_state() -> MagicMock:
    return MagicMock()


# ── _parse_or_error invariant guard ──────────────────────────────────────────


@pytest.mark.unit
class TestParseOrErrorGuard:
    """Error Guessing: (None, None) path raises RuntimeError with known message."""

    @pytest.mark.asyncio
    async def test_mapping_assign_raises_on_impossible_none(self) -> None:
        """mapping_assign raises RuntimeError when _parse_or_error returns (None, None).

        Technique: Error Guessing — monkey-patch _parse_or_error to trigger the
        invariant that should be unreachable in normal operation.
        """
        with patch("jeelink2mqtt.main._parse_or_error", return_value=(None, None)):
            from jeelink2mqtt.main import mapping_assign

            with pytest.raises(
                RuntimeError, match=re.escape(_PARSE_OR_ERROR_IMPOSSIBLE)
            ):
                await mapping_assign(
                    payload="{}",
                    store=_make_store(),
                    state=_make_state(),
                )

    @pytest.mark.asyncio
    async def test_mapping_reset_raises_on_impossible_none(self) -> None:
        """mapping_reset raises RuntimeError when _parse_or_error returns (None, None).

        Technique: Error Guessing — same invariant guard as mapping_assign.
        """
        with patch("jeelink2mqtt.main._parse_or_error", return_value=(None, None)):
            from jeelink2mqtt.main import mapping_reset

            with pytest.raises(
                RuntimeError, match=re.escape(_PARSE_OR_ERROR_IMPOSSIBLE)
            ):
                await mapping_reset(
                    payload="{}",
                    store=_make_store(),
                    state=_make_state(),
                )

    def test_impossible_none_message_matches_constant(self) -> None:
        """The guard message constant is non-empty and references the function name.

        Technique: Specification-based — constant value check so future renames
        stay intentional.
        """
        assert "_parse_or_error" in _PARSE_OR_ERROR_IMPOSSIBLE
        assert "(None, None)" in _PARSE_OR_ERROR_IMPOSSIBLE
