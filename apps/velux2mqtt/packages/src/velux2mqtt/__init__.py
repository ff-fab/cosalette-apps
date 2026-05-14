"""velux2mqtt — Control Velux covers via KLF 050 remotes and M74HC4066 GPIO switches."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("velux2mqtt")
except PackageNotFoundError:  # pragma: no cover
    # Fallback for editable installs without metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
