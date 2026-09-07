"""Session-local identity scope for portal-derived transcript data.

The scraper owns the authenticated request, while this module owns the small
state boundary between that request and the analysis input. Only an opaque,
session-local account fingerprint is retained; credentials and raw portal
responses never enter application state.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Mapping, MutableMapping
from typing import Any

SCOPE_SALT_KEY = "_portal_scope_salt"
TRANSCRIPT_SCOPE_KEY = "transcript_scope"
SCOPE_WARNING_CODES_KEY = "_portal_scope_warning_codes"

SCOPE_STATUS_VERIFIED = "VERIFIED"
SCOPE_STATUS_PENDING = "PENDING"
SCOPE_STATUS_UNVERIFIED = "UNVERIFIED"
SCOPE_STATUS_MISMATCH = "MISMATCH"
SCOPE_STATUS_LEGACY = "LEGACY"
SCOPE_STATUSES = frozenset(
    {
        SCOPE_STATUS_VERIFIED,
        SCOPE_STATUS_PENDING,
        SCOPE_STATUS_UNVERIFIED,
        SCOPE_STATUS_MISMATCH,
        SCOPE_STATUS_LEGACY,
    }
)

SOURCE_PORTAL = "portal"
SOURCE_UPLOAD = "upload"
SOURCE_MANUAL = "manual"
SCOPE_SOURCES = frozenset({SOURCE_PORTAL, SOURCE_UPLOAD, SOURCE_MANUAL})

# Keep the scope-warning channel closed until a warning is backed by verified
# evidence and has a defined public meaning.
SCOPE_WARNING_CODES = frozenset()

_SALT_BYTES = 32
_FINGERPRINT_HEX_LENGTH = hashlib.sha256().digest_size * 2


def _text(value: object) -> str:
    return str(value or "").strip()


def _safe_source(value: object) -> str:
    source = _text(value).lower()
    return source if source in SCOPE_SOURCES else SOURCE_MANUAL


def _safe_status(value: object, *, verified: bool = False) -> str:
    status = _text(value)
    if status in SCOPE_STATUSES:
        return status
    return SCOPE_STATUS_VERIFIED if verified else SCOPE_STATUS_UNVERIFIED


def _valid_salt(value: object) -> bool:
    return isinstance(value, bytes) and len(value) >= 16


def ensure_session_salt(state: MutableMapping[str, Any]) -> bytes:
    """Return a per-session random salt, creating it when necessary."""

    current = state.get(SCOPE_SALT_KEY)
    if not _valid_salt(current):
        current = secrets.token_bytes(_SALT_BYTES)
        state[SCOPE_SALT_KEY] = current
    return current


def account_fingerprint(state: MutableMapping[str, Any], account: object) -> str | None:
    """Return an opaque HMAC binding for a trimmed account identifier."""

    account_text = _text(account)
    if not account_text:
        return None
    return hmac.new(
        ensure_session_salt(state),
        account_text.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_scope(
    state: MutableMapping[str, Any],
    account: object,
    year: object | None = None,
    semester: object | None = None,
    *,
    source: str = SOURCE_PORTAL,
    verified: bool = True,
    pending: bool = False,
) -> dict[str, Any]:
    """Build a normalized transcript identity scope.

    ``year`` and ``semester`` remain optional compatibility metadata for old
    callers. They no longer select or identify any fetched course list.
    """

    if pending:
        status = SCOPE_STATUS_PENDING
    else:
        status = SCOPE_STATUS_VERIFIED if verified else SCOPE_STATUS_UNVERIFIED
    return {
        "account_fingerprint": account_fingerprint(state, account),
        "year": _text(year),
        "semester": _text(semester),
        "verified": bool(verified),
        "status": status,
        "source": _safe_source(source),
    }


def build_transcript_scope(state: MutableMapping[str, Any], account: object) -> dict[str, Any]:
    """Build the account-only scope used by live transcript retrieval."""

    return build_scope(state, account, source=SOURCE_PORTAL, verified=True)


def build_upload_scope() -> dict[str, Any]:
    """Build an explicitly unbound scope for a user-uploaded transcript."""

    return {
        "account_fingerprint": None,
        "year": "",
        "semester": "",
        "verified": False,
        "status": SCOPE_STATUS_UNVERIFIED,
        "source": SOURCE_UPLOAD,
    }


def _is_verified_portal_scope(scope: object) -> bool:
    if not isinstance(scope, Mapping):
        return False
    fingerprint = _text(scope.get("account_fingerprint"))
    if len(fingerprint) != _FINGERPRINT_HEX_LENGTH:
        return False
    try:
        int(fingerprint, 16)
    except (TypeError, ValueError):
        return False
    return (
        bool(scope.get("verified"))
        and _text(scope.get("status")) == SCOPE_STATUS_VERIFIED
        and _safe_source(scope.get("source")) == SOURCE_PORTAL
    )


def public_scope_metadata(scope: object) -> dict[str, Any]:
    """Return a fixed, non-sensitive scope summary with no fingerprint."""

    if not isinstance(scope, Mapping):
        return {
            "status": SCOPE_STATUS_UNVERIFIED,
            "year": "",
            "semester": "",
            "source": SOURCE_MANUAL,
            "verified": False,
        }
    status = _safe_status(scope.get("status"), verified=bool(scope.get("verified")))
    verified = bool(scope.get("verified")) and status == SCOPE_STATUS_VERIFIED
    return {
        "status": status,
        "year": _text(scope.get("year")),
        "semester": _text(scope.get("semester")),
        "source": _safe_source(scope.get("source")),
        "verified": verified,
    }


def add_warning(state: MutableMapping[str, Any], code: object) -> tuple[str, ...]:
    """Ignore obsolete warning codes and return the empty safe tuple."""

    del code
    state[SCOPE_WARNING_CODES_KEY] = ()
    return ()


def get_warning_codes(state: Mapping[str, Any]) -> tuple[str, ...]:
    """Return only fixed warning codes suitable for a DecisionSnapshot."""

    del state
    return ()


def initialize_scope_state(state: MutableMapping[str, Any], *, salt: bytes | None = None) -> None:
    """Initialize the session-local transcript scope state."""

    if salt is not None and _valid_salt(salt):
        state[SCOPE_SALT_KEY] = salt
    ensure_session_salt(state)
    state.setdefault(TRANSCRIPT_SCOPE_KEY, None)
    state[SCOPE_WARNING_CODES_KEY] = ()

    scope = state.get(TRANSCRIPT_SCOPE_KEY)
    if scope is None:
        return
    if isinstance(scope, Mapping) and _safe_source(scope.get("source")) == SOURCE_UPLOAD:
        state[TRANSCRIPT_SCOPE_KEY] = build_upload_scope()
        return
    if not _is_verified_portal_scope(scope):
        state[TRANSCRIPT_SCOPE_KEY] = None
        return
    state[TRANSCRIPT_SCOPE_KEY] = _normalized_transcript_scope(scope)


def _normalized_transcript_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "account_fingerprint": _text(scope.get("account_fingerprint")),
        "year": _text(scope.get("year")),
        "semester": _text(scope.get("semester")),
        "verified": True,
        "status": SCOPE_STATUS_VERIFIED,
        "source": SOURCE_PORTAL,
    }


def set_transcript_scope(state: MutableMapping[str, Any], scope: Mapping[str, Any] | None) -> None:
    """Set a normalized transcript scope without copying arbitrary fields."""

    if scope is None:
        state[TRANSCRIPT_SCOPE_KEY] = None
        return
    if _safe_source(scope.get("source")) == SOURCE_UPLOAD:
        state[TRANSCRIPT_SCOPE_KEY] = build_upload_scope()
        return
    state[TRANSCRIPT_SCOPE_KEY] = (
        _normalized_transcript_scope(scope) if _is_verified_portal_scope(scope) else None
    )


def clear_scope_state(state: MutableMapping[str, Any]) -> None:
    """Clear private scope material while retaining an empty scope boundary."""

    for key in (
        SCOPE_SALT_KEY,
        TRANSCRIPT_SCOPE_KEY,
        SCOPE_WARNING_CODES_KEY,
    ):
        state.pop(key, None)
    state[TRANSCRIPT_SCOPE_KEY] = None
    state[SCOPE_WARNING_CODES_KEY] = ()


__all__ = [
    "SCOPE_SALT_KEY",
    "TRANSCRIPT_SCOPE_KEY",
    "SCOPE_WARNING_CODES_KEY",
    "SOURCE_PORTAL",
    "SOURCE_UPLOAD",
    "SOURCE_MANUAL",
    "SCOPE_STATUS_VERIFIED",
    "SCOPE_STATUS_PENDING",
    "SCOPE_STATUS_UNVERIFIED",
    "SCOPE_STATUS_MISMATCH",
    "SCOPE_STATUS_LEGACY",
    "ensure_session_salt",
    "account_fingerprint",
    "build_scope",
    "build_transcript_scope",
    "build_upload_scope",
    "public_scope_metadata",
    "add_warning",
    "get_warning_codes",
    "initialize_scope_state",
    "set_transcript_scope",
    "clear_scope_state",
]
