"""Structured logging utilities for the AOP MCP."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping


class StructuredLogger:
    def __init__(self, name: str = "aop-mcp") -> None:
        self._logger = logging.getLogger(name)

    def info(self, message: str, **context: Any) -> None:
        self._logger.info(self._format(message, context))

    def warning(self, message: str, **context: Any) -> None:
        self._logger.warning(self._format(message, context))

    def error(self, message: str, **context: Any) -> None:
        self._logger.error(self._format(message, context))

    def _format(self, message: str, context: Mapping[str, Any]) -> str:
        enriched = {"message": message, **{k: self._normalize(v) for k, v in context.items()}}
        return json.dumps(enriched)

    @staticmethod
    def _normalize(value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, (list, tuple)):
            return [StructuredLogger._normalize(v) for v in value]
        if isinstance(value, dict):
            return {k: StructuredLogger._normalize(v) for k, v in value.items()}
        return value

