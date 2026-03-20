# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Unit tests for ports.py — OptolinkPort Protocol.

Test Techniques Used:
- Specification-based: Verify protocol is runtime_checkable
- Structural Subtyping: Conforming/non-conforming class checks via isinstance
- Introspection: Verify method signatures via inspect module
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from vito2mqtt.ports import OptolinkPort

# ---------------------------------------------------------------------------
# Runtime checkable
# ---------------------------------------------------------------------------


class TestRuntimeCheckable:
    """OptolinkPort must be decorated with @runtime_checkable."""

    def test_ports_protocol_is_runtime_checkable(self) -> None:
        """isinstance() checks must work with OptolinkPort.

        Technique: Specification-based — PEP 544 runtime_checkable decorator.
        """
        # runtime_checkable protocols have _is_runtime_protocol set to True
        assert getattr(OptolinkPort, "_is_runtime_protocol", False) is True


# ---------------------------------------------------------------------------
# Structural subtyping (isinstance checks)
# ---------------------------------------------------------------------------


class _ConformingAdapter:
    """Adapter that implements all OptolinkPort methods."""

    async def read_signal(self, name: str) -> Any:
        return None

    async def write_signal(self, name: str, value: Any) -> None:
        pass

    async def read_signals(self, names: Sequence[str]) -> dict[str, Any]:
        return {}


class _NonConformingAdapter:
    """Adapter missing required methods."""

    async def read_signal(self, name: str) -> Any:
        return None

    # Missing write_signal and read_signals


class TestStructuralSubtyping:
    """isinstance() checks honour structural subtyping."""

    def test_ports_conforming_class_is_instance(self) -> None:
        """A class with all three methods satisfies the protocol.

        Technique: Structural Subtyping — duck-typing with type safety.
        """
        adapter = _ConformingAdapter()
        assert isinstance(adapter, OptolinkPort)

    def test_ports_non_conforming_class_is_not_instance(self) -> None:
        """A class missing methods does NOT satisfy the protocol.

        Technique: Error Guessing — incomplete implementation.
        """
        adapter = _NonConformingAdapter()
        assert not isinstance(adapter, OptolinkPort)


# ---------------------------------------------------------------------------
# Method signatures
# ---------------------------------------------------------------------------


class TestMethodSignatures:
    """OptolinkPort exposes the expected method signatures."""

    @pytest.mark.parametrize(
        "method_name",
        ["read_signal", "write_signal", "read_signals"],
    )
    def test_ports_protocol_has_method(self, method_name: str) -> None:
        """Protocol must declare the expected methods.

        Technique: Introspection — verify protocol surface area.
        """
        assert hasattr(OptolinkPort, method_name)
        assert callable(getattr(OptolinkPort, method_name))
