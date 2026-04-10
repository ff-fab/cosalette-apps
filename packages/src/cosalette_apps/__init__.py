"""cosalette_apps

A monorepo collection for various cosalette based smart home apps.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    # Prefer the generated version file (setuptools_scm at build time)
    from ._version import __version__ as _v
except ImportError:
    try:
        # Fallback to installed package metadata
        _v = version("cosalette_apps")
    except PackageNotFoundError:
        # Last resort fallback for editable installs without metadata
        _v = "0.0.0+unknown"

__version__: str = _v
__all__ = ["__version__"]
