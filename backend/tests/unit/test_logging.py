import logging

import pytest

from app.core.logging import HideQueryString, configure_log_redaction


@pytest.mark.parametrize(
    "name,message,args",
    [
        (
            "uvicorn.access",
            '%s - "%s %s HTTP/%s" %d',
            ("client", "GET", "/auth/github/callback?code=secret&state=hidden", "1.1", 302),
        ),
        (
            "uvicorn.error",
            '%s - "WebSocket %s" [accepted]',
            ("client", "/ws/documents/id?token=secret"),
        ),
    ],
)
def test_uvicorn_query_parameters_are_redacted(name, message, args):
    record = logging.LogRecord(name, logging.INFO, "", 0, message, args, None)
    assert HideQueryString().filter(record)
    assert "secret" not in record.getMessage()
    assert "?" not in record.getMessage()
    assert (
        "/auth/github/callback" in record.getMessage() or "/ws/documents/id" in record.getMessage()
    )


def test_redaction_configuration_is_idempotent():
    configure_log_redaction()
    configure_log_redaction()
    for name in ("uvicorn.access", "uvicorn.error"):
        assert (
            sum(isinstance(item, HideQueryString) for item in logging.getLogger(name).filters) == 1
        )


def test_redaction_handles_messages_without_arguments():
    record = logging.LogRecord("uvicorn.error", logging.INFO, "", 0, "started", (), None)
    assert HideQueryString().filter(record)
    assert record.getMessage() == "started"
