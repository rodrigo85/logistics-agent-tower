"""
Centralised logging configuration.

Library modules must only call `logging.getLogger(__name__)`; entry points
(API, CLI, seeder, MCP server) call `configure_logging()` exactly once.
"""

import logging
import sys

from logistics_tower.config import settings

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_NOISY_LOGGERS = ("httpx", "httpcore", "uvicorn.access")


def configure_logging(level: str | None = None) -> None:
    """Configure the root logger once, honouring LOG_LEVEL from settings."""
    root = logging.getLogger()
    if getattr(root, "_logistics_tower_configured", False):
        return

    resolved = (level or settings.log_level).upper()
    # Windows consoles default to a legacy code page; make sure accented text never crashes the logger.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))

    root.setLevel(resolved)
    root.addHandler(handler)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(logging.WARNING, root.level))

    root._logistics_tower_configured = True  # type: ignore[attr-defined]
