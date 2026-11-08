"""Application logging to a rotating file in the data directory.

Log messages MUST NOT include customer personal data (names, phone numbers, emails,
addresses, notes). Refer to customers by their reference (e.g. ``C-00042``) instead.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from floorpro.paths import logs_dir

_HANDLER_NAME = "floorpro-file"


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(getattr(h, "name", None) == _HANDLER_NAME for h in root.handlers):
        return
    handler = RotatingFileHandler(
        logs_dir() / "floorpro.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    handler.name = _HANDLER_NAME
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)
