from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any


SENSITIVE_KEYS = ("password", "pwd", "token", "cookie", "authorization", "username")
REDACTED = "[REDACTED]"


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: REDACTED if any(s in str(key).lower() for s in SENSITIVE_KEYS) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        redacted = value
        for key in SENSITIVE_KEYS:
            redacted = re.sub(
                rf"({key}\s*[=:]\s*)([^&\s,;]+)",
                rf"\1{REDACTED}",
                redacted,
                flags=re.IGNORECASE,
            )
        return redacted
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True

