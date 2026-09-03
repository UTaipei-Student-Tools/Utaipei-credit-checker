"""The single, evidence-aware graduation evaluation boundary.

The Streamlit application has several historical report paths.  This module
is deliberately framework-independent: a caller hands it a frozen request
whose course rows have already crossed :mod:`input_confirmation`, and it
returns one :class:`decision_snapshot.DecisionSnapshot`.  UI, charts, and
exports can then consume that snapshot without re-running a rule engine.

The service is intentionally conservative.  A checked-in curriculum record
may expose useful planning aggregates while still lacking a named course
pool.  Such rows are compiled as non-accepting requirements and remain
``UNKNOWN`` until an official, complete source is available.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from allocation_engine import (
    COMPLETE,
    CONFLICTED,
    FAIL,
    MANUAL_REVIEW,
    MISSING,
    NONE,
    NOT_APPLICABLE,
    PARTIAL,
    PASS,
    SHARED_SHADOW,
    UNKNOWN,
    VERIFIED,
    WAIVER,
    AllocationResult,
    CourseAttempt,
    EquivalencyBinding,
    RequirementResult,
    RequirementSpec,
    allocate_credits,
    normalize_course_kind,
)
from application_resolution import (
    resolve_application_case,
    resolve_formal_award,
    resolve_minor_application_case,
    resolve_minor_award,
)
from curriculum_registry import get_curriculum, resolve_rule_context
from decision_snapshot import DecisionSnapshot
from input_confirmation import (
    ConfirmationState,
    CourseConfirmation,
    NormalizedCourseRow,
    fingerprint_course_rows,
    release_formal_attempts,
)
from snapshot_projection import build_statistics_v2

SERVICE_SCHEMA_VERSION = "graduation-evaluation.v1"
ENGINE_VERSION = "graduation-service.v1"

_DOUBLE_MAJOR = "雙主修"
_TEXT_FIELDS = frozenset({"admission_cohort", "primary_curriculum_id", "program_type", "secondary_kind", "target_curriculum_year"})
# Portal input is transcript-only.  Keep the allowlist empty so stale warning
# values from a pre-removal session cannot affect a DecisionSnapshot.
INPUT_WARNING_CODES = frozenset()
_EVIDENCE_FIELDS = (
    "target_curriculum_evidence_id",
    "rule_applicability_evidence_id",
    "department_decision_evidence_id",
    "registrar_registration_evidence_id",
    "formal_qualification_evidence_id",
    "formal_award_evidence_id",
)


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float, bool)) else ""


def _number(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, float, str)) and not isinstance(value, bool):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return default
    else:
        return default
    return result if result.is_finite() else default


def _positive_number(value: Any) -> Decimal:
    return max(Decimal("0"), _number(value))


def _freeze(value: Any) -> Any:
    """Recursively freeze a JSON-shaped value for a snapshot field."""

    from types import MappingProxyType

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _unique_text(values: Any) -> tuple[str, ...]:
    if isinstance(values, str):
        values = (values,)
    if not isinstance(values, Sequence) or isinstance(values, (bytes, bytearray)):
        return ()
    return tuple(sorted({_text(item) for item in values if _text(item)}))


def _is_double_major(value: Any) -> bool:
    normalized = _text(value)
    return normalized == _DOUBLE_MAJOR or normalized.lower() in {"double", "double_major", "dm"}


def _secondary_kind(value: Any, program_type: Any = None) -> str:
    """Normalize the additive secondary role without breaking old callers."""

    candidate = _text(value) or _text(program_type)
    normalized = candidate.lower().replace("-", "_").replace(" ", "")
    if normalized in {"minor", "minor_target", "secondary_minor", "輔系"}:
        return "minor"
    if _is_double_major(candidate):
        return "double_major"
    return "none"


def _is_minor_request(request: EvaluationRequest) -> bool:
    return _secondary_kind(request.secondary_kind, request.program_type) == "minor"


def _is_double_request(request: EvaluationRequest) -> bool:
    return _secondary_kind(request.secondary_kind, request.program_type) == "double_major"


def _course_label(value: Any) -> str:
    """Normalize punctuation/spacing only; never perform fuzzy matching."""

    return re.sub(r"\s+", "", _text(value)).replace("（", "(").replace("）", ")").casefold()


def _safe_provenance(record: Any, *, requirement_id: str = "", scope: str = "") -> dict[str, Any]:
    """Keep official scalar audit handles and discard arbitrary record data."""

    if not isinstance(record, Mapping):
        return {
            "requirement_id": requirement_id,
            "scope": scope,
            "evidence_state": UNKNOWN,
            "automatic_decision": False,
        }
    result: dict[str, Any] = {
        "requirement_id": requirement_id,
        "scope": scope,
    }
    keys = (
        "id",
        "assertion_id",
        "source_assertion_id",
        "evidence_id",
        "record_id",
        "curriculum_id",
        "version",
        "curriculum_version",
        "admission_cohort",
        "program",
        "program_slug",
        "track",
        "track_slug",
        "source_type",
        "source_file",
        "source_url",
        "source_reference",
        "pages",
        "page",
        "pdf_page",
        "printed_page",
        "location",
        "table_location",
        "original_text",
        "original_clause",
        "claim",
        "raw_title",
        "evidence_state",
        "coverage_state",
        "extraction_method",
        "named_course_pool_state",
        "research_file",
        "verification_status",
        "automatic_decision",
        "manual_reason",
        "original_clause",
        "original_text",
    )
    for key in keys:
        value = record.get(key)
        if isinstance(value, (str, int, float, bool, Decimal)) and not isinstance(value, (bytes, bytearray)):
            result[key] = str(value) if isinstance(value, Decimal) else value
    evidence_state = _text(result.get("evidence_state")) or UNKNOWN
    coverage_state = _text(result.get("coverage_state")) or NONE
    result["evidence_state"] = evidence_state
    result["coverage_state"] = coverage_state
    explicit_automatic = result.get("automatic_decision")
    result["automatic_decision"] = (
        bool(explicit_automatic)
        if isinstance(explicit_automatic, bool)
        else evidence_state == VERIFIED and coverage_state == COMPLETE
    )
    return result


def _safe_curriculum(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(record, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in (
        "id",
        "curriculum_id",
        "kind",
        "type",
        "curriculum_kind",
        "version",
        "curriculum_version",
        "admission_cohort",
        "program",
        "program_slug",
        "track",
        "track_slug",
        "program_type",
        "total_required",
        "base_required",
        "other_required",
        "source_file",
        "source_url",
        "evidence_state",
        "coverage_state",
        "aggregate_status",
        "status",
        "pass_eligible",
        "legacy_planning",
        "research_file",
        "warnings",
        "blockers",
        "manual_review_reasons",
        "zero_credit_gate",
        "conflicted_course_names",
    ):
        value = record.get(key)
        if isinstance(value, (str, int, float, bool, Decimal)):
            result[key] = str(value) if isinstance(value, Decimal) else value
    thresholds = record.get("thresholds")
    if isinstance(thresholds, Mapping):
        result["thresholds"] = _safe_thresholds(thresholds)
    catalog: list[dict[str, Any]] = []
    for row in record.get("course_catalog", ()) if isinstance(record.get("course_catalog", ()), Sequence) else ():
        if not isinstance(row, Mapping):
            continue
        safe: dict[str, Any] = {}
        for key in (
            "id",
            "requirement_id",
            "name",
            "display_name",
            "raw_title",
            "credits",
            "bucket",
            "kind",
            "requirement_type",
            "choice_group",
            "choice_rule",
            "component",
            "component_type",
            "component_label",
            "lecture_or_lab",
            "is_lab",
            "is_zero_credit",
            "track",
            "track_slug",
            "curriculum_version",
            "evidence_state",
            "source_assertion_id",
            "assertion_id",
            "source_reference",
            "source_url",
            "source_file",
            "pdf_page",
            "printed_page",
            "page",
            "pages",
            "official_course_identity",
            "course_code",
            "official_course_code",
            "course_id",
            "department",
            "dept",
            "section",
            "named_course_pool_state",
            "eligible_course_names",
            "eligible_course_options",
            "accept_any",
            "waiver",
            "waiver_generates_credits",
            "allow_combined_lab_source",
            "source_assertion_id",
            "assertion_id",
            "research_file",
            "verification_status",
            "automatic_decision",
            "manual_reason",
            "original_clause",
            "original_text",
            "table_location",
        ):
            value = row.get(key)
            if isinstance(value, (str, int, float, bool, Decimal)):
                safe[key] = str(value) if isinstance(value, Decimal) else value
            elif key == "eligible_course_names" and isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                safe[key] = tuple(_text(item) for item in value if _text(item))
            elif key == "eligible_course_options" and isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                safe[key] = tuple(
                    {"name": _text(item.get("name")), "credits": _text(item.get("credits"))}
                    for item in value
                    if isinstance(item, Mapping) and _text(item.get("name"))
                )
        catalog.append(safe)
    result["course_catalog"] = tuple(sorted(catalog, key=lambda item: (str(item.get("id", "")), str(item.get("name", "")))))
    for key in ("warnings", "manual_review_reasons"):
        value = record.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            result[key] = tuple(_text(item) for item in value if _text(item))
    blockers = record.get("blockers")
    if isinstance(blockers, Sequence) and not isinstance(blockers, (str, bytes, bytearray)):
        result["blockers"] = tuple(
            _safe_blocker(item) if isinstance(item, Mapping) else {"reason": _text(item)}
            for item in blockers
            if isinstance(item, Mapping) or _text(item)
        )
    for key in ("zero_credit_gate",):
        if isinstance(record.get(key), bool):
            result[key] = bool(record[key])
    for key in ("conflicted_course_names",):
        value = record.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            result[key] = tuple(_text(item) for item in value if _text(item))
    result["citations"] = tuple(_safe_provenance(item) for item in record.get("citations", ()) if isinstance(item, Mapping))
    result["source_assertions"] = tuple(
        _safe_provenance({**dict(record), **dict(item)}, scope="curriculum_assertion")
        for item in record.get("source_assertions", record.get("assertions", ()))
        if isinstance(item, Mapping)
    )
    result["assertions"] = result["source_assertions"]
    return result


def _safe_thresholds(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        key_text = _text(key)
        if not key_text:
            continue
        if isinstance(item, Mapping):
            result[key_text] = _safe_thresholds(item)
        elif isinstance(item, (int, float, str, Decimal)) and not isinstance(item, bool):
            numeric = _number(item, Decimal("NaN"))
            if numeric.is_finite() and numeric >= 0:
                result[key_text] = str(numeric)
    return result


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    """Privacy-safe, confirmed input for one deterministic evaluation.

    The dataclass intentionally has no fields for names, student numbers,
    passwords, cookies, PDF bytes, or evidence blobs.  ``from_mapping`` is a
    convenience adapter that only reads this allowlisted schema.
    """

    admission_cohort: str = ""
    primary_curriculum_id: str = ""
    confirmed_course_rows: tuple[NormalizedCourseRow, ...] = ()
    confirmed_course_fingerprint: str = ""
    transcript_confirmed: bool = False
    confirmation_state: str = ""
    # Compatibility spellings for adapters that already expose a confirmation
    # object.  They are normalized into the canonical fields below and are
    # never emitted as separate persistence fields.
    confirmed_rows: tuple[NormalizedCourseRow, ...] = ()
    confirmed_fingerprint: str = ""
    course_confirmation: CourseConfirmation | None = None
    input_confirmation_state: str | None = None
    program_type: str = "單主修"
    # Explicit secondary role; ``program_type`` remains a compatibility
    # spelling for existing single/double-major callers.
    secondary_kind: str | None = None
    target_curriculum_id: str | None = None
    target_curriculum_version_candidate: str | None = None
    # ``target_curriculum_version`` is retained as an explicit alias because
    # older callers use that wording.  It is never inferred from cohort.
    target_curriculum_version: str | None = None
    target_curriculum_version_id: str | None = None
    target_curriculum_year: str | int | None = None
    target_program: str | None = None
    target_track: str | None = None
    application_year: str | int | None = None
    application_semester: str | int | None = None
    application_term: str | None = None
    application_status: str | None = None
    school_approval_status: str | None = None
    formal_qualification_status: str | None = None
    formal_qualification_state: str | None = None
    formal_award_status: str | None = None
    # Opaque, session-scoped subject binding used only by trusted resolvers.
    # It is intentionally not emitted in ``as_dict`` or the DecisionSnapshot.
    subject_ref: str | None = field(default=None, repr=False)
    target_curriculum_evidence_id: str | None = None
    target_version_evidence_id: str | None = None
    rule_applicability_evidence_id: str | None = None
    rule_evidence_id: str | None = None
    department_decision_evidence_id: str | None = None
    school_approval_evidence_id: str | None = None
    registrar_registration_evidence_id: str | None = None
    registrar_evidence_id: str | None = None
    formal_qualification_evidence_id: str | None = None
    formal_award_evidence_id: str | None = None
    equivalency_evidence_ids: tuple[str, ...] = ()
    equivalency_binding_ids: tuple[str, ...] = ()
    official_evidence_ids: tuple[str, ...] = ()
    notice_evidence_ids: tuple[str, ...] = ()
    as_of: str | None = None
    search_limit: int = 10000
    # Only fixed, non-sensitive warning codes may cross the UI -> service
    # boundary.  Account fingerprints, scopes, and raw portal data never do.
    input_warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        rows = self.confirmed_course_rows
        confirmation = self.course_confirmation if isinstance(self.course_confirmation, CourseConfirmation) else None
        if not rows and self.confirmed_rows:
            rows = self.confirmed_rows
        if isinstance(rows, CourseConfirmation):
            confirmation = rows
            rows = confirmation.rows
        if confirmation is not None and not rows:
            rows = confirmation.rows
        if confirmation is not None:
            if not self.confirmed_course_fingerprint:
                object.__setattr__(self, "confirmed_course_fingerprint", confirmation.fingerprint)
            if not self.confirmation_state and not self.input_confirmation_state:
                object.__setattr__(self, "confirmation_state", confirmation.state.value)
        if isinstance(rows, (str, bytes, bytearray)) or not isinstance(rows, Sequence):
            raise TypeError("confirmed_course_rows must contain NormalizedCourseRow values")
        if not all(isinstance(row, NormalizedCourseRow) for row in rows):
            raise TypeError("confirmed_course_rows must contain NormalizedCourseRow values")
        ordered_rows = tuple(sorted(rows, key=lambda row: tuple(_text(row.as_dict().get(key)) for key in sorted(row.as_dict()))))
        object.__setattr__(self, "confirmed_course_rows", ordered_rows)
        object.__setattr__(self, "confirmed_rows", ordered_rows)
        object.__setattr__(self, "admission_cohort", _text(self.admission_cohort))
        object.__setattr__(self, "primary_curriculum_id", _text(self.primary_curriculum_id))
        object.__setattr__(self, "program_type", _text(self.program_type) or "單主修")
        object.__setattr__(self, "secondary_kind", _secondary_kind(self.secondary_kind, self.program_type))
        fingerprint = _text(self.confirmed_course_fingerprint) or _text(self.confirmed_fingerprint)
        object.__setattr__(self, "confirmed_course_fingerprint", fingerprint)
        object.__setattr__(self, "confirmed_fingerprint", fingerprint)
        object.__setattr__(self, "transcript_confirmed", bool(self.transcript_confirmed))
        state = _text(self.confirmation_state or self.input_confirmation_state).upper() or ("CONFIRMED" if self.transcript_confirmed else "UNCONFIRMED")
        if state not in {item.value for item in ConfirmationState}:
            state = "UNCONFIRMED"
        if not self.transcript_confirmed:
            state = "UNCONFIRMED" if state == "CONFIRMED" else state
        # If an adapter supplied a CourseConfirmation object, all canonical
        # row/fingerprint/state fields must describe that exact object.  A
        # mismatch is stale input, never a second opportunity to assert
        # confirmation via the request booleans.
        confirmation_mismatch = False
        if confirmation is not None:
            current_rows_fingerprint = fingerprint_course_rows(ordered_rows)
            supplied_fingerprint = _text(self.confirmed_course_fingerprint)
            if confirmation.fingerprint != current_rows_fingerprint:
                confirmation_mismatch = True
            if supplied_fingerprint and supplied_fingerprint != confirmation.fingerprint:
                confirmation_mismatch = True
            if self.transcript_confirmed != (confirmation.state is ConfirmationState.CONFIRMED):
                confirmation_mismatch = True
            if confirmation_mismatch:
                object.__setattr__(self, "transcript_confirmed", False)
                state = "STALE"
        object.__setattr__(self, "confirmation_state", state)
        for key in (
            "target_curriculum_id",
            "target_curriculum_version_candidate",
            "target_curriculum_version",
            "target_program",
            "target_track",
            "target_curriculum_year",
            "application_term",
            "application_status",
            "school_approval_status",
            "formal_qualification_status",
            "formal_award_status",
            "as_of",
            "subject_ref",
        ):
            value = getattr(self, key)
            object.__setattr__(self, key, _text(value) or None)
        for key in ("application_year", "application_semester"):
            value = getattr(self, key)
            object.__setattr__(self, key, _text(value) or None)
        for key in _EVIDENCE_FIELDS:
            value = getattr(self, key)
            object.__setattr__(self, key, _text(value) or None)
        aliases = {
            "target_curriculum_id": self.target_curriculum_version_id,
            "target_curriculum_evidence_id": self.target_version_evidence_id,
            "rule_applicability_evidence_id": self.rule_evidence_id,
            "department_decision_evidence_id": self.school_approval_evidence_id,
            "registrar_registration_evidence_id": self.registrar_evidence_id,
            "formal_qualification_status": self.formal_qualification_state,
        }
        for canonical, alias in aliases.items():
            if not getattr(self, canonical) and alias:
                object.__setattr__(self, canonical, _text(alias) or None)
        object.__setattr__(self, "target_curriculum_version_id", self.target_curriculum_id)
        object.__setattr__(self, "target_version_evidence_id", self.target_curriculum_evidence_id)
        object.__setattr__(self, "rule_evidence_id", self.rule_applicability_evidence_id)
        object.__setattr__(self, "school_approval_evidence_id", self.department_decision_evidence_id)
        object.__setattr__(self, "registrar_evidence_id", self.registrar_registration_evidence_id)
        object.__setattr__(self, "formal_qualification_state", self.formal_qualification_status)
        equivalency_ids = (*self.equivalency_evidence_ids, *self.equivalency_binding_ids)
        object.__setattr__(self, "equivalency_evidence_ids", _unique_text(equivalency_ids))
        object.__setattr__(self, "equivalency_binding_ids", self.equivalency_evidence_ids)
        object.__setattr__(self, "official_evidence_ids", _unique_text(self.official_evidence_ids))
        object.__setattr__(self, "notice_evidence_ids", _unique_text(self.notice_evidence_ids))
        warning_codes = []
        raw_warning_codes = self.input_warning_codes
        if isinstance(raw_warning_codes, Sequence) and not isinstance(raw_warning_codes, (str, bytes, bytearray)):
            for item in raw_warning_codes:
                code = _text(item)
                if code in INPUT_WARNING_CODES and code not in warning_codes:
                    warning_codes.append(code)
        object.__setattr__(self, "input_warning_codes", tuple(warning_codes))
        try:
            limit = int(self.search_limit)
        except (TypeError, ValueError, OverflowError):
            limit = 10000
        object.__setattr__(self, "search_limit", max(1, limit))

    @property
    def target_version(self) -> str | None:
        return self.target_curriculum_id or self.target_curriculum_version_candidate or self.target_curriculum_version

    @property
    def resolved_application_term(self) -> str | None:
        if self.application_term:
            return self.application_term
        if self.application_year and self.application_semester:
            return f"{self.application_year}-{self.application_semester}"
        return None

    @classmethod
    def from_confirmation(
        cls,
        confirmation: CourseConfirmation,
        *,
        admission_cohort: str,
        primary_curriculum_id: str,
        **kwargs: Any,
    ) -> EvaluationRequest:
        if not isinstance(confirmation, CourseConfirmation):
            raise TypeError("confirmation must be a CourseConfirmation")
        return cls(
            admission_cohort=admission_cohort,
            primary_curriculum_id=primary_curriculum_id,
            confirmed_course_rows=confirmation.rows,
            confirmed_course_fingerprint=confirmation.confirmed_fingerprint or confirmation.fingerprint,
            transcript_confirmed=confirmation.state is ConfirmationState.CONFIRMED,
            confirmation_state=confirmation.state.value,
            **kwargs,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> EvaluationRequest:
        if not isinstance(value, Mapping):
            raise TypeError("evaluation request must be a mapping")
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        payload = {key: value[key] for key in allowed if key in value}
        if "target_curriculum_version_candidate" not in payload and "target_curriculum_version" in payload:
            payload["target_curriculum_version_candidate"] = payload["target_curriculum_version"]
        return cls(**payload)

    def as_dict(self) -> Mapping[str, Any]:
        rows = tuple(row.as_dict() for row in self.confirmed_course_rows)
        payload: dict[str, Any] = {
            "admission_cohort": self.admission_cohort,
            "primary_curriculum_id": self.primary_curriculum_id,
            "confirmed_course_rows": rows,
            "confirmed_course_fingerprint": self.confirmed_course_fingerprint,
            "transcript_confirmed": self.transcript_confirmed,
            "confirmation_state": self.confirmation_state,
            "program_type": self.program_type,
            "secondary_kind": self.secondary_kind,
            "target_curriculum_id": self.target_curriculum_id,
            "target_curriculum_version_candidate": self.target_curriculum_version_candidate,
            "target_curriculum_version": self.target_curriculum_version,
            "target_curriculum_year": self.target_curriculum_year,
            "target_program": self.target_program,
            "target_track": self.target_track,
            "application_year": self.application_year,
            "application_semester": self.application_semester,
            "application_term": self.resolved_application_term,
            "application_status": self.application_status,
            "school_approval_status": self.school_approval_status,
            "formal_qualification_status": self.formal_qualification_status,
            "formal_award_status": self.formal_award_status,
            "input_warning_codes": self.input_warning_codes,
            "equivalency_evidence_ids": self.equivalency_evidence_ids,
            "official_evidence_ids": self.official_evidence_ids,
            "notice_evidence_ids": self.notice_evidence_ids,
            "as_of": self.as_of,
            "search_limit": self.search_limit,
        }
        for key in _EVIDENCE_FIELDS:
            payload[key] = getattr(self, key)
        return _freeze(payload)


def _released_rows(request: EvaluationRequest) -> tuple[NormalizedCourseRow, ...]:
    """Release exactly the current confirmed fingerprint, never raw input."""

    if not request.transcript_confirmed or request.confirmation_state != ConfirmationState.CONFIRMED.value:
        return ()
    if not request.confirmed_course_fingerprint:
        return ()
    if fingerprint_course_rows(request.confirmed_course_rows) != request.confirmed_course_fingerprint:
        return ()
    confirmation = request.course_confirmation
    if confirmation is None:
        confirmation = CourseConfirmation(
            rows=request.confirmed_course_rows,
            fingerprint=request.confirmed_course_fingerprint,
            state=ConfirmationState.CONFIRMED,
            confirmed_fingerprint=request.confirmed_course_fingerprint,
        )
    return release_formal_attempts(confirmation, request.confirmed_course_fingerprint)


def _context_request(request: EvaluationRequest, primary: Mapping[str, Any] | None, target: Mapping[str, Any] | None) -> dict[str, Any]:
    primary_program = _text((primary or {}).get("program_slug"))
    primary_track = _text((primary or {}).get("track_slug"))
    target_program = _text(request.target_program) or _text((target or {}).get("program_slug"))
    target_track = _text(request.target_track) or _text((target or {}).get("track_slug"))
    result: dict[str, Any] = {
        "admission_cohort": request.admission_cohort,
        "primary_curriculum_id": request.primary_curriculum_id,
        "primary_program": primary_program,
        "primary_track": primary_track,
        "program_type": request.program_type,
        "secondary_kind": request.secondary_kind,
        "target_program": target_program,
        "target_track": target_track,
        "application_term": request.resolved_application_term,
        "application_year": request.application_year,
        "application_semester": request.application_semester,
    }
    if request.target_version:
        result["target_curriculum_version"] = request.target_version
    if request.target_curriculum_year:
        result["target_curriculum_year"] = request.target_curriculum_year
    if request.target_curriculum_evidence_id:
        result["target_version_evidence_reference"] = request.target_curriculum_evidence_id
    return {key: value for key, value in result.items() if value not in (None, "")}


def _safe_rule_resolution(result: Mapping[str, Any]) -> dict[str, Any]:
    def dimension(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            return {"status": UNKNOWN, "state": UNKNOWN, "reason": "規則維度無法解析。"}
        safe: dict[str, Any] = {}
        for key in ("status", "state", "value", "reason", "evidence_reference", "evidence_state", "coverage_state", "curriculum_id"):
            item = value.get(key)
            if isinstance(item, (str, int, float, bool, Decimal)) or item is None:
                safe[key] = str(item) if isinstance(item, Decimal) else item
        curriculum = _safe_curriculum(value.get("curriculum"))
        if curriculum is not None:
            safe["curriculum"] = curriculum
        return safe

    safe = {
        key: result.get(key)
        for key in (
            "status",
            "state",
            "resolved",
            "can_pass",
            "secondary_kind",
            "target_role",
            "blocker",
            "admission_cohort",
            "application_term",
            "target_program",
            "target_track",
            "primary_curriculum_id",
            "target_curriculum_id",
        )
        if isinstance(result.get(key), (str, int, float, bool)) or result.get(key) is None
    }
    safe["blocker_codes"] = tuple(_text(item) for item in result.get("blocker_codes", ()) if _text(item))
    safe["warnings"] = tuple(_text(item) for item in result.get("warnings", ()) if _text(item))
    dimensions = result.get("dimensions")
    safe["dimensions"] = {
        _text(key): dimension(item)
        for key, item in dimensions.items()
        if _text(key)
    } if isinstance(dimensions, Mapping) else {}
    safe["blockers"] = tuple(
        _safe_blocker(item)
        for item in result.get("blockers", ())
        if isinstance(item, Mapping)
    )
    safe["primary_curriculum"] = _safe_curriculum(result.get("primary_curriculum"))
    safe["target_curriculum"] = _safe_curriculum(result.get("target_curriculum"))
    return safe


def _safe_blocker(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in ("code", "dimension", "reason", "curriculum_id")
        if isinstance(value.get(key), (str, int, float, bool)) or value.get(key) is None
    }


def _safe_gate(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"status": UNKNOWN, "state": UNKNOWN, "reason": "官方申請證據無法解析。"}
    result: dict[str, Any] = {}
    for key in (
        "status",
        "state",
        "code",
        "reason",
        "value",
        "award_state",
        "qualification_state",
        "is_official",
        "effective_term",
        "record_type",
    ):
        item = value.get(key)
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[key] = item
    result["evidence_ids"] = tuple(_text(item) for item in value.get("evidence_ids", ()) if _text(item))
    result["provenance"] = tuple(_safe_provenance(item) for item in value.get("provenance", ()) if isinstance(item, Mapping))
    return result


def _safe_application(result: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        return {"status": UNKNOWN, "state": UNKNOWN, "can_pass": False}
    safe = {key: result.get(key) for key in ("status", "state", "can_pass", "graduation_ready", "application_term", "target_program", "target_track", "as_of") if isinstance(result.get(key), (str, int, float, bool)) or result.get(key) is None}
    for key in (
        "notice",
        "university_window",
        "department_window",
        "submission",
        "rule_version",
        "rule_applicability",
        "department_decision",
        "department",
        "registrar_registration",
        "registration",
        "activity",
        "formal_qualification",
        "formal_award",
    ):
        if key in result:
            safe[key] = _safe_gate(result[key])
    safe["gates"] = {str(key): _text(value) for key, value in result.get("gates", {}).items()} if isinstance(result.get("gates"), Mapping) else {}
    safe["blockers"] = tuple(_safe_blocker(item) for item in result.get("blockers", ()) if isinstance(item, Mapping))
    safe["evidence_ids"] = tuple(_text(item) for item in result.get("evidence_ids", ()) if _text(item))
    safe["provenance"] = tuple(_safe_provenance(item) for item in result.get("provenance", ()) if isinstance(item, Mapping))
    # Self-reported status is useful to explain a pending gate, but only the
    # resolver's official statuses above participate in a verdict.
    self_reported = result.get("self_reported")
    if isinstance(self_reported, Mapping):
        safe["self_reported"] = {
            key: item
            for key, item in self_reported.items()
            if key not in {"student_id", "subject_id", "subject_ref"} and isinstance(item, (str, int, float, bool))
        }
    return safe


def _curriculum_rows(record: Mapping[str, Any] | None) -> tuple[Mapping[str, Any], ...]:
    rows = record.get("course_catalog", ()) if isinstance(record, Mapping) else ()
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in rows if isinstance(item, Mapping))


def _flatten_numeric_thresholds(value: Mapping[str, Any], prefix: str = "") -> Iterable[tuple[str, Decimal]]:
    for key in sorted(value):
        name = _text(key)
        if not name:
            continue
        full = f"{prefix}.{name}" if prefix else name
        item = value[key]
        if isinstance(item, Mapping):
            yield from _flatten_numeric_thresholds(item, full)
        elif isinstance(item, (int, float, str, Decimal)) and not isinstance(item, bool):
            amount = _positive_number(item)
            if amount > 0:
                yield full, amount


def _coverage(value: Any) -> str:
    text = _text(value).upper()
    return text if text in {COMPLETE, PARTIAL, NONE} else NONE


def _evidence(value: Any) -> str:
    text = _text(value).upper()
    return text if text in {VERIFIED, CONFLICTED, MISSING, MANUAL_REVIEW} else UNKNOWN


def _requirement_id(scope: str, curriculum_id: str, suffix: str) -> str:
    return f"{scope}:{curriculum_id}:{suffix}"


_EXECUTABLE_ROW_TYPES = frozenset(
    {
        "course",
        "named_course",
        "required_course",
        "required",
        "choice",
        "choice_course",
        "course_pool",
        "credit_quota",
        "quota",
        "aggregate",
    }
)
_DERIVED_THRESHOLD_KEYS = frozenset({"total", "total_required", "graduation_total", "graduation_total_required"})


def _has_executable_row_semantics(row: Mapping[str, Any]) -> bool:
    """Require an explicit required/choice meaning before compiling a row."""

    requirement_type = _text(row.get("requirement_type")).lower().replace("-", "_").replace(" ", "_")
    if requirement_type in _EXECUTABLE_ROW_TYPES:
        return True
    # A checked-in source may use boolean/selection fields instead of the
    # normalized requirement_type.  A bucket or a name alone is intentionally
    # insufficient: CS department rows are candidate lists, not requirements.
    for key in (
        "required",
        "is_required",
        "required_course",
        "formal_requirement",
        "executable",
        "choice_rule",
        "selection_rule",
        "eligible_course_ids",
        "eligible_pool_ids",
        "accept_any",
    ):
        if row.get(key) not in (None, "", False, (), [], {}):
            return True
    return False


def _unresolved_threshold_quotas(
    record: Mapping[str, Any],
    *,
    scope: str,
    curriculum_id: str,
    record_coverage: str,
    record_evidence: str,
    existing_generic: bool,
) -> tuple[RequirementSpec, ...]:
    """Expose explicit aggregate claims without inventing a course pool.

    A threshold is only materialized when the registry has no explicit quota
    row for it.  It remains a non-allocatable UNKNOWN placeholder; derived
    total aliases are deliberately excluded.
    """

    if existing_generic or not isinstance(record.get("thresholds"), Mapping):
        return ()
    specs: list[RequirementSpec] = []
    seen_keys: set[str] = set()
    for key, raw_value in sorted(record["thresholds"].items(), key=lambda item: str(item[0])):
        key_text = _text(key).lower().replace("-", "_").replace(" ", "_")
        if not key_text or key_text in _DERIVED_THRESHOLD_KEYS:
            continue
        if key_text.endswith("_required") and key_text.removesuffix("_required") in {"base", "other"}:
            key_text = key_text.removesuffix("_required")
        if key_text in seen_keys:
            continue
        amount = _positive_number(raw_value)
        if amount <= 0 or isinstance(raw_value, Mapping):
            continue
        seen_keys.add(key_text)
        requirement_id = _requirement_id(scope, curriculum_id, f"quota:{key_text}")
        specs.append(
            RequirementSpec(
                requirement_id=requirement_id,
                name=f"未解析額度：{key_text}",
                credits_required=amount,
                eligible_course_ids=(),
                eligible_course_names=(),
                coverage_state=record_coverage,
                evidence_state=record_evidence,
                required=True,
                accept_any=False,
                bucket=key_text,
                kind="AGGREGATE",
                owner="PRIMARY" if scope == "primary" else "TARGET" if scope == "target" else _text(scope).upper(),
                domain=f"{scope}:{key_text}",
            )
        )
    return tuple(specs)


def _compile_requirements(
    record: Mapping[str, Any] | None,
    *,
    scope: str,
) -> tuple[tuple[RequirementSpec, ...], dict[str, dict[str, Any]], tuple[dict[str, Any], ...]]:
    """Compile executable leaf rows without flattening derived aggregates.

    Registry thresholds such as ``total`` and ``base`` remain available in
    the curriculum/provenance projections, but they are derived constraints,
    not independent consumers of transcript credits.  Only an exact named
    catalog row or an explicitly named incomplete quota becomes a requirement
    spec; the latter has no course pool and is deliberately UNKNOWN.
    """

    if not isinstance(record, Mapping):
        return (), {}, ()
    curriculum_id = _text(record.get("curriculum_id"))
    record_coverage = _coverage(record.get("coverage_state"))
    record_evidence = _evidence(record.get("evidence_state"))
    specs: list[RequirementSpec] = []
    metadata: dict[str, dict[str, Any]] = {}
    provenance: list[dict[str, Any]] = []
    seen: set[str] = set()
    rows = _curriculum_rows(record)
    for index, row in enumerate(rows):
        row_type = _text(row.get("requirement_type")).lower().replace("-", "_").replace(" ", "_")
        if row_type in {"conflict_candidate", "candidate_alias"}:
            # A conflict candidate is retained in the curriculum provenance,
            # but it is not a separate credit consumer.  The evaluation gate
            # below marks the overall minor UNKNOWN only when a transcript
            # actually uses that candidate.
            continue
        name = _text(row.get("name") or row.get("raw_title") or row.get("display_name"))
        credits = _positive_number(row.get("credits"))
        if not name or credits <= 0:
            continue
        if not _has_executable_row_semantics(row):
            # Preserve a planning candidate in provenance/registry output, but
            # never turn a bare department catalogue row into a required
            # deficit or a formal allocator consumer.
            continue
        raw_id = _text(row.get("requirement_id") or row.get("id"))
        suffix = raw_id or f"course:{_digest([name, str(credits), _text(row.get('bucket')), index])}"
        rid = _requirement_id(scope, curriculum_id, suffix)
        if rid in seen:
            continue
        seen.add(rid)
        row_evidence = _evidence(row.get("evidence_state") or row.get("evidence") or record_evidence)
        row_coverage = _coverage(row.get("coverage_state") or record_coverage)
        component = _text(row.get("component_type") or row.get("component") or row.get("lecture_or_lab"))
        kind = component.upper() if component else ""
        generic = row_type in {"credit_quota", "quota", "aggregate"} or not _text(row.get("name"))
        official_course_id = _text(
            row.get("course_code")
            or row.get("official_course_code")
            or row.get("official_course_identity")
            or row.get("course_id")
        )
        department = _text(row.get("department") or row.get("dept") or row.get("department_code"))
        section = _text(row.get("section") or row.get("track") or row.get("track_slug"))
        bucket = _text(row.get("bucket")) or scope
        owner = "PRIMARY" if scope == "primary" else "TARGET" if scope == "target" else _text(scope).upper()
        domain = _text(row.get("domain") or row.get("requirement_domain")) or f"{scope}:{bucket}"
        row_names = tuple(_text(item) for item in row.get("eligible_course_names", ()) if _text(item)) if isinstance(row.get("eligible_course_names"), Sequence) and not isinstance(row.get("eligible_course_names"), (str, bytes, bytearray)) else ()
        eligible_names = () if generic else row_names or (name,)
        accept_any = bool(row.get("accept_any")) if not generic else False
        spec = RequirementSpec(
            requirement_id=rid,
            name=name,
            credits_required=credits,
            max_credits=credits,
            eligible_course_ids=() if generic else ((official_course_id,) if official_course_id else ()),
            eligible_course_names=eligible_names,
            allowed_course_kinds=(kind,) if kind else (),
            coverage_state=row_coverage,
            evidence_state=row_evidence,
            required=True,
            waiver=bool(row.get("waiver")),
            accept_any=accept_any,
            bucket=bucket,
            kind="AGGREGATE" if generic else _text(row.get("kind")) or "NAMED_COURSE",
            owner=owner,
            domain=domain,
        )
        specs.append(spec)
        meta = {
            "requirement_id": rid,
            "scope": scope,
            "curriculum_id": curriculum_id,
            "course_name": name,
            "course_id": official_course_id,
            "course_code": _text(row.get("course_code") or row.get("official_course_code")),
            "official_course_identity": _text(row.get("official_course_identity")),
            "department": department,
            "section": section,
            "course_kind": kind,
            "owner": owner,
            "domain": domain,
            "required_identity_dimensions": tuple(
                key for key, value in (("course_code", official_course_id), ("course_kind", kind), ("department", department), ("section", section)) if value
            ),
            "bucket": spec.bucket,
            "generic": generic,
            "eligible_course_names": eligible_names,
            "accept_any": accept_any,
            "choice_group": _text(row.get("choice_group")),
            "choice_rule": _text(row.get("choice_rule")),
            "waiver": bool(row.get("waiver")),
            "waiver_generates_credits": bool(row.get("waiver_generates_credits")),
            "component_type": component,
            "source": _safe_provenance({**dict(record), **dict(row)}, requirement_id=rid, scope=scope),
        }
        metadata[rid] = meta
        provenance.append(meta["source"])
    quota_specs = _unresolved_threshold_quotas(
        record,
        scope=scope,
        curriculum_id=curriculum_id,
        record_coverage=record_coverage,
        record_evidence=record_evidence,
        # Minor catalogues encode their own aggregate rows (including APC's
        # explicit unnamed quota).  Do not append registry threshold aliases
        # as extra credit consumers; that would double count the same rule.
        existing_generic=scope == "minor" or any(bool(item.get("generic")) for item in metadata.values()),
    )
    for spec in quota_specs:
        specs.append(spec)
        source = _safe_provenance(
            {
                **dict(record),
                "claim": f"{spec.name} {spec.credits_required} 學分；官方可執行課程池尚未建置。",
            },
            requirement_id=spec.requirement_id,
            scope=scope,
        )
        metadata[spec.requirement_id] = {
            "requirement_id": spec.requirement_id,
            "scope": scope,
            "curriculum_id": curriculum_id,
            "course_name": spec.name,
            "course_id": "",
            "course_code": "",
            "official_course_identity": "",
            "department": "",
            "section": "",
            "course_kind": "",
            "owner": spec.owner,
            "domain": spec.domain,
            "required_identity_dimensions": (),
            "bucket": spec.bucket,
            "generic": True,
            "source": source,
        }
        provenance.append(source)
    specs = sorted(specs, key=lambda item: item.requirement_id)
    provenance = sorted(provenance, key=lambda item: (str(item.get("requirement_id", "")), str(item.get("assertion_id", ""))))
    return tuple(specs), metadata, tuple(provenance)


def _curriculum_provenance(record: Mapping[str, Any] | None, *, scope: str) -> tuple[dict[str, Any], ...]:
    """Project each checked-in rule assertion as a safe provenance row."""

    if not isinstance(record, Mapping):
        return ()
    curriculum_id = _text(record.get("curriculum_id"))
    assertions = record.get("source_assertions", record.get("assertions", ()))
    rows: list[dict[str, Any]] = []
    if isinstance(assertions, Sequence) and not isinstance(assertions, (str, bytes, bytearray)):
        for assertion in assertions:
            if not isinstance(assertion, Mapping):
                continue
            merged = {
                **dict(record),
                **dict(assertion),
                "curriculum_id": curriculum_id,
                "version": record.get("version"),
                "admission_cohort": record.get("admission_cohort") or record.get("version"),
            }
            rows.append(_safe_provenance(merged, scope=scope))
    if not rows:
        rows.append(_safe_provenance(record, scope=scope))
    return tuple(sorted(rows, key=lambda item: (str(item.get("assertion_id", item.get("id", ""))), str(item.get("curriculum_id", "")))))


def _compile_attempts(
    rows: Sequence[NormalizedCourseRow],
    metadata: Mapping[str, Mapping[str, Any]],
) -> tuple[tuple[CourseAttempt, ...], dict[str, dict[str, Any]]]:
    curriculum_category_tokens = frozenset(
        {
            "必",
            "必修",
            "系必修",
            "專業必修",
            "核心必修",
            "選",
            "選修",
            "系選修",
            "專業選修",
            "共同必修",
            "共同選修",
            "通識",
            "通識課程",
            "自由學分",
            "自由選修",
            "一般選修",
            "required",
            "required_course",
            "elective",
            "elective_course",
            "general_education",
            "free_elective",
        }
    )

    def kind_token(value: Any) -> str:
        return normalize_course_kind(value)

    def is_curriculum_category(value: Any) -> bool:
        """Recognize category labels without treating them as components.

        Transcript ``type`` fields often carry curriculum placement (for
        example ``系必修`` or ``共同選修``), while the registry's
        ``component_type`` carries lecture/lab semantics.  This allowlist is
        deliberately narrow: an empty or arbitrary value remains UNKNOWN.
        """

        raw = _text(value).strip()
        if not raw:
            return False
        compact = re.sub(r"[\s_\-()/（）]", "", raw).casefold()
        if compact in {
            re.sub(r"[\s_\-()/（）]", "", item).casefold()
            for item in curriculum_category_tokens
        }:
            return True
        return compact.endswith(("必修", "選修", "通識", "自由學分"))

    def row_component(value: Any) -> tuple[str, bool]:
        """Return (component kind, category-only marker) for a transcript row."""

        kind = kind_token(value)
        if kind != UNKNOWN:
            return kind, False
        return "", is_curriculum_category(value)

    catalog_by_code: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for meta in metadata.values():
        if meta.get("generic"):
            continue
        for key in ("course_code", "official_course_identity", "course_id"):
            value = _text(meta.get(key))
            if value:
                catalog_by_code[value].append(meta)
    attempts: list[CourseAttempt] = []
    safe_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_dict = row.as_dict()
        course_code = _text(row.course_code)
        course_name = _text(row.course_name)
        attempt_id = f"attempt:{_digest([course_code, course_name, row.term, str(row.credits), str(row.earned_credits), row.status, row.attempt_group])}"
        label = _course_label(course_name)
        identity = UNKNOWN
        row_kind, row_component_unspecified = row_component(row.course_type)
        code_candidates = catalog_by_code.get(course_code, ()) if course_code else ()
        matching_candidates: list[tuple[Mapping[str, Any], str]] = []
        seen_candidate_objects: set[int] = set()
        for meta in code_candidates:
            candidate_object_id = id(meta)
            if candidate_object_id in seen_candidate_objects:
                continue
            seen_candidate_objects.add(candidate_object_id)
            expected_kind = kind_token(meta.get("course_kind") or meta.get("component_type"))
            if expected_kind == UNKNOWN:
                continue
            if not row_component_unspecified and (row_kind == UNKNOWN or expected_kind != row_kind):
                continue
            required_dimensions = set(meta.get("required_identity_dimensions", ()))
            if "department" in required_dimensions and _text(meta.get("department")) != _text(row.department):
                continue
            # A raw course code does not establish a registry track/section.
            # The checked-in official identity, however, is already scoped by
            # that section; accepting it here does not infer anything from a
            # title or category label.  Other section-aware codes remain
            # unresolved until an adapter supplies section evidence.
            official_identity = _text(meta.get("official_course_identity"))
            if "section" in required_dimensions and course_code != official_identity:
                continue
            if label and _course_label(meta.get("course_name")) != label:
                continue
            matching_candidates.append((meta, expected_kind))
        if len(matching_candidates) == 1:
            identity = VERIFIED
            resolved_kind = matching_candidates[0][1]
        else:
            # Multiple exact candidates (especially candidates with different
            # components) are not safe to resolve by input order.
            resolved_kind = UNKNOWN
        status_map = {
            "COMPLETED": PASS,
            "IN_PROGRESS": "IN_PROGRESS",
            "FAILED": FAIL,
            "WITHDRAWN": FAIL,
            "NOT_TAKEN": "NOT_TAKEN",
            "WAIVED": WAIVER,
            "TRANSFERRED": UNKNOWN,
        }
        status = status_map.get(_text(row.status).upper(), UNKNOWN)
        if row_kind in {"LECTURE", "LAB", "COMBINED"}:
            course_kind = row_kind
        elif identity == VERIFIED and row_component_unspecified:
            course_kind = resolved_kind
        else:
            course_kind = UNKNOWN
        attempt = CourseAttempt(
            attempt_id=attempt_id,
            course_id=course_code or course_name,
            course_name=course_name,
            credits=Decimal(str(row.credits)),
            earned_credits=Decimal(str(row.earned_credits)),
            academic_term=row.term,
            repeat_group_id=row.attempt_group or None,
            identity_status=identity,
            course_kind=course_kind,
            status=status,
            source_kind="CONFIRMED_TRANSCRIPT",
            grade=row.grade,
            grade_evidence_state=VERIFIED if _text(row.grade) else UNKNOWN,
        )
        attempts.append(attempt)
        safe_rows[attempt_id] = {
            key: row_dict[key]
            for key in row_dict
            if key in {"course_code", "course_name", "credits", "earned_credits", "status", "term", "grade", "course_type"}
        }
    attempts.sort(key=lambda item: (item.attempt_id, item.course_id, item.academic_term))
    return tuple(attempts), safe_rows


def _source_attempt_id(value: Any, attempts: Sequence[CourseAttempt]) -> str | None:
    candidate = _text(value)
    if not candidate:
        return None
    for attempt in attempts:
        # A source course title is not a stable identity: two departments can
        # legitimately offer the same title.  Only exact released attempt or
        # course identifiers may be addressed by an opaque binding record.
        if candidate in {attempt.attempt_id, attempt.course_id}:
            return attempt.attempt_id
    return None


def _target_requirement_id(value: Any, requirements: Sequence[RequirementSpec], metadata: Mapping[str, Mapping[str, Any]]) -> str | None:
    candidate = _text(value)
    if not candidate:
        return None
    by_id = {item.requirement_id for item in requirements}
    if candidate in by_id:
        return candidate
    label = _course_label(candidate)
    matches = sorted(
        rid
        for rid, meta in metadata.items()
        if not meta.get("generic") and _course_label(meta.get("course_name")) == label
    )
    return matches[0] if len(matches) == 1 else None


def _binding_projection(binding_id: str, *, state: str = UNKNOWN, reason: str = "") -> dict[str, Any]:
    return {
        "binding_id": binding_id,
        "source_attempt_id": "",
        "target_requirement_id": "",
        "approved_credits": "0",
        "evidence_state": state,
        "authority": "",
        "evidence_reference": "",
        "direction": "",
        "shared": False,
        "decision": "PENDING",
        "allocation_kind": "",
        "source_requirement_id": "",
        "source_owner": "",
        "target_owner": "",
        "source_domain": "",
        "target_domain": "",
        "reason": reason,
    }


def _compile_bindings(
    evidence_ids: Sequence[str],
    *,
    attempts: Sequence[CourseAttempt],
    requirements: Sequence[RequirementSpec],
    metadata: Mapping[str, Mapping[str, Any]],
    evidence_resolver: Callable[[str], Any] | None,
    forbid_shared: bool = False,
) -> tuple[tuple[EquivalencyBinding, ...], tuple[dict[str, Any], ...], tuple[str, ...], tuple[str, ...]]:
    bindings: list[EquivalencyBinding] = []
    projections: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    for binding_id in sorted(set(_text(item) for item in evidence_ids if _text(item))):
        record = None
        if callable(evidence_resolver):
            try:
                record = evidence_resolver(binding_id)
            except Exception:
                record = None
        record_type = _text(record.get("record_type") or record.get("type")).upper() if isinstance(record, Mapping) else ""
        valid = (
            isinstance(record, Mapping)
            and _text(record.get("record_id")) == binding_id
            and record_type in {
                "EQUIVALENCY_RECORD",
                "EQUIVALENCY_BINDING_RECORD",
                "COURSE_EQUIVALENCY_RECORD",
                "CREDIT_TRANSFER_RECORD",
                "SHARED_CREDIT_RECORD",
            }
        )
        if valid:
            # An equivalency record is not approval merely because it has an
            # official-looking type and evidence reference.  The source
            # authority must explicitly issue the APPROVED decision.
            valid = (
                _text(record.get("evidence_state")).upper() == VERIFIED
                and _text(record.get("decision")).upper() == "APPROVED"
            )
        authority = _text(record.get("authority")) if isinstance(record, Mapping) else ""
        reference = _text(record.get("evidence_reference") or record.get("source_reference")) if isinstance(record, Mapping) else ""
        valid = valid and bool(authority) and bool(reference)
        source = _source_attempt_id(
            record.get("source_attempt_id") or record.get("source_course_id") or record.get("source_course_code"),
            attempts,
        ) if isinstance(record, Mapping) else None
        target = _target_requirement_id(
            record.get("target_requirement_id") or record.get("target_course_id") or record.get("target_course_code") or record.get("target_course_name"),
            requirements,
            metadata,
        ) if isinstance(record, Mapping) else None
        if isinstance(record, Mapping):
            # An explicit zero is a real authority decision: never fall back
            # to a legacy ``credits`` alias when ``approved_credits`` is
            # present, or an unresolved record could mint an approved amount.
            amount_value = record["approved_credits"] if "approved_credits" in record else record.get("credits")
            amount = _positive_number(amount_value)
        else:
            amount = Decimal("0")
        if not source or not target or amount <= 0:
            valid = False
        source_requirement_id = _text(record.get("source_requirement_id")) if isinstance(record, Mapping) else ""
        direction = _text(record.get("direction") or record.get("ledger")) if isinstance(record, Mapping) else ""
        source_owner = _text(record.get("source_owner") or record.get("source_role")) if isinstance(record, Mapping) else ""
        target_owner = _text(record.get("target_owner") or record.get("target_role")) if isinstance(record, Mapping) else ""
        source_domain = _text(record.get("source_domain")) if isinstance(record, Mapping) else ""
        target_domain = _text(record.get("target_domain")) if isinstance(record, Mapping) else ""
        allocation_kind = _text(record.get("allocation_kind")) if isinstance(record, Mapping) else ""
        raw_shared = record.get("shared", False) if isinstance(record, Mapping) else False
        shared_input_is_boolean = not isinstance(record, Mapping) or "shared" not in record or raw_shared is True or raw_shared is False
        normalized_direction = direction.upper().replace("-", "_").replace(" ", "_")
        normalized_allocation_kind = allocation_kind.upper().replace("-", "_").replace(" ", "_")
        explicit_shared_marker = normalized_direction in {"PRIMARY_TO_TARGET", "TARGET_TO_PRIMARY"} or normalized_allocation_kind in {SHARED_SHADOW, "SHARED_REUSE"}
        shared = shared_input_is_boolean and (
            raw_shared is True
            or (raw_shared is False and explicit_shared_marker)
        )
        if not shared_input_is_boolean:
            # A malformed shared flag must not be rescued by a truthy
            # direction/kind.  Strip those hints before constructing the
            # binding, so the dataclass cannot accidentally re-enable sharing.
            direction = ""
            allocation_kind = ""
        if shared and forbid_shared:
            # A minor may not project a primary allocation through a shadow
            # ledger.  Preserve the opaque evidence ID as a pending audit row
            # but never hand the binding to the allocator.
            projections.append(_binding_projection(binding_id, reason="輔系不得使用雙主修 shared/shadow credit。"))
            blockers.append("MINOR_SHARED_CREDIT_FORBIDDEN")
            warnings.append("MINOR_SHARED_CREDIT_FORBIDDEN")
            bindings.append(
                EquivalencyBinding(
                    binding_id=binding_id,
                    source_attempt_id="",
                    target_requirement_id="",
                    evidence_state=UNKNOWN,
                    decision="PENDING",
                )
            )
            continue
        if shared:
            # Shared credit is a projection from one exact allocated source
            # requirement.  Never infer source scope, direction, owner or
            # domain from the current compiler metadata.
            source_requirement = next((item for item in requirements if item.requirement_id == source_requirement_id), None)
            target_requirement = next((item for item in requirements if item.requirement_id == target), None)
            explicit_target_id = _text(record.get("target_requirement_id")) if isinstance(record, Mapping) else ""
            expected_source_owner = _text(source_requirement.owner) if source_requirement else ""
            expected_target_owner = _text(target_requirement.owner) if target_requirement else ""
            expected_source_domain = _text(source_requirement.domain) if source_requirement else ""
            expected_target_domain = _text(target_requirement.domain) if target_requirement else ""
            shared = bool(
                valid
                and source_requirement_id
                and source_requirement is not None
                and target_requirement is not None
                and explicit_target_id == target
                and source_requirement_id != target
                and direction in {"PRIMARY_TO_TARGET", "TARGET_TO_PRIMARY"}
                and source_owner
                and target_owner
                and source_domain
                and target_domain
                and source_owner.upper() == expected_source_owner.upper()
                and target_owner.upper() == expected_target_owner.upper()
                and source_domain == expected_source_domain
                and target_domain == expected_target_domain
            )
            if not shared:
                valid = False
        if not valid:
            reason = "equivalency evidence is unresolved or does not match a released attempt/requirement"
            projections.append(_binding_projection(binding_id, reason=reason))
            blockers.append(f"EQUIVALENCY_UNRESOLVED:{binding_id}")
            warnings.append(f"UNVERIFIED_EQUIVALENCY:{binding_id}")
            bindings.append(
                EquivalencyBinding(
                    binding_id=binding_id,
                    source_attempt_id="",
                    target_requirement_id="",
                    evidence_state=UNKNOWN,
                    decision="PENDING",
                )
            )
            continue
        attempt = next(item for item in attempts if item.attempt_id == source)
        binding = EquivalencyBinding(
            binding_id=binding_id,
            source_attempt_id=source,
            target_requirement_id=target,
            approved_credits=amount,
            evidence_state=VERIFIED,
            authority=authority,
            evidence_reference=reference,
            direction=direction,
            shared=shared,
            source_course_id=attempt.course_id,
            target_course_id=_text(record.get("target_course_id") or record.get("target_course_code")),
            source_course_kind=attempt.course_kind,
            allocation_kind=allocation_kind,
            decision=_text(record.get("decision") or "PENDING"),
            scope=_text(record.get("scope")),
            source_requirement_id=source_requirement_id,
            source_owner=source_owner,
            target_owner=target_owner,
            source_domain=source_domain,
            target_domain=target_domain,
        )
        bindings.append(binding)
        projections.append(
            {
                "binding_id": binding.binding_id,
                "source_attempt_id": binding.source_attempt_id,
                "target_requirement_id": binding.target_requirement_id,
                "approved_credits": str(binding.approved_credits),
                "evidence_state": binding.evidence_state,
                "authority": binding.authority,
                "evidence_reference": binding.evidence_reference,
                "direction": binding.direction,
                "shared": binding.shared,
                "decision": binding.decision,
                "allocation_kind": binding.allocation_kind,
                "source_requirement_id": binding.source_requirement_id,
                "source_owner": binding.source_owner,
                "target_owner": binding.target_owner,
                "source_domain": binding.source_domain,
                "target_domain": binding.target_domain,
                "reason": "trusted opaque evidence resolved",
            }
        )
    return tuple(bindings), tuple(sorted(projections, key=lambda item: str(item.get("binding_id", "")))), tuple(blockers), tuple(warnings)


def _requirement_status(allocation: AllocationResult, requirement_ids: Sequence[str]) -> str:
    selected = [item for item in allocation.requirement_results if item.requirement_id in set(requirement_ids) and item.status != NOT_APPLICABLE]
    if not selected:
        return UNKNOWN
    if any(item.status == UNKNOWN for item in selected):
        return UNKNOWN
    if any(item.status == FAIL for item in selected):
        return FAIL
    return PASS


def _with_generic_unknown(allocation: AllocationResult, generic_ids: set[str]) -> AllocationResult:
    if not generic_ids:
        return allocation
    results: list[RequirementResult] = []
    blockers = list(allocation.blockers)
    for item in allocation.requirement_results:
        if item.requirement_id in generic_ids and item.status != NOT_APPLICABLE:
            code = f"REQUIREMENT_CATALOG_PARTIAL:{item.requirement_id}"
            if code not in blockers:
                blockers.append(code)
            results.append(replace(item, status=UNKNOWN, blockers=tuple(dict.fromkeys((*item.blockers, code)))))
        else:
            results.append(item)
    status = UNKNOWN if allocation.status == PASS else allocation.status
    return replace(allocation, requirement_results=tuple(results), status=status, pass_eligible=False, blockers=tuple(blockers))


def _combine_status(*statuses: str) -> str:
    statuses = tuple(status for status in statuses if status not in {NOT_APPLICABLE, ""})
    if FAIL in statuses:
        return FAIL
    if UNKNOWN in statuses:
        return UNKNOWN
    return PASS if statuses else UNKNOWN


def _safe_status(value: Any) -> str:
    normalized = _text(value).upper()
    return normalized if normalized in {PASS, FAIL, UNKNOWN, NOT_APPLICABLE} else UNKNOWN


def _self_report_status(value: Any) -> str:
    """Project a user claim for display without treating it as evidence."""
    # Keep this helper fail-closed even if a future caller reuses it.  The
    # human-readable claim belongs in ``claimed_state`` and can never become
    # an official PASS/FAIL decision without scoped registrar evidence.
    _ = value
    return UNKNOWN


def _self_report_claimed_state(value: Any) -> str:
    """Return a localized claim label that can never look like an official gate."""

    text = _text(value)
    if not text:
        return "使用者未提供申請狀態自述"
    normalized = text.upper().replace(" ", "")
    if any(token in normalized for token in ("REJECT", "DENY", "未核准", "未取得", "否")):
        return "使用者自述：未核准／未取得"
    if any(token in normalized for token in ("PASS", "APPROV", "已申請", "已核准", "已取得", "QUALIFIED", "GRANTED")):
        return "使用者自述：已申請／已核准"
    return f"使用者自述：{text}"


def _minor_coursework_blockers(
    target: Mapping[str, Any] | None,
    attempts: Sequence[CourseAttempt],
    allocation: AllocationResult,
) -> tuple[str, ...]:
    """Return only source-backed minor gates that allocation cannot encode."""

    if not isinstance(target, Mapping):
        return ()
    blockers: list[str] = []
    if bool(target.get("zero_credit_gate")):
        blockers.append("MINOR_ZERO_CREDIT_GATE_MANUAL_REVIEW")
    conflicted_names = {
        _course_label(item)
        for item in target.get("conflicted_course_names", ())
        if _course_label(item)
    }
    attempts_by_id = {attempt.attempt_id: attempt for attempt in attempts}
    conflict_used = any(
        _course_label(attempts_by_id.get(item.attempt_id).course_name) in conflicted_names
        and item.allocation_kind == "EXCLUSIVE"
        and _positive_number(item.credits) > 0
        for allocation_item in allocation.allocations
        for item in allocation_item.portions
        if attempts_by_id.get(item.attempt_id) is not None
    )
    if conflicted_names and conflict_used:
        blockers.append("MINOR_SOURCE_CONFLICT_USED")
    return tuple(dict.fromkeys(blockers))


def _statistics(
    attempts: Sequence[CourseAttempt],
    requirements: Sequence[RequirementSpec],
    allocation: AllocationResult,
    *,
    decisions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return build_statistics_v2(attempts, requirements, allocation, decisions=decisions)


def _evidence_projection(
    request: EvaluationRequest,
    *,
    rule_resolution: Mapping[str, Any],
    application: Mapping[str, Any] | None,
    bindings: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for item in request.official_evidence_ids:
        result.append({"evidence_id": item, "kind": "official", "resolution_state": "UNRESOLVED"})
    for evidence_field in _EVIDENCE_FIELDS:
        item = _text(getattr(request, evidence_field))
        if item:
            result.append({"evidence_id": item, "kind": evidence_field.removesuffix("_evidence_id"), "resolution_state": "UNRESOLVED"})
    for item in request.equivalency_evidence_ids:
        result.append({"evidence_id": item, "kind": "equivalency", "resolution_state": "RESOLVED" if any(binding.get("binding_id") == item and binding.get("evidence_state") == VERIFIED for binding in bindings) else "UNRESOLVED"})
    target_dimension = rule_resolution.get("dimensions", {}).get("target_curriculum_version", {}) if isinstance(rule_resolution.get("dimensions"), Mapping) else {}
    target_evidence = _text(target_dimension.get("evidence_reference"))
    if target_evidence:
        result.append({"evidence_id": target_evidence, "kind": "target_applicability", "resolution_state": "RESOLVED" if target_dimension.get("status") == "RESOLVED" else "UNRESOLVED"})
    if isinstance(application, Mapping):
        for item in application.get("evidence_ids", ()):
            evidence_id = _text(item)
            if evidence_id:
                result.append({"evidence_id": evidence_id, "kind": "application", "resolution_state": "RESOLVED"})
    unique = {(item["evidence_id"], item["kind"]): item for item in result}
    return tuple(unique[key] for key in sorted(unique))


def evaluate(
    request: EvaluationRequest,
    *,
    evidence_resolver: Callable[[str], Any] | None = None,
) -> DecisionSnapshot:
    """Evaluate one confirmed request and return the sole canonical snapshot."""

    if not isinstance(request, EvaluationRequest):
        raise TypeError("evaluate expects an EvaluationRequest")

    released_rows = _released_rows(request)
    input_state = request.confirmation_state
    input_blockers: list[str] = []
    if not released_rows and request.confirmed_course_rows:
        input_blockers.append("INPUT_CONFIRMATION_REQUIRED")
        input_state = "STALE" if request.transcript_confirmed and request.confirmation_state == ConfirmationState.CONFIRMED.value else input_state
    elif not request.transcript_confirmed or request.confirmation_state != ConfirmationState.CONFIRMED.value:
        input_blockers.append("INPUT_CONFIRMATION_REQUIRED")
    input_confirmation = {
        "state": input_state,
        "transcript_confirmed": request.transcript_confirmed,
        "fingerprint": request.confirmed_course_fingerprint,
        "confirmed_fingerprint": request.confirmed_course_fingerprint
        if released_rows or (not request.confirmed_course_rows and input_state == ConfirmationState.CONFIRMED.value)
        else None,
        "row_count": len(request.confirmed_course_rows),
        "released_row_count": len(released_rows),
        "cardinality_consistent": len(released_rows) <= len(request.confirmed_course_rows),
        "release_allowed": bool(
            released_rows
            or (
                request.transcript_confirmed
                and not request.confirmed_course_rows
                and request.confirmation_state == ConfirmationState.CONFIRMED.value
            )
        ),
    }

    primary: Mapping[str, Any] | None = None
    target: Mapping[str, Any] | None = None
    registry_blockers: list[str] = []
    try:
        if request.primary_curriculum_id:
            primary = get_curriculum(request.primary_curriculum_id)
        else:
            registry_blockers.append("PRIMARY_CURRICULUM_MISSING")
    except (KeyError, TypeError, ValueError):
        registry_blockers.append("PRIMARY_CURRICULUM_UNRESOLVED")
    secondary_kind = _secondary_kind(request.secondary_kind, request.program_type)
    is_minor = secondary_kind == "minor"
    is_double = secondary_kind == "double_major"
    target_candidate = request.target_version
    target_prefixes = ("minor:",) if is_minor else ("target:",) if is_double else ()
    if target_candidate and target_prefixes and target_candidate.startswith(target_prefixes):
        try:
            target = get_curriculum(target_candidate)
        except (KeyError, TypeError, ValueError):
            registry_blockers.append("TARGET_CURRICULUM_UNRESOLVED")
    context_request = _context_request(request, primary, target)
    try:
        raw_rule_resolution = resolve_rule_context(context_request, evidence_resolver=evidence_resolver)
    except Exception:
        raw_rule_resolution = {"status": UNKNOWN, "state": UNKNOWN, "can_pass": False, "blocker_codes": ["RULE_CONTEXT_UNRESOLVED"], "blockers": []}
    rule_resolution = _safe_rule_resolution(raw_rule_resolution)
    primary_from_context = raw_rule_resolution.get("primary_curriculum") if isinstance(raw_rule_resolution, Mapping) else None
    target_from_context = raw_rule_resolution.get("target_curriculum") if isinstance(raw_rule_resolution, Mapping) else None
    if isinstance(primary_from_context, Mapping):
        primary = primary_from_context
    if isinstance(target_from_context, Mapping):
        target = target_from_context
    if primary is None:
        registry_blockers.append("PRIMARY_CURRICULUM_UNRESOLVED")
    primary_specs, primary_meta, primary_provenance = _compile_requirements(primary, scope="primary")
    target_scope = "minor" if is_minor else "target"
    target_specs, target_meta, target_provenance = _compile_requirements(target, scope=target_scope) if (is_minor or is_double) else ((), {}, ())
    requirements = tuple(sorted((*primary_specs, *target_specs), key=lambda item: item.requirement_id))
    metadata = {**primary_meta, **target_meta}
    provenance = tuple(
        sorted(
            (
                *primary_provenance,
                *target_provenance,
                *_curriculum_provenance(primary, scope="primary"),
                *_curriculum_provenance(target, scope=target_scope),
            ),
            key=lambda item: (
                str(item.get("requirement_id", "")),
                str(item.get("assertion_id", item.get("id", ""))),
                str(item.get("scope", "")),
            ),
        )
    )
    attempts, _safe_rows = _compile_attempts(released_rows, metadata)
    binding_values = request.equivalency_evidence_ids
    bindings, binding_projections, binding_blockers, binding_warnings = _compile_bindings(
        binding_values,
        attempts=attempts,
        requirements=requirements,
        metadata=metadata,
        evidence_resolver=evidence_resolver,
        forbid_shared=is_minor,
    )
    minor_shared_blockers: list[str] = []
    if is_minor and any(binding.shared for binding in bindings):
        # A minor has no shared/shadow-credit path.  Keep the evidence row for
        # audit, but remove it from the allocator rather than letting a
        # malformed cross-curriculum binding create credit from nowhere.
        minor_shared_blockers.append("MINOR_SHARED_CREDIT_FORBIDDEN")
        binding_warnings = (*binding_warnings, "MINOR_SHARED_CREDIT_FORBIDDEN")
        bindings = tuple(binding for binding in bindings if not binding.shared)
        binding_projections = tuple(
            {
                **dict(item),
                "decision": "PENDING",
                "shared": False,
                "reason": "輔系不得使用雙主修 shared/shadow credit。",
            }
            if item.get("shared")
            else item
            for item in binding_projections
        )
    allocation = allocate_credits(attempts, requirements, bindings, search_limit=request.search_limit)
    generic_ids = {rid for rid, meta in metadata.items() if bool(meta.get("generic"))}
    allocation = _with_generic_unknown(allocation, generic_ids)

    application: Mapping[str, Any] | None = None
    formal_award: Mapping[str, Any] | None = None
    if is_double:
        app_request = {
            "application_term": request.resolved_application_term,
            "target_program": request.target_program or (target or {}).get("program_slug"),
            "target_track": request.target_track or (target or {}).get("track_slug"),
            "admission_cohort": request.admission_cohort,
            "application_status": request.application_status,
            "school_approval_status": request.school_approval_status,
            "formal_qualification_status": request.formal_qualification_status,
            "subject_ref": request.subject_ref,
        }
        try:
            application = resolve_application_case(
                app_request,
                notice_records=request.notice_evidence_ids or None,
                rule_applicability=request.rule_applicability_evidence_id,
                department_decision=request.department_decision_evidence_id,
                registrar_registration=request.registrar_registration_evidence_id,
                formal_qualification=request.formal_qualification_evidence_id,
                subject_ref=request.subject_ref,
                as_of=request.as_of,
                evidence_resolver=evidence_resolver,
            )
        except Exception:
            application = {"status": UNKNOWN, "state": UNKNOWN, "can_pass": False, "blockers": [{"code": "APPLICATION_RESOLUTION_UNKNOWN", "reason": "官方申請證據無法解析。"}]}
        try:
            formal_award = resolve_formal_award(
                request.formal_award_evidence_id,
                evidence_resolver=evidence_resolver,
                target_program=request.target_program or (target or {}).get("program_slug"),
                target_track=request.target_track or (target or {}).get("track_slug"),
                subject_ref=request.subject_ref,
            )
        except Exception:
            formal_award = {"status": UNKNOWN, "state": UNKNOWN, "award_state": UNKNOWN, "is_official": False}
    elif is_minor:
        minor_app_request = {
            "application_term": request.resolved_application_term,
            "target_program": request.target_program or (target or {}).get("program_slug"),
            "target_track": request.target_track or (target or {}).get("track_slug"),
            "application_status": request.application_status,
            "subject_ref": request.subject_ref,
        }
        try:
            application = resolve_minor_application_case(
                minor_app_request,
                department_approval=request.department_decision_evidence_id,
                registrar_registration=request.registrar_registration_evidence_id,
                formal_qualification=request.formal_qualification_evidence_id,
                evidence_resolver=evidence_resolver,
            )
        except Exception:
            application = {
                "status": UNKNOWN,
                "state": UNKNOWN,
                "can_pass": False,
                "blockers": [{"code": "MINOR_APPLICATION_RESOLUTION_UNKNOWN", "reason": "官方輔系申請證據無法解析。"}],
            }
        try:
            formal_award = resolve_minor_award(
                request.formal_award_evidence_id,
                evidence_resolver=evidence_resolver,
                target_program=request.target_program or (target or {}).get("program_slug"),
                target_track=request.target_track or (target or {}).get("track_slug"),
                subject_ref=request.subject_ref,
                application_term=request.resolved_application_term,
            )
        except Exception:
            formal_award = {"status": UNKNOWN, "state": UNKNOWN, "award_state": UNKNOWN, "is_official": False}

    safe_application = _safe_application(application)
    safe_formal_award = _safe_gate(formal_award) if formal_award is not None else {"status": NOT_APPLICABLE, "state": NOT_APPLICABLE, "award_state": NOT_APPLICABLE, "is_official": False}
    rule_status = _text(raw_rule_resolution.get("status")) if isinstance(raw_rule_resolution, Mapping) else UNKNOWN
    primary_dimension = raw_rule_resolution.get("dimensions", {}).get("primary_curriculum", {}) if isinstance(raw_rule_resolution.get("dimensions"), Mapping) else {}
    target_dimension = raw_rule_resolution.get("dimensions", {}).get("target_curriculum_version", {}) if isinstance(raw_rule_resolution.get("dimensions"), Mapping) else {}
    primary_status = _requirement_status(allocation, [item.requirement_id for item in primary_specs])
    target_status = _requirement_status(allocation, [item.requirement_id for item in target_specs]) if target_specs else UNKNOWN
    allocation_uncertain = allocation.search_exhausted or allocation.allocation_ambiguous
    if not released_rows or input_blockers or registry_blockers or rule_status in {UNKNOWN, MISSING, MANUAL_REVIEW, CONFLICTED} or primary_dimension.get("status") != "RESOLVED":
        primary_status = UNKNOWN
    elif allocation_uncertain:
        primary_status = UNKNOWN
    primary_decision = {
        "status": primary_status,
        "state": primary_status,
        "can_pass": primary_status == PASS,
        "allocation_status": allocation.status,
        "requirement_ids": tuple(item.requirement_id for item in primary_specs),
        "reason": "主修課表、確認輸入與全域配置均可安全判定。" if primary_status == PASS else "主修規則、課程池、輸入確認或配置結果仍有未決條件。",
    }
    application_self_report = {
        # A self-report is deliberately never a PASS/FAIL decision.  Keep
        # the claimed state separately so a UI can explain what the user
        # entered without rendering it as an official approval badge.
        "status": UNKNOWN,
        "state": UNKNOWN,
        "authoritative": False,
        "value": request.application_status,
        "claimed_state": _self_report_claimed_state(request.application_status),
        "reason": "這是使用者自述，不能升級任何官方資格或授予 gate。",
    }
    minor_application: dict[str, Any] = {
        "status": NOT_APPLICABLE,
        "state": NOT_APPLICABLE,
        "can_pass": False,
        "self_report": application_self_report,
        "reason": "目前規劃不是輔系。",
    }
    minor_decision: dict[str, Any] = {
        "status": NOT_APPLICABLE,
        "state": NOT_APPLICABLE,
        "can_pass": False,
        "reason": "目前規劃不是輔系。",
    }
    formal_minor_award: dict[str, Any] = {
        "status": NOT_APPLICABLE,
        "state": NOT_APPLICABLE,
        "can_pass": False,
        "award_state": NOT_APPLICABLE,
        "reason": "目前規劃不是輔系。",
    }
    if not (is_double or is_minor):
        double_decision: dict[str, Any] = {"status": NOT_APPLICABLE, "state": NOT_APPLICABLE, "can_pass": False, "reason": "目前規劃不是雙主修。"}
        formal_decision: dict[str, Any] = {"status": NOT_APPLICABLE, "state": NOT_APPLICABLE, "can_pass": False, "award_state": NOT_APPLICABLE, "reason": "目前規劃不是雙主修。"}
        department_approval = {"status": NOT_APPLICABLE, "state": NOT_APPLICABLE, "can_pass": False, "authoritative": True}
        registrar_registration = {"status": NOT_APPLICABLE, "state": NOT_APPLICABLE, "can_pass": False, "authoritative": True}
        formal_qualification = {"status": NOT_APPLICABLE, "state": NOT_APPLICABLE, "can_pass": False, "authoritative": True}
        target_coursework = {"status": NOT_APPLICABLE, "state": NOT_APPLICABLE, "can_pass": False}
        award_eligibility = {"status": NOT_APPLICABLE, "state": NOT_APPLICABLE, "can_pass": False}
    elif is_minor:
        minor_rule_blockers = _minor_coursework_blockers(target, attempts, allocation)
        if (
            target_dimension.get("status") != "RESOLVED"
            or allocation_uncertain
            or input_blockers
            or minor_rule_blockers
        ):
            target_status = UNKNOWN
        app_status = _safe_status(safe_application.get("status"))
        department_status = _safe_status(safe_application.get("department_decision", {}).get("status"))
        registrar_status = _safe_status(safe_application.get("registration", {}).get("status"))
        qualification_status = _safe_status(safe_application.get("formal_qualification", {}).get("status"))
        department_approval = {
            **safe_application.get("department_decision", {}),
            "status": department_status,
            "state": department_status,
            "can_pass": department_status == PASS,
            "authoritative": True,
        }
        registrar_registration = {
            **safe_application.get("registration", {}),
            "status": registrar_status,
            "state": registrar_status,
            "can_pass": registrar_status == PASS,
            "authoritative": True,
        }
        formal_qualification = {
            **safe_application.get("formal_qualification", {}),
            "status": qualification_status,
            "state": qualification_status,
            "can_pass": qualification_status == PASS and safe_application.get("formal_qualification", {}).get("is_official") is True,
            "authoritative": True,
        }
        # ``minor_application_or_qualification`` only requires the official
        # department approval + registrar registration chain.  A self-report
        # and coursework completion are kept as independent dimensions.
        minor_application = {
            "status": _combine_status(department_status, registrar_status),
            "state": _combine_status(department_status, registrar_status),
            "can_pass": department_status == PASS and registrar_status == PASS,
            "self_report": application_self_report,
            "application": safe_application,
            "department_approval": department_approval,
            "registrar_registration": registrar_registration,
            "formal_qualification": formal_qualification,
            "requirement": "系所正式核准 + 教務處正式登錄；自述不具核准效力。",
            "reason": "系所核准與教務登錄均已核實。" if department_status == PASS and registrar_status == PASS else "輔系申請／正式修讀資格仍缺官方核准鏈。",
        }
        if minor_rule_blockers:
            minor_application["blockers"] = tuple(minor_rule_blockers)
        target_coursework = {
            "status": target_status,
            "state": target_status,
            "can_pass": target_status == PASS,
            "requirement_ids": tuple(item.requirement_id for item in target_specs),
            "blockers": tuple(minor_rule_blockers),
            "reason": "輔系目標課程配置可安全判定。" if target_status == PASS else "輔系課表、課程配置或年度 gate 仍需確認。",
        }
        award_eligibility_status = _combine_status(minor_application["status"], target_status)
        award_eligibility = {
            "status": award_eligibility_status,
            "state": award_eligibility_status,
            "can_pass": award_eligibility_status == PASS,
            "requires": ("minor_application_or_qualification", "minor_coursework_completion"),
            "reason": "輔系官方修讀資格與課程均已核實。" if award_eligibility_status == PASS else "輔系官方修讀資格或課程仍未全部核實。",
        }
        minor_decision_status = _combine_status(minor_application["status"], target_status)
        double_decision = {
            "status": NOT_APPLICABLE,
            "state": NOT_APPLICABLE,
            "can_pass": False,
            "reason": "目前規劃是輔系，雙主修決策不適用。",
        }
        formal_decision = {
            "status": NOT_APPLICABLE,
            "state": NOT_APPLICABLE,
            "can_pass": False,
            "award_state": NOT_APPLICABLE,
            "reason": "目前規劃是輔系，正式雙主修授予不適用。",
        }
        minor_decision = {
            "status": minor_decision_status,
            "state": minor_decision_status,
            "can_pass": minor_decision_status == PASS,
            "coursework_status": target_status,
            "application": minor_application,
            "requirement_ids": tuple(item.requirement_id for item in target_specs),
            "reason": "輔系課程與正式修讀資格均已核實。" if minor_decision_status == PASS else "輔系課程、年度規則或官方修讀資格仍需確認。",
        }
        formal_minor_status = _safe_status(safe_formal_award.get("status"))
        formal_minor_award = {
            "status": formal_minor_status,
            "state": formal_minor_status,
            "can_pass": formal_minor_status == PASS and safe_formal_award.get("is_official") is True,
            "award_state": safe_formal_award.get("award_state", UNKNOWN),
            "formal_award": safe_formal_award,
            "reason": "官方正式授予輔系紀錄已核實。" if formal_minor_status == PASS else "正式授予輔系需要獨立的教務處官方紀錄。",
        }
    else:
        if target_dimension.get("status") != "RESOLVED" or rule_status in {UNKNOWN, MISSING, MANUAL_REVIEW, CONFLICTED} or allocation_uncertain or input_blockers:
            target_status = UNKNOWN
        app_status = _safe_status(safe_application.get("status"))
        department_status = _safe_status(safe_application.get("department_decision", {}).get("status"))
        registrar_status = _safe_status(safe_application.get("registration", {}).get("status"))
        qualification_status = _safe_status(safe_application.get("formal_qualification", {}).get("status"))
        department_approval = {
            **safe_application.get("department_decision", {}),
            "status": department_status,
            "state": department_status,
            "can_pass": department_status == PASS,
            "authoritative": True,
        }
        registrar_registration = {
            **safe_application.get("registration", {}),
            "status": registrar_status,
            "state": registrar_status,
            "can_pass": registrar_status == PASS,
            "authoritative": True,
        }
        formal_qualification = {
            **safe_application.get("formal_qualification", {}),
            "status": qualification_status,
            "state": qualification_status,
            "can_pass": qualification_status == PASS and safe_application.get("formal_qualification", {}).get("is_official") is True,
            "authoritative": True,
        }
        target_coursework = {
            "status": target_status,
            "state": target_status,
            "can_pass": target_status == PASS,
            "requirement_ids": tuple(item.requirement_id for item in target_specs),
            "reason": "雙主修目標課程配置可安全判定。" if target_status == PASS else "雙主修目標課表或課程配置仍需確認。",
        }
        eligibility_status = _combine_status(qualification_status, target_status, department_status, registrar_status)
        award_eligibility = {
            "status": eligibility_status,
            "state": eligibility_status,
            "can_pass": eligibility_status == PASS,
            "requires": ("formal_qualification", "target_coursework_completion", "department_approval", "registrar_registration"),
            "reason": "正式資格、目標課程與官方登錄 gate 均已核實。" if eligibility_status == PASS else "正式資格、目標課程或官方登錄 gate 尚未全部核實。",
        }
        double_status = _combine_status(target_status, app_status)
        double_decision = {
            "status": double_status,
            "state": double_status,
            "can_pass": double_status == PASS,
            "coursework_status": target_status,
            "application": safe_application,
            "requirement_ids": tuple(item.requirement_id for item in target_specs),
            "reason": "雙主修目標課表、課程配置與官方申請 gates 均已核實。" if double_status == PASS else "雙主修課表版本、申請核准或課程配置仍需確認。",
        }
        formal_status = _safe_status(safe_formal_award.get("status"))
        formal_decision = {
            "status": formal_status,
            "state": formal_status,
            "can_pass": formal_status == PASS and safe_formal_award.get("is_official") is True,
            "award_state": safe_formal_award.get("award_state", UNKNOWN),
            "formal_award": safe_formal_award,
            "reason": "官方正式授予紀錄已核實。" if formal_status == PASS else "正式授予雙主修需要獨立的教務處官方紀錄。",
        }
    secondary_decision = minor_decision if is_minor else double_decision
    overall_status = _combine_status(primary_status, secondary_decision["status"])
    if input_blockers or registry_blockers or binding_blockers or minor_shared_blockers or allocation_uncertain:
        overall_status = UNKNOWN
    decisions = {
        "primary_graduation": primary_decision,
        "double_major_qualification": double_decision,
        "formal_double_major_award": formal_decision,
        "application_self_report": application_self_report,
        "department_approval": department_approval,
        "registrar_registration": registrar_registration,
        "formal_qualification": formal_qualification,
        "target_coursework_completion": target_coursework,
        "minor_application_or_qualification": minor_application,
        "minor_coursework_completion": target_coursework if is_minor else {"status": NOT_APPLICABLE, "state": NOT_APPLICABLE, "can_pass": False, "reason": "目前規劃不是輔系。"},
        "formal_minor_award": formal_minor_award,
        "award_eligibility": award_eligibility,
        "formal_award": formal_minor_award if is_minor else formal_decision,
        "overall": {
            "status": overall_status,
            "state": overall_status,
            "can_pass": overall_status == PASS,
            "reason": "所有適用決策均可安全判定。" if overall_status == PASS else "至少一項必要規則、輸入、配置或官方證據尚未安全判定。",
        },
    }
    context_blockers = []
    for code in raw_rule_resolution.get("blocker_codes", ()) if isinstance(raw_rule_resolution, Mapping) else ():
        code_text = _text(code)
        if code_text:
            context_blockers.append(f"RULE_CONTEXT:{code_text}")
    blockers = tuple(dict.fromkeys((*input_blockers, *registry_blockers, *context_blockers, *binding_blockers, *minor_shared_blockers, *(f"APPLICATION:{item.get('code') or item.get('status')}" for item in safe_application.get("blockers", ()) if isinstance(item, Mapping) and (item.get("code") or item.get("status"))), *allocation.blockers)))
    warnings = tuple(
        dict.fromkeys(
            (
                *request.input_warning_codes,
                *binding_warnings,
                *(_text(item) for item in raw_rule_resolution.get("warnings", ()) if _text(item)),
                *allocation.warnings,
            )
        )
    )
    statistics = _statistics(attempts, requirements, allocation, decisions=decisions)
    input_request = request.as_dict()
    safe_request = dict(input_request)
    # Request rows are already normalized, but they are available in the
    # allocation attempts as the canonical course view.  Keep the request
    # projection small enough for exports and exclude any caller extensions.
    safe_request["confirmed_course_rows"] = tuple(
        {
            key: item[key]
            for key in item
            if key in {"course_code", "course_name", "credits", "earned_credits", "status", "term", "grade", "course_type"}
        }
        for item in input_request.get("confirmed_course_rows", ())
        if isinstance(item, Mapping)
    )
    curriculum = {
        "primary": _safe_curriculum(primary),
        "target": _safe_curriculum(target),
    }
    safe_rule_provenance = tuple(provenance)
    evidence = _evidence_projection(request, rule_resolution=raw_rule_resolution, application=application, bindings=binding_projections)
    remediation = tuple(statistics.get("safe_remediation_directions", ()))
    initial = DecisionSnapshot(
        snapshot_id="",
        evaluated_at=request.as_of or "UNSPECIFIED",
        request=_freeze(safe_request),
        attempts=attempts,
        requirements=requirements,
        bindings=tuple(binding_projections),
        curriculum=_freeze(curriculum),
        rule_resolution=_freeze(rule_resolution),
        evidence=tuple(_freeze(item) for item in evidence),
        allocation=allocation,
        verdict=overall_status,
        blockers=blockers,
        warnings=warnings,
        schema_version=SERVICE_SCHEMA_VERSION,
        engine_version=ENGINE_VERSION,
        decisions=_freeze(decisions),
        rule_provenance=tuple(_freeze(item) for item in safe_rule_provenance),
        input_confirmation=_freeze(input_confirmation),
        search_complete=not allocation.search_exhausted,
        optimality="NON_UNIQUE" if allocation.allocation_ambiguous else "BOUNDED_NOT_COMPLETE" if allocation.search_exhausted else "OPTIMAL",
        allocation_ambiguous=allocation.allocation_ambiguous,
        alternatives=allocation.alternative_allocations,
        statistics=_freeze(statistics),
        remediation_suggestions=remediation,
    )
    canonical = _plain(initial.as_dict())
    canonical.pop("snapshot_id", None)
    snapshot_id = f"snapshot:{_digest(canonical)}"
    return replace(initial, snapshot_id=snapshot_id)


__all__ = [
    "ENGINE_VERSION",
    "SERVICE_SCHEMA_VERSION",
    "INPUT_WARNING_CODES",
    "EvaluationRequest",
    "evaluate",
]
