from __future__ import annotations

import csv
import io
import json
from dataclasses import replace
from decimal import Decimal

import fitz
import pytest

from allocation_engine import (
    COMPLETE,
    VERIFIED,
    AllocationResult,
    AttemptAllocation,
    CourseAttempt,
    CreditPortion,
    RequirementResult,
    RequirementSpec,
)
from decision_snapshot import DecisionSnapshot, build_decision_snapshot
from snapshot_exports import (
    build_snapshot_export_payload,
    build_student_allocation_csv,
    build_student_pdf,
    export_snapshot_audit_json,
    export_snapshot_csv,
    export_snapshot_pdf,
)
from snapshot_renderer import render_snapshot


def _snapshot() -> DecisionSnapshot:
    snapshot = build_decision_snapshot(
        {
            "attempts": (
                CourseAttempt("a", "A-001", "=公式課程", Decimal("3"), Decimal("3"), "114-1"),
                CourseAttempt("b", "B-001", "普通課程", Decimal("2"), Decimal("2"), "114-2"),
            ),
            "requirements": (
                RequirementSpec(
                    "req-a",
                    "系必修",
                    Decimal("3"),
                    eligible_course_ids=("A-001",),
                    coverage_state=COMPLETE,
                    evidence_state=VERIFIED,
                    bucket="required",
                    kind="必修",
                ),
            ),
            "input_confirmation": {
                "state": "CONFIRMED",
                "current_fingerprint": "export-fixture",
                "confirmed_fingerprint": "export-fixture",
                "formal_release_success": True,
                "row_count": 2,
                "released_row_count": 2,
            },
        },
        evaluated_at="2026-09-02T00:00:00Z",
    )
    allocation = AllocationResult(
        status="UNKNOWN",
        allocations=(
            AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "req-a", Decimal("3")),), Decimal("0")),
            AttemptAllocation("b", Decimal("2"), (), Decimal("2")),
        ),
        requirement_results=(
            RequirementResult("req-a", "PASS", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "COMPLETE", "VERIFIED"),
        ),
        source_earned_credits=Decimal("5"),
        recognized_credits=Decimal("3"),
        unallocated_credits=Decimal("2"),
        credit_conservation=True,
        alternative_allocations=(("a", (("req-a", "3", "EXCLUSIVE", "", ""),), "0"),),
    )
    return replace(
        snapshot,
        allocation=allocation,
        snapshot_id="snapshot:export-fixture",
        verdict="UNKNOWN",
        decisions={"overall": {"status": "UNKNOWN", "reason": "仍需人工確認"}},
        statistics={
            "total_graduation_credits": "128",
            "by_bucket": {"required": "3"},
            "completed": 2,
            "in_progress": 0,
            "unresolved": 0,
            "credit_conservation": True,
        },
        blockers=("RULE_CONTEXT:MANUAL_REVIEW",),
        warnings=("規則證據不足",),
        remediation_suggestions=("請由系所確認課表版本。",),
    )


def _json_cell(value: str):
    return json.loads(value)


