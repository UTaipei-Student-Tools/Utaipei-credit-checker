"""Snapshot-only HTML presentation for 北市大畢業通.

The renderer is deliberately a *consumer* of :class:`DecisionSnapshot`, not
another graduation engine.  It calls ``snapshot.as_dict()`` exactly once,
then joins the immutable allocation projection with its requirement and
attempt records for display.  No rule, curriculum, application, or allocator
module is imported here.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from decision_snapshot import DecisionSnapshot
from lieflat_progress_chart import (
    render_chart_unavailable,
    render_f1_rung_bars,
    render_f5_tick_rows,
    render_f7_stacked_rungs,
    render_f11_tick_gauge,
)
from snapshot_projection import (
    PROJECTION_SCHEMA_VERSION,
    build_chart_datasets,
    statistics_projection_from_payload,
)

UNKNOWN = "UNKNOWN"
PASS = "PASS"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"
MANUAL_LABEL = "資料不足／需人工確認"

# Snapshot values remain machine-readable in the projection and audit JSON.
# These labels are the only vocabulary allowed to cross into the student view.
PUBLIC_PENDING = "需要補資料"
PUBLIC_NOT_APPLICABLE = "不適用"

_INPUT_CONFIRMATION_LABELS = {
    "CONFIRMED": "已確認",
    "PARSED": "待確認",
    "STALE": "資料已變更",
    "UNCONFIRMED": "待補資料",
    "PENDING": "待確認",
}

_PUBLIC_STATUS_LABELS = {
    PASS: "已完成",
    "COMPLETED": "已完成",
    "VERIFIED": "已核對",
    "IN_PROGRESS": "修習中",
    "IP": "修習中",
    FAIL: "尚未完成",
    "FAILED": "尚未完成",
    "W": "停修／未完成",
    "WITHDRAWN": "停修／未完成",
    "WAIVER": "免修／抵認",
    "WAIVED": "免修／抵認",
    "TRANSFERRED": "抵免／抵認",
    "NOT_ATTEMPTED": "尚未修課",
    "NOT_TAKEN": "尚未修課",
    "MISSING": "尚未修課",
    "UNALLOCATED": "尚未配置",
    UNKNOWN: PUBLIC_PENDING,
    "PENDING": PUBLIC_PENDING,
    "MANUAL_REVIEW": PUBLIC_PENDING,
    "CONFLICTED": "資料互相矛盾",
    NOT_APPLICABLE: PUBLIC_NOT_APPLICABLE,
}

_PUBLIC_TERM_REPLACEMENTS = (
    ("F1", "採計學分圖表"),
    ("F5", "要求進度圖表"),
    ("F7", "狀態分布圖表"),
    ("F11", "總學分圖表"),
    ("DecisionSnapshot", "本次分析資料"),
    ("decision-statistics.v2", "學分統計資料"),
    ("UNKNOWN", PUBLIC_PENDING),
    ("NOT_APPLICABLE", PUBLIC_NOT_APPLICABLE),
    ("EXCLUSIVE_REQUIREMENT_ROUTE", "依本要求採計"),
    ("EXCLUSIVE", "本要求採計"),
    ("SHARED_SHADOW", "共同課程採計"),
    ("SHARED_REUSE", "共同課程採計"),
    ("shadow", "共同課程採計"),
    ("DIRECTION_ONLY", "提供修課方向"),
    ("MANUAL_REVIEW", "需要人工核對"),
    ("VERIFIED", "來源已核對"),
    ("CONFLICTED", "資料互相矛盾"),
    ("PARTIAL", "來源尚未完整"),
    ("COMPLETE", "規則資料完整"),
    ("MISSING", "缺少來源資料"),
)

_PUBLIC_CODE_REASONS = {
    "AGGREGATE_GATE_UNAVAILABLE": "尚未找到可核對的主修總學分門檻。",
    "AGGREGATE_GATE_STATUS_UNKNOWN": "主修總學分門檻仍需人工核對。",
    "CREDIT_CONSERVATION_FAILED": "成績學分與採計結果無法相互核對，請重新確認成績列。",
    "PRIMARY_AGGREGATE_NUMERATOR_UNVERIFIED": "主修總學分的已採計數字缺少可追溯來源。",
    "INCOMPLETE_EVIDENCE_OR_COVERAGE": "課程清單或規則來源尚未完整，請查看規則來源並補齊資料。",
    "RULE_CONTEXT:MANUAL_REVIEW": "適用規則版本仍需人工核對。",
    "RULE_CONTEXT": "適用規則版本仍需人工核對。",
    "CURRICULUM_UNRESOLVED": "適用課程版本尚未確認。",
    "EVIDENCE_UNRESOLVED": "規則來源尚未取得，請補充可核對的資料。",
    "REQUIREMENT_RESULT": "要求項目的採計結果需要重新核對。",
    "ALLOCATION": "課程採計結果需要重新核對。",
    "NON_CREDIT_DEFICIT": "非學分門檻尚有缺項，請依規則補足。",
    "OFFICIAL_EVIDENCE_MISSING": "規則來源尚未取得，請補充可核對的官方資料。",
    "RULE_POLICY_SCOPE_UNVERIFIED": "適用規則範圍尚待核對。",
    "RULE_POLICY_EVIDENCE_INCOMPLETE": "規則來源尚未完整，請查看來源並補充資料。",
    "RULE_POLICY_METADATA_MISSING": "規則資料尚未完整，請查看來源並人工核對。",
    "RULE_POLICY_SOURCE_MISSING": "規則來源尚未取得，請補充可核對的手冊資料。",
    "RULE_NOT_IMPLEMENTED": "此門檻的核對方式尚未完整設定，請人工確認。",
    "MANUAL_DECISION_REQUIRED": "此門檻需要人工確認。",
    "STUDENT_INPUT_MISSING": "成績資料缺少必要欄位，請補充後再核對。",
    "SUBSET_CONSTRAINT_INVALID": "學分採計條件資料不完整，請查看規則來源。",
    "SUBSET_CONSTRAINT_EVIDENCE_UNKNOWN": "學分採計條件的來源尚待核對。",
    "SUBSET_CONSTRAINT_DEFICIT": "學分採計條件尚有缺額，請依規則補足。",
}

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


def _public_status_label(status: Any, fallback: str = PUBLIC_PENDING) -> str:
    """Translate an internal status into a short action-oriented label."""

    normalized = _text(status).strip().upper().replace("-", "_").replace(" ", "_")
    return _PUBLIC_STATUS_LABELS.get(normalized, fallback)


def _public_status_slug(status: Any) -> str:
    """Return a stable, non-technical value for a DOM status attribute."""

    normalized = _text(status).strip().upper().replace("-", "_").replace(" ", "_")
    return {
        PASS: "complete",
        "COMPLETED": "complete",
        FAIL: "incomplete",
        "FAILED": "incomplete",
        "IN_PROGRESS": "in-progress",
        "IP": "in-progress",
        NOT_APPLICABLE: "not-applicable",
    }.get(normalized, "needs-information")


def _input_confirmation_label(state: Any) -> str:
    """Translate the transcript confirmation state without exposing codes."""

    normalized = _text(state).strip().upper().replace("-", "_").replace(" ", "_")
    return _INPUT_CONFIRMATION_LABELS.get(normalized, "需要補資料")


def _public_text(value: Any, fallback: str = PUBLIC_PENDING) -> str:
    """Make a scalar explanation readable without exposing implementation codes."""

    text = _text(value).strip()
    if not text:
        return fallback
    normalized = text.upper().replace("-", "_").replace(" ", "_")
    if normalized in _PUBLIC_STATUS_LABELS:
        return _public_status_label(normalized, fallback)
    for code, reason in _PUBLIC_CODE_REASONS.items():
        if normalized == code or normalized.startswith(code + ":"):
            return reason
        if code in text:
            text = text.replace(code, reason.rstrip("。"))
    for source, replacement in _PUBLIC_TERM_REPLACEMENTS:
        text = text.replace(source, replacement)
    # A code that was not explicitly named above is still not useful to a
    # student. Keep its meaning at the category level and send the opaque
    # value to the audit export only.
    if text == normalized and normalized and all(character.isupper() or character in "_0123456789:" for character in text):
        return fallback
    return text


def _public_credit(value: Any, fallback: str = PUBLIC_PENDING) -> str:
    return _credit(value, unavailable=fallback)


def _public_bucket_label(value: Any) -> str:
    normalized = _text(value).strip().lower()
    if normalized.startswith("ge_") and any("\u4e00" <= char <= "\u9fff" for char in normalized):
        return f"通識：{_text(value)[3:]}"
    fallback = "其他要求" if re.fullmatch(r"[a-z0-9_:.-]+", normalized) else _public_text(value, "其他要求")
    return {
        "required": "必修",
        "major": "主修專業",
        "major_common": "系共同必修",
        "university_compulsory": "校共同必修",
        "free_elective": "自由選修",
        "ge_common_elective": "通識共同選修",
        "ge_flexible_remainder": "通識彈性補足",
        "ge_flex": "通識彈性補足",
        "cs_alpha_required": "資科系選修54・甲類指定課程32",
        "cs_elective_beta": "資科系選修54・乙類選修22",
        "cs_compulsory": "資科系專業必修",
        "cs_required": "資科系專業必修",
        "math_common_compulsory": "數學系共同必修",
        "math_department_elective": "數學系專業選修",
        "math_domain_required": "數學系領域必修",
        "math_scientific_computing:required": "數學與科學計算領域必修",
        "data_science:required": "數據科學領域必修",
        "math_education:required": "數學教育領域必修",
        "apc_common_compulsory": "物化系共同必修",
        "apc_common": "物化系共同必修",
        "apc_track_compulsory": "物化系組別必修",
        "apc_track_elective": "物化系組別選修",
        "common_compulsory": "系共同必修",
        "common_alternative_1": "共同課程擇一（一）",
        "common_alternative_2": "共同課程擇一（二）",
        "common_elective": "系共同選修",
        "department_professional": "系內專業選修",
        "domain_elective": "主修領域選修",
        "地球環境:compulsory": "地球環境領域必修",
        "生命科學:compulsory": "生命科學領域必修",
        "elective": "專業選修",
        "general_education": "通識",
        "ge": "通識",
        "free": "自由學分",
        "double_major": "雙主修",
        "minor": "輔系",
        "target": "修讀身分要求",
        "total": "畢業總學分",
        "unclassified": "尚待分類",
        "unclassified_category": "尚待分類",
    }.get(normalized, fallback)


def _public_condition(value: Any) -> str:
    """Translate a condition that may still contain machine field names."""

    text = _public_text(value, MANUAL_LABEL)
    replacements = (
        ("min_credits", "至少學分"),
        ("max_credits", "最多學分"),
        ("required_credits", "要求學分"),
        ("course_ids", "課程"),
        ("eligible_course_ids", "可採計課程"),
        ("count", "門數"),
        ("kind", "課程類型"),
        ("owner", "適用對象"),
    )
    for source, replacement in replacements:
        text = text.replace(source, replacement)
    return text


def _public_reason(value: Any, fallback: str = MANUAL_LABEL) -> str:
    return _public_text(value, fallback)


def _public_course_value(value: Any, fallback: str = "") -> str:
    """Return a course label/code without exposing an internal sentinel."""

    text = _text(value).strip()
    normalized = text.upper().replace("-", "_").replace(" ", "_")
    if normalized in {UNKNOWN, NOT_APPLICABLE, "PASS", "FAIL", "IN_PROGRESS", "FAILED"}:
        return fallback
    return text or fallback


def _public_course_id(value: Any, fallback: str = "") -> str:
    """Return a short official course number, hiding internal identities."""

    text = _public_course_value(value, "").strip()
    if not text:
        return fallback
    normalized = text.casefold()
    if re.match(r"^(?:primary|target|minor|pool)(?::|$)", normalized):
        return fallback
    if re.match(r"^\d{3}:(?:earth|cs|math|apc)(?::|$)", normalized):
        return fallback
    return text


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
    return _public_status_label(normalized)


def _allocation_kind_label(kind: Any) -> str:
    normalized = _text(kind).upper()
    return {
        "EXCLUSIVE": "本要求採計",
        "SHARED_SHADOW": "共同課程採計",
        "SHARED_REUSE": "共同課程採計",
        "WAIVER": "免修／抵認（不增加實得學分）",
        "UNALLOCATED": "尚未配置",
    }.get(normalized, PUBLIC_PENDING)


def _requirement_kind_label(requirement: Mapping[str, Any]) -> str:
    explicit = _text(requirement.get("kind"))
    if explicit:
        normalized = explicit.upper().replace("-", "_").replace(" ", "_")
        explicit_label = {
            "NAMED_COURSE": "指定課程",
            "COURSE_POOL": "課程群組",
            "AGGREGATE": "總學分要求",
            "CREDIT_TOTAL": "總學分要求",
            "CS_ELECTIVE_BETA": "乙類選修",
            "CS_ALPHA_REQUIRED": "甲類指定課程",
            "必修": "必修",
            "選修": "選修",
        }.get(normalized)
        if explicit_label:
            return explicit_label
        if re.fullmatch(r"[A-Za-z0-9_:.-]+", explicit):
            return "畢業要求"
        if any(character.isupper() for character in explicit) and all(
            character.isupper() or character in "_0123456789" for character in explicit
        ):
            return "畢業要求"
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
    }.get(bucket.lower(), _public_bucket_label(bucket) if bucket else "畢業要求")


def _allocation_reason(item: Mapping[str, Any], portions: Sequence[Mapping[str, Any]]) -> str:
    reason = _text(item.get("allocation_reason"))
    if reason == "EXCLUSIVE_REQUIREMENT_ROUTE":
        return "依目前規則，將實得學分採計到此要求。"
    if reason == "WAIVER_DECISION":
        return "保留免修／抵認決定；免修本身不增加實得學分。"
    if reason == "NO_SAFE_REQUIREMENT_ROUTE" or not portions:
        return "目前沒有可由規則安全確認的採計方式，請查看規則來源。"
    return _public_reason(reason, "採計原因尚未提供，請查看規則來源。")


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
        reasons.append("目前資料不足，無法安全完成判定")
    if coverage_state not in {"COMPLETE", "RESOLVED"}:
        reasons.append("適用課程清單尚未完整")
    if evidence_state != "VERIFIED":
        reasons.append("規則來源尚未完成核對")
    reasons.extend(_public_reason(item, "資料仍需人工核對") for item in blockers if _text(item))
    if not provenance:
        reasons.append("尚未找到可追溯的規則來源")
    return MANUAL_LABEL + "：" + "；".join(dict.fromkeys(reasons)) if reasons else "可依已核對的規則來源判定。"


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
        reason = MANUAL_LABEL + "：課程身分或要求來源尚不足以安全認列，請查看規則來源。"
    return {
        "attempt_id": _text(attempt.get("attempt_id")),
        "course_id": _text(attempt.get("course_id")),
        "course_name": _text(attempt.get("course_name")) or _text(attempt.get("course_id")),
        "academic_term": _text(attempt.get("academic_term")),
        "course_kind": _text(attempt.get("course_kind")),
        "status": display_status,
        "status_label": _status_label(display_status),
        "identity_status": identity_status,
        "identity_status_label": _public_status_label(identity_status),
        "source_credits": _text(attempt.get("credits")),
        "earned_credits": _text(attempt.get("earned_credits")),
        "used_credits": _credit(used),
        "unallocated_credits": _text(allocation.get("unallocated_credits"), "0"),
        "allocation_kind": allocation_kind,
        "allocation_kind_label": _allocation_kind_label(allocation_kind),
        "shared_credit": shared,
        "portions": tuple(_plain(item) for item in portions),
        "allocation_reason": _public_reason(reason),
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


def _summary(payload: Mapping[str, Any], requirements: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    allocation = payload.get("allocation") if isinstance(payload.get("allocation"), Mapping) else {}
    statistics = payload.get("statistics") if isinstance(payload.get("statistics"), Mapping) else {}
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), Mapping) else {}
    primary = decisions.get("primary_graduation") if isinstance(decisions.get("primary_graduation"), Mapping) else {}
    double = decisions.get("double_major_qualification") if isinstance(decisions.get("double_major_qualification"), Mapping) else {}
    formal_award = decisions.get("formal_double_major_award") if isinstance(decisions.get("formal_double_major_award"), Mapping) else {}
    minor_application = decisions.get("minor_application_or_qualification") if isinstance(decisions.get("minor_application_or_qualification"), Mapping) else {}
    minor_coursework = decisions.get("minor_coursework_completion") if isinstance(decisions.get("minor_coursework_completion"), Mapping) else {}
    formal_minor_award = decisions.get("formal_minor_award") if isinstance(decisions.get("formal_minor_award"), Mapping) else {}
    input_confirmation = payload.get("input_confirmation") if isinstance(payload.get("input_confirmation"), Mapping) else {}
    ledger = statistics.get("credit_ledger") if isinstance(statistics.get("credit_ledger"), Mapping) else {}
    by_bucket = ledger.get("exclusive_by_bucket") if isinstance(ledger.get("exclusive_by_bucket"), Mapping) else statistics.get("by_bucket") if isinstance(statistics.get("by_bucket"), Mapping) else {}
    progress = statistics.get("program_progress") if isinstance(statistics.get("program_progress"), Mapping) else {}
    primary_progress = progress.get("primary") if isinstance(progress.get("primary"), Mapping) else {}
    double_progress = progress.get("double_major") if isinstance(progress.get("double_major"), Mapping) else {}
    minor_progress = progress.get("minor") if isinstance(progress.get("minor"), Mapping) else {}
    aggregate = primary_progress.get("aggregate_credit_progress") if isinstance(primary_progress.get("aggregate_credit_progress"), Mapping) else {}
    observations = statistics.get("course_observations") if isinstance(statistics.get("course_observations"), Mapping) else {}
    observation_counts = observations.get("counts") if isinstance(observations.get("counts"), Mapping) else statistics.get("course_status_counts", {})
    remediation = statistics.get("remediation") if isinstance(statistics.get("remediation"), Mapping) else {}
    directions = remediation.get("directions") if isinstance(remediation.get("directions"), (list, tuple)) else statistics.get("safe_remediation_directions") if isinstance(statistics.get("safe_remediation_directions"), (list, tuple)) else statistics.get("shortest_safe_remediation", ())
    # The total credit numerator is intentionally unavailable unless the
    # service identified one explicit, verified aggregate gate.  The legacy
    # ``_total_required`` name-based fallback was unsafe and is not used.
    total_required = _text(aggregate.get("required_credits")) if aggregate.get("available") else MANUAL_LABEL
    primary_status = _text(primary_progress.get("status"), _text(primary.get("status"), UNKNOWN))
    double_status = _text(double_progress.get("status"), _text(double.get("status"), NOT_APPLICABLE))
    minor_status = _text(minor_progress.get("status"), _text(minor_application.get("status"), NOT_APPLICABLE))
    source_earned = _text(ledger.get("source_earned_credits"), _text(statistics.get("source_earned_credits"), _text(allocation.get("source_earned_credits"), MANUAL_LABEL)))
    counted = _text(ledger.get("exclusive_allocated_credits"), _text(statistics.get("recognized_credits"), _text(allocation.get("recognized_credits"), MANUAL_LABEL)))
    unallocated = _text(ledger.get("unallocated_credits"), _text(statistics.get("unallocated_credits"), _text(allocation.get("unallocated_credits"), MANUAL_LABEL)))
    shadow = _text(ledger.get("shared_shadow_credits"), _text(statistics.get("shared_shadow_credits"), MANUAL_LABEL))
    conservation = ledger.get("conservation", {}).get("ok") if isinstance(ledger.get("conservation"), Mapping) else statistics.get("credit_conservation", allocation.get("credit_conservation"))
    completed = observations.get("completed_count", statistics.get("completed", MANUAL_LABEL))
    in_progress = observations.get("in_progress_count", statistics.get("in_progress", MANUAL_LABEL))
    raw_course_counts = statistics.get("course_counts")
    if not isinstance(raw_course_counts, Mapping):
        raw_course_counts = observation_counts
    course_counts = _plain(raw_course_counts)
    if not isinstance(course_counts, Mapping):
        course_counts = {}
    # Requirement counts are status observations over requirement rows, not
    # transcript rows.  Preserve any additional explicit status (for example
    # NOT_APPLICABLE), while always exposing the three v2 gate statuses and a
    # separately named deficit count.
    requirement_status_counts = statistics.get("requirement_metrics", {}).get("status_counts", {}) if isinstance(statistics.get("requirement_metrics"), Mapping) else statistics.get("requirement_status_counts", {})
    raw_requirement_counts = statistics.get("requirement_counts")
    if not isinstance(raw_requirement_counts, Mapping):
        raw_requirement_counts = requirement_status_counts
    requirement_counts = {
        str(key): value
        for key, value in raw_requirement_counts.items()
        if str(key) != "deficit_count"
    }
    deficits = statistics.get("requirement_metrics", {}).get("deficits", ()) if isinstance(statistics.get("requirement_metrics"), Mapping) else statistics.get("deficits", ())
    if "deficit_count" in raw_requirement_counts:
        requirement_counts["deficit_count"] = raw_requirement_counts["deficit_count"]
    else:
        requirement_counts["deficit_count"] = len(_as_sequence(deficits))
    course_unresolved = course_counts.get(UNKNOWN, MANUAL_LABEL)
    requirement_pending = requirement_counts.get(UNKNOWN, MANUAL_LABEL)
    requirement_deficit_count = requirement_counts.get("deficit_count", MANUAL_LABEL)
    metric_container = statistics.get("requirement_metrics") if isinstance(statistics.get("requirement_metrics"), Mapping) else {}
    metric_items = tuple(
        item for item in _as_sequence(metric_container.get("items")) if isinstance(item, Mapping)
    )
    required_items = tuple(
        item
        for item in metric_items
        if _text(item.get("bucket")).lower() in {"required", "major", "major_common"}
        or "必修" in _text(item.get("kind"))
    )
    required_done = sum(1 for item in required_items if _text(item.get("status")).upper() == PASS)
    required_todo = sum(1 for item in required_items if _text(item.get("status")).upper() != PASS)
    todo_count = sum(
        1
        for item in metric_items
        if _text(item.get("status")).upper() in {FAIL, UNKNOWN}
        or (_decimal(item.get("deficit")) or Decimal("0")) > 0
    )
    missing_credits = ""
    aggregate_completed = _decimal(aggregate.get("completed_credits"))
    aggregate_required = _decimal(aggregate.get("required_credits"))
    if aggregate.get("available") and aggregate_completed is not None and aggregate_required is not None:
        missing_credits = _credit(max(Decimal("0"), aggregate_required - aggregate_completed))
    return {
        "verdict": _text(payload.get("verdict"), UNKNOWN),
        "source_earned_credits": source_earned,
        "counted_exclusive_credits": counted,
        "legacy_aliases": {"total_graduation_credits": {"value": source_earned, "deprecated": True, "meaning": "來源成績中的實得學分，不是畢業要求總量"}},
        "required_graduation_credits": total_required or MANUAL_LABEL,
        "recognized_credits": counted,
        "effective_recognized_credits": counted,
        "unallocated_credits": unallocated,
        "shared_shadow_credits": shadow,
        "credit_conservation": conservation,
        "primary_status": primary_status,
        "double_major_status": double_status,
        "formal_double_major_award_status": _text(formal_award.get("status"), NOT_APPLICABLE),
        "minor_application_status": minor_status,
        "minor_coursework_status": _text(minor_coursework.get("status"), NOT_APPLICABLE),
        "formal_minor_award_status": _text(formal_minor_award.get("status"), NOT_APPLICABLE),
        "minor_credits": _text(statistics.get("minor_credits"), "0"),
        "input_confirmation_state": _text(input_confirmation.get("state"), MANUAL_LABEL),
        "by_bucket": _plain(by_bucket),
        "requirement_status_counts": _plain(requirement_status_counts),
        "course_status_counts": _plain(observation_counts),
        "course_counts": course_counts,
        "requirement_counts": _plain(requirement_counts),
        "completed": completed,
        "in_progress": in_progress,
        "course_unresolved_count": course_unresolved,
        "requirement_pending_count": requirement_pending,
        "requirement_deficit_count": requirement_deficit_count,
        "missing": requirement_deficit_count,
        "missing_credits": missing_credits,
        "required_progress": {
            "completed": required_done,
            "required": len(required_items),
            "todo": required_todo,
            "available": bool(required_items),
        },
        "todo_count": todo_count,
        "statistics_schema": _text(statistics.get("schema_version"), "decision-statistics.v2"),
        "statistics_digest": _text(statistics.get("statistics_digest"), MANUAL_LABEL),
        "aggregate_credit_progress": _plain(aggregate),
        "reallocation": {
            "allocation_status": _text(allocation.get("status"), UNKNOWN),
            "recognized_credits": counted,
            "unallocated_credits": unallocated,
            "shared_shadow_credits": shadow,
            "credit_conservation": conservation,
            "allocation_ambiguous": allocation.get("allocation_ambiguous"),
            "alternative_count": len(_as_sequence(payload.get("alternatives") or allocation.get("alternative_allocations"))),
        },
        "blockers": tuple(_text(item) for item in _as_sequence(payload.get("blockers")) if _text(item)),
        "warnings": tuple(_text(item) for item in _as_sequence(payload.get("warnings")) if _text(item)),
        "remediation_suggestions": tuple(
            _text(item)
            for item in _as_sequence(payload.get("remediation_suggestions") or directions)
            if _text(item)
        ),
        "remediation_status": _text(remediation.get("status"), "DIRECTION_ONLY"),
    }


def build_snapshot_projection(snapshot: DecisionSnapshot) -> Mapping[str, Any]:
    """Build a deterministic, display-safe projection from one snapshot read."""

    payload = _snapshot_payload(snapshot)
    validated_statistics = statistics_projection_from_payload(payload)
    plain_payload = _plain(payload)
    # Normalize legacy snapshots once at the projection boundary.  New
    # service snapshots already contain decision-statistics.v2; old fixtures
    # are upgraded from their immutable allocation records without invoking
    # the allocator.  Every downstream renderer/export receives these exact
    # statistics and chart datasets.
    statistics = _plain(validated_statistics)
    plain_payload = {**plain_payload, "statistics": statistics}
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
    metric_container = statistics.get("requirement_metrics") if isinstance(statistics.get("requirement_metrics"), Mapping) else {}
    metric_by_requirement = {
        _text(item.get("requirement_id")): item
        for item in _as_sequence(metric_container.get("items"))
        if isinstance(item, Mapping) and _text(item.get("requirement_id"))
    }
    alternatives = tuple(plain_payload.get("alternatives") or allocation.get("alternative_allocations") or ())
    provenance = tuple(item for item in plain_payload.get("rule_provenance", ()) if isinstance(item, Mapping))
    requirement_views: list[Mapping[str, Any]] = []
    for requirement in requirements:
        requirement_id = _text(requirement.get("requirement_id"))
        source_result = result_by_requirement.get(requirement_id, {})
        metric = metric_by_requirement.get(requirement_id, {})
        result = dict(source_result) if isinstance(source_result, Mapping) else {}
        # Requirement cards must consume the validated metric status.  The
        # original allocator status remains available as ``observed_status``
        # for audit, but cannot leak a PASS after conservation failed.
        for key in (
            "required_credits",
            "exclusive_credits",
            "shared_shadow_credits",
            "effective_credits",
            "deficit",
            "status",
            "coverage_state",
            "evidence_state",
            "waived",
        ):
            if key in metric:
                result[key] = metric[key]
        observed_status = _text(metric.get("observed_status"), _text(source_result.get("status"), UNKNOWN))
        status_authoritative = bool(metric.get("status_authoritative", True))
        status_reason_code = _text(metric.get("status_reason_code"))
        status = _text(result.get("status"), UNKNOWN)
        requirement_provenance = _provenance_view(_provenance_for(requirement_id, provenance))
        blockers = tuple(_text(item) for item in _as_sequence(result.get("blockers")) if _text(item))
        if not status_authoritative and status_reason_code and status_reason_code not in blockers:
            blockers = (*blockers, status_reason_code)
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
                "observed_status": observed_status,
                "status_authoritative": status_authoritative,
                "status_reason_code": status_reason_code,
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
    # Keep the chart projection immutable and structurally identical to the
    # statistics-only projection; exporters can thaw it through their one
    # privacy serializer without rebuilding any dataset.
    chart_datasets = build_chart_datasets(statistics, snapshot_id=_text(plain_payload.get("snapshot_id")))
    presentation_warnings = tuple(
        _text(item)
        for item in chart_datasets.get("presentation_warnings", ())
        if _text(item) and _text(item) != "F7：TOO_MANY_GATE_CATEGORIES"
    )
    summary = {**summary, "presentation_warnings": presentation_warnings}
    context_request = plain_payload.get("request") if isinstance(plain_payload.get("request"), Mapping) else {}
    context = {
        key: context_request[key]
        for key in (
            "admission_cohort",
            "primary_curriculum_id",
            "primary_program",
            "primary_track",
            "target_curriculum_id",
            "target_curriculum_version",
            "target_curriculum_version_candidate",
            "target_curriculum_year",
            "target_program",
            "target_track",
            "secondary_kind",
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
    non_credit_results = _optional_result_rows(
        plain_payload,
        "non_credit_results",
        "non_credit_requirement_results",
        "non_credit_requirements_results",
        "non_credit_requirements",
    )
    subset_results = _optional_result_rows(
        plain_payload,
        "subset_results",
        "free_subset_results",
        "subset_constraint_results",
        "subset_evaluations",
    )
    return {
        "_projection_schema": PROJECTION_SCHEMA_VERSION,
        "_source": "DecisionSnapshot",
        "snapshot_id": _text(plain_payload.get("snapshot_id")),
        "_snapshot_id": _text(plain_payload.get("snapshot_id")),
        "evaluated_at": _text(plain_payload.get("evaluated_at")),
        "verdict": _text(plain_payload.get("verdict"), UNKNOWN),
        "statistics_schema": _text(summary.get("statistics_schema"), "decision-statistics.v2"),
        "statistics_digest": _text(summary.get("statistics_digest"), MANUAL_LABEL),
        "context": context,
        "summary": summary,
        "decisions": _plain(plain_payload.get("decisions", {})),
        "attempts": tuple(_plain(item) for item in attempts),
        "requirements": tuple(requirement_views),
        "non_credit_results": tuple(_plain(item) for item in non_credit_results),
        "subset_results": tuple(_plain(item) for item in subset_results),
        "allocations": _plain(_as_sequence(allocation.get("allocations"))),
        "allocation": _plain(allocation),
        "alternatives": _plain(alternatives),
        "statistics": _plain(statistics),
        "course_counts": _plain(statistics.get("course_counts", summary.get("course_counts", {}))),
        "requirement_counts": _plain(statistics.get("requirement_counts", summary.get("requirement_counts", {}))),
        "chart_datasets": chart_datasets,
        "presentation_warnings": presentation_warnings,
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
        "COMPLETED": "is-pass",
        FAIL: "is-fail",
        "FAILED": "is-fail",
        "IN_PROGRESS": "is-progress",
        "IP": "is-progress",
        UNKNOWN: "is-pending",
        NOT_APPLICABLE: "is-na",
    }.get(normalized, "is-pending")


def _metric(label: str, value: Any, detail: Any = "") -> str:
    detail_markup = f'<small>{_escape(detail)}</small>' if detail not in (None, "") else ""
    return f'<article class="snapshot-metric"><span>{_escape(label)}</span><strong>{_escape(value)}</strong>{detail_markup}</article>'


def _provenance_markup(items: Sequence[Any]) -> str:
    rows: list[str] = []
    if isinstance(items, Mapping):
        source_items: Sequence[Any] = (items,)
    elif isinstance(items, (str, int, float)):
        source_items = (items,)
    elif isinstance(items, Sequence):
        source_items = items
    else:
        source_items = ()
    for item in source_items:
        if not isinstance(item, Mapping):
            reference = _public_text(item, "規則來源已保留於稽核資料")
            if reference:
                rows.append(f"<li>來源：{_escape(reference)}</li>")
            continue
        parts: list[str] = []
        location = _text(item.get("source_location") or item.get("location") or item.get("table_location"))
        source_file = _text(item.get("source_file"))
        pages = _text(item.get("pages") or item.get("page") or item.get("pdf_page") or item.get("printed_page"))
        authority = _text(item.get("authority"))
        clause = _text(item.get("original_clause") or item.get("original_text"))
        if location:
            parts.append(f"位置：{location}")
        elif source_file:
            parts.append(f"文件：{source_file}")
        if pages:
            parts.append(f"頁碼：{pages}")
        if authority:
            parts.append(f"依據：{_public_text(authority, '學校規定')}")
        if clause:
            parts.append(f"條文：{_public_text(clause)}")
        if not parts:
            reference = _text(item.get("source_reference") or item.get("evidence_reference"))
            parts.append(f"來源：{_public_text(reference, '規則來源已保留於稽核資料')}")
        evidence = _text(item.get("evidence_state"))
        if evidence:
            parts.append(f"{_public_status_label(evidence, _public_text(evidence))}")
        rows.append(f"<li>{_escape('；'.join(parts))}</li>")
    return "".join(rows) or "<li>目前沒有可直接顯示的規則位置，請補充可核對的手冊來源。</li>"


def _public_context_markup(view: Mapping[str, Any]) -> str:
    context = view.get("context") if isinstance(view.get("context"), Mapping) else {}
    program_labels = {"earth": "地生", "apc": "物化", "cs": "資科", "math": "數學"}
    track_labels = {
        "earth_environment": "地球環境",
        "life_science": "生命科學",
        "physics": "電子物理",
        "chemistry": "應用化學",
        "math_scientific_computing": "數學與科學計算",
        "data_science": "數據科學",
        "math_education": "數學教育",
    }
    primary_program = _text(context.get("primary_program"))
    primary_track = _text(context.get("primary_track"))
    if not primary_program:
        primary_id = _text(context.get("primary_curriculum_id"))
        identity_parts = primary_id.split(":")
        if len(identity_parts) >= 3 and identity_parts[0] == "primary":
            primary_program = identity_parts[2]
            primary_track = primary_track or (identity_parts[3] if len(identity_parts) > 3 else "")
    primary_label = program_labels.get(primary_program, primary_program or "主修尚待確認")
    track_label = track_labels.get(primary_track, primary_track)
    if track_label and track_label not in primary_label:
        primary_label = f"{primary_label}（{track_label}）"
    parts = []
    cohort = _text(context.get("admission_cohort"))
    if cohort:
        parts.append(f"{cohort} 學年度入學")
    parts.append(f"主修：{primary_label}")
    secondary_kind = _text(context.get("secondary_kind")).lower()
    target_program = program_labels.get(_text(context.get("target_program")), _text(context.get("target_program")))
    target_track = track_labels.get(_text(context.get("target_track")), _text(context.get("target_track")))
    if secondary_kind in {"minor", "double_major"}:
        role = "輔系" if secondary_kind == "minor" else "雙主修"
        target = target_program or "尚未選定"
        if target_track and target_track not in target:
            target = f"{target}（{target_track}）"
        parts.append(f"{role}：{target}")
    masked_id = _text(context.get("masked_student_id"))
    if masked_id:
        parts.append(f"學號：{masked_id}")
    return "　·　".join(parts)


def _format_evaluated_at(value: Any) -> str:
    text = _text(value).strip()
    normalized = text.upper().replace("-", "_").replace(" ", "_")
    if not text or normalized in {"UNSPECIFIED", "UNKNOWN", "NOT_APPLICABLE", "N_A", "PENDING", "UNCONFIRMED"}:
        return "本次分析"
    # A renderer timestamp should be a date-like value.  Avoid exposing an
    # opaque source code when the snapshot carries no usable date.
    if not re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", text):
        return "本次分析"
    # Keep the timestamp useful to the student while avoiding a technical
    # ISO-looking label when the source already carries a normal date.
    return text.replace("T", " ").replace("Z", "").strip()


def _public_chart_markup(markup: Any) -> str:
    """Keep legacy chart geometry while translating its labels for students."""

    text = _text(markup)
    replacements = (
        ("F1 Rung Bars", "採計學分分布"),
        ("F5 Tick Rows", "各項要求進度"),
        ("F7 Stacked Rungs", "各項狀態分布"),
        ("F11 Tick Gauge", "總學分完成度"),
        ("Tick Gauge", "精確數字"),
        ("Rung Bars", "學分分布"),
        ("DecisionSnapshot", "本次分析資料"),
        ("EXCLUSIVE_REQUIREMENT_ROUTE", "依本要求採計"),
        ("EXCLUSIVE", "本要求採計"),
        ("SHARED_SHADOW", "共同課程採計"),
        ("SHARED_REUSE", "共同課程採計"),
        ("shared shadow", "共同課程採計"),
        ("shadow", "共同課程採計"),
        ("AGGREGATE_GATE_UNAVAILABLE", "尚未找到可核對的主修總學分門檻"),
        ("EXCLUSIVE_CREDIT_LEDGER_EMPTY", "目前沒有可加總的已採計學分"),
        ("REQUIREMENT_METRICS_UNAVAILABLE", "目前沒有可比較的要求進度"),
        ("GATE_COUNTS_UNAVAILABLE", "目前沒有可比較的要求狀態"),
        ("CREDIT_CONSERVATION_FAILED", "成績學分與採計結果需要重新核對"),
        ('data-status="UNKNOWN"', 'data-status="PENDING"'),
        ("UNKNOWN", PUBLIC_PENDING),
    )
    for source, replacement in replacements:
        text = text.replace(source, replacement)
    return text


def _mapping_rows(value: Any) -> tuple[Mapping[str, Any], ...]:
    """Read result records without interpreting their values."""

    if isinstance(value, Mapping):
        if any(key in value for key in ("id", "requirement_id", "constraint_id", "name", "status")):
            return (value,)
        return tuple(item for item in value.values() if isinstance(item, Mapping))
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def _optional_result_rows(view: Mapping[str, Any], *keys: str) -> tuple[Mapping[str, Any], ...]:
    """Find an additive result collection in the snapshot projection."""

    allocation = view.get("allocation") if isinstance(view.get("allocation"), Mapping) else {}
    containers = (view, allocation)
    for key in keys:
        for container in containers:
            if key not in container:
                continue
            rows = _mapping_rows(container.get(key))
            if rows:
                return rows
    return ()


def _non_credit_result_rows(view: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    return _optional_result_rows(
        view,
        "non_credit_results",
        "non_credit_requirement_results",
        "non_credit_requirements_results",
        "non_credit_requirements",
    )


def _subset_result_rows(view: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    results = _optional_result_rows(
        view,
        "subset_results",
        "free_subset_results",
        "subset_constraint_results",
        "subset_evaluations",
    )
    owners = {
        _text(item.get("requirement_id")): item
        for item in view.get("requirements", ()) if isinstance(item, Mapping)
    }
    enriched = []
    for result in results:
        owner = owners.get(_text(result.get("requirement_id")), {})
        provenance = owner.get("rule_provenance")
        reference = _text(result.get("source_reference"))
        if provenance and reference.startswith(("evidence:", "handbook:")) and not result.get("provenance"):
            # The constraint keeps its own audit reference; the same
            # snapshot's owning requirement supplies the readable PDF link.
            enriched.append({**result, "provenance": provenance})
        else:
            enriched.append(result)
    return tuple(enriched)


def _result_value(result: Mapping[str, Any], keys: Sequence[str], fallback: str = "需要補資料") -> str:
    for key in keys:
        if key in result and result.get(key) not in (None, ""):
            return _text(result.get(key))
    return fallback


def _result_values(value: Any, *, fallback: str = "尚無") -> str:
    values: list[str] = []
    raw_values = value.values() if isinstance(value, Mapping) else value if isinstance(value, (list, tuple, set, frozenset)) else (value,)
    for item in raw_values:
        if isinstance(item, Mapping):
            item = item.get("term") or item.get("academic_term") or item.get("label") or item.get("name")
        text = _text(item).strip()
        if text:
            values.append(text)
    return "、".join(dict.fromkeys(values)) or fallback


def _non_credit_progress_text(result: Mapping[str, Any]) -> str:
    kind = _text(result.get("kind") or result.get("requirement_kind")).upper()
    name = _text(result.get("name") or result.get("label"))
    unit = "學期／項目" if "TERM" in kind or "體育" in name else "項目"
    completed = _result_value(result, ("completed_count", "completed_completions", "completed"))
    required = _result_value(result, ("required_count", "required_completions", "required"))
    progress = f"{completed}／{required} {unit}" if completed != "需要補資料" and required != "需要補資料" else "進度需要補資料"
    completed_hours = _result_value(result, ("completed_hours", "earned_hours", "hours_completed"), "")
    required_hours = _result_value(result, ("required_hours", "hours_required"), "")
    if completed_hours and required_hours:
        progress += f"；時數 {completed_hours}／{required_hours} 小時"
    return progress


def _subset_progress_text(result: Mapping[str, Any]) -> str:
    if result.get("minimum_course_count") is not None or result.get("required_course_count") is not None:
        completed_count = _result_value(result, ("verified_course_count", "completed_course_count"))
        required_count = _result_value(result, ("minimum_course_count", "required_course_count"))
        if completed_count != "需要補資料" and required_count != "需要補資料":
            return f"{completed_count}／{required_count} 門課程"
        return "課程門數需要補資料"
    completed = _result_value(result, ("verified_credits", "completed_credits", "effective_credits", "observed_credits"))
    required = _result_value(result, ("required_credits", "minimum_credits", "required"))
    maximum = _result_value(result, ("maximum_credits", "max_credits"), "")
    if completed != "需要補資料" and maximum:
        progress = f"已採計 {completed} 學分／上限 {maximum} 學分"
        if (_decimal(required) or Decimal("0")) > 0:
            progress += f"；至少 {required} 學分"
        return progress
    if completed != "需要補資料" and required != "需要補資料":
        return f"{completed}／{required} 學分"
    return "進度需要補資料"


def _subset_name(result: Mapping[str, Any]) -> str:
    name = result.get("name") or result.get("label")
    if name:
        return _public_text(name, "學分採計條件")
    membership = _text(result.get("membership_id"))
    if membership == "science_college":
        return "理學院課程學分要求"
    if membership == "external_department_or_school_professional":
        return "外系／外校專門課程採計上限"
    if membership.startswith("math_alpha:"):
        return "數學系甲類選修學分要求"
    if membership.startswith("cs_beta_domain:"):
        domain = {"common": "共通", "software": "軟體", "network": "網路"}.get(membership.rsplit(":", 1)[-1])
        return f"資科系乙類選修：{domain}領域" if domain else "資科系乙類選修領域要求"
    return "學分採計條件"


def _cs_elective_rollup(view: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Summarize existing validated requirement metrics without allocating."""
    primary_id = _text(view.get("context", {}).get("primary_curriculum_id"))
    if not re.fullmatch(r"primary:11[1-5]:cs", primary_id):
        return None
    requirements = tuple(item for item in view.get("requirements", ()) if isinstance(item, Mapping))
    alpha = tuple(item for item in requirements if item.get("bucket") == "cs_alpha_required")
    beta = tuple(item for item in requirements if item.get("bucket") == "cs_elective_beta")
    if len(alpha) != 12 or len(beta) != 1:
        return None
    if sum((_decimal(item.get("required_credits")) or Decimal("0") for item in alpha), Decimal("0")) != 32:
        return None
    if _decimal(beta[0].get("required_credits")) != 22:
        return None
    members = (*alpha, *beta)
    values = tuple(_decimal(item.get("effective_credits")) for item in members)
    if any(value is None for value in values) or any(item.get("status_authoritative") is False for item in members):
        completed = PUBLIC_PENDING
    else:
        completed = _credit(sum(values, Decimal("0")))
    statuses = {_text(item.get("status")) for item in members}
    status = PASS if statuses == {PASS} else UNKNOWN if UNKNOWN in statuses else FAIL
    return {"name": "資科系選修", "required_credits": "54", "effective_credits": completed,
            "status": status, "alpha": alpha, "beta": beta,
            "requirement_ids": tuple(item["requirement_id"] for item in members)}


