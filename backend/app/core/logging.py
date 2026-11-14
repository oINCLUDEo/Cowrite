"""Не даём query-параметрам OAuth и WebSocket попасть в журналы Uvicorn."""

import logging

import structlog


class HideQueryString(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                value.partition("?")[0] if isinstance(value, str) else value
                for value in record.args
            )
        return True


def configure_log_redaction() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )
    for name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, HideQueryString) for item in logger.filters):
            logger.addFilter(HideQueryString())
