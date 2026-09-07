"""Portable JSON/CSV exports for policy and graduation audits."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping
from typing import Any

_SHARED_REUSE_DEFAULTS = {
    "approval_scope": "aggregate_allowance_only",
    "allocation_type": "simulated",
    "selection_basis": "deterministic_planning_only",
    "course_identity_status": "not_official",
    "official_course_identity_note": (
        "共同修課核准僅代表合計額度；列出的課名只是規劃用模擬配置，不代表系所已核准該課程身分。"
        "正式共同修課科目身分須由系所證據確認。"
    ),
}


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_csv_cell(value: Any) -> Any:
    """Prevent spreadsheet formula injection while preserving ordinary values."""

    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


sanitize_csv_cell = _safe_csv_cell


def _credit_parts(course: Mapping[str, Any]) -> tuple[float, float]:
    """Read the allocated earned/in-progress slices from a report row."""

    try:
        completed = float(course.get("allocated_completed_credits", course.get("completed_credit", 0.0)) or 0.0)
    except (TypeError, ValueError):
        completed = 0.0
    try:
        if "allocated_ip_credits" in course:
            in_progress = float(course.get("allocated_ip_credits") or 0.0)
        elif course.get("is_in_progress"):
            in_progress = max(float(course.get("total_credit") or 0.0) - completed, 0.0)
        else:
            in_progress = 0.0
    except (TypeError, ValueError):
        in_progress = 0.0
    return max(completed, 0.0), max(in_progress, 0.0)


def _normalize_shared_reuse(value: Any) -> dict[str, Any]:
    """Keep shared-credit exports explicit about aggregate/simulated status."""

    normalized = dict(value) if isinstance(value, Mapping) else {"value": value}
    for key, default in _SHARED_REUSE_DEFAULTS.items():
        normalized.setdefault(key, default)
    rows = normalized.get("rows", [])
    if isinstance(rows, (list, tuple)):
        normalized["rows"] = []
        for item in rows:
            row = dict(item) if isinstance(item, Mapping) else {"value": item}
            for key, default in _SHARED_REUSE_DEFAULTS.items():
                row.setdefault(key, default)
            normalized["rows"].append(row)
    return normalized


def _normalize_equivalency(value: Any) -> dict[str, Any]:
    """Normalize source-attempt bindings without dropping audit fields."""

    normalized = dict(value) if isinstance(value, Mapping) else {}
    for key, default in {
        "status": "NOT_APPLICABLE",
        "state": "NOT_APPLICABLE",
        "decisions": [],
        "approved_mappings": [],
        "candidates": [],
        "validation_codes": [],
        "warnings": [],
        "approved_credits": 0.0,
        "approved_shared_reuse_credits": 0.0,
        "approved_exclusive_credits": 0.0,
        "legacy_unbound": False,
    }.items():
        normalized.setdefault(key, default)
    for key in ("decisions", "approved_mappings", "candidates"):
        rows = normalized.get(key)
        if isinstance(rows, (list, tuple)):
            normalized[key] = [dict(row) if isinstance(row, Mapping) else {"value": row} for row in rows]
        else:
            normalized[key] = []
    return normalized


def flatten_equivalency_rows(audit: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return one export row per proposed/approved/rejected binding."""

    audit = _normalize_equivalency(audit)
    rows = []
    for item in audit.get("decisions", []):
        row = dict(item) if isinstance(item, Mapping) else {"value": item}
        rows.append(
            {
                "source_attempt_id": row.get("source_attempt_id", ""),
                "source_course_name": row.get("source_course_name", ""),
                "source_credit": row.get("source_credit", 0.0),
                "source_completed_credits": row.get("source_completed_credits", 0.0),
                "target_requirement_id": row.get("target_requirement_id", ""),
                "target_requirement_name": row.get("target_requirement_name", ""),
                "target_credits": row.get("target_credits", 0.0),
                "decision": row.get("decision", row.get("state", "")),
                "authority": row.get("authority", ""),
                "evidence_reference": row.get("evidence_reference", ""),
                "approved_credits": row.get("approved_credits", 0.0),
                "allocation_type": row.get("allocation_type", ""),
                "counts": bool(row.get("counts", False)),
                "validation_codes": row.get("validation_codes", []),
                "reasons": row.get("reasons", []),
            }
        )
    return rows


