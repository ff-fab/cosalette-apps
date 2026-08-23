"""Unit tests for ports.py — WizBulbPort Protocol.

Test Techniques Used:
- Specification-based: Verify protocol is runtime_checkable
- Structural Subtyping: Conforming/non-conforming class checks via isinstance
- Introspection: Verify method signatures via hasattr
"""

from __future__ import annotations

import pytest

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.ports import WizBulbPort

# ---------------------------------------------------------------------------
# Runtime checkable
# ---------------------------------------------------------------------------


class TestRuntimeCheckable:
    """WizBulbPort must be decorated with @runtime_checkable."""

    def test_ports_protocol_is_runtime_checkable(self) -> None:
        """isinstance() checks must work with WizBulbPort.

        Technique: Specification-based — PEP 544 runtime_checkable decorator.
        """
        assert getattr(WizBulbPort, "_is_runtime_protocol", False) is True


# ---------------------------------------------------------------------------
# Structural subtyping (isinstance checks)
# ---------------------------------------------------------------------------


class _NonConformingAdapter:
    """Adapter missing required methods."""

    async def get_state(self, ip: str) -> None:
        return None

    # Missing get_capabilities, set_state, health_check, __aenter__/__aexit__


class TestStructuralSubtyping:
    """isinstance() checks honour structural subtyping."""

    def test_ports_fake_adapter_satisfies_protocol(self) -> None:
        """FakeWizBulbAdapter implements every WizBulbPort method.

        Technique: Structural Subtyping — duck-typing with type safety.
        """
        fake = FakeWizBulbAdapter()
        assert isinstance(fake, WizBulbPort)

    def test_ports_non_conforming_class_is_not_instance(self) -> None:
        """A class missing methods does NOT satisfy the protocol.

        Technique: Error Guessing — incomplete implementation.
        """
        adapter = _NonConformingAdapter()
        assert not isinstance(adapter, WizBulbPort)


# ---------------------------------------------------------------------------
# Method signatures
# ---------------------------------------------------------------------------


class TestMethodSignatures:
    """WizBulbPort exposes the expected method signatures."""

    @pytest.mark.parametrize(
        "method_name",
        [
            "get_capabilities",
            "get_state",
            "set_state",
            "health_check",
            "__aenter__",
            "__aexit__",
        ],
    )
    def test_ports_protocol_has_method(self, method_name: str) -> None:
        """Protocol must declare the expected methods.

        Technique: Introspection — verify protocol surface area.
        """
        assert hasattr(WizBulbPort, method_name)
        assert callable(getattr(WizBulbPort, method_name))
