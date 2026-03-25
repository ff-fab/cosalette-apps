"""Placeholder test to validate CI pipeline.

This test imports the application package so coverage is non-zero.
Replace it with real tests as the project evolves.
"""

import importlib


def test_package_imports() -> None:
    """Ensure the scaffolded package can be imported."""
    mod = importlib.import_module("airthings2mqtt")
    assert mod is not None
