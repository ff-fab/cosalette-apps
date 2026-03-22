"""Unit tests for port protocol definitions.

Test Techniques Used:
- Structural Subtyping Verification: FakeGpio satisfies GpioSwitchPort protocol
"""

from velux2mqtt.adapters.fake import FakeGpio
from velux2mqtt.ports import GpioSwitchPort


class TestGpioSwitchPort:
    """Verify that protocol is well-defined and FakeGpio satisfies it."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """GpioSwitchPort is decorated with @runtime_checkable."""
        assert hasattr(GpioSwitchPort, "__protocol_attrs__")

    def test_fake_gpio_satisfies_protocol(self) -> None:
        """FakeGpio implements all methods required by GpioSwitchPort."""
        fake = FakeGpio()
        assert isinstance(fake, GpioSwitchPort)