def _requirements_markup(view: Mapping[str, Any]) -> str:
    rollup = _cs_elective_rollup(view)
    if not rollup:
        return "".join(_requirement_markup(item) for item in view["requirements"])
    group_ids = set(rollup["requirement_ids"])
    output, emitted = [], False
    for item in view["requirements"]:
        if item["requirement_id"] not in group_ids:
            output.append(_requirement_markup(item))
        elif not emitted:
            emitted = True
            output.append(
                '<details class="snapshot-card snapshot-cs-electives"><summary>'
                f'<strong>資科系選修：{_escape(rollup["effective_credits"])}／54 學分</strong>　'
                f'{_escape(_status_label(rollup["status"]))} — 展開甲、乙類明細</summary>'
                '<p>54 學分包含甲類指定課程32學分與乙類選修22學分；以下沿用各課程的採計結果，不另增加學分。</p>'
                '<h3>甲類指定課程：32 學分</h3>'
                + "".join(_requirement_markup(row) for row in rollup["alpha"])
                + '<h3>乙類選修：22 學分</h3>'
                + "".join(_requirement_markup(row) for row in rollup["beta"])
                + '</details>'
            )
    return "".join(output)


def _result_source_items(result: Mapping[str, Any]) -> Any:
    return result.get("provenance") or result.get("rule_provenance") or result.get("source") or result.get("source_reference")