flatten_source_target_rows = flatten_equivalency_rows


def flatten_allocation_rows(report: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Flatten every allocated report bucket into deterministic audit rows.

    Overflow slices remain separate rows, making credit conservation and the
    reason a course moved to another bucket visible in exported audits.
    """

    report = report or {}
    rows: list[dict[str, Any]] = []

    def add(bucket: str, courses: Any) -> None:
        if not isinstance(courses, (list, tuple)):
            return
        for course in courses:
            if not isinstance(course, Mapping):
                continue
            completed, in_progress = _credit_parts(course)
            rows.append(
                {
                    "bucket": bucket,
                    "course_name": str(course.get("name") or course.get("raw_name") or ""),
                    "course_code": str(course.get("course_code") or ""),
                    "offering_department": str(course.get("offering_department") or ""),
                    "identity_status": str(course.get("identity_status") or ""),
                    "identity_scope": str(course.get("identity_scope") or ""),
                    "identity_reason": str(course.get("identity_reason") or ""),
                    "identity_authority": str(course.get("identity_authority") or course.get("authority") or ""),
                    "identity_evidence_reference": str(
                        course.get("identity_evidence_reference") or course.get("evidence_reference") or ""
                    ),
                    # Keep the established equivalency names in the flat row as
                    # well; manual approvals should remain auditable by either
                    # schema consumer.
                    "authority": str(course.get("authority") or course.get("identity_authority") or ""),
                    "evidence_reference": str(
                        course.get("evidence_reference") or course.get("identity_evidence_reference") or ""
                    ),
                    "target_requirement_id": str(course.get("target_requirement_id") or ""),
                    "target_requirement_name": str(course.get("target_requirement_name") or ""),
                    "allocated_completed_credits": completed,
                    "allocated_ip_credits": in_progress,
                    "allocation_note": str(course.get("allocation_note") or ""),
                    "_origin": str(course.get("_origin_id") or ""),
                }
            )

    common = report.get("common", {}) if isinstance(report.get("common", {}), Mapping) else {}
    for key, bucket in (("compulsory_courses", "common_compulsory"), ("common_elective_courses", "common_elective")):
        add(bucket, common.get(key, []))
    categories = common.get("categories", {})
    if isinstance(categories, Mapping):
        for category in sorted(categories, key=str):
            category_data = categories.get(category, {})
            if isinstance(category_data, Mapping):
                add(f"ge:{category}", category_data.get("courses", []))
        overflow = common.get("category_overflow", {})
        if isinstance(overflow, Mapping):
            for category in sorted(overflow, key=str):
                add(f"ge_overflow:{category}", overflow.get(category, []))

    major = report.get("major", {}) if isinstance(report.get("major", {}), Mapping) else {}
    for key, bucket in (
        ("dept_compulsory_courses", "major_common_compulsory"),
        ("domain_compulsory_courses", "domain_compulsory"),
        ("domain_elective_courses", "domain_elective"),
        ("other_elective_courses", "other_elective"),
    ):
        add(bucket, major.get(key, []))

    target = report.get("target", {}) if isinstance(report.get("target", {}), Mapping) else {}
    for key, bucket in (
        ("basic_core_courses", "target_basic_core"),
        ("compulsory_courses", "target_compulsory"),
        ("elective_courses", "target_elective"),
    ):
        add(bucket, target.get(key, []))

    pe = report.get("pe", {}) if isinstance(report.get("pe", {}), Mapping) else {}
    add("physical_education", pe.get("courses", []))
    free = report.get("free", {}) if isinstance(report.get("free", {}), Mapping) else {}
    add("free", free.get("courses", []))

    rows.sort(
        key=lambda row: (
            row["bucket"],
            row["course_name"],
            row["_origin"],
            row["allocated_completed_credits"],
            row["allocated_ip_credits"],
            row["allocation_note"],
        )
    )
    for row in rows:
        row.pop("_origin", None)
    return rows


flatten_report_allocations = flatten_allocation_rows


def dataframe_csv_bytes(frame: Any, encoding: str = "utf-8") -> bytes:
    """Serialize a DataFrame after escaping formula-like cell prefixes."""

    safe_frame = frame.copy()
    for column in safe_frame.columns:
        safe_frame[column] = safe_frame[column].map(_safe_csv_cell)
    return safe_frame.to_csv(index=False).encode(encoding)


def build_audit_payload(audit: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Normalize an audit object into a stable, export-friendly schema."""

    source = dict(audit or {})
    report = source.get("report") if isinstance(source.get("report"), Mapping) else {}
    report_summary = report.get("summary", {}) if isinstance(report.get("summary", {}), Mapping) else {}
    application = dict(source.get("application") or {})
    eligibility = source.get("eligibility", source.get("double_major", report.get("double_major_eligibility", {})))
    if not isinstance(eligibility, Mapping):
        eligibility = {"status": eligibility}
    report_application = report.get("application", {})
    if not isinstance(report_application, Mapping):
        report_application = {}
    for key in (
        "application_year",
        "application_semester",
        "application_status",
        "interrupted",
        "shared_evidence_state",
        "cohort_mismatch_confirmed",
    ):
        if key in source and key not in application:
            application[key] = source[key]
        if key in eligibility and key not in application:
            application[key] = eligibility[key]
        if key in report_application and key not in application:
            application[key] = report_application[key]
    if "shared_evidence_state" not in application and eligibility.get("shared_credit_state"):
        application["shared_evidence_state"] = eligibility.get("shared_credit_state")
    if "cohort_mismatch_confirmed" not in application:
        cohort_match_hint = report.get("cohort_match", {})
        if isinstance(cohort_match_hint, Mapping) and "confirmed" in cohort_match_hint:
            application["cohort_mismatch_confirmed"] = bool(cohort_match_hint.get("confirmed"))
    requirements = source.get("requirements", report.get("requirements", source.get("program_plan", {})))
    if not isinstance(requirements, Mapping):
        requirements = {"value": requirements}
    warnings = source.get("warnings", report.get("policy_warnings", []) + report.get("document_warnings", []))
    if isinstance(warnings, str):
        warnings = [warnings]
    citations = source.get("citations", report.get("citations", []))
    if isinstance(citations, Mapping):
        citations = [citations]
    gate_results = source.get("gate_results", source.get("graduation_gates", report.get("graduation_gates", {})))
    manual_gates = source.get("manual_gates", report.get("manual_gates", {}))
    allocation_rows = source.get("allocation_rows")
    if allocation_rows is None:
        allocation_rows = flatten_allocation_rows(report)
    if not isinstance(allocation_rows, (list, tuple)):
        allocation_rows = []
    shared_reuse = _normalize_shared_reuse(source.get("shared_reuse", report.get("shared_reuse", {})))
    equivalency = _normalize_equivalency(
        source.get("equivalency", source.get("equivalency_audit", report.get("equivalency", report.get("equivalency_audit", {}))))
    )
    credit_audit = source.get("credit_audit", report.get("audit", {}))
    if not isinstance(credit_audit, Mapping):
        credit_audit = {"value": credit_audit}
    evidence_states = source.get(
        "evidence_states",
        report.get("evidence_states", report.get("primary_plan", {}).get("evidence_states", {})),
    )
    if not isinstance(evidence_states, Mapping):
        evidence_states = {"value": evidence_states}
    cohort_match = source.get("cohort_match", report.get("cohort_match", {}))
    if not isinstance(cohort_match, Mapping):
        cohort_match = {"status": cohort_match}
    identity_gate = source.get("identity_gate", report.get("identity_gate", {}))
    if not isinstance(identity_gate, Mapping):
        identity_gate = {"status": identity_gate}
    identity_issues = source.get("identity_issues", report.get("identity_issues", []))
    if not isinstance(identity_issues, (list, tuple)):
        identity_issues = []
    return {
        "cohort": source.get("cohort", source.get("admission_cohort", report.get("handbook_year", ""))),
        "primary_program": source.get("primary_program", source.get("program", report.get("primary_plan", {}).get("primary_program", ""))),
        "track": source.get("track", report.get("primary_plan", {}).get("track", "")),
        "program_type": source.get("program_type", report.get("program_type", "")),
        "application": application,
        "evidence_states": dict(evidence_states),
        "cohort_match": dict(cohort_match),
        "eligibility": dict(eligibility),
        "status": source.get("status", source.get("graduation_status", report_summary.get("graduation_status", "UNKNOWN"))),
        "requirements": dict(requirements),
        "gate_results": dict(gate_results) if isinstance(gate_results, Mapping) else gate_results,
        "identity_gate": dict(identity_gate),
        "identity_issues": [dict(item) if isinstance(item, Mapping) else {"value": item} for item in identity_issues],
        "manual_gates": dict(manual_gates) if isinstance(manual_gates, Mapping) else manual_gates,
        "warnings": [str(item) for item in warnings],
        "citations": [dict(item) if isinstance(item, Mapping) else {"citation": str(item)} for item in citations],
        "allocation_rows": [dict(item) if isinstance(item, Mapping) else {"value": item} for item in allocation_rows],
        "shared_reuse": dict(shared_reuse),
        "equivalency": dict(equivalency),
        "credit_audit": dict(credit_audit),
    }


def audit_json_bytes(audit: Mapping[str, Any] | None = None) -> bytes:
    """Return UTF-8 JSON bytes containing policy, eligibility, and evidence."""

    return (json.dumps(build_audit_payload(audit), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def audit_csv_bytes(audit: Mapping[str, Any] | None = None) -> bytes:
    """Return a one-row UTF-8 CSV audit, hardened for spreadsheet consumers."""

    payload = build_audit_payload(audit)
    application = payload["application"]
    eligibility = payload["eligibility"]
    shared_reuse = payload["shared_reuse"]
    equivalency = payload["equivalency"]
    identity_gate = payload["identity_gate"]
    row = {
        "cohort": payload["cohort"],
        "primary_program": payload["primary_program"],
        "track": payload["track"],
        "program_type": payload["program_type"],
        "application_year": application.get("application_year", ""),
        "application_semester": application.get("application_semester", ""),
        "application_status": application.get("application_status", ""),
        "interrupted": application.get("interrupted", False),
        "shared_evidence_state": application.get("shared_evidence_state", eligibility.get("shared_credit_state", "")),
        "shared_reuse_approval_scope": shared_reuse.get("approval_scope", ""),
        "shared_reuse_allocation_type": shared_reuse.get("allocation_type", ""),
        "shared_reuse_course_identity_status": shared_reuse.get("course_identity_status", ""),
        "shared_reuse_official_identity_note": shared_reuse.get("official_course_identity_note", ""),
        "cohort_mismatch_confirmed": application.get("cohort_mismatch_confirmed", False),
        "eligibility": eligibility.get("status", eligibility.get("state", payload["status"])),
        "status": payload["status"],
        "identity_gate_status": identity_gate.get("status", identity_gate.get("state", "")),
        "identity_gate_reasons": _json_value(identity_gate.get("reasons", [])),
        "identity_issues": _json_value(payload["identity_issues"]),
        "evidence_states": _json_value(payload["evidence_states"]),
        "cohort_match": _json_value(payload["cohort_match"]),
        "requirements": _json_value(payload["requirements"]),
        "gate_results": _json_value(payload["gate_results"]),
        "manual_gates": _json_value(payload["manual_gates"]),
        "warnings": _json_value(payload["warnings"]),
        "citations": _json_value(payload["citations"]),
        "allocation_rows": _json_value(payload["allocation_rows"]),
        "shared_reuse": _json_value(payload["shared_reuse"]),
        "equivalency_status": equivalency.get("status", ""),
        "equivalency_decisions": _json_value(equivalency.get("decisions", [])),
        "equivalency_approved_mappings": _json_value(equivalency.get("approved_mappings", [])),
        "equivalency_validation_codes": _json_value(equivalency.get("validation_codes", [])),
        "equivalency_warnings": _json_value(equivalency.get("warnings", [])),
        "equivalency_legacy_unbound": bool(equivalency.get("legacy_unbound", False)),
        "credit_audit": _json_value(payload["credit_audit"]),
    }
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(row), lineterminator="\n")
    writer.writeheader()
    writer.writerow({key: _safe_csv_cell(value) for key, value in row.items()})
    return output.getvalue().encode("utf-8-sig")


# Friendly aliases for integrations that use export_* naming.
export_audit_json = audit_json_bytes
export_audit_csv = audit_csv_bytes