def _snapshot_with_distinct_unknown_counts() -> DecisionSnapshot:
    snapshot = _snapshot()
    extra_attempts = snapshot.attempts + (
        CourseAttempt("c", "C-001", "待確認課程一", Decimal("2"), Decimal("0"), "114-2", status="UNKNOWN"),
        CourseAttempt("d", "D-001", "待確認課程二", Decimal("2"), Decimal("0"), "114-2", status="UNKNOWN"),
    )
    extra_requirement = RequirementSpec(
        "req-unknown", "資料不足要求", Decimal("2"), bucket="elective", kind="選修",
        coverage_state="PARTIAL", evidence_state="UNKNOWN",
    )
    extra_result = RequirementResult(
        "req-unknown", "UNKNOWN", Decimal("2"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("2"), "PARTIAL", "UNKNOWN",
    )
    allocation = replace(
        snapshot.allocation,
        requirement_results=snapshot.allocation.requirement_results + (extra_result,),
    )
    return replace(
        snapshot,
        attempts=extra_attempts,
        requirements=snapshot.requirements + (extra_requirement,),
        allocation=allocation,
        statistics={},
        input_confirmation={
            "state": "CONFIRMED",
            "current_fingerprint": "export-fixture-extended",
            "confirmed_fingerprint": "export-fixture-extended",
            "formal_release_success": True,
            "row_count": 4,
            "released_row_count": 4,
        },
    )


def _snapshot_with_conservation_failure(kind: str) -> DecisionSnapshot:
    snapshot = _snapshot()
    if kind == "cross_cancel":
        allocations = (
            AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "req-a", Decimal("4")),), Decimal("0")),
            AttemptAllocation("b", Decimal("2"), (CreditPortion("b", "req-a", Decimal("1")),), Decimal("0")),
        )
        result = RequirementResult("req-a", "PASS", Decimal("5"), Decimal("5"), Decimal("0"), Decimal("5"), Decimal("0"), "COMPLETE", "VERIFIED")
    elif kind == "mismatched_portion":
        allocations = (
            AttemptAllocation("a", Decimal("3"), (CreditPortion("b", "req-a", Decimal("3")),), Decimal("0")),
            AttemptAllocation("b", Decimal("2"), (), Decimal("2")),
        )
        result = RequirementResult("req-a", "PASS", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "COMPLETE", "VERIFIED")
    else:
        raise AssertionError(f"unknown conservation fixture: {kind}")
    allocation = replace(
        snapshot.allocation,
        allocations=allocations,
        requirement_results=(result,),
        source_earned_credits=Decimal("5"),
        recognized_credits=Decimal("5"),
        unallocated_credits=Decimal("0"),
        credit_conservation=True,
        shadow_allocations=(),
    )
    return replace(snapshot, allocation=allocation, statistics={})


