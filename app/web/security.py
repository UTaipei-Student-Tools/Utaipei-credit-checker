from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

SENSITIVE_KEYS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "cookie",
    "authorization",
    "username",
    "user_name",
    "uid",
)
REDACTED = "[REDACTED]"
_KEY_PATTERN = "|".join(re.escape(key) for key in SENSITIVE_KEYS)


def _redact_string(value: str) -> str:
    redacted = value
    # Redact whole HTTP header values before generic key/value matching.
    redacted = re.sub(
        r"(?i)(authorization\s*:\s*)(?:bearer|basic)?\s*[^\r\n,;]+",
        rf"\1{REDACTED}",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(cookie\s*:\s*)[^\r\n]+",
        rf"\1{REDACTED}",
        redacted,
    )
    # JSON, form and key=value forms, including optionally quoted keys and values.
    redacted = re.sub(
        rf"(?i)([\"']?(?:{_KEY_PATTERN})[\"']?\s*[:=]\s*)([\"']?)([^\"'&\s,;}}]+)([\"']?)",
        rf"\1\2{REDACTED}\4",
        redacted,
    )
    return redacted


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: REDACTED if any(s in str(key).casefold() for s in SENSITIVE_KEYS) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Render first so format-string arguments cannot bypass key-aware redaction.
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


_REDACTION_INSTALLED = False


def install_log_redaction() -> None:
    """Redact sensitive fields before any logger or handler can render them."""

    global _REDACTION_INSTALLED
    if _REDACTION_INSTALLED:
        return

    previous_factory = logging.getLogRecordFactory()

    def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        # Render %-style arguments first; otherwise a secret can live only in args.
        try:
            rendered = record.getMessage()
        except Exception:
            rendered = str(record.msg)
        record.msg = redact(rendered)
        record.args = ()
        return record

    logging.setLogRecordFactory(redacting_factory)
    _REDACTION_INSTALLED = True
