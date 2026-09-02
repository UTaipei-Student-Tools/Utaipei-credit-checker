"""Snapshot-only HTML presentation for 北市大畢業通.

The renderer is deliberately a *consumer* of :class:`DecisionSnapshot`, not
another graduation engine.  It calls ``snapshot.as_dict()`` exactly once,
then joins the immutable allocation projection with its requirement and
attempt records for display.  No rule, curriculum, application, or allocator
module is imported here.
"""

from __future__ import annotations

import html
import unicodedata
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from decision_snapshot import DecisionSnapshot
from lieflat_progress_chart import render_f5_tick_rows, render_f7_stacked_rungs, render_f11_tick_gauge

UNKNOWN = "UNKNOWN"
PASS = "PASS"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"
MANUAL_LABEL = "資料不足／需人工確認"

_SENSITIVE_KEY_FRAGMENTS = (
    # English identity/credential/transcript spellings.  Keys are compared
    # after Unicode NFKC, case-folding, and punctuation removal so that
    # studentNo, student_number, HF Token, rawPDF, etc. share one policy.
    "studentid",
    "studentnumber",
    "studentno",
    "studentname",
    "namezh",
    "nameen",
    "username",
    "account",
    "password",
    "credential",
    "authorization",
    "session",
    "cookie",
    "token",
    "transcript",
    "rawpdf",
    "pdf",
    "blob",
    "bytes",
    "rawrecord",
    "rawidentity",
    # Common Chinese identity/credential labels.
    "學號",
    "学号",
    "姓名",
    "使用者名稱",
    "使用者名",
    "帳號",
    "密碼",
    "密码",
    "憑證",
    "凭证",
    "授權",
    "授权",
    "會話",
    "会话",
)


