"""Synthetic fixtures owned by core.logging."""

from __future__ import annotations

import logging



def build_logger() -> logging.LoggerAdapter:
    """Builds a quiet logger adapter for tests."""

    logger = logging.getLogger("pnc_automation.tests")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logging.LoggerAdapter(logger, extra={})
