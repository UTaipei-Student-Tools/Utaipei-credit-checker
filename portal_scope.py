"""Session-local identity and term scope for portal-derived course data.

The portal scraper deliberately does not own application state.  This module
is the small boundary between a successful portal response and the analysis
input: rows are only released when a verified transcript and schedule carry
the same session-scoped account fingerprint and term.

The account fingerprint is an HMAC using a per-session random salt.  It is an
internal binding value only; callers must never put it into a request,
snapshot, export, UI projection, or log.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

SCOPE_SALT_KEY = "_portal_scope_salt"
TRANSCRIPT_SCOPE_KEY = "transcript_scope"
SCHEDULE_SCOPE_KEY = "schedule_scope"
PENDING_SCHEDULE_ROWS_KEY = "_portal_pending_schedule_courses"
PENDING_SCHEDULE_SCOPE_KEY = "_portal_pending_schedule_scope"
SCHEDULE_QUARANTINE_KEY = "schedule_quarantine"
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

SCHEDULE_SCOPE_MISMATCH = "SCHEDULE_SCOPE_MISMATCH"
SCHEDULE_SCOPE_UNVERIFIED = "SCHEDULE_SCOPE_UNVERIFIED"
SCOPE_WARNING_CODES = frozenset({SCHEDULE_SCOPE_MISMATCH, SCHEDULE_SCOPE_UNVERIFIED})

_SALT_BYTES = 32
_FINGERPRINT_HEX_LENGTH = hashlib.sha256().digest_size * 2
_PUBLIC_QUARANTINE_REASONS = SCOPE_WARNING_CODES


def _text(value: object) -> str:
    return str(value or "").strip()


def _term(value: object) -> str:
    return _text(value)


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
    salt = ensure_session_salt(state)
    return hmac.new(salt, account_text.encode("utf-8"), hashlib.sha256).hexdigest()


def _safe_source(value: object) -> str:
    source = _text(value).lower()
    return source if source in SCOPE_SOURCES else SOURCE_MANUAL


def _scope_status(*, verified: bool, pending: bool = False) -> str:
    if pending:
        return SCOPE_STATUS_PENDING
    return SCOPE_STATUS_VERIFIED if verified else SCOPE_STATUS_UNVERIFIED


def build_scope(
    state: MutableMapping[str, Any],
    account: object,
    year: object,
    semester: object,
    *,
    source: str = SOURCE_PORTAL,
    verified: bool = True,
    pending: bool = False,
) -> dict[str, Any]:
    """Build a normalized portal scope; no raw account is retained."""

    return {
        "account_fingerprint": account_fingerprint(state, account),
        "year": _term(year),
        "semester": _term(semester),
        "verified": bool(verified),
        "status": _scope_status(verified=bool(verified), pending=pending),
        "source": _safe_source(source),
    }


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


def _is_verified_scope(scope: object, *, source: str | None = None) -> bool:
    if not isinstance(scope, Mapping):
        return False
    fingerprint = _text(scope.get("account_fingerprint"))
    if len(fingerprint) != _FINGERPRINT_HEX_LENGTH:
        return False
    try:
        int(fingerprint, 16)
    except (TypeError, ValueError):
        return False
    if not bool(scope.get("verified")) or _text(scope.get("status")) != SCOPE_STATUS_VERIFIED:
        return False
    if not _term(scope.get("year")) or not _term(scope.get("semester")):
        return False
    if source is not None and _safe_source(scope.get("source")) != source:
        return False
    return True


def _normalized_verified_scope(scope: object) -> dict[str, Any] | None:
    """Project a trusted-looking scope to the fixed internal schema."""

    if not _is_verified_scope(scope, source=SOURCE_PORTAL) or not isinstance(scope, Mapping):
        return None
    return {
        "account_fingerprint": _text(scope.get("account_fingerprint")),
        "year": _term(scope.get("year")),
        "semester": _term(scope.get("semester")),
        "verified": True,
        "status": SCOPE_STATUS_VERIFIED,
        "source": SOURCE_PORTAL,
    }


def scopes_match(left: object, right: object) -> bool:
    """Return true only for two verified portal scopes of the same identity/term."""

    if not _is_verified_scope(left, source=SOURCE_PORTAL) or not _is_verified_scope(right, source=SOURCE_PORTAL):
        return False
    assert isinstance(left, Mapping)
    assert isinstance(right, Mapping)
    return (
        _text(left.get("account_fingerprint")) == _text(right.get("account_fingerprint"))
        and _term(left.get("year")) == _term(right.get("year"))
        and _term(left.get("semester")) == _term(right.get("semester"))
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
    status = _text(scope.get("status"))
    if status not in SCOPE_STATUSES:
        status = SCOPE_STATUS_UNVERIFIED
    source = _safe_source(scope.get("source"))
    return {
        "status": status,
        "year": _term(scope.get("year")),
        "semester": _term(scope.get("semester")),
        "source": source,
        "verified": bool(scope.get("verified")) and status == SCOPE_STATUS_VERIFIED,
    }


def _append_warning(state: MutableMapping[str, Any], code: object) -> None:
    code_text = _text(code)
    if code_text not in SCOPE_WARNING_CODES:
        return
    current = [item for item in state.get(SCOPE_WARNING_CODES_KEY, ()) if item in SCOPE_WARNING_CODES]
    if code_text not in current:
        current.append(code_text)
    state[SCOPE_WARNING_CODES_KEY] = tuple(current)


def _remove_warning(state: MutableMapping[str, Any], code: object) -> None:
    code_text = _text(code)
    state[SCOPE_WARNING_CODES_KEY] = tuple(
        item for item in state.get(SCOPE_WARNING_CODES_KEY, ()) if item in SCOPE_WARNING_CODES and item != code_text
    )


def add_warning(state: MutableMapping[str, Any], code: object) -> tuple[str, ...]:
    """Add one allowlisted warning code and return the safe tuple."""

    _append_warning(state, code)
    return get_warning_codes(state)


def get_warning_codes(state: Mapping[str, Any]) -> tuple[str, ...]:
    """Return only fixed warning codes suitable for a DecisionSnapshot."""

    result = []
    for item in state.get(SCOPE_WARNING_CODES_KEY, ()):
        code = _text(item)
        if code in SCOPE_WARNING_CODES and code not in result:
            result.append(code)
    return tuple(result)


def _quarantine_entry(scope: object, *, reason: str, row_count: int) -> dict[str, Any]:
    """Create non-sensitive quarantine metadata; never copy rows or fingerprints."""

    safe_reason = reason if reason in _PUBLIC_QUARANTINE_REASONS else SCHEDULE_SCOPE_UNVERIFIED
    metadata = public_scope_metadata(scope)
    return {
        "status": metadata["status"],
        "year": metadata["year"],
        "semester": metadata["semester"],
        "source": metadata["source"],
        "verified": metadata["verified"],
        "reason": safe_reason,
        "had_rows": bool(row_count),
        "row_count": max(0, int(row_count)),
    }


def _quarantine(
    state: MutableMapping[str, Any],
    scope: object,
    rows: object,
    *,
    reason: str,
) -> None:
    if isinstance(rows, (str, bytes, bytearray)) or rows is None:
        row_count = 0
    else:
        try:
            row_count = len(rows)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            row_count = 0
    current = state.get(SCHEDULE_QUARANTINE_KEY, ())
    if isinstance(current, (str, bytes, bytearray)) or not isinstance(current, Sequence):
        current = ()
    entries = [item for item in current if isinstance(item, Mapping)]
    entries.append(_quarantine_entry(scope, reason=reason, row_count=row_count))
    # Keep the metadata bounded so a long-lived browser session cannot grow
    # without limit.  This is intentionally a tuple of scalars only.
    state[SCHEDULE_QUARANTINE_KEY] = tuple(entries[-8:])


def _rows(value: object) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes, bytearray)) or value is None:
        return ()
    if not isinstance(value, Sequence):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def initialize_scope_state(state: MutableMapping[str, Any], *, salt: bytes | None = None) -> None:
    """Initialize/migrate state and fail closed for legacy unscoped rows."""

    if salt is not None and _valid_salt(salt):
        state[SCOPE_SALT_KEY] = salt
    ensure_session_salt(state)
    state.setdefault(TRANSCRIPT_SCOPE_KEY, None)
    state.setdefault(SCHEDULE_SCOPE_KEY, None)
    state.setdefault(PENDING_SCHEDULE_ROWS_KEY, [])
    state.setdefault(PENDING_SCHEDULE_SCOPE_KEY, None)
    state.setdefault(SCHEDULE_QUARANTINE_KEY, ())
    state.setdefault(SCOPE_WARNING_CODES_KEY, ())

    active_rows = state.get("schedule_courses", ())
    active_scope = state.get(SCHEDULE_SCOPE_KEY)
    normalized_active_scope = _normalized_verified_scope(active_scope)
    if _rows(active_rows) and normalized_active_scope is None:
        _quarantine(state, active_scope, active_rows, reason=SCHEDULE_SCOPE_UNVERIFIED)
        state["schedule_courses"] = []
        state[SCHEDULE_SCOPE_KEY] = None
        _append_warning(state, SCHEDULE_SCOPE_UNVERIFIED)
    elif normalized_active_scope is None:
        state[SCHEDULE_SCOPE_KEY] = None
    else:
        state[SCHEDULE_SCOPE_KEY] = normalized_active_scope

    pending_rows = state.get(PENDING_SCHEDULE_ROWS_KEY, ())
    pending_scope = state.get(PENDING_SCHEDULE_SCOPE_KEY)
    normalized_pending_scope = _normalized_verified_scope(pending_scope)
    if _rows(pending_rows) and normalized_pending_scope is None:
        _quarantine(state, pending_scope, pending_rows, reason=SCHEDULE_SCOPE_UNVERIFIED)
        state[PENDING_SCHEDULE_ROWS_KEY] = []
        state[PENDING_SCHEDULE_SCOPE_KEY] = None
        _append_warning(state, SCHEDULE_SCOPE_UNVERIFIED)
    elif normalized_pending_scope is None:
        state[PENDING_SCHEDULE_SCOPE_KEY] = None
    else:
        state[PENDING_SCHEDULE_SCOPE_KEY] = normalized_pending_scope

    transcript_scope = state.get(TRANSCRIPT_SCOPE_KEY)
    if transcript_scope is not None and not (
        _is_verified_scope(transcript_scope, source=SOURCE_PORTAL)
        or (
            isinstance(transcript_scope, Mapping)
            and _safe_source(transcript_scope.get("source")) == SOURCE_UPLOAD
            and not transcript_scope.get("account_fingerprint")
        )
    ):
        state[TRANSCRIPT_SCOPE_KEY] = None


def set_transcript_scope(state: MutableMapping[str, Any], scope: Mapping[str, Any] | None) -> None:
    """Set a normalized transcript scope without copying arbitrary fields."""

    if scope is None:
        state[TRANSCRIPT_SCOPE_KEY] = None
        return
    if _safe_source(scope.get("source")) == SOURCE_UPLOAD:
        state[TRANSCRIPT_SCOPE_KEY] = build_upload_scope()
        return
    state[TRANSCRIPT_SCOPE_KEY] = {
        "account_fingerprint": _text(scope.get("account_fingerprint")) or None,
        "year": _term(scope.get("year")),
        "semester": _term(scope.get("semester")),
        "verified": bool(scope.get("verified")),
        "status": _text(scope.get("status")) if _text(scope.get("status")) in SCOPE_STATUSES else SCOPE_STATUS_UNVERIFIED,
        "source": SOURCE_PORTAL,
    }


def set_active_schedule(state: MutableMapping[str, Any], rows: object, scope: Mapping[str, Any] | None) -> bool:
    """Commit only rows paired with a verified portal scope."""

    safe_rows = list(_rows(rows))
    normalized_scope = _normalized_verified_scope(scope)
    if normalized_scope is None:
        if safe_rows:
            _quarantine(state, scope, safe_rows, reason=SCHEDULE_SCOPE_UNVERIFIED)
        state["schedule_courses"] = []
        state[SCHEDULE_SCOPE_KEY] = None
        _append_warning(state, SCHEDULE_SCOPE_UNVERIFIED)
        return False
    state["schedule_courses"] = safe_rows
    state[SCHEDULE_SCOPE_KEY] = normalized_scope
    state[PENDING_SCHEDULE_ROWS_KEY] = []
    state[PENDING_SCHEDULE_SCOPE_KEY] = None
    _remove_warning(state, SCHEDULE_SCOPE_MISMATCH)
    _remove_warning(state, SCHEDULE_SCOPE_UNVERIFIED)
    return True


def set_pending_schedule(state: MutableMapping[str, Any], rows: object, scope: Mapping[str, Any] | None) -> bool:
    """Keep a verified schedule private until a matching portal transcript exists."""

    safe_rows = list(_rows(rows))
    normalized_scope = _normalized_verified_scope(scope)
    if normalized_scope is None:
        if safe_rows:
            _quarantine(state, scope, safe_rows, reason=SCHEDULE_SCOPE_UNVERIFIED)
        state[PENDING_SCHEDULE_ROWS_KEY] = []
        state[PENDING_SCHEDULE_SCOPE_KEY] = None
        _append_warning(state, SCHEDULE_SCOPE_UNVERIFIED)
        return False
    state[PENDING_SCHEDULE_ROWS_KEY] = safe_rows
    state[PENDING_SCHEDULE_SCOPE_KEY] = normalized_scope
    return True


def _clear_active_schedule(state: MutableMapping[str, Any]) -> None:
    state["schedule_courses"] = []
    state[SCHEDULE_SCOPE_KEY] = None


def _clear_pending_schedule(state: MutableMapping[str, Any]) -> None:
    state[PENDING_SCHEDULE_ROWS_KEY] = []
    state[PENDING_SCHEDULE_SCOPE_KEY] = None


def isolate_for_uploaded_transcript(state: MutableMapping[str, Any]) -> None:
    """Clear portal rows before accepting an unbound uploaded PDF."""

    active_rows = _rows(state.get("schedule_courses", ()))
    active_scope = state.get(SCHEDULE_SCOPE_KEY)
    pending_rows = _rows(state.get(PENDING_SCHEDULE_ROWS_KEY, ()))
    pending_scope = state.get(PENDING_SCHEDULE_SCOPE_KEY)
    had_portal_candidate = bool(active_rows or active_scope is not None or pending_rows or pending_scope is not None)
    if active_rows:
        _quarantine(state, active_scope, active_rows, reason=SCHEDULE_SCOPE_UNVERIFIED)
    if pending_rows:
        _quarantine(state, pending_scope, pending_rows, reason=SCHEDULE_SCOPE_UNVERIFIED)
    _clear_active_schedule(state)
    _clear_pending_schedule(state)
    if had_portal_candidate:
        _append_warning(state, SCHEDULE_SCOPE_UNVERIFIED)
    else:
        _remove_warning(state, SCHEDULE_SCOPE_UNVERIFIED)


def _isolate_mismatched_schedule(state: MutableMapping[str, Any], requested_scope: Mapping[str, Any]) -> None:
    active_rows = _rows(state.get("schedule_courses", ()))
    active_scope = state.get(SCHEDULE_SCOPE_KEY)
    pending_rows = _rows(state.get(PENDING_SCHEDULE_ROWS_KEY, ()))
    pending_scope = state.get(PENDING_SCHEDULE_SCOPE_KEY)
    reason = SCHEDULE_SCOPE_MISMATCH if active_scope is not None and _is_verified_scope(active_scope, source=SOURCE_PORTAL) else SCHEDULE_SCOPE_UNVERIFIED
    if active_rows or active_scope is not None:
        _quarantine(state, active_scope, active_rows, reason=reason)
    if pending_rows or pending_scope is not None:
        pending_reason = SCHEDULE_SCOPE_MISMATCH if _is_verified_scope(pending_scope, source=SOURCE_PORTAL) else SCHEDULE_SCOPE_UNVERIFIED
        _quarantine(state, pending_scope, pending_rows, reason=pending_reason)
    _clear_active_schedule(state)
    _clear_pending_schedule(state)
    _append_warning(state, reason)


def retain_or_isolate_schedule(state: MutableMapping[str, Any], requested_scope: Mapping[str, Any]) -> bool:
    """Retain existing rows only for an exact verified account/term match."""

    active_scope = state.get(SCHEDULE_SCOPE_KEY)
    if scopes_match(active_scope, requested_scope):
        return True
    pending_scope = state.get(PENDING_SCHEDULE_SCOPE_KEY)
    if scopes_match(pending_scope, requested_scope):
        rows = _rows(state.get(PENDING_SCHEDULE_ROWS_KEY, ()))
        set_active_schedule(state, rows, requested_scope)
        return True
    _isolate_mismatched_schedule(state, requested_scope)
    return False


def adopt_pending_schedule(state: MutableMapping[str, Any], transcript_scope: Mapping[str, Any] | None) -> tuple[Mapping[str, Any], ...]:
    """Adopt pending rows only for the same portal account and term."""

    if isinstance(transcript_scope, Mapping) and _safe_source(transcript_scope.get("source")) == SOURCE_UPLOAD:
        isolate_for_uploaded_transcript(state)
        return ()
    pending_scope = state.get(PENDING_SCHEDULE_SCOPE_KEY)
    pending_rows = _rows(state.get(PENDING_SCHEDULE_ROWS_KEY, ()))
    if scopes_match(pending_scope, transcript_scope):
        set_active_schedule(state, pending_rows, transcript_scope)
        return tuple(pending_rows)
    # A pending schedule is not active analysis input.  Keep it private and
    # scoped so a later portal transcript for that exact account/term can
    # adopt it; merely viewing a different account/term must not destroy the
    # pending candidate or make it active.
    return ()


def verified_schedule_rows(
    state: Mapping[str, Any],
    transcript_scope: Mapping[str, Any] | None = None,
    *,
    year: object | None = None,
    semester: object | None = None,
) -> tuple[Mapping[str, Any], ...]:
    """Return rows eligible for analysis, otherwise the empty tuple."""

    if transcript_scope is None:
        transcript_scope = state.get(TRANSCRIPT_SCOPE_KEY)
    schedule_scope = state.get(SCHEDULE_SCOPE_KEY)
    if not scopes_match(transcript_scope, schedule_scope):
        return ()
    assert isinstance(schedule_scope, Mapping)
    if year is not None and _term(year) != _term(schedule_scope.get("year")):
        return ()
    if semester is not None and _term(semester) != _term(schedule_scope.get("semester")):
        return ()
    rows = _rows(state.get("schedule_courses", ()))
    for row in rows:
        row_year = _term(row.get("academic_year"))
        row_semester = _term(row.get("semester"))
        if row_year and row_year != _term(schedule_scope.get("year")):
            return ()
        if row_semester and row_semester != _term(schedule_scope.get("semester")):
            return ()
    return rows


def clear_scope_state(state: MutableMapping[str, Any]) -> None:
    """Purge all private scope material and quarantine metadata."""

    for key in (
        SCOPE_SALT_KEY,
        TRANSCRIPT_SCOPE_KEY,
        SCHEDULE_SCOPE_KEY,
        PENDING_SCHEDULE_ROWS_KEY,
        PENDING_SCHEDULE_SCOPE_KEY,
        SCHEDULE_QUARANTINE_KEY,
        SCOPE_WARNING_CODES_KEY,
    ):
        state.pop(key, None)
    state["schedule_courses"] = []
    state[TRANSCRIPT_SCOPE_KEY] = None
    state[SCHEDULE_SCOPE_KEY] = None
    state[PENDING_SCHEDULE_ROWS_KEY] = []
    state[PENDING_SCHEDULE_SCOPE_KEY] = None
    state[SCHEDULE_QUARANTINE_KEY] = []
    state[SCOPE_WARNING_CODES_KEY] = ()


__all__ = [
    "SCHEDULE_SCOPE_MISMATCH",
    "SCHEDULE_SCOPE_UNVERIFIED",
    "SCOPE_SALT_KEY",
    "TRANSCRIPT_SCOPE_KEY",
    "SCHEDULE_SCOPE_KEY",
    "SCHEDULE_QUARANTINE_KEY",
    "SCOPE_WARNING_CODES_KEY",
    "SOURCE_PORTAL",
    "SOURCE_UPLOAD",
    "SCOPE_STATUS_VERIFIED",
    "SCOPE_STATUS_PENDING",
    "SCOPE_STATUS_UNVERIFIED",
    "SCOPE_STATUS_MISMATCH",
    "SCOPE_STATUS_LEGACY",
    "ensure_session_salt",
    "account_fingerprint",
    "build_scope",
    "build_upload_scope",
    "public_scope_metadata",
    "scopes_match",
    "add_warning",
    "get_warning_codes",
    "initialize_scope_state",
    "set_transcript_scope",
    "set_active_schedule",
    "set_pending_schedule",
    "isolate_for_uploaded_transcript",
    "retain_or_isolate_schedule",
    "adopt_pending_schedule",
    "verified_schedule_rows",
    "clear_scope_state",
]