def _normalize_key(key: Any) -> str:
    """Return a comparison key resilient to casing and naming conventions."""

    normalized = unicodedata.normalize("NFKC", str(key)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _is_masked_identifier(value: Any) -> bool:
    text = _text(value).strip()
    if not text:
        return False
    lowered = text.casefold()
    return any(marker in text for marker in ("*", "＊", "•", "…", "⋯")) or lowered.startswith(("masked", "redacted", "已遮罩"))


def _is_sensitive_key(key: Any) -> bool:
    normalized = _normalize_key(key)
    if normalized == "maskedstudentid":
        return False
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _plain(value: Any) -> Any:
    """Copy snapshot values while recursively dropping private/raw fields.

    The snapshot itself is already a safe boundary, but presentation and
    export are deliberately defense-in-depth boundaries.  A future additive
    field (or a test double) must not be able to leak identity, credentials,
    or raw transcript bytes merely because it was nested under an otherwise
    harmless parent key.
    """

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = _normalize_key(key)
            if normalized == "maskedstudentid":
                # A masked identifier is safe only when the caller clearly
                # supplied a redacted value; an unmasked value under this key
                # is treated as private identity and dropped.
                if _is_masked_identifier(item):
                    result["masked_student_id"] = _text(item)
                continue
            if _is_sensitive_key(normalized):
                continue
            result[str(key)] = _plain(item)
        return result
    if isinstance(value, (set, frozenset)):
        return [_plain(item) for item in sorted(value, key=str)]
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    return value


# Export modules use this same sanitizer before serializing their payload.
sanitize_snapshot_value = _plain


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return fallback


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _credit(value: Any, *, unavailable: str = MANUAL_LABEL) -> str:
    number = _decimal(value)
    if number is None:
        return unavailable
    if number == number.to_integral():
        return str(number.quantize(Decimal("1")))
    return format(number.normalize(), "f").rstrip("0").rstrip(".")


def _escape(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def _value_sequence(value: Any) -> tuple[Any, ...]:
    """Read a scalar or sequence without treating a mapping as a course list."""

    if value is None or isinstance(value, (bytes, bytearray, memoryview, Mapping)):
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(value, key=str))
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _snapshot_payload(snapshot: DecisionSnapshot) -> Mapping[str, Any]:
    if not isinstance(snapshot, DecisionSnapshot):
        raise TypeError("snapshot renderer expects a DecisionSnapshot")
    # This is the only snapshot.as_dict call in each public renderer entry
    # point.  Consumers work from the resulting frozen projection only.
    payload = snapshot.as_dict()
    if not isinstance(payload, Mapping):
        raise TypeError("DecisionSnapshot.as_dict() must return a mapping")
    snapshot_id = _text(payload.get("snapshot_id"))
    if not snapshot_id or snapshot_id != snapshot.snapshot_id:
        raise ValueError("DecisionSnapshot snapshot_id is missing or unstable")
    return payload


def _status_label(status: Any) -> str:
    normalized = _text(status).upper()
    return {
        PASS: "已修畢",
        "COMPLETED": "已修畢",
        "IN_PROGRESS": "修習中",
        "IP": "修習中",
        FAIL: "未通過",
        "W": "停修／未通過",
        "WITHDRAWN": "停修／未通過",
        "WAIVER": "抵認／免修",
        "NOT_ATTEMPTED": "未修",
        "MISSING": "未修",
        "UNALLOCATED": "未配置",
        UNKNOWN: "待確認",
        "PENDING": "待確認",
    }.get(normalized, "待確認")


def _allocation_kind_label(kind: Any) -> str:
    normalized = _text(kind).upper()
    return {
        "EXCLUSIVE": "正式配置",
        "SHARED_SHADOW": "雙主修共享",
        "SHARED_REUSE": "雙主修共享",
        "WAIVER": "免修／抵認（不產生實得學分）",
    }.get(normalized, "待確認配置")


def _requirement_kind_label(requirement: Mapping[str, Any]) -> str:
    explicit = _text(requirement.get("kind"))
    if explicit:
        return explicit
    bucket = _text(requirement.get("bucket"))
    return {
        "required": "必修",
        "major": "主修",
        "major_common": "系共同必修",
        "elective": "選修",
        "general_education": "通識",
        "ge": "通識",
        "free": "自由學分",
        "double_major": "雙主修要求",
        "target": "雙主修要求",
    }.get(bucket.lower(), bucket or "畢業要求")


def _allocation_reason(item: Mapping[str, Any], portions: Sequence[Mapping[str, Any]]) -> str:
    reason = _text(item.get("allocation_reason"))
    if reason == "EXCLUSIVE_REQUIREMENT_ROUTE":
        return "依全域配置結果，將實得學分配置到此要求。"
    if reason == "WAIVER_DECISION":
        return "快照保留免修／抵認決定；免修本身不增加實得學分。"
    if reason == "NO_SAFE_REQUIREMENT_ROUTE" or not portions:
        return "沒有可由目前規則安全確認的要求路徑。"
    return reason or "配置原因未提供；需人工確認。"


def _portion_credit(portion: Mapping[str, Any]) -> Decimal:
    return _decimal(portion.get("credits")) or Decimal("0")


def _alternative_routes(alternatives: Sequence[Any], attempt_id: str, requirement_id: str) -> tuple[str, ...]:
    """Read route labels from allocator-provided alternative signatures.

    The signature is intentionally opaque and may evolve.  This parser only
    reads scalar route identifiers already present in the snapshot; it never
    asks the allocator to produce another result or infers a new equivalency.
    """

    routes: list[str] = []
    for alternative in alternatives:
        parts = _as_sequence(alternative)
        if not parts or _text(parts[0]) != attempt_id:
            continue
        route_parts = _as_sequence(parts[1]) if len(parts) > 1 else ()
        for route in route_parts:
            if isinstance(route, Mapping):
                route_requirement = _text(route.get("requirement_id"))
                if route_requirement and route_requirement != requirement_id:
                    continue
                route_text = route_requirement or _text(route.get("route"))
            else:
                route_values = _as_sequence(route)
                route_text = _text(route_values[0]) if route_values else _text(route)
            if route_text and route_text != requirement_id and route_text not in routes:
                routes.append(route_text)
    return tuple(routes)


def _metadata_routes(item: Mapping[str, Any], requirement_id: str) -> tuple[str, ...]:
    """Read already-materialized route labels from an attempt/allocation row."""

    routes: list[str] = []
    for key in ("alternative_routes", "safe_routes", "route_options", "routes", "alternative_requirement_ids"):
        raw = item.get(key)
        values = (raw,) if isinstance(raw, Mapping) else _value_sequence(raw)
        for route in values:
            if isinstance(route, Mapping):
                route_requirement = _text(
                    route.get("requirement_id")
                    or route.get("target_requirement_id")
                    or route.get("route_id")
                )
                if route_requirement == requirement_id:
                    continue
                route_text = _text(route.get("label") or route.get("route") or route_requirement)
            else:
                route_values = _as_sequence(route)
                route_text = _text(route_values[0]) if route_values else _text(route)
            if route_text and route_text != requirement_id and route_text not in routes:
                routes.append(route_text)
    return tuple(routes)


def _provenance_for(requirement_id: str, provenance: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    matched: list[Mapping[str, Any]] = []
    for item in provenance:
        if not isinstance(item, Mapping):
            continue
        item_requirement = _text(item.get("requirement_id"))
        requirement_ids = item.get("requirement_ids")
        listed = {_text(value) for value in _as_sequence(requirement_ids) if _text(value)}
        if item_requirement == requirement_id or requirement_id in listed or not item_requirement and not listed:
            matched.append(item)
    return tuple(matched)


def _provenance_view(items: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    for item in items:
        row = {
            key: _plain(item[key])
            for key in (
                "source_reference",
                "source_location",
                "source_file",
                "source_url",
                "pages",
                "original_clause",
                "authority",
                "evidence_reference",
                "evidence_id",
                "evidence_state",
                "coverage_state",
                "automatic_decision",
                "assertion_id",
                "scope",
            )
            if key in item and str(item[key])
        }
        if row:
            rows.append(row)
    return tuple(rows)


_COURSE_COLLECTION_KEYS = (
    "eligible_courses",
    "course_options",
    "named_courses",
    "official_courses",
    "official_course_list",
    "official_course_options",
    "eligible_course_list",
    "required_courses",
    "choice_courses",
    "allowed_courses",
    "course_choices",
    "course_catalog",
)
_COURSE_ID_KEYS = ("course_id", "course_code", "code", "id")
_COURSE_NAME_KEYS = ("course_name", "name", "title", "label")
_CONDITION_KEYS = (
    "choice_condition",
    "selection_condition",
    "requirement_condition",
    "condition",
    "choice",
    "selection_rule",
    "required_condition",
)


def _mapping_value(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    wanted = {_normalize_key(key) for key in keys}
    for key, value in mapping.items():
        if _normalize_key(key) in wanted:
            return value
    return None


def _course_option(course_id: Any = "", course_name: Any = "") -> Mapping[str, str] | None:
    normalized_id = _text(course_id).strip()
    normalized_name = _text(course_name).strip()
    if not normalized_id and not normalized_name:
        return None
    return {"course_id": normalized_id, "course_name": normalized_name}


def _append_course_option(rows: list[dict[str, str]], option: Mapping[str, str] | None) -> None:
    if option is None:
        return
    course_id = _text(option.get("course_id")).strip()
    course_name = _text(option.get("course_name")).strip()
    id_key = course_id.casefold()
    name_key = course_name.casefold()
    for row in rows:
        same_id = id_key and id_key == _text(row.get("course_id")).casefold()
        same_name = name_key and name_key == _text(row.get("course_name")).casefold()
        same_label = (
            (id_key and id_key == _text(row.get("course_name")).casefold())
            or (name_key and name_key == _text(row.get("course_id")).casefold())
        )
        if same_id or same_name or same_label:
            if course_id and not row.get("course_id"):
                row["course_id"] = course_id
            if course_name and not row.get("course_name"):
                row["course_name"] = course_name
            return
    rows.append({"course_id": course_id, "course_name": course_name})


def _eligible_course_options(requirement: Mapping[str, Any]) -> tuple[Mapping[str, str], ...]:
    """Return only explicit official course IDs/names carried by the snapshot."""

    rows: list[dict[str, str]] = []

    def add_collection(raw: Any) -> None:
        if isinstance(raw, Mapping):
            # A single course record, e.g. {course_id: ..., course_name: ...}.
            direct_id = _mapping_value(raw, _COURSE_ID_KEYS)
            direct_name = _mapping_value(raw, _COURSE_NAME_KEYS)
            if direct_id is not None or direct_name is not None:
                _append_course_option(rows, _course_option(direct_id, direct_name))
                return
            # A mapping of official course ID -> official name/record.
            for course_id, course in raw.items():
                if isinstance(course, Mapping):
                    _append_course_option(
                        rows,
                        _course_option(
                            _mapping_value(course, _COURSE_ID_KEYS) or course_id,
                            _mapping_value(course, _COURSE_NAME_KEYS),
                        ),
                    )
                else:
                    _append_course_option(rows, _course_option(course_id, course))
            return
        for course in _value_sequence(raw):
            if isinstance(course, Mapping):
                _append_course_option(
                    rows,
                    _course_option(
                        _mapping_value(course, _COURSE_ID_KEYS),
                        _mapping_value(course, _COURSE_NAME_KEYS),
                    ),
                )
            else:
                # A scalar official-list item is retained as its official
                # label; no synthetic course name or ID is invented.
                _append_course_option(rows, _course_option(course_name=course))

    for key in _COURSE_COLLECTION_KEYS:
        add_collection(_mapping_value(requirement, (key,)))
    for nested_key in ("eligibility", "course_selection", "selection"):
        nested = _mapping_value(requirement, (nested_key,))
        if isinstance(nested, Mapping):
            for key in _COURSE_COLLECTION_KEYS:
                add_collection(_mapping_value(nested, (key,)))

    ids = _value_sequence(_mapping_value(requirement, ("eligible_course_ids", "course_ids")))
    names = _value_sequence(_mapping_value(requirement, ("eligible_course_names", "course_names")))
    for index in range(max(len(ids), len(names))):
        course_id = ids[index] if index < len(ids) else ""
        course_name = names[index] if index < len(names) else ""
        _append_course_option(rows, _course_option(course_id, course_name))
    return tuple(rows)


def _requirement_condition(requirement: Mapping[str, Any]) -> str:
    def readable(value: Any) -> str:
        if isinstance(value, Mapping):
            parts = []
            for key, item in value.items():
                if isinstance(item, Mapping):
                    nested = readable(item)
                elif _as_sequence(item):
                    nested = "、".join(_text(entry) for entry in _as_sequence(item) if _text(entry))
                else:
                    nested = _text(item)
                if nested:
                    parts.append(f"{key}：{nested}")
            return "；".join(parts)
        if _as_sequence(value):
            return "、".join(_text(item) for item in _as_sequence(value) if _text(item))
        return _text(value).strip()

    for key in _CONDITION_KEYS:
        value = _mapping_value(requirement, (key,))
        if isinstance(value, Mapping):
            nested = _mapping_value(value, ("text", "description", "label", "condition", "rule"))
            value = nested if nested is not None else value
        text = readable(value)
        if text:
            return text
    for nested_key in ("eligibility", "course_selection", "selection", "constraints"):
        nested = _mapping_value(requirement, (nested_key,))
        if not isinstance(nested, Mapping):
            continue
        for key in _CONDITION_KEYS:
            value = _mapping_value(nested, (key,))
            if isinstance(value, Mapping):
                nested_value = _mapping_value(value, ("text", "description", "label", "condition", "rule"))
                value = nested_value if nested_value is not None else value
            text = readable(value)
            if text:
                return text
    return MANUAL_LABEL


def _attempt_matches_option(attempt: Mapping[str, Any], option: Mapping[str, Any]) -> bool:
    attempt_id = _text(attempt.get("course_id")).strip().casefold()
    attempt_name = _text(attempt.get("course_name")).strip().casefold()
    option_id = _text(option.get("course_id")).strip().casefold()
    option_name = _text(option.get("course_name")).strip().casefold()
    return bool((option_id and option_id == attempt_id) or (option_name and option_name == attempt_name))


def _manual_reason(
    *,
    status: str,
    coverage_state: str,
    evidence_state: str,
    blockers: Sequence[Any],
    provenance: Sequence[Mapping[str, Any]],
) -> str:
    reasons: list[str] = []
    if status == UNKNOWN:
        reasons.append("判定狀態為 UNKNOWN")
    if coverage_state not in {"COMPLETE", "RESOLVED"}:
        reasons.append(f"課表覆蓋狀態為 {coverage_state or 'UNKNOWN'}")
    if evidence_state != "VERIFIED":
        reasons.append(f"證據狀態為 {evidence_state or 'UNKNOWN'}")
    reasons.extend(_text(item) for item in blockers if _text(item))
    if not provenance:
        reasons.append("沒有可追溯的規則來源")
    return MANUAL_LABEL + "：" + "；".join(dict.fromkeys(reasons)) if reasons else "可依快照中的官方證據判定。"


def _attempt_view(
    attempt: Mapping[str, Any],
    allocation: Mapping[str, Any],
    requirement_id: str,
    alternatives: Sequence[Any],
    *,
    evidence_state: str = "VERIFIED",
    force_unallocated_reason: bool = False,
) -> Mapping[str, Any]:
    portions = tuple(
        portion
        for portion in _as_sequence(allocation.get("portions"))
        if isinstance(portion, Mapping) and _text(portion.get("requirement_id")) == requirement_id
    )
    used = sum((_portion_credit(item) for item in portions), Decimal("0"))
    shared = any(_text(item.get("allocation_kind")).upper() in {"SHARED_SHADOW", "SHARED_REUSE"} for item in portions)
    allocation_kind = _text(portions[0].get("allocation_kind")) if portions else ""
    alternative_routes = _alternative_routes(alternatives, _text(attempt.get("attempt_id")), requirement_id)
    metadata_routes = _metadata_routes(attempt, requirement_id) + _metadata_routes(allocation, requirement_id)
    route_labels = tuple(dict.fromkeys((*alternative_routes, *metadata_routes)))
    if not route_labels:
        route_labels = ("沒有其他安全路徑",)
    identity_status = _text(attempt.get("identity_status"), UNKNOWN)
    status = _text(attempt.get("status"), UNKNOWN)
    evidence_verified = _text(evidence_state, UNKNOWN).upper() == "VERIFIED"
    identity_verified = identity_status.upper() == "VERIFIED"
    display_status = status
    if not identity_verified or not evidence_verified:
        display_status = UNKNOWN
    reason = _allocation_reason(allocation, portions)
    if force_unallocated_reason and not portions:
        if _as_sequence(allocation.get("portions")):
            reason = "此課程已配置至其他畢業要求，本要求未使用其學分。"
        else:
            reason = "此課程符合快照中的官方清單，但目前沒有安全配置至本要求。"
    if display_status == UNKNOWN and (not identity_verified or not evidence_verified):
        reason = MANUAL_LABEL + "：課程身分或要求證據尚不足以安全認列。"
    return {
        "attempt_id": _text(attempt.get("attempt_id")),
        "course_id": _text(attempt.get("course_id")),
        "course_name": _text(attempt.get("course_name")) or _text(attempt.get("course_id")),
        "academic_term": _text(attempt.get("academic_term")),
        "course_kind": _text(attempt.get("course_kind")),
        "status": display_status,
        "status_label": _status_label(display_status),
        "identity_status": identity_status,
        "source_credits": _text(attempt.get("credits")),
        "earned_credits": _text(attempt.get("earned_credits")),
        "used_credits": _credit(used),
        "unallocated_credits": _text(allocation.get("unallocated_credits"), "0"),
        "allocation_kind": allocation_kind,
        "allocation_kind_label": _allocation_kind_label(allocation_kind),
        "shared_credit": shared,
        "portions": tuple(_plain(item) for item in portions),
        "allocation_reason": reason,
        "alternative_routes": route_labels,
        "is_allocated": bool(portions),
        "is_not_attempted": False,
    }


def _not_attempted_view(option: Mapping[str, Any]) -> Mapping[str, Any]:
    course_id = _text(option.get("course_id"))
    course_name = _text(option.get("course_name"))
    return {
        "attempt_id": "",
        "course_id": course_id,
        "course_name": course_name or course_id,
        "academic_term": "",
        "course_kind": "",
        "status": "NOT_ATTEMPTED",
        "status_label": _status_label("NOT_ATTEMPTED"),
        "identity_status": "NOT_ATTEMPTED",
        "source_credits": "0",
        "earned_credits": "0",
        "used_credits": "0",
        "unallocated_credits": "0",
        "allocation_kind": "UNALLOCATED",
        "allocation_kind_label": _allocation_kind_label("UNALLOCATED"),
        "shared_credit": False,
        "portions": (),
        "allocation_reason": "官方課程清單中的科目尚未出現在已確認修課紀錄。",
        "alternative_routes": ("沒有其他安全路徑",),
        "is_allocated": False,
        "is_not_attempted": True,
    }


def _status_distribution(statistics: Mapping[str, Any], buckets: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    candidate = None
    for key in ("category_status_distribution", "bucket_status_distribution", "status_by_bucket", "by_bucket_status"):
        if isinstance(statistics.get(key), Mapping):
            candidate = statistics[key]
            break
    rows: list[Mapping[str, Any]] = []
    if isinstance(candidate, Mapping):
        for label, values in sorted(candidate.items(), key=lambda item: str(item[0])):
            if isinstance(values, Mapping):
                row = {"label": _text(label), **{str(key): value for key, value in values.items()}}
                rows.append(row)
            else:
                rows.append({"label": _text(label), "unknown": values, "total": values})
    if rows:
        return tuple(rows)
    # Effective bucket totals without a status split are deliberately shown as
    # "待確認" rather than being relabelled as completed credits.
    return tuple({"label": _text(label), "unknown": value, "total": value} for label, value in sorted(buckets.items(), key=lambda item: str(item[0])))


def _total_required(requirements: Sequence[Mapping[str, Any]]) -> str:
    for requirement in requirements:
        bucket = _text(requirement.get("bucket")).lower()
        kind = _text(requirement.get("kind")).lower()
        name = _text(requirement.get("name")).lower()
        if bucket in {"total", "graduation_total", "total_graduation"} or "total" in kind or "總" in name:
            return _text(requirement.get("credits_required"), "")
    return ""


def _summary(payload: Mapping[str, Any], requirements: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    allocation = payload.get("allocation") if isinstance(payload.get("allocation"), Mapping) else {}
    statistics = payload.get("statistics") if isinstance(payload.get("statistics"), Mapping) else {}
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), Mapping) else {}
    primary = decisions.get("primary_graduation") if isinstance(decisions.get("primary_graduation"), Mapping) else {}
    double = decisions.get("double_major_qualification") if isinstance(decisions.get("double_major_qualification"), Mapping) else {}
    formal_award = decisions.get("formal_double_major_award") if isinstance(decisions.get("formal_double_major_award"), Mapping) else {}
    input_confirmation = payload.get("input_confirmation") if isinstance(payload.get("input_confirmation"), Mapping) else {}
    by_bucket = statistics.get("by_bucket") if isinstance(statistics.get("by_bucket"), Mapping) else {}
    total_required = _text(
        statistics.get("required_graduation_credits")
        or statistics.get("graduation_requirement_total")
        or statistics.get("total_required_credits")
        or _total_required(requirements)
    )
    return {
        "verdict": _text(payload.get("verdict"), UNKNOWN),
        "total_graduation_credits": _text(statistics.get("total_graduation_credits"), MANUAL_LABEL),
        "required_graduation_credits": total_required or MANUAL_LABEL,
        "recognized_credits": _text(statistics.get("recognized_credits"), _text(allocation.get("recognized_credits"), MANUAL_LABEL)),
        "effective_recognized_credits": _text(statistics.get("effective_recognized_credits"), _text(allocation.get("effective_recognized_credits"), MANUAL_LABEL)),
        "unallocated_credits": _text(statistics.get("unallocated_credits"), _text(allocation.get("unallocated_credits"), MANUAL_LABEL)),
        "shared_shadow_credits": _text(statistics.get("shared_shadow_credits"), MANUAL_LABEL),
        "credit_conservation": statistics.get("credit_conservation", allocation.get("credit_conservation")),
        "primary_status": _text(primary.get("status"), UNKNOWN),
        "double_major_status": _text(double.get("status"), NOT_APPLICABLE),
        "formal_double_major_award_status": _text(formal_award.get("status"), NOT_APPLICABLE),
        "input_confirmation_state": _text(input_confirmation.get("state"), MANUAL_LABEL),
        "by_bucket": _plain(by_bucket),
        "requirement_status_counts": _plain(statistics.get("requirement_status_counts", {})),
        "course_status_counts": _plain(statistics.get("course_status_counts", {})),
        "completed": statistics.get("completed", MANUAL_LABEL),
        "in_progress": statistics.get("in_progress", MANUAL_LABEL),
        "missing": statistics.get(
            "missing",
            statistics.get(
                "deficit_count",
                len(_as_sequence(statistics.get("deficits"))) if "deficits" in statistics else MANUAL_LABEL,
            ),
        ),
        "unknown": statistics.get("unresolved", statistics.get("unknown", MANUAL_LABEL)),
        "reallocation": {
            "allocation_status": _text(allocation.get("status"), UNKNOWN),
            "recognized_credits": _text(allocation.get("recognized_credits"), MANUAL_LABEL),
            "unallocated_credits": _text(allocation.get("unallocated_credits"), MANUAL_LABEL),
            "shared_shadow_credits": _text(statistics.get("shared_shadow_credits"), MANUAL_LABEL),
            "credit_conservation": allocation.get("credit_conservation"),
            "allocation_ambiguous": allocation.get("allocation_ambiguous"),
            "alternative_count": len(_as_sequence(payload.get("alternatives") or allocation.get("alternative_allocations"))),
        },
        "blockers": tuple(_text(item) for item in _as_sequence(payload.get("blockers")) if _text(item)),
        "warnings": tuple(_text(item) for item in _as_sequence(payload.get("warnings")) if _text(item)),
        "remediation_suggestions": tuple(
            _text(item)
            for item in _as_sequence(payload.get("remediation_suggestions") or statistics.get("shortest_safe_remediation"))
            if _text(item)
        ),
    }


def build_snapshot_projection(snapshot: DecisionSnapshot) -> Mapping[str, Any]:
    """Build a deterministic, display-safe projection from one snapshot read."""

    payload = _snapshot_payload(snapshot)
    plain_payload = _plain(payload)
    requirements = tuple(item for item in plain_payload.get("requirements", ()) if isinstance(item, Mapping))
    attempts = tuple(item for item in plain_payload.get("attempts", ()) if isinstance(item, Mapping))
    allocation = plain_payload.get("allocation") if isinstance(plain_payload.get("allocation"), Mapping) else {}
    attempt_allocations = {
        _text(item.get("attempt_id")): item
        for item in _as_sequence(allocation.get("allocations"))
        if isinstance(item, Mapping) and _text(item.get("attempt_id"))
    }
    result_by_requirement = {
        _text(item.get("requirement_id")): item
        for item in _as_sequence(allocation.get("requirement_results"))
        if isinstance(item, Mapping) and _text(item.get("requirement_id"))
    }
    alternatives = tuple(plain_payload.get("alternatives") or allocation.get("alternative_allocations") or ())
    provenance = tuple(item for item in plain_payload.get("rule_provenance", ()) if isinstance(item, Mapping))
    requirement_views: list[Mapping[str, Any]] = []
    for requirement in requirements:
        requirement_id = _text(requirement.get("requirement_id"))
        result = result_by_requirement.get(requirement_id, {})
        status = _text(result.get("status"), UNKNOWN)
        requirement_provenance = _provenance_view(_provenance_for(requirement_id, provenance))
        blockers = tuple(_text(item) for item in _as_sequence(result.get("blockers")) if _text(item))
        eligible_courses = _eligible_course_options(requirement)
        choice_condition = _requirement_condition(requirement)
        coverage_state = _text(result.get("coverage_state"), _text(requirement.get("coverage_state"), UNKNOWN))
        evidence_state = _text(result.get("evidence_state"), _text(requirement.get("evidence_state"), UNKNOWN))
        if status not in {NOT_APPLICABLE, UNKNOWN} and (
            coverage_state.upper() not in {"COMPLETE", "RESOLVED"} or evidence_state.upper() != "VERIFIED"
        ):
            # A positive allocator status cannot be presented as PASS when
            # the snapshot itself says its official coverage/evidence is not
            # complete.  This is a fail-closed display guard, not a rebuild
            # of the allocation decision.
            status = UNKNOWN
        course_views: list[Mapping[str, Any]] = []
        matched_attempt_ids: set[str] = set()
        for attempt in attempts:
            attempt_id = _text(attempt.get("attempt_id"))
            allocation_item = attempt_allocations.get(attempt_id)
            if allocation_item is None:
                continue
            portions = tuple(
                portion
                for portion in _as_sequence(allocation_item.get("portions"))
                if isinstance(portion, Mapping) and _text(portion.get("requirement_id")) == requirement_id
            )
            if portions:
                course_views.append(
                    _attempt_view(
                        attempt,
                        allocation_item,
                        requirement_id,
                        alternatives,
                        evidence_state=evidence_state,
                    )
                )
                if attempt_id:
                    matched_attempt_ids.add(attempt_id)
        # An official list is descriptive evidence carried by the snapshot;
        # it is not reconstructed from the allocator.  Join only by the
        # explicit course ID/name values and show all other states honestly.
        for option in eligible_courses:
            matches = [attempt for attempt in attempts if _attempt_matches_option(attempt, option)]
            unmatched = [attempt for attempt in matches if _text(attempt.get("attempt_id")) not in matched_attempt_ids]
            if unmatched:
                for attempt in unmatched:
                    attempt_id = _text(attempt.get("attempt_id"))
                    allocation_item = attempt_allocations.get(attempt_id, {})
                    course_views.append(
                        _attempt_view(
                            attempt,
                            allocation_item,
                            requirement_id,
                            alternatives,
                            evidence_state=evidence_state,
                            force_unallocated_reason=True,
                        )
                    )
                    if attempt_id:
                        matched_attempt_ids.add(attempt_id)
            elif not matches:
                course_views.append(_not_attempted_view(option))
        requirement_views.append(
            {
                "requirement_id": requirement_id,
                "name": _text(requirement.get("name"), requirement_id),
                "kind": _requirement_kind_label(requirement),
                "bucket": _text(requirement.get("bucket")),
                "required_credits": _text(result.get("required_credits"), _text(requirement.get("credits_required"), MANUAL_LABEL)),
                "max_credits": _text(requirement.get("max_credits"), MANUAL_LABEL),
                "exclusive_credits": _text(result.get("exclusive_credits"), MANUAL_LABEL),
                "shared_credits": _text(result.get("shared_shadow_credits"), MANUAL_LABEL),
                "effective_credits": _text(result.get("effective_credits"), MANUAL_LABEL),
                "deficit": _text(result.get("deficit"), MANUAL_LABEL),
                "status": status,
                "status_label": _status_label(status),
                "coverage_state": coverage_state,
                "evidence_state": evidence_state,
                "waived": bool(result.get("waived", requirement.get("waiver", False))),
                "blockers": blockers,
                "rule_provenance": requirement_provenance,
                "manual_confirmation": _manual_reason(
                    status=status,
                    coverage_state=coverage_state,
                    evidence_state=evidence_state,
                    blockers=blockers,
                    provenance=requirement_provenance,
                ),
                "eligible_courses": tuple(_plain(item) for item in eligible_courses),
                "choice_condition": choice_condition,
                "courses": tuple(course_views),
                "has_shared_credit": any(course.get("shared_credit") for course in course_views),
            }
        )

    summary = _summary(plain_payload, requirements)
    statistics = plain_payload.get("statistics") if isinstance(plain_payload.get("statistics"), Mapping) else {}
    context_request = plain_payload.get("request") if isinstance(plain_payload.get("request"), Mapping) else {}
    context = {
        key: context_request[key]
        for key in (
            "admission_cohort",
            "primary_curriculum_id",
            "target_curriculum_id",
            "target_curriculum_version",
            "target_curriculum_version_candidate",
            "target_program",
            "target_track",
            "application_term",
            "application_year",
            "application_semester",
            "application_status",
            "school_approval_status",
            "formal_qualification_status",
            "formal_award_status",
            "masked_student_id",
        )
        if key in context_request and context_request[key] not in (None, "")
    }
    if "masked_student_id" not in context:
        masked_student_id = plain_payload.get("masked_student_id")
        if masked_student_id not in (None, ""):
            context["masked_student_id"] = masked_student_id
    return {
        "_projection_schema": "snapshot-presentation.v1",
        "_source": "DecisionSnapshot",
        "snapshot_id": _text(plain_payload.get("snapshot_id")),
        "_snapshot_id": _text(plain_payload.get("snapshot_id")),
        "evaluated_at": _text(plain_payload.get("evaluated_at")),
        "verdict": _text(plain_payload.get("verdict"), UNKNOWN),
        "context": context,
        "summary": summary,
        "decisions": _plain(plain_payload.get("decisions", {})),
        "attempts": tuple(_plain(item) for item in attempts),
        "requirements": tuple(requirement_views),
        "allocations": _plain(_as_sequence(allocation.get("allocations"))),
        "allocation": _plain(allocation),
        "alternatives": _plain(alternatives),
        "statistics": _plain(statistics),
        "rule_provenance": _provenance_view(provenance),
        "blockers": tuple(summary["blockers"]),
        "warnings": tuple(summary["warnings"]),
        "remediation_suggestions": tuple(summary["remediation_suggestions"]),
        "input_confirmation": _plain(plain_payload.get("input_confirmation", {})),
    }


def _status_class(status: Any) -> str:
    normalized = _text(status).upper()
    return {
        PASS: "is-pass",
        FAIL: "is-fail",
        UNKNOWN: "is-unknown",
        NOT_APPLICABLE: "is-na",
    }.get(normalized, "is-unknown")


def _metric(label: str, value: Any, detail: Any = "") -> str:
    detail_markup = f'<small>{_escape(detail)}</small>' if detail not in (None, "") else ""
    return f'<article class="snapshot-metric"><span>{_escape(label)}</span><strong>{_escape(value)}</strong>{detail_markup}</article>'


def _course_markup(course: Mapping[str, Any]) -> str:
    shared = '<span class="snapshot-shared">雙主修共享</span>' if course.get("shared_credit") else ""
    route_markup = "、".join(_text(item) for item in _as_sequence(course.get("alternative_routes")) if _text(item))
    course_label = _text(course.get("course_name")) or _text(course.get("course_id")) or MANUAL_LABEL
    meta = " · ".join(
        _text(value)
        for value in (course.get("course_id"), course.get("academic_term"))
        if _text(value)
    )
    return (
        '<li class="snapshot-course">'
        f'<div class="snapshot-course-main"><strong>{_escape(course_label)}</strong>{shared}'
        f'<span class="snapshot-course-meta">{_escape(meta)}</span></div>'
        f'<div class="snapshot-course-status"><span class="snapshot-badge {_status_class(course.get("status"))}">{_escape(course.get("status_label"))}</span>'
        f'<span>使用學分：{_escape(course.get("used_credits"))}</span>'
        f'<span>認列狀態：{_escape("已認列" if course.get("is_allocated") else "未配置")}</span></div>'
        f'<p>課程身分／證據：{_escape(course.get("identity_status"))}</p>'
        f'<p>配置：{_escape(course.get("allocation_kind_label"))}。配置原因：{_escape(course.get("allocation_reason"))}</p>'
        f'<p>未配置學分：{_escape(course.get("unallocated_credits"))}</p>'
        f'<p>其他安全路徑：{_escape(route_markup or "沒有其他安全路徑")}</p>'
        '</li>'
    )


def _eligible_course_markup(requirement: Mapping[str, Any]) -> str:
    options = _as_sequence(requirement.get("eligible_courses"))
    rows: list[str] = []
    for option in options:
        if not isinstance(option, Mapping):
            continue
        course_id = _text(option.get("course_id"))
        course_name = _text(option.get("course_name"))
        label = course_name or course_id or MANUAL_LABEL
        meta = f"（{course_id}）" if course_id and course_name else ""
        rows.append(f"<li><strong>{_escape(label)}</strong>{_escape(meta)}</li>")
    return "".join(rows) or f'<li class="snapshot-course--empty">{_escape(MANUAL_LABEL)}</li>'


def _requirement_markup(requirement: Mapping[str, Any]) -> str:
    courses = _as_sequence(requirement.get("courses"))
    course_markup = "".join(_course_markup(course) for course in courses if isinstance(course, Mapping))
    if not course_markup:
        course_markup = '<li class="snapshot-course snapshot-course--empty"><span class="snapshot-badge is-unknown">未配置／待確認</span> 目前沒有已配置課程；若有相容課程，仍須依快照中的規則與證據確認。</li>'
    provenance = _as_sequence(requirement.get("rule_provenance"))
    provenance_markup = "".join(
        "<li>"
        + " · ".join(
            _escape(item.get(key))
            for key in ("source_reference", "source_location", "source_file", "pages", "authority", "evidence_reference")
            if isinstance(item, Mapping) and item.get(key) not in (None, "")
        )
        + "</li>"
        for item in provenance
        if isinstance(item, Mapping)
    ) or f"<li>{_escape(MANUAL_LABEL)}</li>"
    status = _text(requirement.get("status"), UNKNOWN)
    return (
        f'<details class="snapshot-requirement-expander" data-requirement-id="{_escape(requirement.get("requirement_id"))}">'
        '<summary><span class="snapshot-requirement-title">'
        f'{_escape(requirement.get("name"))} · {_escape(requirement.get("kind"))}</span>'
        f'<span class="snapshot-requirement-progress">{_escape(requirement.get("effective_credits"))} / {_escape(requirement.get("required_credits"))} 學分 · '
        f'<span class="snapshot-badge {_status_class(status)}">{_escape(requirement.get("status_label"))}</span></span></summary>'
        '<div class="snapshot-requirement-body">'
        '<dl class="snapshot-requirement-facts">'
        f'<div><dt>要求學分</dt><dd>{_escape(requirement.get("required_credits"))}</dd></div>'
        f'<div><dt>實際配置</dt><dd>{_escape(requirement.get("effective_credits"))}</dd></div>'
        f'<div><dt>正式配置</dt><dd>{_escape(requirement.get("exclusive_credits"))}</dd></div>'
        f'<div><dt>共享配置</dt><dd>{_escape(requirement.get("shared_credits"))}</dd></div>'
        f'<div><dt>尚缺</dt><dd>{_escape(requirement.get("deficit"))}</dd></div>'
        f'<div><dt>覆蓋／證據</dt><dd>{_escape(requirement.get("coverage_state"))}／{_escape(requirement.get("evidence_state"))}</dd></div>'
        '</dl>'
        f'<p class="snapshot-manual-note">{_escape(requirement.get("manual_confirmation"))}</p>'
        f'<p class="snapshot-blocker-note">阻塞：{_escape("；".join(_text(item) for item in _as_sequence(requirement.get("blockers"))) or "無")}</p>'
        '<h4>官方可選／指定科目</h4><ul class="snapshot-course-options">'
        f'{_eligible_course_markup(requirement)}</ul>'
        f'<p class="snapshot-choice-condition">修課條件：{_escape(requirement.get("choice_condition"))}</p>'
        '<h4>課程配置明細</h4><ul class="snapshot-course-list">'
        f'{course_markup}</ul>'
        f'<h4>規則來源</h4><ul class="snapshot-provenance-list">{provenance_markup}</ul>'
        '</div></details>'
    )


def render_snapshot(snapshot: DecisionSnapshot) -> str:
    """Render the complete responsive HTML view from one DecisionSnapshot."""

    view = build_snapshot_projection(snapshot)
    summary = view["summary"]
    requirements = tuple(item for item in view["requirements"] if isinstance(item, Mapping))
    charts_source = f"DecisionSnapshot {_text(view.get('snapshot_id'))}"
    threshold_rows = [
        {
            "label": item.get("name"),
            "completed": item.get("effective_credits"),
            "required": item.get("required_credits"),
            "unit": "學分",
        }
        for item in requirements
    ]
    # F5 is a threshold overview, not the source of truth.  The complete
    # expandable requirement list below remains the authoritative detail.
    f5 = render_f5_tick_rows(threshold_rows, source=charts_source, title="畢業門檻進度（F5 Tick Rows）")
    required_total = summary.get("required_graduation_credits")
    completed_total = summary.get("effective_recognized_credits")
    f11 = render_f11_tick_gauge(completed_total, required_total, source=charts_source, title="總畢業學分完成度")
    f7 = render_f7_stacked_rungs(
        _status_distribution(view.get("statistics", {}), summary.get("by_bucket", {})),
        source=charts_source,
        title="分類學分狀態分布（F7 Stacked Rungs）",
    )
    decision_rows = []
    for key, decision in (view.get("decisions") or {}).items():
        if isinstance(decision, Mapping):
            status = _text(decision.get("status"), UNKNOWN)
            is_self_report = key == "application_self_report" or decision.get("authoritative") is False
            if is_self_report:
                status = UNKNOWN
            label = "申請狀態（使用者自述）" if key == "application_self_report" else key
            reason = _text(decision.get("reason"))
            if is_self_report:
                claimed = _text(decision.get("claimed_state"), "使用者未提供自述")
                reason = f"{claimed}；{reason}" if reason else claimed
            decision_rows.append(
                f'<li><span>{_escape(label)}</span><span class="snapshot-badge {_status_class(status)}">{_escape("待確認" if is_self_report else status)}</span>'
                f'<small>{_escape(reason)}</small></li>'
            )
    decision_markup = "".join(decision_rows) or f'<li>{_escape(MANUAL_LABEL)}</li>'
    bucket_rows = "".join(
        f'<li><span>{_escape(key)}</span><strong>{_escape(value)} 學分</strong></li>'
        for key, value in sorted((summary.get("by_bucket") or {}).items(), key=lambda item: str(item[0]))
    ) or f'<li>{_escape(MANUAL_LABEL)}</li>'
    blocker_markup = "".join(f"<li>{_escape(item)}</li>" for item in summary.get("blockers", ())) or "<li>無</li>"
    warning_markup = "".join(f"<li>{_escape(item)}</li>" for item in summary.get("warnings", ())) or "<li>無</li>"
    remediation_markup = "".join(f"<li>{_escape(item)}</li>" for item in summary.get("remediation_suggestions", ())) or f"<li>{_escape(MANUAL_LABEL)}</li>"
    context_markup = " · ".join(f"{_escape(key)}：{_escape(value)}" for key, value in (view.get("context") or {}).items()) or _escape(MANUAL_LABEL)
    css = """
    .snapshot-report {
      --snapshot-bg: #F8FAFC; --snapshot-card: #FFFFFF; --snapshot-text: #0F172A;
      --snapshot-muted: #475569; --snapshot-border: #CBD5E1; --snapshot-primary: #1E3A5F;
      --snapshot-action: #2563EB; background: var(--snapshot-bg); color: var(--snapshot-text);
      box-sizing: border-box; font-family: "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
      line-height: 1.6; max-width: 100%; overflow-wrap: anywhere; padding: 1rem;
    }
    .snapshot-report *, .snapshot-report *::before, .snapshot-report *::after { box-sizing: border-box; }
    .snapshot-report h1, .snapshot-report h2, .snapshot-report h3, .snapshot-report h4 { color: var(--snapshot-text); line-height: 1.35; margin: 0; }
    .snapshot-report h1 { font-size: clamp(1.35rem, 4vw, 2rem); }
    .snapshot-report h2 { font-size: 1.2rem; margin-block: 1.5rem .75rem; }
    .snapshot-report h3 { font-size: 1rem; margin-block: 1rem .5rem; }
    .snapshot-report h4 { font-size: .94rem; margin-block: 1rem .4rem; }
    .snapshot-report p { margin: .45rem 0; }
    .snapshot-header { align-items: start; display: flex; flex-wrap: wrap; gap: .75rem 1.5rem; justify-content: space-between; }
    .snapshot-kicker, .snapshot-context, .snapshot-muted { color: var(--snapshot-muted); font-size: .84rem; }
    .snapshot-kicker { margin: .25rem 0 0; }
    .snapshot-context { border-bottom: 1px solid var(--snapshot-border); padding: .65rem 0 1rem; }
    .snapshot-card { background: var(--snapshot-card); border: 1px solid var(--snapshot-border); border-radius: .85rem; margin-block: .75rem; padding: 1rem; }
    .snapshot-metrics { display: grid; gap: .7rem; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); margin-block: 1rem; }
    .snapshot-metric { background: var(--snapshot-card); border: 1px solid var(--snapshot-border); border-radius: .7rem; display: grid; gap: .15rem; padding: .75rem; }
    .snapshot-metric span, .snapshot-metric small { color: var(--snapshot-muted); font-size: .78rem; }
    .snapshot-metric strong { font-size: 1.25rem; font-variant-numeric: tabular-nums; }
    .snapshot-badge { border: 1px solid currentColor; border-radius: 999px; display: inline-block; font-size: .75rem; font-weight: 800; line-height: 1.35; padding: .12rem .45rem; white-space: nowrap; }
    .snapshot-badge.is-pass { color: #166534; } .snapshot-badge.is-fail { color: #B91C1C; }
    .snapshot-badge.is-unknown { color: #92400E; } .snapshot-badge.is-na { color: var(--snapshot-muted); }
    .snapshot-decision-list, .snapshot-simple-list, .snapshot-provenance-list, .snapshot-course-list, .snapshot-course-options { list-style: none; margin: 0; padding: 0; }
    .snapshot-decision-list li { align-items: start; border-bottom: 1px solid var(--snapshot-border); display: grid; gap: .35rem; grid-template-columns: minmax(8rem, 1fr) auto; padding: .6rem 0; }
    .snapshot-decision-list small { color: var(--snapshot-muted); grid-column: 1 / -1; }
    .snapshot-simple-list li { align-items: center; border-bottom: 1px solid var(--snapshot-border); display: flex; gap: .75rem; justify-content: space-between; padding: .4rem 0; }
    .snapshot-simple-list strong { font-variant-numeric: tabular-nums; }
    .snapshot-chart-details { border-top: 1px solid var(--snapshot-border); margin-top: 1rem; }
    .snapshot-chart-details summary { color: var(--snapshot-primary); cursor: pointer; font-weight: 800; min-block-size: 2.75rem; padding: .65rem 0; }
    .snapshot-requirement-expander { background: var(--snapshot-card); border: 1px solid var(--snapshot-border); border-radius: .75rem; margin-block: .7rem; }
    .snapshot-requirement-expander summary { align-items: center; cursor: pointer; display: flex; flex-wrap: wrap; gap: .45rem 1rem; justify-content: space-between; list-style: none; min-block-size: 2.9rem; padding: .75rem 1rem; }
    .snapshot-requirement-expander summary::-webkit-details-marker { display: none; }
    .snapshot-requirement-title { font-weight: 800; }
    .snapshot-requirement-progress { color: var(--snapshot-muted); font-variant-numeric: tabular-nums; }
    .snapshot-requirement-body { border-top: 1px solid var(--snapshot-border); padding: .8rem 1rem 1rem; }
    .snapshot-requirement-facts { display: grid; gap: .5rem; grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); margin: 0; }
    .snapshot-requirement-facts div { border: 1px solid var(--snapshot-border); border-radius: .55rem; padding: .45rem .6rem; }
    .snapshot-requirement-facts dt { color: var(--snapshot-muted); font-size: .75rem; }
    .snapshot-requirement-facts dd { font-size: .95rem; font-variant-numeric: tabular-nums; margin: 0; }
    .snapshot-manual-note { background: color-mix(in srgb, #F59E0B 12%, var(--snapshot-card)); border-inline-start: .25rem solid #B45309; padding: .55rem .7rem; }
    .snapshot-blocker-note { color: var(--snapshot-muted); font-size: .82rem; }
    .snapshot-course { border: 1px solid var(--snapshot-border); border-radius: .6rem; margin-block: .55rem; padding: .65rem .75rem; }
    .snapshot-course-options li { border-bottom: 1px solid var(--snapshot-border); padding: .4rem 0; }
    .snapshot-course-main, .snapshot-course-status { align-items: center; display: flex; flex-wrap: wrap; gap: .35rem .6rem; justify-content: space-between; }
    .snapshot-course-meta { color: var(--snapshot-muted); font-size: .78rem; }
    .snapshot-course-status { color: var(--snapshot-muted); font-size: .82rem; justify-content: start; margin-top: .3rem; }
    .snapshot-course p { color: var(--snapshot-muted); font-size: .82rem; }
    .snapshot-shared { border: 1px solid var(--snapshot-action); border-radius: 999px; color: var(--snapshot-action); font-size: .72rem; padding: .12rem .4rem; }
    .snapshot-course--empty { color: var(--snapshot-muted); }
    .snapshot-provenance-list li { border-bottom: 1px solid var(--snapshot-border); color: var(--snapshot-muted); font-size: .78rem; padding: .4rem 0; }
    .snapshot-status-block { display: grid; gap: .8rem; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); }
     @media (prefers-color-scheme: dark) { .snapshot-report { --snapshot-bg: #0B1120; --snapshot-card: #111827; --snapshot-text: #F8FAFC; --snapshot-muted: #CBD5E1; --snapshot-border: #334155; --snapshot-primary: #60A5FA; --snapshot-action: #60A5FA; } .snapshot-badge.is-pass { color: #86EFAC; } .snapshot-badge.is-fail { color: #FCA5A5; } .snapshot-badge.is-unknown { color: #FCD34D; } }
     html[data-theme="light"] .snapshot-report, body[data-theme="light"] .snapshot-report { --snapshot-bg: #F8FAFC; --snapshot-card: #FFFFFF; --snapshot-text: #0F172A; --snapshot-muted: #475569; --snapshot-border: #CBD5E1; --snapshot-primary: #1E3A5F; --snapshot-action: #2563EB; }
     html[data-theme="dark"] .snapshot-report, body[data-theme="dark"] .snapshot-report { --snapshot-bg: #0B1120; --snapshot-card: #111827; --snapshot-text: #F8FAFC; --snapshot-muted: #CBD5E1; --snapshot-border: #334155; --snapshot-primary: #60A5FA; --snapshot-action: #60A5FA; }
     html[data-utaipei-theme="light"] .snapshot-report { --snapshot-bg: #F8FAFC; --snapshot-card: #FFFFFF; --snapshot-text: #0F172A; --snapshot-muted: #475569; --snapshot-border: #CBD5E1; --snapshot-primary: #1E3A5F; --snapshot-action: #2563EB; }
     html[data-utaipei-theme="dark"] .snapshot-report { --snapshot-bg: #0B1120; --snapshot-card: #111827; --snapshot-text: #F8FAFC; --snapshot-muted: #CBD5E1; --snapshot-border: #334155; --snapshot-primary: #60A5FA; --snapshot-action: #60A5FA; }
     html[data-utaipei-theme="light"] .snapshot-report .snapshot-badge.is-pass { color: #166534; }
     html[data-utaipei-theme="light"] .snapshot-report .snapshot-badge.is-fail { color: #B91C1C; }
     html[data-utaipei-theme="light"] .snapshot-report .snapshot-badge.is-unknown { color: #92400E; }
     html[data-utaipei-theme="dark"] .snapshot-report .snapshot-badge.is-pass { color: #86EFAC; }
     html[data-utaipei-theme="dark"] .snapshot-report .snapshot-badge.is-fail { color: #FCA5A5; }
     html[data-utaipei-theme="dark"] .snapshot-report .snapshot-badge.is-unknown { color: #FCD34D; }
     @media (prefers-reduced-motion: reduce) { .snapshot-report * { animation: none !important; transition: none !important; } }
    @media (max-width: 600px) { .snapshot-report { padding-inline: .25rem; } .snapshot-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } .snapshot-requirement-expander summary { align-items: start; flex-direction: column; } }
    """
    snapshot_id = _escape(view.get("snapshot_id"))
    total_detail = f"要求總量：{summary.get('required_graduation_credits')}"
    progress_detail = f"{summary.get('completed')}／{summary.get('in_progress')}"
    deficit_detail = f"{summary.get('missing')}／{summary.get('unknown')}"
    return (
        f'<section id="utaipei-snapshot-report" class="snapshot-report" data-snapshot-id="{snapshot_id}" data-verdict="{_escape(view.get("verdict"))}">'
        f'<style>{css}</style><span id="utaipei-analysis-state" data-analysis-active="true" data-exported="false" hidden></span>'
        '<header class="snapshot-header"><div><h1>北市大畢業通</h1>'
        f'<p class="snapshot-kicker">DecisionSnapshot · {_escape(view.get("snapshot_id"))} · 評估時間 {_escape(view.get("evaluated_at"))}</p></div>'
        f'<span class="snapshot-badge {_status_class(view.get("verdict"))}">{_escape(view.get("verdict"))}</span></header>'
        f'<p class="snapshot-context">{context_markup}</p>'
        '<div class="snapshot-metrics">'
        f'{_metric("總畢業學分", summary.get("total_graduation_credits"), total_detail)}'
        f'{_metric("主修完成度", summary.get("primary_status"))}'
        f'{_metric("雙主修完成度", summary.get("double_major_status"))}'
        f'{_metric("正式授予雙主修", summary.get("formal_double_major_award_status"))}'
        f'{_metric("資料確認狀態", summary.get("input_confirmation_state"))}'
        f'{_metric("已完成／修習中", progress_detail)}'
        f'{_metric("尚缺／待確認", deficit_detail)}'
        '</div>'
        '<section class="snapshot-card"><h2>判定摘要</h2><ul class="snapshot-decision-list">'
        f'{decision_markup}</ul></section>'
        '<section class="snapshot-card"><h2>統計與重新配置</h2><div class="snapshot-status-block">'
        f'<div><h3>分類學分</h3><ul class="snapshot-simple-list">{bucket_rows}</ul></div>'
        f'<div><h3>重新配置</h3><ul class="snapshot-simple-list"><li><span>已認列</span><strong>{_escape(summary.get("recognized_credits"))}</strong></li><li><span>尚未配置</span><strong>{_escape(summary.get("unallocated_credits"))}</strong></li><li><span>共享影子學分</span><strong>{_escape(summary.get("shared_shadow_credits"))}</strong></li><li><span>學分守恆</span><strong>{_escape(summary.get("credit_conservation"))}</strong></li></ul></div>'
        '</div></section>'
        '<section class="snapshot-card"><h2>Lieflat Charts</h2>'
        f'<details class="snapshot-chart-details"><summary>總畢業學分完成度圖表</summary>{f11}</details>'
        f'<details class="snapshot-chart-details"><summary>分類狀態分布圖表</summary>{f7}</details>'
        f'<details class="snapshot-chart-details"><summary>門檻進度與精確數字</summary>{f5}</details>'
        '</section>'
        '<section><h2>畢業要求與課程配置</h2>'
        f'{"".join(_requirement_markup(item) for item in requirements)}'
        '</section>'
        '<section class="snapshot-card"><h2>畢業阻塞項目</h2><ul class="snapshot-simple-list">'
        f'{blocker_markup}</ul><h3>警告</h3><ul class="snapshot-simple-list">{warning_markup}</ul>'
        '<h3>最短安全補修建議</h3><ul class="snapshot-simple-list">'
        f'{remediation_markup}</ul></section>'
        '</section>'
    )


# Stable integration names for the application layer.
build_snapshot_view = build_snapshot_projection
render_snapshot_html = render_snapshot
render_decision_snapshot = render_snapshot


__all__ = [
    "MANUAL_LABEL",
    "build_snapshot_projection",
    "build_snapshot_view",
    "render_decision_snapshot",
    "render_snapshot",
    "render_snapshot_html",
    "sanitize_snapshot_value",
]
