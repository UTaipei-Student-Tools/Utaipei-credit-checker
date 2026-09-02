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
from typing import Any

from decision_snapshot import DecisionSnapshot
from snapshot_renderer import MANUAL_LABEL, build_snapshot_view, sanitize_snapshot_value

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
    "credits",
    "allocation_kind",
    "direction",
    "binding_id",
    "shared_credit",
    "allocation_reason",
    "allocations_json",
    "warnings_json",
    "blockers_json",
    "statistics_json",
    "decisions_json",
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
        "snapshot_id": view.get("snapshot_id"),
        "_snapshot_id": view.get("snapshot_id"),
        "evaluated_at": view.get("evaluated_at"),
        "verdict": view.get("verdict"),
        "context": _plain(view.get("context", {})),
        "summary": _plain(view.get("summary", {})),
        "decisions": _plain(view.get("decisions", {})),
        "requirements": _plain(view.get("requirements", ())),
        "attempts": _plain(view.get("attempts", ())),
        "allocations": _plain(view.get("allocations", ())),
        "allocation": _plain(view.get("allocation", {})),
        "alternatives": _plain(view.get("alternatives", ())),
        "warnings": _plain(view.get("warnings", ())),
        "blockers": _plain(view.get("blockers", ())),
        "statistics": _plain(view.get("statistics", {})),
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
            "blockers_json": _json(payload.get("blockers", ())),
            "statistics_json": _json(payload.get("statistics", {})),
            "decisions_json": _json(payload.get("decisions", {})),
        }
        if portions:
            for portion in portions:
                requirement_id = _text(portion.get("requirement_id"))
                rows.append(
                    {
                        **base,
                        "requirement_id": requirement_id,
                        "requirement_name": requirement_names.get(requirement_id, ""),
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
            "credits": "0",
            "allocation_kind": "NO_DATA",
            "direction": "",
            "binding_id": "",
            "shared_credit": False,
            "allocation_reason": MANUAL_LABEL,
            "allocations_json": _json(payload.get("allocations", ())),
            "warnings_json": _json(payload.get("warnings", ())),
            "blockers_json": _json(payload.get("blockers", ())),
            "statistics_json": _json(payload.get("statistics", {})),
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


def build_audit_json(snapshot: DecisionSnapshot) -> bytes:
    """Return a deterministic UTF-8 audit JSON export."""

    payload = build_snapshot_export_payload(snapshot)
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _pdf_lines(payload: Mapping[str, Any]) -> list[str]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    lines = [
        "北市大畢業通｜可稽核分析摘要",
        f"DecisionSnapshot：{_text(payload.get('snapshot_id'))}",
        f"評估時間：{_text(payload.get('evaluated_at'))}",
        f"判定：{_text(payload.get('verdict'), 'UNKNOWN')}",
        "",
        "摘要",
        f"總畢業學分：{_text(summary.get('total_graduation_credits'), MANUAL_LABEL)}",
        f"要求總量：{_text(summary.get('required_graduation_credits'), MANUAL_LABEL)}",
        f"主修完成度：{_text(summary.get('primary_status'), UNKNOWN)}",
        f"雙主修完成度：{_text(summary.get('double_major_status'), NOT_APPLICABLE)}",
        f"已完成／修習中：{_text(summary.get('completed'), MANUAL_LABEL)}／{_text(summary.get('in_progress'), MANUAL_LABEL)}",
        f"尚缺／待確認：{_text(summary.get('missing'), MANUAL_LABEL)}／{_text(summary.get('unknown'), MANUAL_LABEL)}",
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
    lines.extend(("最短安全補修建議",))
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
            "blockers=" + _json(payload.get("blockers", ())),
            "statistics=" + _json(payload.get("statistics", {})),
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
    "build_snapshot_export_payload",
    "export_snapshot_audit_json",
    "export_snapshot_csv",
    "export_snapshot_pdf",
    "snapshot_to_audit_json_bytes",
    "snapshot_to_csv_bytes",
    "snapshot_to_pdf_bytes",
]
