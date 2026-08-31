"""Auditable source-attempt to target-requirement bindings.

The graduation engine can classify an exact course identity, but a course
which merely *may* be accepted by another department needs a different model.
This module deliberately keeps that decision explicit:

``source attempt -> target requirement -> decision -> authority/evidence``

Suggestions are never credit.  Only an ``approved`` decision with both an
authority and an evidence reference can create a target allocation.  The
result is session-friendly plain dictionaries so it can be serialized by the
existing audit exporters without adding persistence or a database.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import secrets
from typing import Any, Iterable, Mapping

from handbook_rules import get_apc_target_requirements, normalize_course_name


PROPOSED = "proposed"
PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
INVALID = "invalid"
AMBIGUOUS = "ambiguous"
DECISION_STATES = (PROPOSED, PENDING, APPROVED, REJECTED)
NON_COUNTING_STATES = {PROPOSED, PENDING, REJECTED, INVALID, AMBIGUOUS}

EQUIVALENCY_SATISFIED = "SATISFIED"
EQUIVALENCY_UNKNOWN = "UNKNOWN"
EQUIVALENCY_NOT_APPLICABLE = "NOT_APPLICABLE"

# Validation codes are intentionally stable strings.  They are shown in the
# UI and exported so a later manual review can explain exactly why a row did or
# did not affect the plan.
VALIDATION_OK = "OK"
DECISION_NOT_APPROVED = "DECISION_NOT_APPROVED"
INVALID_DECISION_STATE = "INVALID_DECISION_STATE"
SOURCE_REQUIRED = "SOURCE_REQUIRED"
TARGET_REQUIRED = "TARGET_REQUIRED"
SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
SOURCE_AMBIGUOUS = "SOURCE_AMBIGUOUS"
TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
COHORT_MISMATCH = "COHORT_MISMATCH"
TARGET_CONTEXT_MISMATCH = "TARGET_CONTEXT_MISMATCH"
AUTHORITY_REQUIRED = "AUTHORITY_REQUIRED"
EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
SOURCE_NOT_COMPLETED = "SOURCE_NOT_COMPLETED"
SOURCE_CREDIT_EXCEEDS_COMPLETED = "SOURCE_CREDIT_EXCEEDS_COMPLETED"
APPROVED_CREDIT_REQUIRED = "APPROVED_CREDIT_REQUIRED"
TARGET_OVERFILLED = "TARGET_OVERFILLED"
SOURCE_ALREADY_BOUND = "SOURCE_ALREADY_BOUND"
TARGET_ALREADY_BOUND = "TARGET_ALREADY_BOUND"
SHARED_LIMIT_EXCEEDED = "SHARED_LIMIT_EXCEEDED"
LAB_NOT_SPLIT = "LAB_NOT_SPLIT"
NON_PRIMARY_RECLASSIFICATION_UNSAFE = "NON_PRIMARY_RECLASSIFICATION_UNSAFE"
LEGACY_UNBOUND = "LEGACY_UNBOUND"
NO_TARGET_COURSE = "NO_TARGET_COURSE"
APPLY_PROVENANCE_REQUIRED = "APPLY_PROVENANCE_REQUIRED"
APPLY_SCOPE_MISMATCH = "APPLY_SCOPE_MISMATCH"
APPLY_SOURCE_INVALID = "APPLY_SOURCE_INVALID"
APPLY_TARGET_INVALID = "APPLY_TARGET_INVALID"
EXCLUSIVE_APPLY_UNSUPPORTED = "EXCLUSIVE_APPLY_UNSUPPORTED"

# ``shared_credits`` is the name used by the current UI, while older saved
# configs used several aggregate-only spellings.  Keep accepting them as
# compatibility input, but never treat one of these values as a course
# binding.  A positive value is surfaced as ``legacy_unbound`` below.
_LEGACY_AGGREGATE_KEYS = (
    "shared_credits",
    "shared_course_credits",
    "shared_reuse_credits",
    "shared_reuse",
    "shared_allowance",
)

_STATE_ALIASES = {
    "建議": PROPOSED,
    "候選": PROPOSED,
    "proposed": PROPOSED,
    "待審": PENDING,
    "待確認": PENDING,
    "pending": PENDING,
    "已核准": APPROVED,
    "核准": APPROVED,
    "approved": APPROVED,
    "拒絕": REJECTED,
    "不採認": REJECTED,
    "rejected": REJECTED,
    "invalid": INVALID,
    "無效": INVALID,
    "ambiguous": AMBIGUOUS,
    "不明確": AMBIGUOUS,
}

_COMBINED_PHYSICS_NAMES = {
    "普通物理(含實驗)",
    "普通物理學(含實驗)",
    "普物",
    "普通物理",
    "普通物理學",
}
_COMBINED_CHEMISTRY_NAMES = {
    "普通化學(含實驗)",
    "普通化學學(含實驗)",  # Keep an observed typo explicit, never fuzzy.
    "普化",
    "普通化學",
}
_CALCULUS_UNNUMBERED_NAMES = {"微積分"}
_CALCULUS_ONE_NAMES = {"微積分(I)", "微積分I", "微積分(一)"}
_CALCULUS_TWO_NAMES = {"微積分(II)", "微積分II", "微積分(二)"}

# Audits are intentionally in-memory products.  The opaque token prevents a
# caller from hand-building a superficially complete ``approved_mappings``
# list and passing it to the public apply boundary.  A digest is stored with
# each token as well, so mutating a genuine audit after validation invalidates
# the provenance.  The token is removed from report/export copies below.
_VALIDATION_SEALS: dict[str, str] = {}
_MAX_VALIDATION_SEALS = 1024


def _audit_digest(audit: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in audit.items() if key != "_validation_seal"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _issue_validation_seal(audit: Mapping[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    _VALIDATION_SEALS[token] = _audit_digest(audit)
    while len(_VALIDATION_SEALS) > _MAX_VALIDATION_SEALS:
        _VALIDATION_SEALS.pop(next(iter(_VALIDATION_SEALS)))
    return token


def _has_valid_validation_seal(audit: Mapping[str, Any] | None) -> bool:
    if not isinstance(audit, Mapping):
        return False
    token = audit.get("_validation_seal")
    return isinstance(token, str) and _VALIDATION_SEALS.get(token) == _audit_digest(audit)


def _seal_audit(result: dict[str, Any]) -> dict[str, Any]:
    result["_validation_seal"] = _issue_validation_seal(result)
    return result


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_decision_state(value: Any) -> str:
    text = str(value or "").strip()
    return _STATE_ALIASES.get(text.lower(), _STATE_ALIASES.get(text, INVALID))


def source_attempt_id(course: Mapping[str, Any] | None = None) -> str:
    """Return the same deterministic attempt key used by ``credit_engine``."""

    course = course or {}
    existing = str(course.get("attempt_id") or course.get("source_attempt_id") or "").strip()
    if existing:
        return existing
    name = normalize_course_name(course.get("name") or course.get("raw_name") or "")
    total = _number(course.get("total_credit"), 0.0) or 0.0
    values = (
        name,
        round(total, 6),
        str(course.get("academic_year") or ""),
        str(course.get("semester") or ""),
        str(course.get("sem1_credit") or ""),
        str(course.get("sem2_credit") or ""),
    )
    return "attempt:" + "|".join(str(value) for value in values)


get_source_attempt_id = source_attempt_id


def _course_completed_credits(course: Mapping[str, Any]) -> float:
    return max(0.0, _number(course.get("completed_credit"), 0.0) or 0.0)


def _course_total_credits(course: Mapping[str, Any]) -> float:
    return max(0.0, _number(course.get("total_credit"), 0.0) or 0.0)


def _course_allocated_credits(course: Mapping[str, Any]) -> float:
    """Return the amount already occupying a target requirement row.

    Target report slices can contain an in-progress portion whose
    ``completed_credit`` is still zero.  Capacity validation must reserve that
    portion too; otherwise a second approved binding could overfill a row that
    is already being taken by the student.
    """

    explicit = _number(course.get("allocated_credits"), None)
    if explicit is not None:
        return max(0.0, explicit)
    completed = _course_completed_credits(course)
    total = _course_total_credits(course)
    return max(completed, total if course.get("is_in_progress") else completed)


def _target_rows(target_requirements: Mapping[str, Any] | Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if isinstance(target_requirements, Mapping):
        rows = target_requirements.get("requirements", target_requirements.get("target_requirements", []))
    else:
        rows = target_requirements
    if not isinstance(rows, (list, tuple)):
        return []
    normalized = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        item = dict(row)
        item["id"] = str(item.get("id") or item.get("requirement_id") or "").strip()
        item["requirement_id"] = item["id"]
        item["name"] = str(item.get("name") or "").strip()
        item["credits"] = _number(item.get("credits", item.get("required_credits")), 0.0) or 0.0
        normalized.append(item)
    return normalized


def _target_context(target_requirements: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(target_requirements, Mapping):
        return {}
    return {
        "cohort": str(target_requirements.get("cohort") or "").strip(),
        "program": str(target_requirements.get("program") or "").strip(),
        "track": str(target_requirements.get("track") or "").strip(),
        "program_type": str(target_requirements.get("program_type") or "").strip(),
    }


def _resolve_target(
    decision: Mapping[str, Any], rows: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str | None]:
    requested_id = str(
        decision.get("target_requirement_id")
        or decision.get("target_id")
        or decision.get("requirement_id")
        or ""
    ).strip()
    if requested_id:
        matches = [row for row in rows if row.get("id") == requested_id]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, TARGET_AMBIGUOUS
        return None, TARGET_NOT_FOUND
    requested_name = normalize_course_name(decision.get("target_requirement_name") or decision.get("target_name") or "")
    if not requested_name:
        return None, TARGET_REQUIRED
    matches = [row for row in rows if normalize_course_name(row.get("name")) == requested_name]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, TARGET_AMBIGUOUS
    return None, TARGET_NOT_FOUND


def _resolve_source(
    decision: Mapping[str, Any], courses: list[Mapping[str, Any]]
) -> tuple[Mapping[str, Any] | None, str | None]:
    requested_id = str(
        decision.get("source_attempt_id")
        or decision.get("attempt_id")
        or decision.get("source_id")
        or ""
    ).strip()
    if requested_id:
        matches = [course for course in courses if source_attempt_id(course) == requested_id]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, SOURCE_AMBIGUOUS
        return None, SOURCE_NOT_FOUND
    requested_name = normalize_course_name(decision.get("source_course_name") or decision.get("source_name") or "")
    if not requested_name:
        return None, SOURCE_REQUIRED
    matches = [
        course
        for course in courses
        if normalize_course_name(course.get("name") or course.get("raw_name")) == requested_name
    ]
    requested_credit = _number(decision.get("source_credit"), None)
    if requested_credit is not None:
        matches = [course for course in matches if abs(_course_total_credits(course) - requested_credit) <= 1e-6]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, SOURCE_AMBIGUOUS
    return None, SOURCE_NOT_FOUND


def _source_name(course: Mapping[str, Any]) -> str:
    return str(course.get("name") or course.get("raw_name") or "").strip()


def _is_lab_target(target: Mapping[str, Any]) -> bool:
    return "實驗" in normalize_course_name(target.get("name"))


def _is_combined_source(course: Mapping[str, Any]) -> bool:
    return normalize_course_name(_source_name(course)) in {
        normalize_course_name(value) for value in (*_COMBINED_PHYSICS_NAMES, *_COMBINED_CHEMISTRY_NAMES)
    }


def _candidate_target(rows: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    wanted = normalize_course_name(name)
    return next((row for row in rows if normalize_course_name(row.get("name")) == wanted), None)


def detect_equivalency_candidates(
    courses: Iterable[Mapping[str, Any]] | None,
    target_requirements: Mapping[str, Any] | Iterable[Mapping[str, Any]] | None = None,
    *,
    cohort: Any = None,
    target_track: Any = "化學組",
    target_program: Any = "物化",
    program_type: str = "雙主修",
) -> list[dict[str, Any]]:
    """Suggest explicit candidates without awarding any credit.

    The source names are a small, visible list.  There is no substring or
    edit-distance matching here.  Combined lecture/lab records only suggest a
    lecture target, so a 3-credit record can never manufacture a 1-credit lab.
    """

    if target_requirements is None:
        if not cohort or str(target_program or "") not in {"物化", "物化系", "物化系物理組", "物化系化學組"}:
            return []
        target_requirements = get_apc_target_requirements(cohort, target_track, program_type)
    target_context = _target_context(target_requirements if isinstance(target_requirements, Mapping) else None)
    effective_cohort = target_context.get("cohort") or str(cohort or "").strip()
    effective_program = target_context.get("program") or str(target_program or "").strip()
    effective_track = target_context.get("track") or str(target_track or "").strip()
    effective_program_type = target_context.get("program_type") or str(program_type or "").strip()
    rows = _target_rows(target_requirements)
    if not rows:
        return []
    output: list[dict[str, Any]] = []
    for course in courses or []:
        if not isinstance(course, Mapping):
            continue
        completed = _course_completed_credits(course)
        if completed <= 1e-6:
            continue
        name = normalize_course_name(_source_name(course))
        proposed_targets: list[tuple[str, str]] = []
        if name in {normalize_course_name(value) for value in _COMBINED_PHYSICS_NAMES}:
            proposed_targets.append(("普通物理學(一)", "講授課與實驗課在手冊中分列；僅提出講授課候選。"))
        elif name in {normalize_course_name(value) for value in _COMBINED_CHEMISTRY_NAMES}:
            proposed_targets.append(("普通化學(一)", "講授課與實驗課在手冊中分列；僅提出講授課候選。"))
        elif effective_cohort == "115" and name in {
            normalize_course_name(value) for value in _CALCULUS_UNNUMBERED_NAMES
        }:
            proposed_targets.extend(
                (
                    ("微積分(一)", "未標示序號，需使用者綁定明確目標。"),
                    ("微積分(二)", "未標示序號，需使用者綁定明確目標。"),
                )
            )
        elif effective_cohort == "115" and name in {
            normalize_course_name(value) for value in _CALCULUS_ONE_NAMES
        }:
            proposed_targets.append(("微積分(一)", "來源序號明確，但外部／跨系認定仍需核准證據。"))
        elif effective_cohort == "115" and name in {
            normalize_course_name(value) for value in _CALCULUS_TWO_NAMES
        }:
            proposed_targets.append(("微積分(二)", "來源序號明確，但外部／跨系認定仍需核准證據。"))

        for target_name, reason in proposed_targets:
            target = _candidate_target(rows, target_name)
            if not target:
                continue
            # An exact course identity is handled by the regular target
            # matcher.  Never create an equivalency row for it.
            if normalize_course_name(_source_name(course)) == normalize_course_name(target.get("name")):
                continue
            source_id = source_attempt_id(course)
            output.append(
                {
                    "decision_id": f"candidate:{source_id}:{target['id']}",
                    "source_attempt_id": source_id,
                    "source_course_name": _source_name(course),
                    "source_credit": _course_total_credits(course),
                    "source_completed_credits": completed,
                    "target_requirement_id": target["id"],
                    "target_requirement_name": target["name"],
                    "target_credits": target["credits"],
                    "cohort": effective_cohort,
                    "target_program": effective_program,
                    "target_track": effective_track,
                    "program_type": effective_program_type,
                    "state": PROPOSED,
                    "decision": PROPOSED,
                    "authority": "",
                    "evidence_reference": "",
                    "approved_credits": 0.0,
                    "validation_codes": [DECISION_NOT_APPROVED],
                    "reason": reason,
                    "candidate": True,
                    "source_is_combined_lab": _is_combined_source(course),
                }
            )
    return output


build_equivalency_candidates = detect_equivalency_candidates


def _context_value(context: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(context.get(key) or "").strip()
        if value:
            return value
    return ""


def _legacy_fields_present(context: Mapping[str, Any]) -> bool:
    """Return whether a legacy aggregate amount was actually supplied.

    The current sidebar also sends ``shared_credits=0`` together with an
    explicit ``confirmed_zero`` answer.  That is not an unbound amount and
    must not make every otherwise clean audit UNKNOWN.  Conversely, any
    positive aggregate value (including an older key spelling) is kept as a
    warning even when its UI said it was approved: it still lacks a source
    attempt and a target requirement row.
    """

    for key in _LEGACY_AGGREGATE_KEYS:
        if key not in context:
            continue
        value = context.get(key)
        if isinstance(value, Mapping):
            if value:
                return True
            continue
        if isinstance(value, (list, tuple, set)):
            if value:
                return True
            continue
        if value in (None, "", False):
            continue
        try:
            if abs(float(value)) > 1e-6:
                return True
            continue
        except (TypeError, ValueError):
            # A non-empty non-numeric aggregate is still unbound input and
            # should be visible for manual cleanup.
            return True
    return False


def _source_allocation_info(report: Mapping[str, Any] | None, attempt_id: str) -> dict[str, Any]:
    """Find the source in exactly one existing non-target report bucket."""

    report = report or {}
    buckets: list[tuple[str, list[Any], bool]] = []
    common = report.get("common", {}) if isinstance(report.get("common", {}), Mapping) else {}
    buckets.extend(
        [
            # University common courses are not primary-department required
            # courses.  They therefore cannot enter the six-credit shared
            # reuse exception merely because they sit in a compulsory bucket.
            ("common_compulsory", common.get("compulsory_courses", []), False),
            ("common_elective", common.get("common_elective_courses", []), False),
        ]
    )
    categories = common.get("categories", {})
    if isinstance(categories, Mapping):
        for category, data in categories.items():
            if isinstance(data, Mapping):
                buckets.append((f"ge:{category}", data.get("courses", []), False))
    major = report.get("major", {}) if isinstance(report.get("major", {}), Mapping) else {}
    buckets.extend(
        [
            ("major_common_compulsory", major.get("dept_compulsory_courses", []), True),
            ("domain_compulsory", major.get("domain_compulsory_courses", []), True),
            ("domain_elective", major.get("domain_elective_courses", []), False),
            ("other_elective", major.get("other_elective_courses", []), False),
        ]
    )
    free = report.get("free", {}) if isinstance(report.get("free", {}), Mapping) else {}
    buckets.append(("free", free.get("courses", []), False))
    matches = []
    for bucket, records, primary_required in buckets:
        if not isinstance(records, (list, tuple)):
            continue
        for record in records:
            if isinstance(record, Mapping) and source_attempt_id(record) == attempt_id:
                matches.append((bucket, record, primary_required))
    return {
        "matches": matches,
        "bucket": matches[0][0] if len(matches) == 1 else "",
        "course": matches[0][1] if len(matches) == 1 else None,
        "source_is_primary_required": bool(matches and len(matches) == 1 and matches[0][2]),
        "safe_for_exclusive_reclassification": len(matches) == 1 and not matches[0][2],
    }


def _target_usage_by_requirement(
    report: Mapping[str, Any] | None,
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, float]:
    """Count target capacity already occupied by a report.

    Named target rows can be counted by their exact requirement ID.  The
    ``其餘必修`` row is a generic quota, however, so its existing bucket
    counter is the source of truth even when the individual catalogue courses
    do not carry that quota ID.  Using ``max`` avoids double counting a report
    that contains both the counter and annotated row records.
    """

    if not isinstance(report, Mapping):
        return {}
    target = report.get("target", {})
    if not isinstance(target, Mapping):
        return {}
    usage: dict[str, float] = {}
    for key in ("basic_core_courses", "compulsory_courses", "elective_courses", "equivalency_courses"):
        records = target.get(key, [])
        if not isinstance(records, (list, tuple)):
            continue
        for record in records:
            if not isinstance(record, Mapping):
                continue
            requirement_id = str(record.get("target_requirement_id") or record.get("requirement_id") or "").strip()
            if not requirement_id:
                continue
            amount = _course_allocated_credits(record)
            usage[requirement_id] = usage.get(requirement_id, 0.0) + amount

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        requirement_id = str(row.get("id") or row.get("requirement_id") or "").strip()
        if not requirement_id or row.get("kind") != "quota":
            continue
        bucket = str(row.get("bucket") or "").strip()
        if bucket in {"other_required", "compulsory"}:
            completed = _number(target.get("compulsory_completed"), 0.0) or 0.0
            in_progress = _number(target.get("compulsory_ip"), 0.0) or 0.0
        elif bucket in {"elective", "other_elective"}:
            completed = _number(target.get("elective_completed"), 0.0) or 0.0
            in_progress = _number(target.get("elective_ip"), 0.0) or 0.0
        else:
            completed = 0.0
            in_progress = 0.0
        usage[requirement_id] = max(usage.get(requirement_id, 0.0), completed + in_progress)
    return usage


def _canonical_cohort(value: Any) -> str:
    """Normalize the small set of cohort spellings used by saved decisions."""

    text = str(value or "").strip()
    match = re.search(r"(?<!\d)(11[1-5])(?!\d)", text)
    return match.group(1) if match else text


def _canonical_scope_value(field: str, value: Any) -> str:
    """Compare equivalent UI labels without making course matching fuzzy."""

    text = str(value or "").strip()
    if field == "cohort":
        return _canonical_cohort(text)
    if field == "program":
        if "物化" in text or "應用化學" in text or "電子物理" in text:
            return "物化"
        if "資科" in text or "資訊科學" in text:
            return "資科"
        if "數學" in text:
            return "數學"
        if "地生" in text or "地球環境" in text or "生命科學" in text:
            return "地生"
    if field == "track":
        if "化學" in text:
            return "化學組"
        if "物理" in text:
            return "物理組"
    if field == "program_type":
        aliases = {"double_major": "雙主修", "double major": "雙主修", "minor": "輔系"}
        return aliases.get(text.lower(), text)
    return text


def _scope_value(raw: Mapping[str, Any], field: str) -> str:
    keys = {
        "cohort": ("cohort", "admission_cohort", "handbook_year"),
        "program": ("target_program", "target_dept", "program"),
        "track": ("target_track", "track"),
        "program_type": ("program_type", "target_program_type"),
    }[field]
    for key in keys:
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return ""


def validate_equivalency_decision(
    decision: Mapping[str, Any],
    source: Mapping[str, Any] | None,
    target: Mapping[str, Any] | None,
    *,
    context: Mapping[str, Any] | None = None,
    source_used: bool = False,
    target_used_credits: float = 0.0,
    shared_used_credits: float = 0.0,
    source_is_primary_required: bool = False,
    source_allocation_count: int = 1,
    safe_for_exclusive_reclassification: bool = True,
) -> dict[str, Any]:
    """Validate one proposed binding; only a fully approved row can count."""

    raw = dict(decision or {})
    state = normalize_decision_state(raw.get("state", raw.get("decision")))
    context = context or {}
    codes: list[str] = []
    reasons: list[str] = []
    approved_credits = 0.0
    source_id = source_attempt_id(source) if source else str(raw.get("source_attempt_id") or "").strip()
    target_id = str(target.get("id") if target else raw.get("target_requirement_id") or "").strip()
    target_name = str(target.get("name") if target else raw.get("target_requirement_name") or "").strip()
    source_name = _source_name(source) if source else str(raw.get("source_course_name") or "").strip()

    if state not in DECISION_STATES:
        state = INVALID
        codes.append(INVALID_DECISION_STATE)
    if state != APPROVED:
        codes.append(DECISION_NOT_APPROVED)
        reasons.append("只有已核准決策才會影響目標門檻。")
    if not source_id:
        codes.append(SOURCE_REQUIRED)
    if not target_id:
        codes.append(TARGET_REQUIRED)

    selected_cohort = _context_value(context, "admission_cohort", "cohort", "handbook_year")
    decision_cohort = _scope_value(raw, "cohort")
    expected_cohort = _canonical_scope_value("cohort", selected_cohort)
    normalized_decision_cohort = _canonical_scope_value("cohort", decision_cohort)
    if expected_cohort and state == APPROVED and not normalized_decision_cohort:
        codes.append(COHORT_MISMATCH)
        reasons.append("已核准決策必須明確帶有適用的入學 cohort。")
    elif normalized_decision_cohort and expected_cohort and normalized_decision_cohort != expected_cohort:
        codes.append(COHORT_MISMATCH)
        reasons.append("這筆決策的入學 cohort 與目前審查手冊不同。")

    expected_program = _context_value(context, "target_program", "target_dept", "program")
    decision_program = _scope_value(raw, "program")
    normalized_expected_program = _canonical_scope_value("program", expected_program)
    normalized_decision_program = _canonical_scope_value("program", decision_program)
    if normalized_expected_program and state == APPROVED and not normalized_decision_program:
        codes.append(TARGET_CONTEXT_MISMATCH)
        reasons.append("已核准決策必須明確帶有目標系所／方案。")
    elif normalized_decision_program and normalized_expected_program and normalized_decision_program != normalized_expected_program:
        codes.append(TARGET_CONTEXT_MISMATCH)
        reasons.append("這筆決策的目標系所與目前選定目標不同。")

    expected_track = _context_value(context, "target_track", "track")
    decision_track = _scope_value(raw, "track")
    normalized_expected_track = _canonical_scope_value("track", expected_track)
    normalized_decision_track = _canonical_scope_value("track", decision_track)
    if normalized_expected_track and state == APPROVED and not normalized_decision_track:
        codes.append(TARGET_CONTEXT_MISMATCH)
        reasons.append("已核准決策必須明確帶有目標組別。")
    elif normalized_decision_track and normalized_expected_track and normalized_decision_track != normalized_expected_track:
        codes.append(TARGET_CONTEXT_MISMATCH)
        reasons.append("這筆決策的目標組別與目前選定目標不同。")

    expected_program_type = _context_value(context, "program_type", "target_program_type")
    decision_program_type = _scope_value(raw, "program_type")
    normalized_expected_program_type = _canonical_scope_value("program_type", expected_program_type)
    normalized_decision_program_type = _canonical_scope_value("program_type", decision_program_type)
    if normalized_expected_program_type and state == APPROVED and not normalized_decision_program_type:
        codes.append(TARGET_CONTEXT_MISMATCH)
        reasons.append("已核准決策必須明確帶有雙主修／輔系身分。")
    elif (
        normalized_decision_program_type
        and normalized_expected_program_type
        and normalized_decision_program_type != normalized_expected_program_type
    ):
        codes.append(TARGET_CONTEXT_MISMATCH)
        reasons.append("這筆決策的修讀身分與目前選定目標不同。")

    if source is None and source_id:
        codes.append(SOURCE_NOT_FOUND)
    if target is None and target_id:
        codes.append(TARGET_NOT_FOUND)

    authority = str(raw.get("authority") or raw.get("approving_authority") or "").strip()
    evidence = str(raw.get("evidence_reference") or raw.get("evidence") or raw.get("evidence_ref") or "").strip()
    if state == APPROVED and not authority:
        codes.append(AUTHORITY_REQUIRED)
        reasons.append("已核准決策必須填寫核准單位／權責人。")
    if state == APPROVED and not evidence:
        codes.append(EVIDENCE_REQUIRED)
        reasons.append("已核准決策必須填寫證據引用（手冊頁、核章或文件編號）。")

    completed = _course_completed_credits(source) if source else 0.0
    total = _course_total_credits(source) if source else 0.0
    if state == APPROVED and completed <= 1e-6:
        codes.append(SOURCE_NOT_COMPLETED)
        reasons.append("來源課程尚無已取得學分；修讀中學分不能完成等價採認。")
    requested_credits = _number(raw.get("approved_credits", raw.get("credits")), None)
    if target is not None:
        target_credits = max(0.0, _number(target.get("credits"), 0.0) or 0.0)
        approved_credits = target_credits if requested_credits is None else max(0.0, requested_credits)
        if approved_credits > completed + 1e-6:
            codes.append(SOURCE_CREDIT_EXCEEDS_COMPLETED)
            reasons.append("核准學分不可超過來源課程已取得學分。")
        if approved_credits + target_used_credits > target_credits + 1e-6:
            codes.append(TARGET_OVERFILLED)
            reasons.append("同一目標門檻不可超額配置。")
    elif requested_credits is not None:
        approved_credits = max(0.0, requested_credits)

    if state == APPROVED and approved_credits <= 1e-6:
        codes.append(APPROVED_CREDIT_REQUIRED)
        reasons.append("已核准綁定必須配置大於0的有效學分。")

    if source_used and state == APPROVED:
        codes.append(SOURCE_ALREADY_BOUND)
        reasons.append("同一來源修課紀錄已綁定另一個目標，不可重複使用。")
    if target_used_credits > 1e-6 and state == APPROVED:
        # A target can be split only when the explicit credit amount remains
        # within its capacity.  A second binding to a partly-filled target is
        # allowed for a different source only up to the remaining amount.
        if target is not None and approved_credits + target_used_credits > float(target.get("credits", 0.0)) + 1e-6:
            if TARGET_OVERFILLED not in codes:
                codes.append(TARGET_OVERFILLED)

    if source and _is_combined_source(source) and target and _is_lab_target(target):
        codes.append(LAB_NOT_SPLIT)
        reasons.append("含實驗合併課只能提出講授課候選，不能拆出實驗學分。")

    if state == APPROVED and source and not source_is_primary_required:
        if not safe_for_exclusive_reclassification or source_allocation_count != 1:
            codes.append(NON_PRIMARY_RECLASSIFICATION_UNSAFE)
            reasons.append("來源不是主修必修，且目前無法安全做排他性重新分類；暫不採認。")

    shared_limit = 6.0
    requested_shared = bool(raw.get("shared_reuse", raw.get("shadow_reuse", False)))
    allocation_type = "shadow_reuse" if source_is_primary_required else "exclusive_reclassification"
    if state == APPROVED and source_is_primary_required:
        if shared_used_credits + approved_credits > shared_limit + 1e-6:
            codes.append(SHARED_LIMIT_EXCEEDED)
            reasons.append("原主修系訂必修的共同修課共享額度合計最多6學分。")
        allocation_type = "shadow_reuse"
    elif requested_shared and not source_is_primary_required:
        codes.append(NON_PRIMARY_RECLASSIFICATION_UNSAFE)
        reasons.append("非主修必修來源不能套用共同修課共享上限；請走排他性重新分類。")

    # Rejected is an explicit user decision and therefore does not create an
    # unknown gate; all other non-approved states remain visible as manual
    # review blockers.
    counts = state == APPROVED and not codes
    if counts:
        reasons.append("已核准且通過來源、目標、學分與證據驗證；可配置至目標門檻。")
        codes = [VALIDATION_OK]
    return {
        **raw,
        "decision": state,
        "state": state,
        "source_attempt_id": source_id,
        "source_course_name": source_name,
        "source_credit": total,
        "source_completed_credits": completed,
        "target_requirement_id": target_id,
        "target_requirement_name": target_name,
        "target_credits": float(target.get("credits", 0.0)) if target else _number(raw.get("target_credits"), 0.0) or 0.0,
        "approved_credits": approved_credits if counts else 0.0,
        "authority": authority,
        "evidence_reference": evidence,
        "allocation_type": allocation_type,
        "source_is_primary_required": bool(source_is_primary_required),
        "counts": counts,
        "validation_codes": list(dict.fromkeys(codes)),
        "reasons": list(dict.fromkeys(reasons)),
        "manual_review": state in {PROPOSED, PENDING, INVALID, AMBIGUOUS} or not counts and state != REJECTED,
    }


def audit_equivalency_decisions(
    courses: Iterable[Mapping[str, Any]] | None,
    target_requirements: Mapping[str, Any] | Iterable[Mapping[str, Any]] | None = None,
    decisions: Iterable[Mapping[str, Any]] | None = None,
    *,
    context: Mapping[str, Any] | None = None,
    report: Mapping[str, Any] | None = None,
    include_candidates: bool = True,
) -> dict[str, Any]:
    """Audit all decisions and return only auditable approved allocations."""

    context = dict(context or {})
    raw_courses = [course for course in (courses or []) if isinstance(course, Mapping)]
    # The engine canonicalizes before invoking this function.  Assigning an
    # ID on a copy keeps standalone callers deterministic without mutating
    # transcript records held by Streamlit.
    canonical_courses = []
    by_id: dict[str, list[Mapping[str, Any]]] = {}
    for course in raw_courses:
        copied = dict(course)
        copied.setdefault("attempt_id", source_attempt_id(copied))
        canonical_courses.append(copied)
        by_id.setdefault(copied["attempt_id"], []).append(copied)

    if target_requirements is None:
        cohort = _context_value(context, "admission_cohort", "cohort", "handbook_year")
        target_track = _context_value(context, "target_track", "track") or "化學組"
        target_program = _context_value(context, "target_program", "target_dept")
        if cohort and ("物化" in target_program or target_program in {"物化", "應用化學", "化學"}):
            target_requirements = get_apc_target_requirements(
                cohort,
                target_track,
                _context_value(context, "program_type") or "雙主修",
            )
    rows = _target_rows(target_requirements)
    target_context = _target_context(target_requirements if isinstance(target_requirements, Mapping) else None)
    if not rows:
        return _seal_audit({
            "status": EQUIVALENCY_NOT_APPLICABLE,
            "state": EQUIVALENCY_NOT_APPLICABLE,
            "decisions": [],
            "approved_mappings": [],
            "candidates": [],
            "manual_gate": {"status": EQUIVALENCY_NOT_APPLICABLE, "state": EQUIVALENCY_NOT_APPLICABLE, "validation_codes": []},
            "warnings": [],
            "validation_codes": [],
            "legacy_unbound": False,
            "approved_shared_reuse_credits": 0.0,
            "approved_exclusive_credits": 0.0,
            "context": target_context,
            "target_requirements": deepcopy(target_requirements) if isinstance(target_requirements, Mapping) else [],
        })

    raw_decisions = [dict(item) for item in (decisions or []) if isinstance(item, Mapping)]
    candidates = detect_equivalency_candidates(
        canonical_courses,
        target_requirements,
        cohort=target_context.get("cohort") or context.get("admission_cohort"),
        target_track=target_context.get("track") or context.get("target_track") or "化學組",
        target_program=target_context.get("program") or context.get("target_program") or "物化",
        program_type=target_context.get("program_type") or context.get("program_type") or "雙主修",
    ) if include_candidates else []

    explicit_pairs = {
        (
            str(item.get("source_attempt_id") or item.get("attempt_id") or "").strip(),
            str(item.get("target_requirement_id") or item.get("target_id") or "").strip(),
        )
        for item in raw_decisions
    }
    explicit_name_pairs = {
        (
            normalize_course_name(item.get("source_course_name") or item.get("source_name") or ""),
            normalize_course_name(item.get("target_requirement_name") or item.get("target_name") or ""),
        )
        for item in raw_decisions
        if normalize_course_name(item.get("source_course_name") or item.get("source_name") or "")
        and normalize_course_name(item.get("target_requirement_name") or item.get("target_name") or "")
    }
    if include_candidates:
        for candidate in candidates:
            key = (candidate["source_attempt_id"], candidate["target_requirement_id"])
            name_key = (
                normalize_course_name(candidate.get("source_course_name") or ""),
                normalize_course_name(candidate.get("target_requirement_name") or ""),
            )
            if key not in explicit_pairs and name_key not in explicit_name_pairs:
                raw_decisions.append(candidate)

    target_capacity = {row["id"]: float(row.get("credits", 0.0) or 0.0) for row in rows}
    existing_target = _target_usage_by_requirement(report, rows)

    validated = []
    approved_mappings = []
    source_used: set[str] = set()
    shared_used = 0.0
    exclusive_used = 0.0
    validation_codes: list[str] = []
    warnings: list[str] = []
    for item in raw_decisions:
        source, source_error = _resolve_source(item, canonical_courses)
        target, target_error = _resolve_target(item, rows)
        source_id = source_attempt_id(source) if source else str(item.get("source_attempt_id") or item.get("attempt_id") or "").strip()
        info = _source_allocation_info(report, source_id)
        # When an evaluated report is available, derive the source bucket from
        # that report.  Do not trust a decision payload that claims a free or
        # already-used row is a primary-required course.  A standalone caller
        # has no bucket to inspect, so it may provide an explicit hint.
        if report is None:
            primary_required = bool(item.get("source_is_primary_required", False))
        else:
            primary_required = bool(info.get("source_is_primary_required", False))
        source_allocation_count = len(info.get("matches", []))
        if report is None and source is not None:
            # The canonical source resolver has already established that this
            # is one unique transcript attempt.  There is simply no report
            # bucket to inspect in a standalone audit, so treat that as one
            # safe source allocation for validation purposes.
            source_allocation_count = 1
        if report is None:
            # Standalone audits have no prior bucket classification to move
            # out of.  They may validate an exclusive binding; the caller
            # that applies it to a report still has to perform the defensive
            # source-allocation check below.
            safe_reclass = bool(item.get("safe_for_exclusive_reclassification", True))
        else:
            safe_reclass = bool(info.get("safe_for_exclusive_reclassification", False))
        selected_target_credits = existing_target.get(target.get("id"), 0.0) if target else 0.0
        row = validate_equivalency_decision(
            item,
            source,
            target,
            context={**context, **target_context},
            source_used=source_id in source_used,
            target_used_credits=selected_target_credits,
            shared_used_credits=shared_used,
            source_is_primary_required=primary_required,
            source_allocation_count=source_allocation_count,
            safe_for_exclusive_reclassification=safe_reclass,
        )
        if source_error and source_error not in row["validation_codes"]:
            row["validation_codes"].append(source_error)
            row["counts"] = False
        if target_error and target_error not in row["validation_codes"]:
            row["validation_codes"].append(target_error)
            row["counts"] = False
        if not row.get("counts") and row.get("state") != REJECTED:
            row["manual_review"] = True
        if row["counts"]:
            source_used.add(row["source_attempt_id"])
            target_id = row["target_requirement_id"]
            target_credit = row["approved_credits"]
            existing_target[target_id] = selected_target_credits + target_credit
            target_capacity[target_id] = target_capacity.get(target_id, 0.0)
            if row["allocation_type"] == "shadow_reuse":
                shared_used += target_credit
            else:
                exclusive_used += target_credit
            approved_mappings.append(row)
        validation_codes.extend(row.get("validation_codes", []))
        validated.append(row)

    legacy_unbound = _legacy_fields_present(context)
    if legacy_unbound:
        validation_codes.append(LEGACY_UNBOUND)
        warnings.append(
            "舊版 aggregate 共同修課欄位只保留相容性；未綁定到來源修課與目標門檻，不會增加有效學分。"
        )

    blockers = [
        row
        for row in validated
        if row.get("manual_review") or row.get("state") in {PROPOSED, PENDING, INVALID, AMBIGUOUS}
    ]
    for blocker in blockers:
        source_label = blocker.get("source_course_name") or blocker.get("source_attempt_id") or "未指定來源"
        target_label = blocker.get("target_requirement_name") or blocker.get("target_requirement_id") or "未指定目標"
        codes = ", ".join(blocker.get("validation_codes", [])) or DECISION_NOT_APPROVED
        warnings.append(f"等價綁定 {source_label} → {target_label} 尚未可採認（{codes}）。")
    # A candidate list itself represents unresolved possible recognition.  A
    # user can explicitly reject it to remove that manual gate.
    status = EQUIVALENCY_UNKNOWN if blockers or legacy_unbound else EQUIVALENCY_SATISFIED
    all_codes = list(dict.fromkeys(validation_codes))
    if status == EQUIVALENCY_UNKNOWN and not all_codes:
        all_codes = [DECISION_NOT_APPROVED]
    manual_gate = {
        "status": status,
        "state": status,
        "validation_codes": all_codes,
        "pending_count": len(blockers),
        "approved_count": len(approved_mappings),
        "warnings": warnings,
    }
    return _seal_audit({
        "status": status,
        "state": status,
        "decisions": validated,
        "approved_mappings": approved_mappings,
        "candidates": candidates,
        "manual_gate": manual_gate,
        "warnings": warnings,
        "validation_codes": all_codes,
        "legacy_unbound": legacy_unbound,
        "approved_shared_reuse_credits": shared_used,
        "approved_exclusive_credits": exclusive_used,
        "approved_credits": shared_used + exclusive_used,
        "context": {
            **target_context,
            "admission_cohort": _context_value(context, "admission_cohort", "cohort", "handbook_year")
            or target_context.get("cohort", ""),
            "target_program": _context_value(context, "target_program", "target_dept")
            or target_context.get("program", ""),
            "target_track": _context_value(context, "target_track", "track") or target_context.get("track", ""),
        },
        "target_requirements": deepcopy(target_requirements) if isinstance(target_requirements, Mapping) else rows,
    })


evaluate_equivalency = audit_equivalency_decisions
audit_course_equivalencies = audit_equivalency_decisions


def _remove_from_report_bucket(report: dict[str, Any], attempt_id: str) -> tuple[dict[str, Any] | None, str]:
    """Remove one non-target allocation and return it for reclassification."""

    bucket_specs = [
        ("common", "compulsory_courses", "compulsory_completed", "common_compulsory"),
        ("common", "common_elective_courses", "common_elective_completed", "common_elective"),
        ("major", "dept_compulsory_courses", "dept_compulsory_completed", "major_common_compulsory"),
        ("major", "domain_compulsory_courses", "domain_compulsory_completed", "domain_compulsory"),
        ("major", "domain_elective_courses", "domain_elective_completed", "domain_elective"),
        ("major", "other_elective_courses", "other_elective_completed", "other_elective"),
        ("free", "courses", "completed", "free"),
    ]
    for section_name, list_name, counter_name, bucket_name in bucket_specs:
        section = report.get(section_name, {})
        if not isinstance(section, dict):
            continue
        records = section.get(list_name, [])
        if not isinstance(records, list):
            continue
        for index, record in enumerate(records):
            if not isinstance(record, Mapping) or source_attempt_id(record) != attempt_id:
                continue
            copied = dict(record)
            records.pop(index)
            amount = _course_completed_credits(copied)
            section[counter_name] = max(0.0, float(section.get(counter_name, 0.0) or 0.0) - amount)
            return copied, bucket_name
    return None, ""


def _target_allocation_copy(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": mapping.get("source_course_name", ""),
        "raw_name": mapping.get("source_course_name", ""),
        "attempt_id": mapping.get("source_attempt_id", ""),
        "total_credit": mapping.get("approved_credits", 0.0),
        "completed_credit": mapping.get("approved_credits", 0.0),
        "is_completed": True,
        "is_in_progress": False,
        "target_requirement_id": mapping.get("target_requirement_id", ""),
        "target_requirement_name": mapping.get("target_requirement_name", ""),
        "allocation_type": mapping.get("allocation_type", ""),
        "allocation_note": "；".join(mapping.get("reasons", [])),
        "equivalency_decision_id": mapping.get("decision_id", ""),
        "authority": mapping.get("authority", ""),
        "evidence_reference": mapping.get("evidence_reference", ""),
    }


def _countable_mapping(mapping: Mapping[str, Any]) -> bool:
    """Defence-in-depth guard for callers that hand-build an audit payload."""

    state = normalize_decision_state(mapping.get("state", mapping.get("decision")))
    allocation_type = str(mapping.get("allocation_type") or "").strip()
    amount = _number(mapping.get("approved_credits"), 0.0) or 0.0
    validation_codes = mapping.get("validation_codes", [])
    target_credits = _number(mapping.get("target_credits"), 0.0) or 0.0
    return bool(
        mapping.get("counts") is True
        and state == APPROVED
        and str(mapping.get("decision_id") or "").strip()
        and str(mapping.get("source_attempt_id") or "").strip()
        and str(mapping.get("target_requirement_id") or "").strip()
        and str(mapping.get("authority") or "").strip()
        and str(mapping.get("evidence_reference") or "").strip()
        and allocation_type in {"shadow_reuse", "exclusive_reclassification"}
        and amount > 1e-6
        and target_credits > 1e-6
        and amount <= target_credits + 1e-6
        and isinstance(validation_codes, (list, tuple, set))
        and VALIDATION_OK in validation_codes
    )


def _report_target_plan(report: Mapping[str, Any] | None, audit: Mapping[str, Any] | None = None) -> Any:
    """Return the cohort-scoped target plan available at apply time."""

    report = report if isinstance(report, Mapping) else {}
    for key in ("target_requirements",):
        candidate = report.get(key)
        if isinstance(candidate, Mapping) and _target_rows(candidate):
            return candidate
    nested = report.get("target_plan")
    if isinstance(nested, Mapping):
        candidate = nested.get("target_requirements")
        if isinstance(candidate, Mapping) and _target_rows(candidate):
            return candidate
        if _target_rows(nested):
            return nested
    audit = audit if isinstance(audit, Mapping) else {}
    candidate = audit.get("target_requirements")
    if isinstance(candidate, Mapping) and _target_rows(candidate):
        return candidate
    return None


def _report_equivalency_context(report: Mapping[str, Any] | None, target_plan: Mapping[str, Any] | None) -> dict[str, str]:
    """Build the apply-time scope from trusted report/target metadata."""

    report = report if isinstance(report, Mapping) else {}
    target_context = _target_context(target_plan)
    return {
        "cohort": str(report.get("handbook_year") or report.get("admission_cohort") or "").strip()
        or target_context.get("cohort", ""),
        "program": str(report.get("target_program") or report.get("target_dept") or "").strip()
        or target_context.get("program", ""),
        "track": str(report.get("target_track") or report.get("track") or "").strip()
        or target_context.get("track", ""),
        "program_type": str(report.get("program_type") or "").strip() or target_context.get("program_type", ""),
    }


def _same_equivalency_scope(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    for field in ("cohort", "program", "track", "program_type"):
        left = _canonical_scope_value(field, expected.get(field))
        right = _canonical_scope_value(field, actual.get(field))
        if left and right and left != right:
            return False
    return True


def _existing_equivalency_sources(target: Mapping[str, Any] | None) -> set[str]:
    target = target if isinstance(target, Mapping) else {}
    records = target.get("equivalency_courses", [])
    if not isinstance(records, (list, tuple)):
        return set()
    return {
        source_attempt_id(item)
        for item in records
        if isinstance(item, Mapping) and source_attempt_id(item)
    }


def _existing_shared_reuse_credits(target: Mapping[str, Any] | None) -> float:
    target = target if isinstance(target, Mapping) else {}
    reported = max(0.0, _number(target.get("equivalency_shared_completed"), 0.0) or 0.0)
    records = target.get("equivalency_courses", [])
    if isinstance(records, (list, tuple)):
        reported = max(
            reported,
            sum(
                max(0.0, _number(item.get("completed_credit", item.get("approved_credits")), 0.0) or 0.0)
                for item in records
                if isinstance(item, Mapping) and item.get("allocation_type") == "shadow_reuse"
            ),
        )
    return reported


def apply_equivalency_audit_to_report(
    report: Mapping[str, Any],
    audit: Mapping[str, Any],
    *,
    mutate: bool = False,
) -> dict[str, Any]:
    """Attach approved mappings and effective target totals to a report.

    ``mutate=False`` returns a deep copy, making this function safe for UI
    previews.  The engine uses ``mutate=True`` after it has finished its exact
    allocation pass.  Shared reuse changes only effective target progress.
    Exclusive reclassification is deliberately rejected here: moving a source
    out of a required/common/free bucket would require rebuilding every
    graduation gate and missing-course list, which this boundary cannot do
    safely.
    """

    output = report if mutate else deepcopy(report)
    if not isinstance(output, dict):
        output = {}
    audit_input = audit if isinstance(audit, Mapping) else {}
    provenance_valid = _has_valid_validation_seal(audit_input)
    audit_copy = deepcopy(dict(audit_input))
    # The in-memory seal is an apply-time capability, not a report/export
    # field.  Keep the public result serializable and avoid leaking it into
    # saved UI state after it has been checked.
    audit_copy.pop("_validation_seal", None)
    output["equivalency"] = audit_copy
    output["equivalency_audit"] = audit_copy
    output.setdefault("manual_gates", {})
    output["manual_gates"]["equivalency"] = audit_copy.get("manual_gate", {"status": EQUIVALENCY_UNKNOWN})
    output.setdefault("policy_warnings", [])
    audit_warnings = audit_copy.get("warnings", [])
    if isinstance(audit_warnings, str):
        audit_warnings = [audit_warnings]
    if not isinstance(audit_warnings, (list, tuple, set)):
        audit_warnings = []
    output["policy_warnings"].extend(audit_warnings)

    target = output.setdefault("target", {})
    target.setdefault("equivalency_courses", [])
    target.setdefault("equivalency_completed", 0.0)
    target.setdefault("equivalency_shared_completed", 0.0)
    target.setdefault("equivalency_exclusive_completed", 0.0)
    target.setdefault("effective_total_completed", target.get("total_completed", 0.0) or 0.0)
    target.setdefault("effective_total_ip", target.get("total_ip", 0.0) or 0.0)

    target_plan = _report_target_plan(output, audit_input)
    target_rows = _target_rows(target_plan)
    audit_context = audit_copy.get("context", {}) if isinstance(audit_copy.get("context", {}), Mapping) else {}
    report_context = _report_equivalency_context(output, target_plan)
    scope_valid = bool(target_rows) and _same_equivalency_scope(audit_context, report_context)
    if not provenance_valid:
        output["policy_warnings"].append(
            f"{APPLY_PROVENANCE_REQUIRED}：等價稽核不是本次驗證產物，所有綁定均不套用。"
        )
    elif not target_rows:
        output["policy_warnings"].append(
            f"{APPLY_TARGET_INVALID}：報告缺少可核對的 cohort 目標門檻，所有綁定均不套用。"
        )
    elif not scope_valid:
        output["policy_warnings"].append(
            f"{APPLY_SCOPE_MISMATCH}：等價稽核範圍與目前報告不一致，所有綁定均不套用。"
        )

    applied_mappings: list[Mapping[str, Any]] = []
    applied_shared = _existing_shared_reuse_credits(target)
    applied_exclusive = max(0.0, _number(target.get("equivalency_exclusive_completed"), 0.0) or 0.0)
    existing_target_usage = _target_usage_by_requirement(output, target_rows)
    existing_equivalency_records = target.get("equivalency_courses", [])
    if not isinstance(existing_equivalency_records, (list, tuple)):
        existing_equivalency_records = []
    existing_equivalency_keys = {
        (
            str(item.get("equivalency_decision_id") or item.get("decision_id") or ""),
            str(item.get("attempt_id") or item.get("source_attempt_id") or ""),
            str(item.get("target_requirement_id") or ""),
        )
        for item in existing_equivalency_records
        if isinstance(item, Mapping)
    }
    existing_source_ids = _existing_equivalency_sources(target)
    seen_source_ids: set[str] = set()
    approved_rows = audit_copy.get("approved_mappings", [])
    if not isinstance(approved_rows, (list, tuple)):
        approved_rows = []
    for mapping in approved_rows:
        if not isinstance(mapping, Mapping):
            continue
        if not _countable_mapping(mapping):
            output["policy_warnings"].append(
                f"等價綁定 {mapping.get('source_attempt_id', '')} → {mapping.get('target_requirement_id', '')} 欠缺完整核准／證據，未套用。"
            )
            continue
        if not provenance_valid or not scope_valid:
            continue
        source_id = str(mapping.get("source_attempt_id") or "").strip()
        target_id = str(mapping.get("target_requirement_id") or "").strip()
        mapping_key = (
            str(mapping.get("decision_id") or ""),
            source_id,
            target_id,
        )
        if mapping_key in existing_equivalency_keys:
            continue
        target_row = next((row for row in target_rows if row.get("id") == target_id), None)
        source_info = _source_allocation_info(output, source_id)
        source_record = source_info.get("course") if isinstance(source_info, Mapping) else None
        if target_row is None:
            output["policy_warnings"].append(
                f"{APPLY_TARGET_INVALID}：目標 requirement {target_id} 不在目前 cohort 門檻中，未套用。"
            )
            continue
        if source_record is None or len(source_info.get("matches", [])) != 1:
            output["policy_warnings"].append(
                f"{APPLY_SOURCE_INVALID}：來源 attempt {source_id} 不存在或不是唯一報告配置，未套用。"
            )
            continue
        actual_primary = bool(source_info.get("source_is_primary_required", False))
        allocation_type = str(mapping.get("allocation_type") or "").strip()
        expected_allocation_type = "shadow_reuse" if actual_primary else "exclusive_reclassification"
        if allocation_type != expected_allocation_type:
            output["policy_warnings"].append(
                f"{APPLY_SOURCE_INVALID}：來源 attempt {source_id} 的實際配置與等價配置類型不一致，未套用。"
            )
            continue
        if normalize_course_name(mapping.get("target_requirement_name")) != normalize_course_name(target_row.get("name")):
            output["policy_warnings"].append(
                f"{APPLY_TARGET_INVALID}：目標 requirement {target_id} 課名不一致，未套用。"
            )
            continue
        amount = max(0.0, _number(mapping.get("approved_credits"), 0.0) or 0.0)
        if amount > _course_completed_credits(source_record) + 1e-6:
            output["policy_warnings"].append(
                f"{APPLY_SOURCE_INVALID}：來源 attempt {source_id} 的已取得學分不足，未套用。"
            )
            continue
        if source_id in seen_source_ids or source_id in existing_source_ids:
            output["policy_warnings"].append(
                f"{APPLY_SOURCE_INVALID}：來源 attempt {source_id} 在等價配置中重複使用，未套用。"
            )
            continue
        if allocation_type == "shadow_reuse" and applied_shared + amount > 6.0 + 1e-6:
            output["policy_warnings"].append(
                f"{SHARED_LIMIT_EXCEEDED}：共享等價學分不可超過6學分，來源 attempt {source_id} 未套用。"
            )
            continue
        target_capacity = max(0.0, _number(target_row.get("credits"), 0.0) or 0.0)
        if existing_target_usage.get(target_id, 0.0) + amount > target_capacity + 1e-6:
            output["policy_warnings"].append(
                f"{TARGET_OVERFILLED}：目標 requirement {target_id} 超過容量，未套用。"
            )
            continue
        if allocation_type == "exclusive_reclassification":
            # Applying this move after the engine's gate computation would
            # leave stale common/major/free totals and missing rows.  Keep the
            # source in its original bucket and make the mapping non-counting.
            output["policy_warnings"].append(
                f"{EXCLUSIVE_APPLY_UNSUPPORTED}：排他性重新分類需要重建所有畢業門檻，這次報告不套用。"
            )
            audit_copy.setdefault("apply_rejected_mappings", []).append(
                {
                    "decision_id": mapping.get("decision_id", ""),
                    "source_attempt_id": source_id,
                    "target_requirement_id": target_id,
                    "reason": EXCLUSIVE_APPLY_UNSUPPORTED,
                }
            )
            continue
        if amount <= 1e-6:
            continue
        allocation = _target_allocation_copy(mapping)
        allocation_type = str(mapping.get("allocation_type") or "")
        if allocation_type == "exclusive_reclassification":
            removed, source_bucket = _remove_from_report_bucket(output, str(mapping.get("source_attempt_id") or ""))
            if removed is None:
                # The audit should already have rejected this, but keep the
                # report conservative if another caller supplied a hand-made
                # audit object.
                output["policy_warnings"].append(
                    f"來源 {mapping.get('source_attempt_id', '')} 無法安全重新分類；等價決策維持人工確認。"
                )
                continue
            allocation["source_bucket"] = source_bucket
            target["equivalency_exclusive_completed"] += amount
            output.setdefault("summary", {})["total_completed"] = max(
                0.0, float(output.get("summary", {}).get("total_completed", 0.0) or 0.0)
            )
            # Removing and adding a completed slice preserves the raw total.
            removed_amount = _course_completed_credits(removed)
            output["summary"]["total_completed"] -= removed_amount
            if source_bucket in {"common_compulsory", "common_elective"} or source_bucket.startswith("ge:"):
                output["summary"]["common_completed"] = max(
                    0.0, float(output["summary"].get("common_completed", 0.0) or 0.0) - removed_amount
                )
            elif source_bucket in {
                "major_common_compulsory",
                "domain_compulsory",
                "domain_elective",
                "other_elective",
            }:
                output["summary"]["major_completed"] = max(
                    0.0, float(output["summary"].get("major_completed", 0.0) or 0.0) - removed_amount
                )
            elif source_bucket == "free":
                output["summary"]["free_completed"] = max(
                    0.0, float(output["summary"].get("free_completed", 0.0) or 0.0) - removed_amount
                )
            # An exclusive move preserves the raw total by adding the mapped
            # slice to the target bucket.  Shadow reuse below intentionally
            # leaves raw target totals unchanged.
            target["total_completed"] = float(target.get("total_completed", 0.0) or 0.0) + amount
            output["summary"]["target_completed"] = float(output["summary"].get("target_completed", 0.0) or 0.0) + amount
            output["summary"]["total_completed"] += amount
        else:
            target["equivalency_shared_completed"] += amount
        target["equivalency_completed"] += amount
        target["equivalency_courses"].append(allocation)
        if allocation_type == "shadow_reuse":
            applied_shared += amount
        else:
            applied_exclusive += amount
        applied_mappings.append(mapping)
        existing_equivalency_keys.add(mapping_key)
        seen_source_ids.add(source_id)
        existing_source_ids.add(source_id)
        existing_target_usage[target_id] = existing_target_usage.get(target_id, 0.0) + amount

        target_name = normalize_course_name(mapping.get("target_requirement_name"))
        target_id = str(mapping.get("target_requirement_id") or "")
        # Reflect the mapped amount in the appropriate target sub-bucket.  The
        # source row remains in its original bucket for shadow reuse.
        if "實驗" in target_name or target_name.startswith("普通") and "實驗" in target_name:
            target["basic_core_completed"] = float(target.get("basic_core_completed", 0.0) or 0.0) + amount
            target["basic_core_courses"] = list(target.get("basic_core_courses", [])) + [allocation]
        elif target_name and target_name not in {""}:
            # All APC target course IDs in the current data model are base;
            # quota rows are identified by the target requirement ID/name and
            # are placed in compulsory progress.
            if "其餘必修" in target_name:
                target["compulsory_completed"] = float(target.get("compulsory_completed", 0.0) or 0.0) + amount
                target["compulsory_courses"] = list(target.get("compulsory_courses", [])) + [allocation]
            else:
                target["basic_core_completed"] = float(target.get("basic_core_completed", 0.0) or 0.0) + amount
                target["basic_core_courses"] = list(target.get("basic_core_courses", [])) + [allocation]

        # Remove a matching missing row only by exact target ID/name.  No
        # substring matching is used for requirement identity.
        for missing_key in ("basic_core_missing", "compulsory_missing", "elective_missing"):
            missing = target.get(missing_key, [])
            if not isinstance(missing, list):
                continue
            for index, item in enumerate(list(missing)):
                if not isinstance(item, Mapping):
                    continue
                item_id = str(item.get("target_requirement_id") or "")
                item_name = normalize_course_name(item.get("name") or "")
                if (target_id and item_id == target_id) or (not target_id and item_name == target_name):
                    remaining = max(0.0, float(item.get("credit", 0.0) or 0.0) - amount)
                    if remaining <= 1e-6:
                        missing.pop(index)
                    else:
                        item["credit"] = remaining
                    break

    # Derive the effective/shared amounts from mappings that were actually
    # applied in this call.  Never trust a legacy aggregate field or a hand
    # assembled ``approved_shared_reuse_credits`` value as a credit source.
    audit_copy["applied_mappings"] = deepcopy(applied_mappings)
    audit_copy["approved_shared_reuse_credits"] = applied_shared
    audit_copy["approved_exclusive_credits"] = applied_exclusive
    audit_copy["approved_credits"] = applied_shared + applied_exclusive
    target["effective_total_completed"] = float(target.get("total_completed", 0.0) or 0.0) + applied_shared
    target["effective_total_ip"] = float(target.get("total_ip", 0.0) or 0.0)
    target["shared_reuse_credits"] = applied_shared
    output["shared_reuse"] = {
        "allowance": 6.0 if applied_shared else 0.0,
        "completed": applied_shared,
        "ip": 0.0,
        "total": applied_shared,
        "rows": [
            {
                "attempt_id": item.get("source_attempt_id", ""),
                "target_requirement_id": item.get("target_requirement_id", ""),
                "target_requirement_name": item.get("target_requirement_name", ""),
                "reused_completed_credits": item.get("approved_credits", 0.0),
                "reused_credits": item.get("approved_credits", 0.0),
                "allocation_type": item.get("allocation_type", ""),
                "authority": item.get("authority", ""),
                "evidence_reference": item.get("evidence_reference", ""),
            }
            for item in applied_mappings
            if item.get("allocation_type") == "shadow_reuse"
        ],
        "approval_scope": "bound_source_to_target",
        "allocation_type": "audited",
        "course_identity_status": "officially_bound_or_pending",
        "official_course_identity_note": "每筆共享額度均綁定來源 attempt、目標 requirement、核准單位與證據；舊 aggregate 不計入。",
    }
    output["policy_warnings"] = list(dict.fromkeys(str(item) for item in output["policy_warnings"] if item))
    return output


apply_equivalency_to_report = apply_equivalency_audit_to_report
