"""Deterministic, privacy-safe exports for a :class:`DecisionSnapshot`.

Every public export function first builds the same presentation projection.
That projection is the only source for the screen-facing values and the
export payload, so an export cannot silently run a second allocation or rule
calculation.  Course identity is retained because it is required for an
audit, while student identity, credentials, raw transcripts, and secret
records are never copied.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping
from html import unescape
from typing import Any

from decision_snapshot import DecisionSnapshot
from snapshot_renderer import (
    MANUAL_LABEL,
    PUBLIC_PENDING,
    _cs_elective_rollup,
    _format_evaluated_at,
    _gate_course_text,
    _matched_gate_courses,
    _non_credit_progress_text,
    _non_credit_result_rows,
    _public_bucket_label,
    _public_condition,
    _public_context_markup,
    _public_course_value,
    _public_credit,
    _public_reason,
    _public_status_label,
    _result_blockers,
    _result_source_items,
    _result_values,
    _subset_name,
    _subset_progress_text,
    _subset_result_rows,
    _unallocated_course_guidance,
    _unallocated_course_items,
    build_snapshot_view,
    sanitize_snapshot_value,
)

UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"

_EXPORT_SCHEMA = "snapshot-export.v1"
_CSV_FIELDS = (
    "snapshot_id",
    "verdict",
    "attempt_id",
    "course_id",
    "course_name",
    "academic_term",
    "course_status",
    "identity_status",
    "source_credits",
    "used_credits",
    "unallocated_credits",
    "requirement_id",
    "requirement_name",
    "requirement_status",
    "requirement_status_authoritative",
    "requirement_observed_status",
    "credits",
    "allocation_kind",
    "direction",
    "binding_id",
    "shared_credit",
    "allocation_reason",
    "allocations_json",
    "warnings_json",
    "presentation_warnings_json",
    "course_counts_json",
    "requirement_counts_json",
    "blockers_json",
    "statistics_schema",
    "statistics_digest",
    "statistics_json",
    "chart_datasets_json",
    "decisions_json",
)

_STUDENT_CSV_FIELDS = (
    "報表編號",
    "要求類別",
    "要求名稱",
    "要求狀態",
    "要求學分",
    "已採計學分",
    "尚缺學分",
    "課程代碼",
    "課程名稱",
    "修課學期",
    "修課狀態",
    "課程學分",
    "本要求採計",
    "尚未配置學分",
    "採計用途",
    "採計原因",
    "規則來源",
    "資料狀態",
    "下一步",
)


def _plain(value: Any) -> Any:
    """Apply the renderer's recursive privacy boundary before serialization."""

    return sanitize_snapshot_value(value)


def _json(value: Any) -> str:
    return json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return fallback


