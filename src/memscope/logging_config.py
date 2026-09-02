"""Idempotent and conservative application logging configuration."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, ClassVar

from memscope.settings import AppSettings, LogFormat

LOGGER_NAME = "memscope"
_MANAGED_HANDLER_MARKER = "_memscope_managed_handler"


class JsonFormatter(logging.Formatter):
    """Render a deliberately small allowlist of structured fields."""

    _OPTIONAL_FIELDS: ClassVar[tuple[str, ...]] = (
        "error_code",
        "retryable",
        "http_method",
        "http_path",
        "status_code",
        "total_duration_ms",
        "storage_operation",
        "storage_result",
        "schema_version",
        "raw_store_duration_ms",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in self._OPTIONAL_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info is not None and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    """Render a compact local-development line without arbitrary extras."""

    def __init__(self) -> None:
        super().__init__("%(levelname)s %(name)s %(message)s")


def configure_logging(settings: AppSettings) -> None:
    """Configure one managed handler without disturbing unrelated loggers."""

    logger = logging.getLogger(LOGGER_NAME)
    for handler in tuple(logger.handlers):
        if getattr(handler, _MANAGED_HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()

    handler = logging.StreamHandler(sys.stderr)
    setattr(handler, _MANAGED_HANDLER_MARKER, True)
    formatter = JsonFormatter() if settings.log_format is LogFormat.JSON else ConsoleFormatter()
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.setLevel(settings.log_level)
    logger.propagate = False
