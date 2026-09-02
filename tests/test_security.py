import logging

from app.web.security import REDACTED, RedactingFilter, redact


def test_redact_mapping_and_string_forms():
    value = {
        "username": "student-id",
        "nested": {"password": "secret"},
        "message": "Authorization: Bearer abc123 Cookie: session=xyz",
    }
    result = redact(value)
    assert result["username"] == REDACTED
    assert result["nested"]["password"] == REDACTED
    assert "abc123" not in result["message"]
    assert "session=xyz" not in result["message"]


def test_logging_filter_hides_json_and_form_values():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='{"username":"u123","password":"p456"} token=abcdef',
        args=(),
        exc_info=None,
    )
    assert RedactingFilter().filter(record)
    rendered = record.getMessage()
    assert "u123" not in rendered
    assert "p456" not in rendered
    assert "abcdef" not in rendered
    assert REDACTED in rendered


def test_logging_filter_redacts_format_arguments():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="password=%s",
        args=("format-secret",),
        exc_info=None,
    )
    assert RedactingFilter().filter(record)
    assert "format-secret" not in record.getMessage()
    assert REDACTED in record.getMessage()


def test_global_installer_redacts_propagated_child_logger(caplog):
    from app.web.security import install_log_redaction

    install_log_redaction()
    logger = logging.getLogger("utaipei.child")
    with caplog.at_level(logging.INFO):
        logger.info("username=%s password=%s", "student-123", "secret-456")
    rendered = " ".join(caplog.messages)
    assert "student-123" not in rendered
    assert "secret-456" not in rendered
    assert REDACTED in rendered