def _csv_cell(value: Any) -> str:
    """Prefix spreadsheet formula-like cells with an apostrophe.

    This applies to course names, identifiers, source references, and all
    textual metadata.  A leading apostrophe is the conventional spreadsheet
    escape and remains visible in raw CSV, making the protection auditable.
    """

    text = _text(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _requirement_names(view: Mapping[str, Any]) -> Mapping[str, str]:
    return {
        _text(item.get("requirement_id")): _text(item.get("name"))
        for item in view.get("requirements", ())
        if isinstance(item, Mapping) and _text(item.get("requirement_id"))
    }


def _requirement_views(view: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    return {
        _text(item.get("requirement_id")): item
        for item in view.get("requirements", ())
        if isinstance(item, Mapping) and _text(item.get("requirement_id"))
    }


def build_snapshot_export_payload(snapshot: DecisionSnapshot) -> Mapping[str, Any]:
    """Return the canonical export payload derived from one snapshot read."""

    view = build_snapshot_view(snapshot)
    # Keep these values exactly as they appear in the screen projection.  The
    # list/dict copies only make JSON serialization deterministic; no numeric
    # or policy decision is recalculated here.
    return {
        "_export_schema": _EXPORT_SCHEMA,
        "_source": "DecisionSnapshot",
        "_projection_schema": view.get("_projection_schema"),
        "statistics_schema": view.get("statistics_schema") or (view.get("summary", {}).get("statistics_schema") if isinstance(view.get("summary"), Mapping) else ""),
        "statistics_digest": view.get("statistics_digest") or (view.get("summary", {}).get("statistics_digest") if isinstance(view.get("summary"), Mapping) else ""),
        "_statistics_schema": view.get("statistics_schema") or (view.get("summary", {}).get("statistics_schema") if isinstance(view.get("summary"), Mapping) else ""),
        "_statistics_digest": view.get("statistics_digest") or (view.get("summary", {}).get("statistics_digest") if isinstance(view.get("summary"), Mapping) else ""),
        "snapshot_id": view.get("snapshot_id"),
        "_snapshot_id": view.get("snapshot_id"),
        "evaluated_at": view.get("evaluated_at"),
        "verdict": view.get("verdict"),
        "context": _plain(view.get("context", {})),
        "summary": _plain(view.get("summary", {})),
        "decisions": _plain(view.get("decisions", {})),
        "requirements": _plain(view.get("requirements", ())),
        "non_credit_results": _plain(view.get("non_credit_results", ())),
        "subset_results": _plain(view.get("subset_results", ())),
        "attempts": _plain(view.get("attempts", ())),
        "allocations": _plain(view.get("allocations", ())),
        "allocation": _plain(view.get("allocation", {})),
        "alternatives": _plain(view.get("alternatives", ())),
        "warnings": _plain(view.get("warnings", ())),
        "presentation_warnings": _plain(view.get("presentation_warnings", ())),
        "course_counts": _plain(view.get("course_counts", view.get("summary", {}).get("course_counts", {}) if isinstance(view.get("summary"), Mapping) else {})),
        "requirement_counts": _plain(view.get("requirement_counts", view.get("summary", {}).get("requirement_counts", {}) if isinstance(view.get("summary"), Mapping) else {})),
        "blockers": _plain(view.get("blockers", ())),
        "statistics": _plain(view.get("statistics", {})),
        "chart_datasets": _plain(view.get("chart_datasets", {})),
        "rule_provenance": _plain(view.get("rule_provenance", ())),
        "remediation_suggestions": _plain(view.get("remediation_suggestions", ())),
        "input_confirmation": _plain(view.get("input_confirmation", {})),
    }


def _allocation_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    attempts = {
        _text(item.get("attempt_id")): item
        for item in payload.get("attempts", ())
        if isinstance(item, Mapping) and _text(item.get("attempt_id"))
    }
    requirement_names = _requirement_names(payload)
    requirement_views = _requirement_views(payload)
    allocations = [item for item in payload.get("allocations", ()) if isinstance(item, Mapping)]
    rows: list[dict[str, Any]] = []
    for allocation in allocations:
        attempt_id = _text(allocation.get("attempt_id"))
        attempt = attempts.get(attempt_id, {})
        portions = [item for item in allocation.get("portions", ()) if isinstance(item, Mapping)]
        base = {
            "snapshot_id": payload.get("snapshot_id"),
            "verdict": payload.get("verdict"),
            "attempt_id": attempt_id,
            "course_id": attempt.get("course_id", ""),
            "course_name": attempt.get("course_name", ""),
            "academic_term": attempt.get("academic_term", ""),
            "course_status": attempt.get("status", "UNKNOWN"),
            "identity_status": attempt.get("identity_status", "UNKNOWN"),
            "source_credits": allocation.get("source_credits", ""),
            "used_credits": allocation.get("used_credits", ""),
            "unallocated_credits": allocation.get("unallocated_credits", ""),
            "allocation_reason": allocation.get("allocation_reason", ""),
            # These JSON columns are repeated on each course row so an
            # exported detail file is independently auditable.
            "allocations_json": _json(payload.get("allocations", ())),
            "warnings_json": _json(payload.get("warnings", ())),
            "presentation_warnings_json": _json(payload.get("presentation_warnings", ())),
            "course_counts_json": _json(payload.get("course_counts", {})),
            "requirement_counts_json": _json(payload.get("requirement_counts", {})),
            "blockers_json": _json(payload.get("blockers", ())),
            "statistics_schema": payload.get("statistics_schema", ""),
            "statistics_digest": payload.get("statistics_digest", ""),
            "statistics_json": _json(payload.get("statistics", {})),
            "chart_datasets_json": _json(payload.get("chart_datasets", {})),
            "decisions_json": _json(payload.get("decisions", {})),
        }
        if portions:
            for portion in portions:
                requirement_id = _text(portion.get("requirement_id"))
                requirement_view = requirement_views.get(requirement_id, {})
                rows.append(
                    {
                        **base,
                        "requirement_id": requirement_id,
                        "requirement_name": requirement_names.get(requirement_id, ""),
                        "requirement_status": requirement_view.get("status", UNKNOWN),
                        "requirement_status_authoritative": requirement_view.get("status_authoritative", False),
                        "requirement_observed_status": requirement_view.get("observed_status", UNKNOWN),
                        "credits": portion.get("credits", ""),
                        "allocation_kind": portion.get("allocation_kind", ""),
                        "direction": portion.get("direction", ""),
                        "binding_id": portion.get("binding_id", ""),
                        "shared_credit": bool(portion.get("is_shared_shadow") or _text(portion.get("allocation_kind")).upper() in {"SHARED_SHADOW", "SHARED_REUSE"}),
                    }
                )
        else:
            rows.append(
                {
                    **base,
                    "requirement_id": "",
                    "requirement_name": "",
                    "requirement_status": UNKNOWN,
                    "requirement_status_authoritative": False,
                    "requirement_observed_status": UNKNOWN,
                    "credits": "0",
                    "allocation_kind": "UNALLOCATED",
                    "direction": "",
                    "binding_id": "",
                    "shared_credit": False,
                }
            )
    if rows:
        return rows
    return [
        {
            "snapshot_id": payload.get("snapshot_id"),
            "verdict": payload.get("verdict"),
            "attempt_id": "",
            "course_id": "",
            "course_name": "",
            "academic_term": "",
            "course_status": "UNKNOWN",
            "identity_status": "UNKNOWN",
            "source_credits": "0",
            "used_credits": "0",
            "unallocated_credits": "0",
            "requirement_id": "",
            "requirement_name": "",
            "requirement_status": UNKNOWN,
            "requirement_status_authoritative": False,
            "requirement_observed_status": UNKNOWN,
            "credits": "0",
            "allocation_kind": "NO_DATA",
            "direction": "",
            "binding_id": "",
            "shared_credit": False,
            "allocation_reason": MANUAL_LABEL,
            "allocations_json": _json(payload.get("allocations", ())),
            "warnings_json": _json(payload.get("warnings", ())),
            "presentation_warnings_json": _json(payload.get("presentation_warnings", ())),
            "course_counts_json": _json(payload.get("course_counts", {})),
            "requirement_counts_json": _json(payload.get("requirement_counts", {})),
            "blockers_json": _json(payload.get("blockers", ())),
            "statistics_schema": payload.get("statistics_schema", ""),
            "statistics_digest": payload.get("statistics_digest", ""),
            "statistics_json": _json(payload.get("statistics", {})),
            "chart_datasets_json": _json(payload.get("chart_datasets", {})),
            "decisions_json": _json(payload.get("decisions", {})),
        }
    ]


def build_allocation_csv(snapshot: DecisionSnapshot) -> bytes:
    """Return UTF-8-BOM allocation detail CSV from one snapshot projection."""

    payload = build_snapshot_export_payload(snapshot)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in _allocation_rows(payload):
        writer.writerow({field: _csv_cell(row.get(field, "")) for field in _CSV_FIELDS})
    return output.getvalue().encode("utf-8-sig")


def _student_source_text(items: Any) -> str:
    """Turn provenance records into a short Chinese reference for students."""

    references: list[str] = []
    if isinstance(items, Mapping):
        source_items = (items,)
    elif isinstance(items, (str, int, float)):
        source_items = (items,)
    elif isinstance(items, (list, tuple)):
        source_items = items
    else:
        source_items = ()
    for item in source_items:
        if not isinstance(item, Mapping):
            reference = _public_reason(item, "規則來源尚待補充")
            if reference != "規則來源尚待補充":
                references.append(f"來源：{reference}")
            continue
        parts: list[str] = []
        location = _text(item.get("source_location") or item.get("location") or item.get("table_location"))
        source_file = _text(item.get("source_file"))
        pages = _text(item.get("pages") or item.get("page") or item.get("pdf_page") or item.get("printed_page"))
        clause = _text(item.get("original_clause") or item.get("original_text"))
        if location:
            parts.append(f"位置：{location}")
        elif source_file:
            parts.append(f"文件：{source_file}")
        if pages:
            parts.append(f"頁碼：{pages}")
        if clause:
            parts.append(f"條文：{_public_reason(clause, '規則條文')}")
        if not parts:
            reference = _text(item.get("source_reference") or item.get("evidence_reference"))
            if reference:
                parts.append(f"來源：{_public_reason(reference, '規則來源已保留於稽核資料')}")
        if parts:
            references.append("；".join(parts))
    return "；".join(dict.fromkeys(references)) or "規則來源尚待補充"


def _student_context_text(view: Mapping[str, Any]) -> str:
    """Return the renderer's identity context without HTML markup."""

    return unescape(_public_context_markup(view)).replace("　·　", "；")


def _student_next_step(requirement: Mapping[str, Any]) -> str:
    status = _text(requirement.get("status"), UNKNOWN).upper()
    if status == "PASS":
        return "目前已完成；請保留這份成績資料。"
    blockers = [
        _public_reason(item, "資料仍需人工核對")
        for item in requirement.get("blockers", ())
        if _text(item)
    ]
    if blockers:
        return "；".join(dict.fromkeys(blockers))
    if status in {UNKNOWN, "NOT_APPLICABLE"}:
        return "請查看規則來源並補充可核對的資料。"
    return "請查看要求明細，確認尚缺課程或學分。"


def _student_gate_next_step(result: Mapping[str, Any]) -> str:
    status = _text(result.get("status"), UNKNOWN).upper()
    blockers = _result_blockers(result)
    if blockers:
        return "；".join(dict.fromkeys(blockers))
    if status == "PASS":
        return "目前已符合此項門檻；請保留規則來源。"
    if status == "FAIL":
        return "請依規則來源補足尚缺項目。"
    return "請查看規則來源並補充可核對的資料。"


def _student_non_credit_row(view: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, str]:
    status = _public_status_label(result.get("status"), PUBLIC_PENDING)
    name = _public_reason(
        result.get("name") or result.get("label") or result.get("requirement_id"),
        "非學分門檻",
    )
    progress = _non_credit_progress_text(result)
    blockers = "；".join(_result_blockers(result)) or "依已確認資料檢查"
    coverage = _public_reason(result.get("coverage_state", result.get("coverage")), "來源尚未完整")
    evidence = _public_reason(result.get("evidence_state", result.get("evidence")), "來源尚未核對")
    courses = _matched_gate_courses(view, result)
    return {
        "報表編號": _text(view.get("snapshot_id"), "需要補資料"),
        "要求類別": "非學分門檻",
        "要求名稱": name,
        "要求狀態": status,
        "要求學分": progress,
        "已採計學分": "門檻不另外增加學分",
        "尚缺學分": "—",
        "課程代碼": "",
        "課程名稱": "；".join(_gate_course_text(course) for course in courses),
        "修課學期": _result_values(result.get("completed_terms"), fallback="尚無"),
        "修課狀態": status,
        "課程學分": "—",
        "本要求採計": "—",
        "尚未配置學分": "—",
        "採計用途": "非學分門檻（不另外增加學分）",
        "採計原因": blockers,
        "規則來源": _student_source_text(_result_source_items(result)),
        "資料狀態": f"{coverage}；{evidence}",
        "下一步": _student_gate_next_step(result),
    }


def _student_subset_row(view: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, str]:
    status = _public_status_label(result.get("status"), PUBLIC_PENDING)
    name = _subset_name(result)
    progress = _subset_progress_text(result)
    unknown = _public_credit(result.get("unknown_candidate_credits"), "0")
    reason = "；".join(_result_blockers(result)) or (f"另有 {unknown} 學分候選仍待核對" if unknown != "0" else "依規則指定的學分採計結果檢查")
    provenance_state = "；".join(
        _public_reason(value, "需要核對來源")
        for value in (
            result.get("coverage_state", result.get("coverage")),
            result.get("evidence_state", result.get("evidence")),
        ) if value not in (None, "")
    ) or ("依列示規則來源" if _result_source_items(result) else "尚未提供規則來源")
    return {
        "報表編號": _text(view.get("snapshot_id"), "需要補資料"),
        "要求類別": "學分採計條件",
        "要求名稱": name,
        "要求狀態": status,
        "要求學分": progress,
        "已採計學分": "沿用已採計學分",
        "尚缺學分": "—",
        "課程代碼": "",
        "課程名稱": "",
        "修課學期": "—",
        "修課狀態": status,
        "課程學分": "—",
        "本要求採計": "—",
        "尚未配置學分": "—",
        "採計用途": "學分採計條件（不另增加學分）",
        "採計原因": reason,
        "規則來源": _student_source_text(_result_source_items(result)),
        "資料狀態": provenance_state,
        "下一步": _student_gate_next_step(result),
    }


def _student_unallocated_courses(view: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return confirmed transcript courses that have no requirement detail row."""

    return list(_unallocated_course_items(view))


def _student_unallocated_row(view: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, str]:
    attempt = item.get("attempt") if isinstance(item.get("attempt"), Mapping) else {}
    allocation = item.get("allocation") if isinstance(item.get("allocation"), Mapping) else {}
    status = _public_status_label(attempt.get("status"), PUBLIC_PENDING)
    term = "尚未修課" if status == "尚未修課" else (_text(attempt.get("academic_term")) or "學期待補")
    course_id = _public_course_value(attempt.get("course_id"))
    course_name = _public_course_value(attempt.get("course_name"))
    source_credits = _public_credit(
        allocation.get("source_credits", attempt.get("credits")),
        "待補",
    )
    used_credits = _public_credit(allocation.get("used_credits"), "0")
    unallocated = _public_credit(allocation.get("unallocated_credits"), source_credits)
    purpose, status_reason = _unallocated_course_guidance(attempt)
    allocation_reason = _public_reason(allocation.get("allocation_reason"), status_reason)
    return {
        "報表編號": _text(view.get("snapshot_id"), "需要補資料"),
        "要求類別": "尚未配置",
        "要求名稱": "尚未採計課程",
        "要求狀態": "需要補資料",
        "要求學分": "—",
        "已採計學分": "0",
        "尚缺學分": "—",
        "課程代碼": course_id,
        "課程名稱": course_name,
        "修課學期": term,
        "修課狀態": status,
        "課程學分": source_credits,
        "本要求採計": used_credits,
        "尚未配置學分": unallocated,
        "採計用途": purpose,
        "採計原因": allocation_reason,
        "規則來源": "尚未對應到特定要求；請查看各項畢業要求",
        "資料狀態": "成績列已確認；尚未安排至畢業要求",
        "下一步": "請查看各項畢業要求，確認是否可作為自由選修。",
    }


def _student_csv_rows(view: Mapping[str, Any]) -> list[dict[str, str]]:
    """Build detail rows from the same projection used by the HTML report."""

    rows: list[dict[str, str]] = []
    for requirement in view.get("requirements", ()):
        if not isinstance(requirement, Mapping):
            continue
        category = _public_bucket_label(requirement.get("bucket"))
        kind = _text(requirement.get("kind"))
        if kind:
            category = f"{category}・{kind}"
        required = _public_credit(requirement.get("required_credits"), "需要補資料")
        effective = _public_credit(requirement.get("effective_credits"), "需要補資料")
        deficit = _public_credit(requirement.get("deficit"), "需要補資料")
        requirement_status = _public_status_label(requirement.get("status"))
        coverage = _public_reason(requirement.get("coverage_state"), "來源尚未完整")
        evidence = _public_reason(requirement.get("evidence_state"), "來源尚未核對")
        data_state = f"{coverage}；{evidence}"
        source = _student_source_text(requirement.get("rule_provenance", ()))
        next_step = _student_next_step(requirement)
        courses = [item for item in requirement.get("courses", ()) if isinstance(item, Mapping)]
        if not courses:
            courses = [{}]
        for course in courses:
            course_status = _public_status_label(course.get("status"), PUBLIC_PENDING)
            allocation_reason = _public_reason(course.get("allocation_reason"), "目前沒有可由規則安全確認的採計方式")
            purpose = _public_reason(course.get("allocation_kind_label"), "採計用途待補")
            rows.append(
                {
                    "報表編號": _text(view.get("snapshot_id"), "需要補資料"),
                    "要求類別": category,
                    "要求名稱": _text(requirement.get("name"), "未命名要求"),
                    "要求狀態": requirement_status,
                    "要求學分": required,
                    "已採計學分": effective,
                    "尚缺學分": deficit,
                    "課程代碼": _public_course_value(course.get("course_id")),
                    "課程名稱": _public_course_value(course.get("course_name")),
                    "修課學期": (
                        "尚未修課"
                        if course.get("is_not_attempted") or _text(course.get("status")).upper() in {"NOT_ATTEMPTED", "NOT_TAKEN"}
                        else _text(course.get("academic_term"), "學期待補")
                    ),
                    "修課狀態": course_status,
                    "課程學分": _public_credit(course.get("source_credits"), "待補"),
                    "本要求採計": _public_credit(course.get("used_credits"), "待補"),
                    "尚未配置學分": _public_credit(course.get("unallocated_credits"), "0"),
                    "採計用途": purpose,
                    "採計原因": allocation_reason,
                    "規則來源": source,
                    "資料狀態": data_state,
                    "下一步": next_step,
                }
            )
    rows.extend(_student_unallocated_row(view, item) for item in _student_unallocated_courses(view))
    rows.extend(_student_non_credit_row(view, item) for item in _non_credit_result_rows(view))
    rows.extend(_student_subset_row(view, item) for item in _subset_result_rows(view))
    if rows:
        return rows
    fallback = {
        field: ("目前沒有可顯示的要求，請先確認成績資料。" if field == "下一步" else "需要補資料")
        for field in _STUDENT_CSV_FIELDS
    }
    fallback["報表編號"] = _text(view.get("snapshot_id"), "需要補資料")
    return [fallback]


def build_student_allocation_csv(snapshot: DecisionSnapshot) -> bytes:
    """Return a Chinese, student-facing detail CSV from one snapshot."""

    view = build_snapshot_view(snapshot)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_STUDENT_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in _student_csv_rows(view):
        writer.writerow({field: _csv_cell(row.get(field, "")) for field in _STUDENT_CSV_FIELDS})
    return output.getvalue().encode("utf-8-sig")


def build_audit_json(snapshot: DecisionSnapshot) -> bytes:
    """Return a deterministic UTF-8 audit JSON export."""

    payload = build_snapshot_export_payload(snapshot)
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _pdf_lines(payload: Mapping[str, Any]) -> list[str]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    course_counts = payload.get("course_counts") if isinstance(payload.get("course_counts"), Mapping) else {}
    requirement_counts = payload.get("requirement_counts") if isinstance(payload.get("requirement_counts"), Mapping) else {}
    lines = [
        "北市大畢業通｜可稽核分析摘要",
        f"DecisionSnapshot：{_text(payload.get('snapshot_id'))}",
        f"評估時間：{_text(payload.get('evaluated_at'))}",
        f"判定：{_text(payload.get('verdict'), 'UNKNOWN')}",
        f"統計 schema／digest：{_text(payload.get('_statistics_schema'), 'decision-statistics.v2')}／{_text(payload.get('_statistics_digest'), MANUAL_LABEL)}",
        "",
        "摘要",
        f"來源實得學分：{_text(summary.get('source_earned_credits'), MANUAL_LABEL)}（不等於畢業要求總量）",
        f"正式配置學分：{_text(summary.get('counted_exclusive_credits'), MANUAL_LABEL)}",
        f"要求總量：{_text(summary.get('required_graduation_credits'), MANUAL_LABEL)}",
        f"主修完成度：{_text(summary.get('primary_status'), UNKNOWN)}",
        f"雙主修完成度：{_text(summary.get('double_major_status'), NOT_APPLICABLE)}",
        f"輔系申請／資格：{_text(summary.get('minor_application_status'), NOT_APPLICABLE)}",
        f"輔系課程完成度：{_text(summary.get('minor_coursework_status'), NOT_APPLICABLE)}；已配置 {_text(summary.get('minor_credits'), '0')} 學分",
        f"正式授予輔系：{_text(summary.get('formal_minor_award_status'), NOT_APPLICABLE)}",
        f"課程列數（已完成／修習中／待確認）：{_text(course_counts.get('PASS'), MANUAL_LABEL)}／{_text(course_counts.get('IN_PROGRESS'), MANUAL_LABEL)}／{_text(course_counts.get('UNKNOWN'), MANUAL_LABEL)}",
        f"要求項目數（通過／未通過／待確認）：{_text(requirement_counts.get('PASS'), MANUAL_LABEL)}／{_text(requirement_counts.get('FAIL'), MANUAL_LABEL)}／{_text(requirement_counts.get('UNKNOWN'), MANUAL_LABEL)}",
        f"要求缺額項目數：{_text(requirement_counts.get('deficit_count'), MANUAL_LABEL)}",
        f"已認列／尚未配置：{_text(summary.get('recognized_credits'), MANUAL_LABEL)}／{_text(summary.get('unallocated_credits'), MANUAL_LABEL)}",
        "",
        "判定與規則來源",
    ]
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), Mapping) else {}
    for key in sorted(decisions, key=str):
        decision = decisions[key]
        if isinstance(decision, Mapping):
            lines.append(f"{key}：{_text(decision.get('status'), UNKNOWN)}；{_text(decision.get('reason'), MANUAL_LABEL)}")
    provenance = payload.get("rule_provenance", ())
    if provenance:
        for item in provenance:
            if isinstance(item, Mapping):
                lines.append(
                    "來源：" + "；".join(
                        _text(item.get(key))
                        for key in ("source_reference", "source_location", "source_file", "pages", "authority", "evidence_reference")
                        if _text(item.get(key))
                    )
                )
    else:
        lines.append(MANUAL_LABEL)
    lines.extend(("", "畢業要求明細"))
    for requirement in payload.get("requirements", ()):
        if not isinstance(requirement, Mapping):
            continue
        lines.extend(
            (
                f"{_text(requirement.get('name'))}｜{_text(requirement.get('kind'))}",
                f"狀態：{_text(requirement.get('status'), UNKNOWN)}；有效／正式／共享／要求：{_text(requirement.get('effective_credits'), MANUAL_LABEL)}／{_text(requirement.get('exclusive_credits'), MANUAL_LABEL)}／{_text(requirement.get('shared_credits'), MANUAL_LABEL)}／{_text(requirement.get('required_credits'), MANUAL_LABEL)}；尚缺：{_text(requirement.get('deficit'), MANUAL_LABEL)}",
                f"覆蓋／證據：{_text(requirement.get('coverage_state'), UNKNOWN)}／{_text(requirement.get('evidence_state'), UNKNOWN)}；{_text(requirement.get('manual_confirmation'), MANUAL_LABEL)}",
                f"修課條件：{_text(requirement.get('choice_condition'), MANUAL_LABEL)}",
            )
        )
        eligible_courses = requirement.get("eligible_courses", ())
        if eligible_courses:
            lines.append("官方可選／指定科目：")
            for option in eligible_courses:
                if isinstance(option, Mapping):
                    option_name = _text(option.get("course_name"))
                    option_id = _text(option.get("course_id"))
                    label = option_name or option_id or MANUAL_LABEL
                    suffix = f"（{option_id}）" if option_name and option_id else ""
                    lines.append(f"  - {label}{suffix}")
        else:
            lines.append("官方可選／指定科目：" + MANUAL_LABEL)
        for course in requirement.get("courses", ()):
            if isinstance(course, Mapping):
                lines.append(
                    f"  課程：{_text(course.get('course_name'))}；使用 {_text(course.get('used_credits'))} 學分；{_text(course.get('status_label'))}；{_text(course.get('allocation_reason'))}"
                )
    lines.extend(("", "阻塞項目"))
    blockers = payload.get("blockers", ())
    lines.extend(f"- {_text(item)}" for item in blockers) if blockers else lines.append("無")
    lines.extend(("警告",))
    warnings = payload.get("warnings", ())
    lines.extend(f"- {_text(item)}" for item in warnings) if warnings else lines.append("無")
    lines.append("呈現提醒")
    presentation_warnings = payload.get("presentation_warnings", ())
    lines.extend(f"- {_text(item)}" for item in presentation_warnings) if presentation_warnings else lines.append("無")
    lines.extend((f"安全補修方向（{_text(summary.get('remediation_status'), 'DIRECTION_ONLY')}）",))
    suggestions = payload.get("remediation_suggestions", ())
    lines.extend(f"- {_text(item)}" for item in suggestions) if suggestions else lines.append(MANUAL_LABEL)
    lines.extend(
        (
            "",
            "以下為與畫面／CSV／JSON一致的快照欄位摘要（不含個資、憑證或原始成績單）：",
            "snapshot_id=" + _text(payload.get("snapshot_id")),
            "verdict=" + _text(payload.get("verdict"), UNKNOWN),
            "allocations=" + _json(payload.get("allocations", ())),
            "warnings=" + _json(payload.get("warnings", ())),
            "presentation_warnings=" + _json(payload.get("presentation_warnings", ())),
            "course_counts=" + _json(payload.get("course_counts", {})),
            "requirement_counts=" + _json(payload.get("requirement_counts", {})),
            "blockers=" + _json(payload.get("blockers", ())),
            "statistics=" + _json(payload.get("statistics", {})),
            "chart_datasets=" + _json(payload.get("chart_datasets", {})),
        )
    )
    return lines


def _wrap_pdf_line(line: str, fitz: Any, *, width: float, fontsize: float) -> list[str]:
    """Wrap by actual built-in-font width so no PDF line clips at the edge."""

    if not line:
        return [" "]
    chunks: list[str] = []
    current = ""
    for character in line:
        candidate = current + character
        try:
            candidate_width = fitz.get_text_length(candidate, fontname="china-t", fontsize=fontsize)
        except (AttributeError, TypeError, ValueError):
            candidate_width = len(candidate) * fontsize
        if current and candidate_width > width:
            chunks.append(current)
            current = character
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [" "]


def build_pdf(snapshot: DecisionSnapshot) -> bytes:
    """Return an openable paginated PDF using PyMuPDF's built-in CJK font."""

    payload = build_snapshot_export_payload(snapshot)
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - dependency is pinned in requirements
        raise RuntimeError("PDF 匯出需要 PyMuPDF（fitz）。") from exc

    document = fitz.open()
    page_width, page_height = fitz.paper_size("a4")
    margin = 42
    line_height = 15
    font_size = 9.5
    page = document.new_page(width=page_width, height=page_height)
    y = margin
    for raw_line in _pdf_lines(payload):
        line = raw_line or " "
        # Keep each insert within the printable width using actual built-in
        # CJK font metrics, rather than a character-count approximation.
        wrapped = _wrap_pdf_line(line, fitz, width=page_width - 2 * margin, fontsize=font_size)
        for chunk in wrapped:
            if y + line_height > page_height - margin:
                page = document.new_page(width=page_width, height=page_height)
                y = margin
            page.insert_text((margin, y), chunk, fontsize=font_size, fontname="china-t", color=(0.06, 0.09, 0.16))
            y += line_height
    document.set_metadata(
        {
            "title": "北市大畢業通",
            "author": "北市大畢業通",
            "subject": f"DecisionSnapshot {_text(payload.get('snapshot_id'))}",
            "keywords": "graduation audit, decision snapshot",
        }
    )
    result = document.tobytes()
    document.close()
    return result


_STUDENT_CALCULATION_LABELS = {
    "primary_graduation": "主修畢業要求",
    "double_major_qualification": "雙主修課程要求",
    "minor_coursework_completion": "輔系課程要求",
    "target_coursework_completion": "修讀身分課程要求",
    "overall": "目前計算結果",
}
_STUDENT_ADMIN_LABELS = {
    "minor_application_or_qualification": "輔系申請與資格",
    "formal_minor_award": "輔系正式授予",
    "formal_double_major_award": "雙主修正式授予",
    "application_self_report": "申請資料（自行填寫）",
}


def _student_decision_lines(view: Mapping[str, Any], labels: Mapping[str, str]) -> list[str]:
    decisions = view.get("decisions") if isinstance(view.get("decisions"), Mapping) else {}
    lines: list[str] = []
    for key, label in labels.items():
        decision = decisions.get(key)
        if not isinstance(decision, Mapping):
            continue
        status = _text(decision.get("status"), UNKNOWN)
        if status.upper() == NOT_APPLICABLE:
            continue
        reason = _public_reason(decision.get("reason"), "目前資料不足，請查看要求明細與規則來源。")
        lines.append(f"{label}：{_public_status_label(status)}；{reason}")
    return lines


def _student_pdf_lines(view: Mapping[str, Any]) -> list[str]:
    summary = view.get("summary") if isinstance(view.get("summary"), Mapping) else {}
    required_progress = summary.get("required_progress") if isinstance(summary.get("required_progress"), Mapping) else {}
    effective = _public_credit(summary.get("counted_exclusive_credits"), "需要補資料")
    missing = _public_credit(summary.get("missing_credits"), "需要補資料")
    lines = [
        "北市大畢業通｜學分進度",
        f"報表編號：{_text(view.get('snapshot_id'), '需要補資料')}",
        _student_context_text(view),
        f"資料更新：{_format_evaluated_at(view.get('evaluated_at')) or '時間待補'}",
        "",
        "摘要",
        f"有效學分：{effective} 學分",
        f"尚缺學分：{missing} 學分",
        f"必修進度：{_text(required_progress.get('completed'), '需要補資料')}／{_text(required_progress.get('required'), '需要補資料')} 項；待辦 {_text(summary.get('todo_count'), '需要補資料')} 項",
        f"修習中：{_text(summary.get('in_progress'), '需要補資料')} 門",
        f"成績單實得學分：{_public_credit(summary.get('source_earned_credits'), '需要補資料')} 學分",
        "",
        "計算結果",
    ]
    lines.extend(_student_decision_lines(view, _STUDENT_CALCULATION_LABELS) or ["目前沒有可顯示的計算結果。"])
    lines.extend(("", "行政資訊"))
    lines.extend(_student_decision_lines(view, _STUDENT_ADMIN_LABELS) or ["目前沒有可顯示的行政資訊。"])
    non_credit_results = _non_credit_result_rows(view)
    if non_credit_results:
        lines.extend(("", "非學分門檻"))
        for result in non_credit_results:
            name = _public_reason(
                result.get("name") or result.get("label") or result.get("requirement_id"),
                "非學分門檻",
            )
            status = _public_status_label(result.get("status"), PUBLIC_PENDING)
            lines.extend(
                (
                    f"{name}｜狀態：{status}｜完成進度：{_non_credit_progress_text(result)}",
                    f"已完成學期／項目：{_result_values(result.get('completed_terms'), fallback='尚無')}；修習中：{_result_values(result.get('in_progress_terms'), fallback='目前沒有')}",
                    "學分計算：這項門檻不另外增加學分；課程學分仍依原類別採計。",
                    f"下一步：{_student_gate_next_step(result)}",
                    f"規則來源：{_student_source_text(_result_source_items(result))}",
                )
            )
            lines.extend(f"採用課程：{_gate_course_text(course)}" for course in _matched_gate_courses(view, result))
    subset_results = _subset_result_rows(view)
    if subset_results:
        lines.extend(("", "學分採計條件"))
        for result in subset_results:
            name = _subset_name(result)
            status = _public_status_label(result.get("status"), PUBLIC_PENDING)
            unknown = _public_credit(result.get("unknown_candidate_credits"), "0")
            unknown_note = f"；另有 {unknown} 學分候選仍待核對" if unknown != "0" else ""
            lines.extend(
                (
                    f"{name}｜狀態：{status}｜子條件進度：{_subset_progress_text(result)}{unknown_note}",
                    "學分計算：依各項規則指定的已採計課程檢查，不另增加或重複計算學分。",
                    f"下一步：{_student_gate_next_step(result)}",
                    f"規則來源：{_student_source_text(_result_source_items(result))}",
                )
            )
    lines.extend(("", "各類別學分"))
    by_bucket = summary.get("by_bucket") if isinstance(summary.get("by_bucket"), Mapping) else {}
    if by_bucket:
        lines.extend(
            f"{_public_bucket_label(key)}：{_public_credit(value, '需要補資料')} 學分"
            for key, value in sorted(by_bucket.items(), key=lambda item: str(item[0]))
        )
    else:
        lines.append("目前沒有可顯示的分類學分。")
    lines.extend(("", "各項畢業要求"))
    cs_rollup = _cs_elective_rollup(view)
    if cs_rollup:
        lines.extend((
            f"資科系選修：{cs_rollup['effective_credits']}／54 學分；{_public_status_label(cs_rollup['status'])}",
            "包含甲類指定課程32學分與乙類選修22學分，以下明細不再額外加計。",
            "",
        ))
    for requirement in view.get("requirements", ()):
        if not isinstance(requirement, Mapping):
            continue
        name = _text(requirement.get("name"), "未命名要求")
        kind = _text(requirement.get("kind"))
        title = f"{name}（{kind}）" if kind else name
        lines.extend(
            (
                title,
                f"狀態：{_public_status_label(requirement.get('status'))}；已採計／要求：{_public_credit(requirement.get('effective_credits'), '需要補資料')}／{_public_credit(requirement.get('required_credits'), '需要補資料')} 學分；尚缺：{_public_credit(requirement.get('deficit'), '需要補資料')} 學分",
                f"資料狀態：{_public_reason(requirement.get('coverage_state'), '來源尚未完整')}；{_public_reason(requirement.get('evidence_state'), '來源尚未核對')}",
                f"下一步：{_student_next_step(requirement)}",
                f"規則條件：{_public_condition(requirement.get('choice_condition'))}",
                f"規則來源：{_student_source_text(requirement.get('rule_provenance', ())) }",
            )
        )
        eligible_courses = requirement.get("eligible_courses", ())
        if eligible_courses:
            lines.append("指定課程：")
            for option in eligible_courses:
                if isinstance(option, Mapping):
                    option_name = _public_course_value(option.get("course_name"))
                    option_id = _public_course_value(option.get("course_id"))
                    label = option_name or option_id or "課程名稱待補"
                    suffix = f"（{option_id}）" if option_name and option_id else ""
                    lines.append(f"  - {label}{suffix}")
        courses = [course for course in requirement.get("courses", ()) if isinstance(course, Mapping)]
        if courses:
            lines.append("課程明細：")
            for course in courses:
                course_id = _public_course_value(course.get("course_id"))
                course_title = _public_course_value(course.get("course_name"), "課程名稱待補")
                if course_id:
                    course_title = f"{course_title}（{course_id}）"
                course_term = (
                    "尚未修課"
                    if course.get("is_not_attempted") or _text(course.get("status")).upper() in {"NOT_ATTEMPTED", "NOT_TAKEN"}
                    else _text(course.get("academic_term"), "學期待補")
                )
                lines.append(
                    "  - "
                    + "；".join(
                        (
                            course_title,
                            f"學期：{course_term}",
                            f"狀態：{_public_status_label(course.get('status'))}",
                            f"課程學分：{_public_credit(course.get('source_credits'), '待補')}",
                            f"本要求採計：{_public_credit(course.get('used_credits'), '待補')}",
                            f"尚未配置：{_public_credit(course.get('unallocated_credits'), '0')} 學分",
                            f"採計用途：{_public_reason(course.get('allocation_kind_label'), '採計用途待補')}",
                            f"原因：{_public_reason(course.get('allocation_reason'), '目前沒有可由規則安全確認的採計方式')}",
                        )
                    )
                )
        lines.append("")
    unallocated_courses = _student_unallocated_courses(view)
    if unallocated_courses:
        lines.extend(("", "尚未採計課程"))
        for item in unallocated_courses:
            row = _student_unallocated_row(view, item)
            course_id = f"（{row['課程代碼']}）" if row["課程代碼"] else ""
            lines.append(
                "  - "
                + "；".join(
                    (
                        f"{row['課程名稱'] or '課程名稱待補'}{course_id}",
                        f"學期：{row['修課學期']}",
                        f"狀態：{row['修課狀態']}",
                        f"課程學分：{row['課程學分']}",
                        f"目前採計：{row['本要求採計']}",
                        f"尚未配置：{row['尚未配置學分']} 學分",
                        f"可能用途：{row['採計用途']}",
                        f"原因：{row['採計原因']}",
                    )
                )
            )
    lines.extend(("待辦與提醒",))
    blockers = view.get("blockers", ())
    warnings = view.get("warnings", ())
    suggestions = view.get("remediation_suggestions", ())
    lines.extend(f"- {_public_reason(item, '資料仍需人工核對')}" for item in blockers if _text(item))
    lines.extend(f"- {_public_reason(item, '資料仍需人工核對')}" for item in warnings if _text(item))
    lines.extend(f"- {_public_reason(item, '請查看要求明細與規則來源')}" for item in suggestions if _text(item))
    if not (blockers or warnings or suggestions):
        lines.append("目前沒有其他待辦。")
    return lines


def build_student_pdf(snapshot: DecisionSnapshot) -> bytes:
    """Return a Chinese, student-facing PDF from one snapshot projection."""

    view = build_snapshot_view(snapshot)
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - dependency is pinned in requirements
        raise RuntimeError("PDF 匯出需要 PyMuPDF（fitz）。") from exc

    document = fitz.open()
    page_width, page_height = fitz.paper_size("a4")
    margin = 42
    line_height = 15
    font_size = 9.5
    page = document.new_page(width=page_width, height=page_height)
    y = margin
    for raw_line in _student_pdf_lines(view):
        wrapped = _wrap_pdf_line(raw_line or " ", fitz, width=page_width - 2 * margin, fontsize=font_size)
        for chunk in wrapped:
            if y + line_height > page_height - margin:
                page = document.new_page(width=page_width, height=page_height)
                y = margin
            page.insert_text((margin, y), chunk, fontsize=font_size, fontname="china-t", color=(0.06, 0.09, 0.16))
            y += line_height
    document.set_metadata(
        {
            "title": "北市大畢業通｜學分進度",
            "author": "北市大畢業通",
            "subject": "學分進度與要求明細",
            "keywords": "北市大 學分進度",
        }
    )
    result = document.tobytes()
    document.close()
    return result


# Friendly aliases used by the application integration layer.
export_snapshot_csv = build_allocation_csv
export_snapshot_audit_json = build_audit_json
export_snapshot_pdf = build_pdf
snapshot_to_csv_bytes = build_allocation_csv
snapshot_to_audit_json_bytes = build_audit_json
snapshot_to_pdf_bytes = build_pdf


__all__ = [
    "build_allocation_csv",
    "build_audit_json",
    "build_pdf",
    "build_student_allocation_csv",
    "build_student_pdf",
    "build_snapshot_export_payload",
    "export_snapshot_audit_json",
    "export_snapshot_csv",
    "export_snapshot_pdf",
    "snapshot_to_audit_json_bytes",
    "snapshot_to_csv_bytes",
    "snapshot_to_pdf_bytes",
]
