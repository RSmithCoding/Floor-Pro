"""FloorPro: shop-management desktop app for flooring retailers."""

from __future__ import annotations

from importlib import metadata

UNKNOWN_VERSION = "0.0.0+unknown"


def _read_version() -> str:
    """The installed package version, or a placeholder when metadata is missing (frozen builds)."""
    try:
        return metadata.version("floorpro")
    except metadata.PackageNotFoundError:
        return UNKNOWN_VERSION


__version__ = _read_version()
