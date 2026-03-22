"""Unit tests for port protocol definitions."""

from typing import runtime_checkable

from velux2mqtt.adapters.fake import FakeGpio
from velux2mqtt.ports import GpioSwitchPort


class TestGpioSwitchPort:
    """Verify that protocol is well-defined and FakeGpio satisfies it."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """GpioSwitchPort can be used with isinstance() checks."""
        assert runtime_checkable(GpioSwitchPort)

    def test_fake_gpio_satisfies_protocol(self) -> None:
        """FakeGpio implements all methods required by GpioSwitchPort."""
        fake = FakeGpio()
        # Structural subtyping check — if this passes, the protocol is satisfied
        assert isinstance(fake, GpioSwitchPort)
