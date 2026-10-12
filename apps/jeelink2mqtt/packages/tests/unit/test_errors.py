"""Unit tests for jeelink2mqtt.errors — Domain exception hierarchy.

Test Techniques Used:
- Specification-based Testing: Verifying exception hierarchy and error_type_map
- Equivalence Partitioning: Each exception type forms an equivalence class
- Error Guessing: Ensure all 5 exceptions can be raised and caught
"""

from __future__ import annotations

import cosalette
import pytest

from jeelink2mqtt.errors import (
    FrameParseError,
    MappingConflictError,
    SerialConnectionError,
    StalenessTimeoutError,
    UnknownSensorError,
    error_type_map,
)

ALL_EXCEPTIONS = [
    SerialConnectionError,
    FrameParseError,
    MappingConflictError,
    StalenessTimeoutError,
    UnknownSensorError,
]


@pytest.mark.unit
class TestExceptionHierarchy:
    """Specification-based tests for the domain exception hierarchy."""

    @pytest.mark.parametrize("exc_cls", ALL_EXCEPTIONS, ids=lambda c: c.__name__)
    def test_exception_is_subclass_of_exception(self, exc_cls: type[Exception]) -> None:
        """Every domain exception subclasses Exception.

        Technique: Specification-based — hierarchy contract.
        """
        # Assert
        assert issubclass(exc_cls, Exception)

    @pytest.mark.parametrize("exc_cls", ALL_EXCEPTIONS, ids=lambda c: c.__name__)
    def test_exception_can_be_raised_and_caught(self, exc_cls: type[Exception]) -> None:
        """Each exception type can be raised and caught with a message.

        Technique: Error Guessing — validate raise/catch cycle.
        """
        # Arrange
        msg = f"test message for {exc_cls.__name__}"

        # Act / Assert
        with pytest.raises(exc_cls, match="test message"):
            raise exc_cls(msg)


@pytest.mark.unit
class TestErrorTypeMap:
    """Specification-based tests for the error_type_map dict."""

    def test_error_type_map_contains_all_exceptions(self) -> None:
        """error_type_map has exactly the 5 domain exceptions as keys.

        Technique: Specification-based — completeness check.
        """
        # Assert
        assert set(error_type_map.keys()) == set(ALL_EXCEPTIONS)

    def test_error_type_map_values_are_strings(self) -> None:
        """Every value in error_type_map is a non-empty string.

        Technique: Specification-based — type contract.
        """
        # Assert
        for exc_cls, type_string in error_type_map.items():
            assert isinstance(type_string, str), f"{exc_cls.__name__} maps to non-str"
            assert len(type_string) > 0, f"{exc_cls.__name__} maps to empty string"

    @pytest.mark.parametrize(
        ("exc_cls", "expected"),
        [
            (SerialConnectionError, "serial_connection"),
            (FrameParseError, "frame_parse"),
            (MappingConflictError, "mapping_conflict"),
            (StalenessTimeoutError, "staleness_timeout"),
            (UnknownSensorError, "unknown_sensor"),
        ],
        ids=lambda x: x if isinstance(x, str) else x.__name__,
    )
    def test_error_type_map_specific_values(
        self, exc_cls: type[Exception], expected: str
    ) -> None:
        """Each exception maps to its expected MQTT error-topic identifier.

        Technique: Specification-based — exact mapping verification.
        """
        # Assert
        assert error_type_map[exc_cls] == expected


@pytest.mark.unit
def test_app_discloses_domain_and_framework_error_messages() -> None:
    """Mapped domain errors keep publishing their sanitised messages.

    Technique: Specification-based — since cosalette 0.12 error_type_map only
    assigns labels; disclosure is the explicit set (ADR-091).
    """
    from jeelink2mqtt.main import app

    assert app.disclose_messages_for == (
        cosalette.FRAMEWORK_DISCLOSED_ERRORS | frozenset(error_type_map)
    )


@pytest.mark.unit
def test_app_allows_verbose_error_publishing() -> None:
    """The JEELINK2MQTT_MQTT__ERROR_PUBLISH_VERBOSE opt-in is usable.

    Technique: Specification-based — since cosalette 0.12 the env var is
    ignored unless the app allows it; the setting itself stays off by default.
    """
    from jeelink2mqtt.main import app

    assert app.allow_error_publish_verbose is True