def _snapshot_with_requirement_result_reconciliation_failure() -> DecisionSnapshot:
    snapshot = _snapshot()
    requirements = snapshot.requirements + (
        RequirementSpec(
            "req-b",
            "系選修",
            Decimal("2"),
            eligible_course_ids=("B-001",),
            coverage_state=COMPLETE,
            evidence_state=VERIFIED,
            bucket="elective",
            kind="選修",
        ),
    )
    allocations = (
        AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "req-a", Decimal("3")),), Decimal("0")),
        AttemptAllocation("b", Decimal("2"), (CreditPortion("b", "req-b", Decimal("2")),), Decimal("0")),
    )
    # The additive rows are globally balanced, but the result evidence
    # attributes each requirement's earned amount to the other requirement.
    results = (
        RequirementResult("req-a", "PASS", Decimal("3"), Decimal("2"), Decimal("0"), Decimal("2"), Decimal("0"), "COMPLETE", "VERIFIED"),
        RequirementResult("req-b", "PASS", Decimal("2"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "COMPLETE", "VERIFIED"),
    )
    allocation = replace(
        snapshot.allocation,
        allocations=allocations,
        requirement_results=results,
        source_earned_credits=Decimal("5"),
        recognized_credits=Decimal("5"),
        unallocated_credits=Decimal("0"),
        credit_conservation=True,
        shadow_allocations=(),
    )
    return replace(snapshot, requirements=requirements, allocation=allocation, statistics={})


def _snapshot_with_shadow_failure(kind: str) -> DecisionSnapshot:
    snapshot = _snapshot()
    if kind == "over_cap":
        shadow = CreditPortion("a", "req-a", Decimal("4"), "SHARED_SHADOW")
        result = RequirementResult("req-a", "PASS", Decimal("3"), Decimal("3"), Decimal("4"), Decimal("7"), Decimal("0"), "COMPLETE", "VERIFIED")
    elif kind == "wrong_kind":
        shadow = CreditPortion("a", "req-a", Decimal("1"), "SHARED_REUSE")
        result = RequirementResult("req-a", "PASS", Decimal("3"), Decimal("3"), Decimal("1"), Decimal("4"), Decimal("0"), "COMPLETE", "VERIFIED")
    elif kind == "unknown_target":
        shadow = CreditPortion("a", "missing-target", Decimal("1"), "SHARED_SHADOW")
        result = RequirementResult("req-a", "PASS", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "COMPLETE", "VERIFIED")
    elif kind == "result_mismatch":
        shadow = CreditPortion("a", "req-a", Decimal("1"), "SHARED_SHADOW")
        result = RequirementResult("req-a", "PASS", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "COMPLETE", "VERIFIED")
    else:
        raise AssertionError(f"unknown shadow fixture: {kind}")
    allocation = replace(snapshot.allocation, requirement_results=(result,), shadow_allocations=(shadow,))
    return replace(snapshot, allocation=allocation, statistics={})


def _assert_fail_closed_media(snapshot: DecisionSnapshot) -> None:
    screen = build_snapshot_export_payload(snapshot)
    audit = _json_cell(export_snapshot_audit_json(snapshot).decode("utf-8"))
    rows = list(csv.DictReader(io.StringIO(export_snapshot_csv(snapshot).decode("utf-8-sig"))))
    pdf_document = fitz.open(stream=export_snapshot_pdf(snapshot), filetype="pdf")
    try:
        pdf_text = "\n".join(page.get_text() for page in pdf_document)
    finally:
        pdf_document.close()
    requirements = [item for item in screen["requirements"] if item.get("status") != "NOT_APPLICABLE"]

    assert requirements
    assert all(item["status"] == "UNKNOWN" for item in requirements)
    assert all(item["status_authoritative"] is False for item in requirements)
    assert all(item["observed_status"] == "PASS" for item in requirements)
    assert screen["statistics"]["requirement_metrics"]["items"][0]["status"] == "UNKNOWN"
    assert screen["chart_datasets"]["f5"]["available"] is False
    assert screen["chart_datasets"]["f5"]["reason_code"] == "CREDIT_CONSERVATION_FAILED"
    assert audit["requirements"] == screen["requirements"]
    assert audit["statistics"]["requirement_metrics"]["items"][0]["status"] == "UNKNOWN"
    assert audit["chart_datasets"]["f5"] == screen["chart_datasets"]["f5"]
    assert rows
    assert all(row["requirement_status"] == "UNKNOWN" for row in rows)
    assert all(row["requirement_status_authoritative"] == "False" for row in rows)
    assert "UNKNOWN" in pdf_text
    rendered = render_snapshot(snapshot)
    assert 'data-chart-id="F5"' in rendered
    assert "CREDIT_CONSERVATION_FAILED" not in rendered
    assert "重新核對" in rendered or "需要補資料" in rendered


def test_all_exports_share_the_same_snapshot_identity_and_decision_fields():
    snapshot = _snapshot()
    screen = build_snapshot_export_payload(snapshot)
    audit = _json_cell(export_snapshot_audit_json(snapshot).decode("utf-8"))
    rows = list(csv.DictReader(io.StringIO(export_snapshot_csv(snapshot).decode("utf-8-sig"))))

    assert screen["snapshot_id"] == snapshot.snapshot_id
    assert audit["snapshot_id"] == screen["snapshot_id"]
    assert audit["verdict"] == screen["verdict"]
    assert audit["allocations"] == screen["allocations"]
    assert audit["warnings"] == screen["warnings"]
    assert audit["blockers"] == screen["blockers"]
    assert audit["statistics"] == screen["statistics"]
    assert audit["presentation_warnings"] == screen["presentation_warnings"]
    assert rows
    assert {row["snapshot_id"] for row in rows} == {screen["snapshot_id"]}
    assert {row["verdict"] for row in rows} == {screen["verdict"]}
    assert all(_json_cell(row["allocations_json"]) == screen["allocations"] for row in rows)
    assert all(_json_cell(row["warnings_json"]) == screen["warnings"] for row in rows)
    assert all(_json_cell(row["blockers_json"]) == screen["blockers"] for row in rows)
    assert all(_json_cell(row["statistics_json"]) == screen["statistics"] for row in rows)
    assert audit["chart_datasets"] == screen["chart_datasets"]
    assert screen["statistics_schema"] == screen["statistics"]["schema_version"]
    assert screen["statistics_digest"] == screen["statistics"]["statistics_digest"]
    assert {row["statistics_schema"] for row in rows} == {screen["statistics_schema"]}
    assert {row["statistics_digest"] for row in rows} == {screen["statistics_digest"]}
    assert all(_json_cell(row["chart_datasets_json"]) == screen["chart_datasets"] for row in rows)
    assert all(_json_cell(row["presentation_warnings_json"]) == screen["presentation_warnings"] for row in rows)


def test_each_export_reads_the_snapshot_once_and_csv_hardens_formula_cells(monkeypatch):
    snapshot = _snapshot()
    original = DecisionSnapshot.as_dict
    calls = 0

    def counted(self):
        nonlocal calls
        calls += 1
        return original(self)

    monkeypatch.setattr(DecisionSnapshot, "as_dict", counted)
    csv_bytes = export_snapshot_csv(snapshot)
    assert calls == 1
    csv_text = csv_bytes.decode("utf-8-sig")
    assert "'=公式課程" in csv_text
    assert "=公式課程" not in csv_text.replace("'=公式課程", "")

    calls = 0
    export_snapshot_audit_json(snapshot)
    assert calls == 1
    calls = 0
    export_snapshot_pdf(snapshot)
    assert calls == 1


def test_pdf_is_openable_searchable_and_contains_manual_confirmation_summary():
    pdf_bytes = export_snapshot_pdf(_snapshot())
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert document.page_count >= 1
    text = "\n".join(page.get_text() for page in document)
    assert "北市大畢業通" in text
    assert "UNKNOWN" in text
    assert "需人工確認" in text or "資料不足" in text
    assert "snapshot:" in text
    assert "chart_datasets=" in text
    assert "課程列數" in text
    assert "要求項目數" in text
    assert "presentation_warnings=" in text
    document.close()


def test_student_exports_are_chinese_and_hide_internal_status_vocabulary():
    snapshot = _snapshot()
    csv_text = build_student_allocation_csv(snapshot).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    pdf_document = fitz.open(stream=build_student_pdf(snapshot), filetype="pdf")
    try:
        pdf_text = "\n".join(page.get_text() for page in pdf_document)
    finally:
        pdf_document.close()

    forbidden = ("UNKNOWN", "DecisionSnapshot", "EXCLUSIVE", "SHARED_SHADOW", "DIRECTION_ONLY")
    assert rows
    assert rows[0].keys() == {
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
    }
    assert "採計用途" in csv_text
    assert "規則來源" in csv_text
    assert "課程明細" in pdf_text
    assert "各項畢業要求" in pdf_text
    assert all(token not in csv_text for token in forbidden)
    assert all(token not in pdf_text for token in forbidden)


def test_exports_keep_course_and_requirement_counts_distinct_across_media():
    snapshot = _snapshot_with_distinct_unknown_counts()
    screen = build_snapshot_export_payload(snapshot)
    audit = _json_cell(export_snapshot_audit_json(snapshot).decode("utf-8"))
    rows = list(csv.DictReader(io.StringIO(export_snapshot_csv(snapshot).decode("utf-8-sig"))))
    pdf_document = fitz.open(stream=export_snapshot_pdf(snapshot), filetype="pdf")
    try:
        pdf_text = "\n".join(page.get_text() for page in pdf_document)
    finally:
        pdf_document.close()

    assert screen["course_counts"]["UNKNOWN"] == 2
    assert screen["requirement_counts"]["UNKNOWN"] == 1
    assert screen["course_counts"] != screen["requirement_counts"]
    assert audit["course_counts"] == screen["course_counts"]
    assert audit["requirement_counts"] == screen["requirement_counts"]
    assert all(_json_cell(row["course_counts_json"]) == screen["course_counts"] for row in rows)
    assert all(_json_cell(row["requirement_counts_json"]) == screen["requirement_counts"] for row in rows)
    assert "課程列數（已完成／修習中／待確認）" in pdf_text
    assert "要求項目數（通過／未通過／待確認）" in pdf_text


@pytest.mark.parametrize("kind", ("cross_cancel", "mismatched_portion"))
def test_conservation_failures_demote_requirement_status_across_all_media(kind):
    _assert_fail_closed_media(_snapshot_with_conservation_failure(kind))


def test_requirement_result_reconciliation_failure_demotes_status_across_all_media():
    _assert_fail_closed_media(_snapshot_with_requirement_result_reconciliation_failure())


@pytest.mark.parametrize("kind", ("over_cap", "wrong_kind", "unknown_target", "result_mismatch"))
def test_shadow_failures_demote_requirement_status_across_all_media(kind):
    _assert_fail_closed_media(_snapshot_with_shadow_failure(kind))


def test_nonfinite_allocation_row_demotes_requirement_status_across_all_media(monkeypatch):
    snapshot = _snapshot()
    original = DecisionSnapshot.as_dict

    def tampered(self):
        payload = dict(original(self))
        allocation = dict(payload["allocation"])
        allocation_rows = [dict(item) for item in allocation["allocations"]]
        allocation_rows[0]["source_credits"] = "NaN"
        allocation["allocations"] = tuple(allocation_rows)
        payload["allocation"] = allocation
        return payload

    monkeypatch.setattr(DecisionSnapshot, "as_dict", tampered)
    _assert_fail_closed_media(snapshot)


def test_exports_reject_non_snapshot_objects():
    try:
        export_snapshot_csv({})  # type: ignore[arg-type]
    except TypeError:
        pass
    else:
        raise AssertionError("export must accept only DecisionSnapshot")


def test_exports_recursively_suppress_identity_credentials_and_raw_transcript(monkeypatch):
    snapshot = _snapshot()
    original = DecisionSnapshot.as_dict
    secrets = {
        "student_id": "RAW_STUDENT_ID_EXPORT_9f31",
        "student_number": "RAW_STUDENT_NUMBER_EXPORT_9f31",
        "studentNo": "RAW_STUDENT_NO_EXPORT_9f31",
        "studentId": "RAW_STUDENT_ID_CAMEL_EXPORT_9f31",
        "學號": "原始學號_EXPORT_9f31",
        "student_name": "RAW_STUDENT_NAME_EXPORT_9f31",
        "姓名": "原始姓名_EXPORT_9f31",
        "username": "RAW_USERNAME_EXPORT_9f31",
        "account": "RAW_ACCOUNT_EXPORT_9f31",
        "password": "RAW_PASSWORD_EXPORT_9f31",
        "credential": "RAW_CREDENTIAL_EXPORT_9f31",
        "authorization": "RAW_AUTH_EXPORT_9f31",
        "session": "RAW_SESSION_EXPORT_9f31",
        "cookie": "RAW_COOKIE_EXPORT_9f31",
        "token": "RAW_TOKEN_EXPORT_9f31",
        "HF Token": "RAW_HF_TOKEN_EXPORT_9f31",
        "transcript": "RAW_TRANSCRIPT_EXPORT_9f31",
        "transcriptBytes": "RAW_TRANSCRIPT_BYTES_EXPORT_9f31",
        "pdf": "RAW_PDF_EXPORT_9f31",
        "rawPDF": "RAW_RAW_PDF_EXPORT_9f31",
        "blob": "RAW_BLOB_EXPORT_9f31",
        "bytes": "RAW_BYTES_EXPORT_9f31",
    }

    def hostile(self):
        payload = dict(original(self))
        payload["request"] = {"masked_student_id": "***5678", "nested": dict(secrets)}
        payload["decisions"] = {"safe_decision": {"nested": dict(secrets)}}
        payload["statistics"] = {"safe_statistics": {"nested": dict(secrets)}}
        payload["rule_provenance"] = ({"source_reference": "official:export", "nested": dict(secrets)},)
        return payload

    monkeypatch.setattr(DecisionSnapshot, "as_dict", hostile)
    pdf_document = fitz.open(stream=export_snapshot_pdf(snapshot), filetype="pdf")
    try:
        outputs = (
            render_snapshot(snapshot),
            export_snapshot_csv(snapshot).decode("utf-8-sig"),
            export_snapshot_audit_json(snapshot).decode("utf-8"),
            "\n".join(page.get_text() for page in pdf_document),
        )
    finally:
        pdf_document.close()
    assert "***5678" in outputs[0]
    assert "***5678" in outputs[2]
    for output in outputs:
        assert all(secret not in output for secret in secrets.values())
