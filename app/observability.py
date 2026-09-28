"""Logging estructurado mínimo: una línea JSON por evento (fácil de filtrar con grep)."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("lexlaboral.events")


def log_event(event: str, **fields) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str, ensure_ascii=False))
