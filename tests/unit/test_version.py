"""floorpro.__version__ works with and without package metadata (frozen builds)."""

from __future__ import annotations

from importlib import metadata

import floorpro


def test_version_from_metadata():
    assert floorpro.__version__ == metadata.version("floorpro")


def test_version_falls_back_without_metadata(monkeypatch):
    def missing(_name):
        raise metadata.PackageNotFoundError("floorpro")

    monkeypatch.setattr(metadata, "version", missing)
    assert floorpro._read_version() == "0.0.0+unknown"