def _result_blockers(result: Mapping[str, Any]) -> tuple[str, ...]:
    raw = result.get("blockers") or result.get("reasons") or result.get("reason")
    if isinstance(raw, Mapping):
        raw = tuple(raw.values())
    if isinstance(raw, (list, tuple, set, frozenset)):
        return tuple(_public_reason(item, "資料仍需人工核對") for item in raw if _text(item))
    return (_public_reason(raw, "資料仍需人工核對"),) if _text(raw) else ()


def _matched_gate_courses(view: Mapping[str, Any], result: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Join gate evidence to the same immutable transcript, without recounting credits."""
    matched = {_text(value) for value in _as_sequence(result.get("matched_attempt_ids"))}
    return tuple(
        attempt for attempt in _as_sequence(view.get("attempts"))
        if isinstance(attempt, Mapping) and _text(attempt.get("attempt_id")) in matched
    )


def _gate_course_text(attempt: Mapping[str, Any]) -> str:
    name = _public_course_value(attempt.get("course_name")) or "未標示課程"
    term = _public_course_value(attempt.get("academic_term")) or "學期待補"
    status = _public_status_label(attempt.get("status"), PUBLIC_PENDING)
    credits = _public_credit(attempt.get("credits"), "學分待補")
    return f"{name}｜{term}｜{status}｜{credits} 學分"


def _gate_course_markup(courses: Sequence[Mapping[str, Any]]) -> str:
    """Render non-credit evidence courses as a readable semantic table."""

    rows: list[str] = []
    for course in courses:
        name = _public_course_value(course.get("course_name")) or "未標示課程"
        term = _public_course_value(course.get("academic_term")) or "學期待補"
        status = _public_status_label(course.get("status"), PUBLIC_PENDING)
        credits = _public_credit(course.get("credits"), "學分待補")
        rows.append(
            '<tr class="snapshot-gate-course">'
            f'<th scope="row">{_escape(name)}</th>'
            f'<td>{_escape(term)}</td>'
            f'<td><span class="snapshot-badge {_status_class(course.get("status"))}">{_escape(status)}</span></td>'
            f'<td>{_escape(credits)} 學分</td>'
            '</tr>'
        )
    if not rows:
        rows.append('<tr class="snapshot-course--empty"><td colspan="4">目前沒有可列出的採用課程。</td></tr>')
    return (
        '<div class="snapshot-table-scroll">'
        '<table class="snapshot-gate-course-list" aria-label="非學分門檻採用課程">'
        '<caption class="snapshot-sr-only">非學分門檻採用課程</caption>'
        '<thead><tr><th scope="col">課名</th><th scope="col">學期</th>'
        '<th scope="col">狀態</th><th scope="col">修得學分</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _non_credit_result_markup(result: Mapping[str, Any], view: Mapping[str, Any]) -> str:
    name = _public_text(
        result.get("name") or result.get("label") or result.get("requirement_id"),
        "非學分門檻",
    )
    status = _text(result.get("status"), UNKNOWN)
    progress = _non_credit_progress_text(result)
    completed_terms = _result_values(result.get("completed_terms"), fallback="尚無已完成學期")
    in_progress_terms = _result_values(result.get("in_progress_terms"), fallback="目前沒有修習中學期")
    blockers = "；".join(_result_blockers(result)) or "目前沒有其他提醒"
    courses = _matched_gate_courses(view, result)
    course_markup = f'<p><b>採用課程：</b></p>{_gate_course_markup(courses)}' if courses else ""
    return (
        '<details class="snapshot-non-credit-details">'
        f'<summary><span>{_escape(name)}</span><span>{_escape(progress)} · '
        f'<span class="snapshot-badge {_status_class(status)}">{_escape(_public_status_label(status))}</span></span></summary>'
        '<div class="snapshot-non-credit-body">'
        f'<p><b>完成進度：</b>{_escape(progress)}</p>'
        f'<p><b>已完成學期／項目：</b>{_escape(completed_terms)}</p>'
        f'<p><b>修習中：</b>{_escape(in_progress_terms)}</p>'
        f'{course_markup}'
        '<p><b>學分計算：</b>這項門檻不另外增加學分；課程學分仍依原類別採計。</p>'
        f'<p class="snapshot-blocker-note"><b>下一步：</b>{_escape(blockers)}</p>'
        '<details class="snapshot-source-details"><summary>查看規則來源</summary>'
        f'<ul class="snapshot-provenance-list">{_provenance_markup(_result_source_items(result))}</ul></details>'
        '</div></details>'
    )


def _subset_result_markup(result: Mapping[str, Any]) -> str:
    name = _subset_name(result)
    status = _text(result.get("status"), UNKNOWN)
    progress = _subset_progress_text(result)
    unknown = _public_credit(result.get("unknown_candidate_credits"), "0")
    blockers = "；".join(_result_blockers(result)) or "目前沒有其他提醒"
    unknown_note = f"；另有 {unknown} 學分候選仍待核對" if unknown != "0" else ""
    return (
        '<details class="snapshot-subset-details">'
        f'<summary><span>{_escape(name)}</span><span>{_escape(progress)} · '
        f'<span class="snapshot-badge {_status_class(status)}">{_escape(_public_status_label(status))}</span></span></summary>'
        '<div class="snapshot-subset-body">'
        f'<p><b>子條件進度：</b>{_escape(progress)}{_escape(unknown_note)}</p>'
        '<p><b>學分計算：</b>依各項規則指定的已採計課程檢查，不另增加或重複計算學分。</p>'
        f'<p class="snapshot-blocker-note"><b>下一步：</b>{_escape(blockers)}</p>'
        '<details class="snapshot-source-details"><summary>查看規則來源</summary>'
        f'<ul class="snapshot-provenance-list">{_provenance_markup(_result_source_items(result))}</ul></details>'
        '</div></details>'
    )


def _additional_gate_markup(view: Mapping[str, Any]) -> str:
    non_credit = _non_credit_result_rows(view)
    subsets = _subset_result_rows(view)
    markup: list[str] = []
    if non_credit:
        markup.append(
            '<section class="snapshot-card snapshot-non-credit-card"><h2>非學分門檻</h2>'
            '<p class="snapshot-blocker-note">這些要求獨立於學分加總；點開可查看完成學期、待辦與來源。</p>'
            + "".join(_non_credit_result_markup(item, view) for item in non_credit)
            + "</section>"
        )
    if subsets:
        markup.append(
            '<section class="snapshot-card snapshot-subset-card"><h2>學分採計條件</h2>'
            '<p class="snapshot-blocker-note">條件沿用各類別的學分採計結果；點開可查看下限、上限與來源。</p>'
            + "".join(_subset_result_markup(item) for item in subsets)
            + "</section>"
        )
    return "".join(markup)


def _unallocated_course_items(view: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return transcript attempts that have no requirement course row.

    Attempt IDs are the primary identity.  A course code is used only for
    rows without an attempt ID, and its term remains part of that fallback
    identity so repeated offerings are not collapsed into one course.
    """

    represented_attempt_ids: set[str] = set()
    represented_course_terms: set[tuple[str, str]] = set()
    for requirement in view.get("requirements", ()):
        if not isinstance(requirement, Mapping):
            continue
        for course in requirement.get("courses", ()):
            if not isinstance(course, Mapping):
                continue
            attempt_id = _text(course.get("attempt_id")).strip()
            if attempt_id:
                represented_attempt_ids.add(attempt_id)
                continue
            course_id = _text(course.get("course_id")).strip().casefold()
            if course_id:
                represented_course_terms.add((course_id, _text(course.get("academic_term")).strip()))

    allocations = {
        _text(item.get("attempt_id")): item
        for item in view.get("allocations", ())
        if isinstance(item, Mapping) and _text(item.get("attempt_id"))
    }
    rows: list[Mapping[str, Any]] = []
    for attempt in view.get("attempts", ()):
        if not isinstance(attempt, Mapping):
            continue
        attempt_id = _text(attempt.get("attempt_id")).strip()
        course_id = _text(attempt.get("course_id")).strip()
        term = _text(attempt.get("academic_term")).strip()
        if attempt_id and attempt_id in represented_attempt_ids:
            continue
        if not attempt_id and course_id and (course_id.casefold(), term) in represented_course_terms:
            continue
        rows.append({"attempt": attempt, "allocation": allocations.get(attempt_id, {})})
    return tuple(rows)


def _unallocated_course_guidance(attempt: Mapping[str, Any]) -> tuple[str, str]:
    """Describe only legal next uses for an unmatched transcript attempt."""

    status = _text(attempt.get("status"), UNKNOWN).strip().upper().replace("-", "_").replace(" ", "_")
    identity = _text(attempt.get("identity_status"), UNKNOWN).strip().upper().replace("-", "_").replace(" ", "_")
    if status in {"IN_PROGRESS", "IP"}:
        return (
            "完成後再依規則確認（目前不計入有效學分）",
            "課程正在修習中，尚未產生可採計學分。",
        )
    if status in {"FAILED", "FAIL"}:
        return (
            "重修或替代方式需依規則確認（目前不計入有效學分）",
            "課程成績未達完成條件，目前不計入有效學分。",
        )
    if status in {"WITHDRAWN", "W"}:
        return (
            "替代課程需依規則確認（目前不計入有效學分）",
            "課程已停修／撤選，目前不計入有效學分。",
        )
    if status in {"NOT_TAKEN", "NOT_ATTEMPTED", "MISSING"}:
        return ("尚未修課，不能產生學分", "這是規則清單中的尚未修課項目。")
    if status in {"WAIVED", "WAIVER", "TRANSFERRED"}:
        return ("依免修／抵認規則確認", "課程涉及免修或抵認，需依正式來源確認用途。")
    if identity not in {"VERIFIED", "CONFIRMED", "KNOWN"}:
        return ("先確認課程身分與規則來源", "課程身分尚未完成核對，暫不判斷可採計用途。")
    if status in {PASS, "COMPLETED"}:
        return (
            "可能採計：自由選修（需依規則確認）",
            "課程已完成但尚未對應到特定畢業要求，可作為自由選修候選。",
        )
    return ("先補齊課程狀態，再依規則確認", "課程狀態尚未完整，暫不判斷可採計用途。")


def _course_markup(course: Mapping[str, Any]) -> str:
    shared = '<span class="snapshot-shared">共同課程採計</span>' if course.get("shared_credit") else ""
    routes = tuple(_public_reason(item, "目前沒有其他可採計方式") for item in _as_sequence(course.get("alternative_routes")) if _text(item))
    course_id = _public_course_id(course.get("course_id"))
    course_label = _public_course_value(course.get("course_name")) or course_id or "未標示課程"
    term = (
        "尚未修課"
        if course.get("is_not_attempted") or _text(course.get("status")).upper() in {"NOT_ATTEMPTED", "NOT_TAKEN"}
        else _text(course.get("academic_term")) or "學期待補"
    )
    source_credits = _public_credit(course.get("source_credits"), "待補")
    used_credits = _public_credit(course.get("used_credits"), "待補")
    status_label = _public_status_label(course.get("status"), _text(course.get("status_label"), PUBLIC_PENDING))
    purpose = _text(course.get("allocation_kind_label"), "採計用途待補")
    identity_note = _public_status_label(course.get("identity_status"), "課程身分待核對")
    route_markup = "、".join(routes)
    notes = (
        f'<div class="snapshot-course-status"><span class="snapshot-badge {_status_class(course.get("status"))}">'
        f'{_escape(status_label)}</span>{shared}</div>'
        f'<p><b>採計用途：</b>{_escape(purpose)}</p>'
        f'<p><b>原因：</b>{_escape(_public_reason(course.get("allocation_reason")))}</p>'
        f'<p class="snapshot-course-meta">課程資料：{_escape(identity_note)}；未採計：'
        f'{_escape(_public_credit(course.get("unallocated_credits"), "0"))} 學分</p>'
        f'<p class="snapshot-course-meta">其他可行方式：{_escape(route_markup or "目前沒有其他可採計方式")}</p>'
    )
    earned_credits = _public_credit(course.get("earned_credits"), "待補")
    return (
        '<tr class="snapshot-course">'
        f'<th scope="row"><div class="snapshot-course-main"><strong>{_escape(course_label)}</strong></div></th>'
        f'<td class="snapshot-course-id"><span class="snapshot-course-meta">{_escape(course_id) or "—"}</span></td>'
        f'<td class="snapshot-course-term"><span class="snapshot-course-meta">{_escape(term)}</span></td>'
        f'<td class="snapshot-course-earned">{_escape(earned_credits)}<small>課程學分：{_escape(source_credits)}</small></td>'
        f'<td class="snapshot-course-used">{_escape(used_credits)}</td>'
        f'<td class="snapshot-course-notes">{notes}</td>'
        '</tr>'
    )


def _eligible_course_markup(requirement: Mapping[str, Any]) -> str:
    options = _as_sequence(requirement.get("eligible_courses"))
    rows: list[str] = []
    for option in options:
        if not isinstance(option, Mapping):
            continue
        course_id = _public_course_id(option.get("course_id"))
        course_name = _public_course_value(option.get("course_name"))
        label = course_name or course_id or MANUAL_LABEL
        rows.append(
            '<tr class="snapshot-course-option">'
            f'<th scope="row"><strong>{_escape(label)}</strong></th>'
            f'<td>{_escape(course_id) or "—"}</td>'
            '</tr>'
        )
    if not rows:
        rows.append('<tr class="snapshot-course--empty"><td colspan="2">目前沒有可列出的指定課程，請查看規則來源。</td></tr>')
    return (
        '<div class="snapshot-table-scroll">'
        '<table class="snapshot-course-options" aria-label="規則指定課程">'
        '<caption class="snapshot-sr-only">規則指定課程</caption>'
        '<thead><tr><th scope="col">課名</th><th scope="col">課號</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _requirement_markup(requirement: Mapping[str, Any]) -> str:
    courses = _as_sequence(requirement.get("courses"))
    course_markup = "".join(_course_markup(course) for course in courses if isinstance(course, Mapping))
    if not course_markup:
        course_markup = (
            '<tr class="snapshot-course snapshot-course--empty">'
            '<td colspan="6"><span class="snapshot-badge is-pending">需要補資料</span> '
            '目前沒有已確認可採計的課程；請查看規則來源並補上成績資料。</td></tr>'
        )
    provenance = _as_sequence(requirement.get("rule_provenance"))
    status = _text(requirement.get("status"), UNKNOWN)
    validation_note = (
        '<p class="snapshot-manual-note">目前只能顯示安全的計算結果；規則或來源尚未完整，請依下方說明補資料。</p>'
        if requirement.get("status_authoritative") is False
        else ""
    )

    status_label = _public_status_label(status, _text(requirement.get("status_label"), PUBLIC_PENDING))
    required = _public_credit(requirement.get("required_credits"))
    effective = _public_credit(requirement.get("effective_credits"))
    exclusive = _public_credit(requirement.get("exclusive_credits"))
    shared = _public_credit(requirement.get("shared_credits"), "0")
    deficit = _public_credit(requirement.get("deficit"), "0")
    coverage_label = _public_text(requirement.get("coverage_state"), "來源尚未完整")
    evidence_label = _public_text(requirement.get("evidence_state"), "來源尚未核對")
    blockers = "；".join(_public_reason(item, "資料仍需人工核對") for item in _as_sequence(requirement.get("blockers"))) or "目前沒有其他提醒"
    return (
        f'<details class="snapshot-requirement-expander" data-requirement-id="{_escape(requirement.get("requirement_id"))}">'
        '<summary><span class="snapshot-requirement-title">'
        f'{_escape(requirement.get("name"))} · {_escape(requirement.get("kind"))}</span>'
        f'<span class="snapshot-requirement-progress">{_escape(effective)}／{_escape(required)} 學分 · '
        f'<span class="snapshot-badge {_status_class(status)}">{_escape(status_label)}</span></span></summary>'
        '<div class="snapshot-requirement-body">'
        '<dl class="snapshot-requirement-facts">'
        f'<div><dt>要求學分</dt><dd>{_escape(required)}</dd></div>'
        f'<div><dt>已採計</dt><dd>{_escape(effective)}</dd></div>'
        f'<div><dt>本要求採計</dt><dd>{_escape(exclusive)}</dd></div>'
        f'<div><dt>共同課程採計</dt><dd>{_escape(shared)}</dd></div>'
        f'<div><dt>尚缺學分</dt><dd>{_escape(deficit)}</dd></div>'
        f'<div><dt>資料狀態</dt><dd>{_escape(coverage_label)}／{_escape(evidence_label)}</dd></div>'
        '</dl>'
        f'{validation_note}'
        f'<p class="snapshot-manual-note">{_escape(_public_reason(requirement.get("manual_confirmation")))}</p>'
        f'<p class="snapshot-blocker-note">下一步：{_escape(blockers)}</p>'
        '<h4>規則指定課程</h4>'
        f'{_eligible_course_markup(requirement)}'
        f'<p class="snapshot-choice-condition">修課條件：{_escape(_public_condition(requirement.get("choice_condition")))}</p>'
        '<h4>課程明細</h4>'
        '<div class="snapshot-table-scroll"><table class="snapshot-course-list" aria-label="課程明細">'
        '<caption class="snapshot-sr-only">課程明細</caption>'
        '<thead><tr><th scope="col">課名</th><th scope="col">課號</th><th scope="col">學期</th>'
        '<th scope="col">修得學分</th><th scope="col">此類採計學分</th><th scope="col">狀態／備註</th></tr></thead>'
        f'<tbody>{course_markup}</tbody></table></div>'
        '<details class="snapshot-source-details"><summary>查看規則來源</summary>'
        f'<ul class="snapshot-provenance-list">{_provenance_markup(provenance)}</ul></details>'
        '</div></details>'
    )


def _unallocated_course_markup(view: Mapping[str, Any]) -> str:
    """Render unmatched attempts in a collapsed, student-readable section."""

    items = _unallocated_course_items(view)
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        attempt = item.get("attempt") if isinstance(item.get("attempt"), Mapping) else {}
        allocation = item.get("allocation") if isinstance(item.get("allocation"), Mapping) else {}
        purpose, reason = _unallocated_course_guidance(attempt)
        source_credits = allocation.get("source_credits", attempt.get("credits"))
        used_credits = allocation.get("used_credits", "0")
        unallocated_credits = allocation.get("unallocated_credits", source_credits)
        rows.append(
            _course_markup(
                {
                    "course_id": _public_course_value(attempt.get("course_id")),
                    "course_name": _public_course_value(attempt.get("course_name")),
                    "academic_term": _text(attempt.get("academic_term")),
                    "status": _text(attempt.get("status"), UNKNOWN),
                    "identity_status": _text(attempt.get("identity_status"), UNKNOWN),
                    "source_credits": source_credits,
                    "earned_credits": attempt.get("earned_credits"),
                    "used_credits": used_credits,
                    "unallocated_credits": unallocated_credits,
                    "allocation_kind_label": purpose,
                    "allocation_reason": reason,
                    "alternative_routes": (),
                }
            )
        )
    return (
        '<section class="snapshot-card snapshot-unallocated-card">'
        '<details class="snapshot-unallocated-details">'
        '<summary>尚未採計課程</summary>'
        '<div class="snapshot-unallocated-body">'
        '<p class="snapshot-manual-note">下列已確認課程目前沒有安全配置至特定畢業要求；各列保留原始學期與狀態。</p>'
        '<div class="snapshot-table-scroll"><table class="snapshot-course-list" aria-label="尚未採計課程">'
        '<caption class="snapshot-sr-only">尚未採計課程</caption>'
        '<thead><tr><th scope="col">課名</th><th scope="col">課號</th><th scope="col">學期</th>'
        '<th scope="col">修得學分</th><th scope="col">此類採計學分</th><th scope="col">狀態／備註</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        '</div></details></section>'
    )


_CALCULATION_DECISION_LABELS = {
    "primary_graduation": "主修畢業要求",
    "double_major_qualification": "雙主修課程要求",
    "minor_coursework_completion": "輔系課程要求",
    "target_coursework_completion": "修讀身分課程要求",
    "overall": "目前計算結果",
}
_ADMINISTRATIVE_DECISION_LABELS = {
    "minor_application_or_qualification": "輔系申請與資格",
    "formal_minor_award": "輔系正式授予",
    "formal_double_major_award": "雙主修正式授予",
    "application_self_report": "申請資料（自行填寫）",
}


def _decision_rows(
    view: Mapping[str, Any],
    labels: Mapping[str, str],
    *,
    hide_secondary_self_report: bool = False,
) -> str:
    decisions = view.get("decisions") if isinstance(view.get("decisions"), Mapping) else {}
    context = view.get("context") if isinstance(view.get("context"), Mapping) else {}
    secondary_kind = _text(context.get("secondary_kind")).strip().casefold().replace("-", "_").replace(" ", "_")
    has_secondary = secondary_kind in {"minor", "double_major", "doublemajor"}
    rows: list[str] = []
    for key, label in labels.items():
        if hide_secondary_self_report and key == "application_self_report" and not has_secondary:
            continue
        decision = decisions.get(key)
        if not isinstance(decision, Mapping):
            continue
        status = _text(decision.get("status"), UNKNOWN)
        if status == NOT_APPLICABLE:
            continue
        status_label = _public_status_label(status)
        reason = _public_reason(
            decision.get("reason"),
            "目前資料不足，請查看下方要求明細與規則來源。" if status == UNKNOWN else "",
        )
        if not reason:
            reason = {
                PASS: "相關要求目前已完成。",
                FAIL: "仍有要求尚未完成，請查看下方待辦。",
            }.get(status, "請查看下方要求明細。")
        rows.append(
            f'<li><span>{_escape(label)}</span>'
            f'<span class="snapshot-badge {_status_class(status)}">{_escape(status_label)}</span>'
            f'<small>{_escape(reason)}</small></li>'
        )
    return "".join(rows) or '<li><span>目前沒有可顯示的計算結果</span><small>請先確認成績資料與適用規則。</small></li>'


def render_snapshot(snapshot: DecisionSnapshot) -> str:
    """Render the complete responsive HTML view from one DecisionSnapshot."""

    view = build_snapshot_projection(snapshot)
    summary = view["summary"]
    charts_source = "已確認的成績與畢業規則"
    chart_datasets = view.get("chart_datasets") if isinstance(view.get("chart_datasets"), Mapping) else {}
    f5_dataset = chart_datasets.get("f5") if isinstance(chart_datasets.get("f5"), Mapping) else {}
    f5_groups = f5_dataset.get("groups") if isinstance(f5_dataset.get("groups"), (list, tuple)) else ()
    f5 = (
        "".join(
            render_f5_tick_rows(
                group.get("rows", ()),
                source=charts_source,
                title="畢業門檻進度",
            )
            for group in f5_groups
            if isinstance(group, Mapping)
        )
        if f5_dataset.get("available")
        else render_chart_unavailable(
            "F5",
            _public_reason(f5_dataset.get("reason"), "目前沒有可比較的要求進度。"),
            source=charts_source,
            title="畢業要求進度目前無法顯示",
        )
    )
    f1_dataset = chart_datasets.get("f1") if isinstance(chart_datasets.get("f1"), Mapping) else {}
    f1 = (
        render_f1_rung_bars(
            tuple({**row, "label": _public_bucket_label(row.get("label"))} for row in f1_dataset.get("rows", ())),
            source=charts_source, title="正式配置學分分布",
        )
        if f1_dataset.get("available")
        else render_chart_unavailable(
            "F1",
            _public_reason(f1_dataset.get("reason"), "目前沒有可加總的已採計學分。"),
            source=charts_source,
            title="採計學分分布目前無法顯示",
        )
    )
    f7_dataset = chart_datasets.get("f7") if isinstance(chart_datasets.get("f7"), Mapping) else {}
    f7 = (
        render_f7_stacked_rungs(
            tuple({**row, "label": _public_bucket_label(row.get("label"))} for row in f7_dataset.get("rows", ())),
            mode="gate_counts",
            source=charts_source,
            title="判定閘門狀態分布",
        )
        if f7_dataset.get("available")
        else render_chart_unavailable(
            "F7",
            _public_reason(f7_dataset.get("reason"), "目前沒有可比較的要求狀態。"),
            source=charts_source,
            title="要求狀態分布目前無法顯示",
        )
    )
    if f7_dataset.get("reason_code") == "TOO_MANY_GATE_CATEGORIES":
        f7 = ""
    f11_dataset = chart_datasets.get("f11") if isinstance(chart_datasets.get("f11"), Mapping) else {}
    f11 = (
        render_f11_tick_gauge(
            f11_dataset.get("completed"),
            f11_dataset.get("required"),
            source=charts_source,
            title="總畢業學分完成度",
        )
        if f11_dataset.get("available")
        else render_chart_unavailable(
            "F11",
            _public_reason(f11_dataset.get("reason"), "尚未找到可核對的主修總學分門檻。"),
            source=charts_source,
            title="總學分完成度目前無法顯示",
        )
    )
    f1 = _public_chart_markup(f1)
    f5 = _public_chart_markup(f5)
    f7 = _public_chart_markup(f7)
    f11 = _public_chart_markup(f11)
    calculation_markup = _decision_rows(view, _CALCULATION_DECISION_LABELS)
    administrative_markup = _decision_rows(
        view,
        _ADMINISTRATIVE_DECISION_LABELS,
        hide_secondary_self_report=True,
    )
    bucket_rows = "".join(
        f'<tr><th scope="row">{_escape(_public_bucket_label(key))}</th>'
        f'<td><strong>{_escape(_public_credit(value, "待補"))} 學分</strong></td></tr>'
        for key, value in sorted((summary.get("by_bucket") or {}).items(), key=lambda item: str(item[0]))
    ) or '<tr><td colspan="2">目前沒有可顯示的分類學分</td></tr>'
    blocker_markup = "".join(f"<li>{_escape(_public_reason(item, '資料仍需人工核對'))}</li>" for item in summary.get("blockers", ())) or "<li>目前沒有其他待辦</li>"
    warning_markup = "".join(f"<li>{_escape(_public_reason(item, '資料仍需人工核對'))}</li>" for item in summary.get("warnings", ())) or "<li>目前沒有提醒</li>"
    presentation_warning_markup = "".join(f"<li>{_escape(_public_reason(item, '部分進度圖表暫時無法顯示'))}</li>" for item in summary.get("presentation_warnings", ())) or "<li>目前沒有提醒</li>"
    remediation_markup = "".join(f"<li>{_escape(_public_reason(item, '請查看要求明細與規則來源'))}</li>" for item in summary.get("remediation_suggestions", ())) or "<li>請查看要求明細中的下一步。</li>"
    additional_gate_markup = _additional_gate_markup(view)
    unallocated_markup = _unallocated_course_markup(view)
    context_markup = _public_context_markup(view)
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
    .snapshot-badge.is-pass { color: #166534; background: #ECFDF5; }
    .snapshot-badge.is-fail { color: #B91C1C; background: #FEF2F2; }
    .snapshot-badge.is-progress { color: #1D4ED8; background: #EFF6FF; }
    .snapshot-badge.is-pending { color: #92400E; background: #FFFBEB; }
    .snapshot-badge.is-na { color: var(--snapshot-muted); }
    .snapshot-decision-list, .snapshot-simple-list, .snapshot-provenance-list, .snapshot-course-list, .snapshot-course-options { list-style: none; margin: 0; padding: 0; }
    .snapshot-table-scroll { max-width: 100%; overflow-x: auto; overflow-y: hidden; -webkit-overflow-scrolling: touch; }
    .snapshot-report table { border-collapse: collapse; width: 100%; }
    .snapshot-report table th, .snapshot-report table td { border-bottom: 1px solid var(--snapshot-border); padding: .55rem .6rem; text-align: start; vertical-align: top; }
    .snapshot-report table thead th { color: var(--snapshot-muted); font-size: .78rem; font-weight: 800; white-space: nowrap; }
    .snapshot-report table tbody th { font-weight: 700; }
    .snapshot-sr-only { block-size: 1px; clip: rect(0 0 0 0); clip-path: inset(50%); inline-size: 1px; overflow: hidden; position: absolute; white-space: nowrap; }
    .snapshot-decision-list li { align-items: start; border-bottom: 1px solid var(--snapshot-border); display: grid; gap: .35rem; grid-template-columns: minmax(8rem, 1fr) auto; padding: .6rem 0; }
    .snapshot-decision-list small { color: var(--snapshot-muted); grid-column: 1 / -1; }
    .snapshot-simple-list li { align-items: center; border-bottom: 1px solid var(--snapshot-border); display: flex; gap: .75rem; justify-content: space-between; padding: .4rem 0; }
    .snapshot-simple-list strong, .snapshot-report table strong { font-variant-numeric: tabular-nums; }
    .snapshot-chart-details { border-top: 1px solid var(--snapshot-border); margin-top: 1rem; }
    .snapshot-chart-details summary, .snapshot-source-details summary, .snapshot-cs-electives > summary { color: var(--snapshot-primary); cursor: pointer; font-weight: 800; min-block-size: 2.75rem; padding: .65rem 0; }
    .snapshot-requirement-expander { background: var(--snapshot-card); border: 1px solid var(--snapshot-border); border-radius: .75rem; margin-block: .7rem; }
    .snapshot-requirement-expander summary { align-items: center; cursor: pointer; display: flex; flex-wrap: wrap; gap: .45rem 1rem; justify-content: space-between; list-style: none; min-block-size: 2.9rem; padding: .75rem 1rem; }
    .snapshot-requirement-expander summary::-webkit-details-marker { display: none; }
    .snapshot-unallocated-details { background: var(--snapshot-card); border: 1px solid var(--snapshot-border); border-radius: .75rem; }
    .snapshot-unallocated-details > summary { align-items: center; cursor: pointer; display: flex; font-weight: 700; justify-content: space-between; list-style: none; min-block-size: 2.9rem; padding: .75rem 1rem; }
    .snapshot-unallocated-details > summary::-webkit-details-marker { display: none; }
    .snapshot-unallocated-body { padding: 0 1rem 1rem; }
    .snapshot-non-credit-details, .snapshot-subset-details { background: var(--snapshot-card); border: 1px solid var(--snapshot-border); border-radius: .7rem; margin-block: .6rem; }
    .snapshot-non-credit-details > summary, .snapshot-subset-details > summary { align-items: center; cursor: pointer; display: flex; flex-wrap: wrap; font-weight: 700; gap: .45rem 1rem; justify-content: space-between; list-style: none; min-block-size: 2.9rem; padding: .7rem .9rem; }
    .snapshot-non-credit-details > summary::-webkit-details-marker, .snapshot-subset-details > summary::-webkit-details-marker { display: none; }
    .snapshot-non-credit-body, .snapshot-subset-body { border-top: 1px solid var(--snapshot-border); padding: .7rem .9rem .9rem; }
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
    .snapshot-course th, .snapshot-course td { padding: .65rem .75rem; }
    .snapshot-course-id, .snapshot-course-term, .snapshot-course-earned, .snapshot-course-used { font-variant-numeric: tabular-nums; }
    .snapshot-course-earned small { color: var(--snapshot-muted); display: block; font-size: .75rem; margin-top: .2rem; }
    .snapshot-course-list { min-inline-size: 46rem; }
    .snapshot-course-list th:first-child { min-inline-size: 9rem; }
    .snapshot-course-term { min-inline-size: 4.5rem; }
    .snapshot-course-notes { min-inline-size: 13rem; }
    .snapshot-gate-course-list th, .snapshot-gate-course-list td, .snapshot-course-options th, .snapshot-course-options td, .snapshot-credit-category-table th, .snapshot-credit-category-table td { padding-block: .45rem; }
    .snapshot-course-options li { border-bottom: 1px solid var(--snapshot-border); padding: .4rem 0; }
    .snapshot-course-main, .snapshot-course-status { align-items: center; display: flex; flex-wrap: wrap; gap: .35rem .6rem; justify-content: space-between; }
    .snapshot-course-meta { color: var(--snapshot-muted); font-size: .78rem; }
    .snapshot-course-status { color: var(--snapshot-muted); font-size: .82rem; justify-content: start; margin-top: .3rem; }
    .snapshot-course p { color: var(--snapshot-muted); font-size: .82rem; }
    .snapshot-shared { border: 1px solid var(--snapshot-action); border-radius: 999px; color: var(--snapshot-action); font-size: .72rem; padding: .12rem .4rem; }
    .snapshot-course--empty { color: var(--snapshot-muted); }
    .snapshot-provenance-list li { border-bottom: 1px solid var(--snapshot-border); color: var(--snapshot-muted); font-size: .78rem; padding: .4rem 0; }
    .snapshot-status-block { display: grid; gap: .8rem; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); }
     @media (prefers-color-scheme: dark) { .snapshot-report { --snapshot-bg: #0B1120; --snapshot-card: #111827; --snapshot-text: #F8FAFC; --snapshot-muted: #CBD5E1; --snapshot-border: #334155; --snapshot-primary: #60A5FA; --snapshot-action: #60A5FA; } .snapshot-badge.is-pass { color: #86EFAC; } .snapshot-badge.is-fail { color: #FCA5A5; } .snapshot-badge.is-pending { color: #FCD34D; } }
     html[data-theme="light"] .snapshot-report, body[data-theme="light"] .snapshot-report { --snapshot-bg: #F8FAFC; --snapshot-card: #FFFFFF; --snapshot-text: #0F172A; --snapshot-muted: #475569; --snapshot-border: #CBD5E1; --snapshot-primary: #1E3A5F; --snapshot-action: #2563EB; }
     html[data-theme="dark"] .snapshot-report, body[data-theme="dark"] .snapshot-report { --snapshot-bg: #0B1120; --snapshot-card: #111827; --snapshot-text: #F8FAFC; --snapshot-muted: #CBD5E1; --snapshot-border: #334155; --snapshot-primary: #60A5FA; --snapshot-action: #60A5FA; }
     html[data-utaipei-theme="light"] .snapshot-report { --snapshot-bg: #F8FAFC; --snapshot-card: #FFFFFF; --snapshot-text: #0F172A; --snapshot-muted: #475569; --snapshot-border: #CBD5E1; --snapshot-primary: #1E3A5F; --snapshot-action: #2563EB; }
     html[data-utaipei-theme="dark"] .snapshot-report { --snapshot-bg: #0B1120; --snapshot-card: #111827; --snapshot-text: #F8FAFC; --snapshot-muted: #CBD5E1; --snapshot-border: #334155; --snapshot-primary: #60A5FA; --snapshot-action: #60A5FA; }
     html[data-utaipei-theme="light"] .snapshot-report .snapshot-badge.is-pass { color: #166534; }
     html[data-utaipei-theme="light"] .snapshot-report .snapshot-badge.is-fail { color: #B91C1C; }
     html[data-utaipei-theme="light"] .snapshot-report .snapshot-badge.is-pending { color: #92400E; }
     html[data-utaipei-theme="dark"] .snapshot-report .snapshot-badge.is-pass { color: #86EFAC; }
     html[data-utaipei-theme="dark"] .snapshot-report .snapshot-badge.is-fail { color: #FCA5A5; }
     html[data-utaipei-theme="dark"] .snapshot-report .snapshot-badge.is-pending { color: #FCD34D; }
     @media (prefers-reduced-motion: reduce) { .snapshot-report * { animation: none !important; transition: none !important; } }
    @media (max-width: 600px) { .snapshot-report { padding-inline: .25rem; } .snapshot-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } .snapshot-requirement-expander summary { align-items: start; flex-direction: column; } }
    """
    snapshot_id = _escape(view.get("snapshot_id"))
    course_counts = summary.get("course_counts") if isinstance(summary.get("course_counts"), Mapping) else {}
    required_progress = summary.get("required_progress") if isinstance(summary.get("required_progress"), Mapping) else {}
    effective_credits = _public_credit(summary.get("counted_exclusive_credits"), "需要補資料")
    missing_credits = _public_credit(summary.get("missing_credits"), "需要補資料")
    required_done = _text(required_progress.get("completed"), "需要補資料")
    required_total = _text(required_progress.get("required"), "需要補資料")
    todo_count = _text(summary.get("todo_count"), "需要補資料")
    in_progress = _text(course_counts.get("IN_PROGRESS", summary.get("in_progress")), "需要補資料")
    public_verdict = _public_status_label(view.get("verdict"))
    statistics_schema = _escape(summary.get("statistics_schema"))
    statistics_digest = _escape(summary.get("statistics_digest"))
    input_state = _input_confirmation_label(summary.get("input_confirmation_state"))
    unallocated = _public_credit(summary.get("unallocated_credits"), "需要補資料")
    required_total_number = _decimal(required_total)
    todo_number = _decimal(todo_count)
    required_progress_display = (
        "請查看要求明細"
        if required_progress.get("available") is False
        or (required_total_number == Decimal("0") and (todo_number or Decimal("0")) > Decimal("0"))
        else f"{required_done}／{required_total} 項"
    )
    current_credit_rows = (
        f'<tr><th scope="row">有效學分</th><td><strong>{_escape(effective_credits)} 學分</strong></td></tr>'
        f'<tr><th scope="row">尚未配置</th><td><strong>{_escape(unallocated)} 學分</strong></td></tr>'
    )
    return (
        f'<section id="utaipei-snapshot-report" class="snapshot-report" data-snapshot-id="{snapshot_id}" data-verdict="{_escape(_public_status_slug(view.get("verdict")))}" data-statistics-schema="{statistics_schema}" data-statistics-digest="{statistics_digest}">'
        f'<style>{css}</style><span id="utaipei-analysis-state" data-analysis-active="true" data-exported="false" hidden></span>'
        '<header class="snapshot-header"><div><p class="snapshot-eyebrow">北市大畢業通</p><h1>畢業進度</h1>'
        f'<p class="snapshot-kicker">依已確認的成績資料整理 · 更新於 {_escape(_format_evaluated_at(view.get("evaluated_at")))}</p></div>'
        f'<span class="snapshot-badge {_status_class(view.get("verdict"))}">{_escape(public_verdict)}</span></header>'
        f'<p class="snapshot-context">{context_markup}</p>'
        '<div class="snapshot-metrics">'
        f'{_metric("有效學分", f"{effective_credits} 學分", "依已確認課程採計")}'
        f'{_metric("尚缺學分", f"{missing_credits} 學分", "依主修總學分門檻計算")}'
        f'{_metric("必修進度", required_progress_display, f"尚有 {todo_count} 項待辦")}'
        f'{_metric("修習中", f"{in_progress} 門", f"資料確認：{input_state}")}'
        '</div>'
        '<section class="snapshot-card"><h2>計算結果</h2><ul class="snapshot-decision-list">'
        f'{calculation_markup}</ul></section>'
        '<section class="snapshot-card"><h2>行政資訊</h2><ul class="snapshot-decision-list">'
        f'{administrative_markup}</ul></section>'
        f'{additional_gate_markup}'
        '<section class="snapshot-card"><h2>學分分布</h2><div class="snapshot-status-block">'
        '<div><h3>各類別學分</h3><div class="snapshot-table-scroll">'
        '<table class="snapshot-simple-list snapshot-credit-category-table" aria-label="各類別學分">'
        '<caption class="snapshot-sr-only">各類別學分</caption><thead><tr><th scope="col">類別</th><th scope="col">學分</th></tr></thead>'
        f'<tbody>{bucket_rows}</tbody></table></div></div>'
        '<div><h3>目前採計情況</h3><div class="snapshot-table-scroll">'
        '<table class="snapshot-simple-list snapshot-credit-summary-table" aria-label="目前採計情況">'
        '<caption class="snapshot-sr-only">目前採計情況</caption><thead><tr><th scope="col">項目</th><th scope="col">學分</th></tr></thead>'
        f'<tbody>{current_credit_rows}</tbody></table></div></div>'
        '</div></section>'
        '<section class="snapshot-card"><h2>其他進度圖表（選看）</h2>'
        f'<details class="snapshot-chart-details"><summary>查看圖表</summary><div class="snapshot-chart-stack">{f11}{f1}{f7}{f5}</div></details>'
        '</section>'
        '<section><h2>各項畢業要求</h2>'
        f'{_requirements_markup(view)}'
        '</section>'
        f'{unallocated_markup}'
        '<section class="snapshot-card"><h2>待辦與提醒</h2><ul class="snapshot-simple-list">'
        f'{blocker_markup}</ul><h3>警告</h3><ul class="snapshot-simple-list">{warning_markup}</ul>'
        f'<h3>呈現提醒</h3><ul class="snapshot-simple-list">{presentation_warning_markup}</ul>'
        f'<h3>建議下一步</h3><ul class="snapshot-simple-list">{remediation_markup}</ul></section>'
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
