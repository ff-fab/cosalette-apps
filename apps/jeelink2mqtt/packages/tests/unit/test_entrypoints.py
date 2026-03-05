"""Unit tests for application entrypoints (main.py, __init__.py).

Test Techniques Used:
- Specification-based: main() wires create_app → cli correctly
- Error Guessing: Version fallback paths when _version or metadata unavailable
- Branch/Condition Coverage: try/except import chains in __init__.py
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

# ======================================================================
# main.py entrypoint
# ======================================================================


@pytest.mark.unit
class TestMainEntrypoint:
    """Specification-based tests for the CLI entrypoint."""

    def test_main_calls_create_app_and_cli(self) -> None:
        """main() creates the app via composition root, then calls cli().

        Technique: Specification-based — verifying wiring contract.
        """
        # Arrange
        mock_app = MagicMock()

        with patch(
            "jeelink2mqtt.main.create_app",
            return_value=mock_app,
        ) as mock_create:
            from jeelink2mqtt.main import main

            # Act
            main()

        # Assert
        mock_create.assert_called_once()
        mock_app.cli.assert_called_once()

    def test_main_module_guard(self) -> None:
        """The ``if __name__ == '__main__'`` guard exists for direct execution.

        Technique: Specification-based — structural check.
        """
        import jeelink2mqtt.main as main_mod

        # Assert — the module has a main function
        assert callable(main_mod.main)


# ======================================================================
# __init__.py version resolution
# ======================================================================


@pytest.mark.unit
class TestVersionResolution:
    """Branch/Condition Coverage for the __init__.py version try/except chain.

    The version resolution has three branches:
    1. ``_version.__version__`` exists (normal build) — the happy path
    2. ``_version`` import fails → fall back to ``importlib.metadata.version()``
    3. Both fail → ``"0.0.0+unknown"``

    Branch 1 is exercised by simply importing jeelink2mqtt (the default).
    Branches 2 and 3 require import-time patching, which is tricky.
    We use ``importlib.reload()`` to re-execute the module-level code
    with different ``sys.modules`` state.
    """

    def test_version_is_available(self) -> None:
        """The package exposes a __version__ string.

        Technique: Specification-based — public API contract.
        """
        # Act
        import jeelink2mqtt

        # Assert
        assert isinstance(jeelink2mqtt.__version__, str)
        assert len(jeelink2mqtt.__version__) > 0

    def test_version_fallback_to_metadata(self) -> None:
        """When _version import fails, falls back to package metadata.

        Technique: Branch/Condition Coverage — second branch of the
        try/except chain.
        """
        import jeelink2mqtt

        # Arrange — make _version import raise ImportError when
        # the module is reloaded
        original_version_mod = sys.modules.get("jeelink2mqtt._version")

        # Remove the _version module so the import inside __init__.py fails
        sys.modules["jeelink2mqtt._version"] = None  # type: ignore[assignment]

        try:
            # Act — reimport to trigger the fallback path
            with patch(
                "importlib.metadata.version",
                return_value="1.2.3.test",
            ):
                importlib.reload(jeelink2mqtt)

            # Assert — __version__ comes from patched metadata.version
            assert jeelink2mqtt.__version__ == "1.2.3.test"
        finally:
            # Restore original state
            if original_version_mod is not None:
                sys.modules["jeelink2mqtt._version"] = original_version_mod
            else:
                sys.modules.pop("jeelink2mqtt._version", None)
            # Reload to restore normal state
            importlib.reload(jeelink2mqtt)

    def test_version_fallback_unknown(self) -> None:
        """When both _version and metadata fail, returns '0.0.0+unknown'.

        Technique: Branch/Condition Coverage — third (last-resort) branch.
        """
        from importlib.metadata import PackageNotFoundError

        import jeelink2mqtt

        # Arrange — sabotage both version sources
        original_version_mod = sys.modules.get("jeelink2mqtt._version")
        sys.modules["jeelink2mqtt._version"] = None  # type: ignore[assignment]

        try:
            # Patch importlib.metadata.version (where the reload re-imports from)
            with patch(
                "importlib.metadata.version",
                side_effect=PackageNotFoundError("jeelink2mqtt"),
            ):
                importlib.reload(jeelink2mqtt)

            # Assert
            assert jeelink2mqtt.__version__ == "0.0.0+unknown"
        finally:
            # Restore original state
            if original_version_mod is not None:
                sys.modules["jeelink2mqtt._version"] = original_version_mod
            else:
                sys.modules.pop("jeelink2mqtt._version", None)
            importlib.reload(jeelink2mqtt)
