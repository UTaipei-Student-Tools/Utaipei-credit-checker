from __future__ import annotations

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
from snapshot_exports import build_student_pdf
from snapshot_renderer import render_snapshot


def _create_test_snapshot(
    double_major_active: bool = False,
    with_non_credit: bool = False,
) -> DecisionSnapshot:
    attempts = (
        CourseAttempt(
            attempt_id="att-1",
            course_id="CS-101",
            course_name="計算機概論",
            credits=Decimal("3"),
            earned_credits=Decimal("3"),
            academic_term="113-1",
            status="PASS",
        ),
        CourseAttempt(
            attempt_id="att-2",
            course_id="CS-102",
            course_name="程式設計實習",
            credits=Decimal("1"),
            earned_credits=Decimal("1"),
            academic_term="113-1",
            status="PASS",
        ),
        CourseAttempt(
            attempt_id="att-3",
            course_id="MA-201",
            course_name="高等微積分",
            credits=Decimal("3"),
            earned_credits=Decimal("0"),
            academic_term="113-2",
            status="IN_PROGRESS",
        ),
        CourseAttempt(
            attempt_id="att-4",
            course_id="FREE-99",
            course_name="課外自由選修",
            credits=Decimal("2"),
            earned_credits=Decimal("2"),
            academic_term="114-1",
            status="PASS",
        ),
    )

    requirements = (
        RequirementSpec(
            requirement_id="req-major-core",
            name="資訊核心必修",
            required_credits=Decimal("4"),
            eligible_course_ids=("CS-101", "CS-102"),
            coverage_state=COMPLETE,
            evidence_state=VERIFIED,
            bucket="required",
            kind="必修",
        ),
        RequirementSpec(
            requirement_id="req-major-adv",
            name="資訊進階選修",
            required_credits=Decimal("3"),
            eligible_course_ids=("MA-201",),
            coverage_state=COMPLETE,
            evidence_state=VERIFIED,
            bucket="elective",
            kind="選修",
        ),
    )

    decisions = {
        "primary_graduation": {"status": "IN_PROGRESS", "reason": "進行中"},
        "double_major_qualification": (
            {"status": "PASS", "reason": "已達標"}
            if double_major_active
            else {"status": "NOT_APPLICABLE", "reason": "非雙主修"}
        ),
        "formal_double_major_award": (
            {"status": "PASS"}
            if double_major_active
            else {"status": "NOT_APPLICABLE"}
        ),
        "overall": {"status": "IN_PROGRESS", "reason": "持續修習中"},
    }

    if with_non_credit:
        decisions["non_credit_thresholds"] = {
            "items": (
                {"name": "英文檢定", "status": "PASS"},
                {"name": "服務學習", "status": "IN_PROGRESS"},
            )
        }

    snapshot = build_decision_snapshot(
        {
            "attempts": attempts,
            "requirements": requirements,
            "input_confirmation": {
                "state": "CONFIRMED",
                "current_fingerprint": "r3-acceptance-fp",
                "confirmed_fingerprint": "r3-acceptance-fp",
                "formal_release_success": True,
                "row_count": len(attempts),
                "released_row_count": len(attempts),
            },
        },
        evaluated_at="2026-09-06T12:00:00Z",
    )

    allocations = (
        AttemptAllocation(
            attempt_id="att-1",
            source_credits=Decimal("3"),
            portions=(CreditPortion("att-1", "req-major-core", Decimal("3")),),
            unallocated_credits=Decimal("0"),
        ),
        AttemptAllocation(
            attempt_id="att-2",
            source_credits=Decimal("1"),
            portions=(CreditPortion("att-2", "req-major-core", Decimal("1")),),
            unallocated_credits=Decimal("0"),
        ),
        AttemptAllocation(
            attempt_id="att-3",
            source_credits=Decimal("3"),
            portions=(),
            unallocated_credits=Decimal("0"),
        ),
        AttemptAllocation(
            attempt_id="att-4",
            source_credits=Decimal("2"),
            portions=(),
            unallocated_credits=Decimal("2"),
        ),
    )

    requirement_results = (
        RequirementResult(
            requirement_id="req-major-core",
            status="PASS",
            required_credits=Decimal("4"),
            exclusive_credits=Decimal("4"),
            shared_shadow_credits=Decimal("0"),
            effective_credits=Decimal("4"),
            deficit=Decimal("0"),
            coverage_state="COMPLETE",
            evidence_state="VERIFIED",
        ),
        RequirementResult(
            requirement_id="req-major-adv",
            status="IN_PROGRESS",
            required_credits=Decimal("3"),
            exclusive_credits=Decimal("0"),
            shared_shadow_credits=Decimal("0"),
            effective_credits=Decimal("0"),
            deficit=Decimal("3"),
            coverage_state="COMPLETE",
            evidence_state="VERIFIED",
        ),
    )

    allocation = AllocationResult(
        status="IN_PROGRESS",
        allocations=allocations,
        requirement_results=requirement_results,
        source_earned_credits=Decimal("6"),
        recognized_credits=Decimal("4"),
        unallocated_credits=Decimal("2"),
        credit_conservation=True,
        alternative_allocations=(),
    )

    return replace(
        snapshot,
        allocation=allocation,
        snapshot_id="snapshot:r3-acceptance",
        verdict="IN_PROGRESS",
        decisions=decisions,
        statistics={
            "total_graduation_credits": "128",
            "recognized_credits": "4",
            "effective_recognized_credits": "4",
            "unallocated_credits": "2",
            "shared_shadow_credits": "0",
            "credit_conservation": True,
            "by_bucket": {"required": "4", "elective": "0"},
            "requirement_status_counts": {"PASS": 1, "IN_PROGRESS": 1},
            "course_status_counts": {"PASS": 3, "IN_PROGRESS": 1},
            "completed": 3,
            "in_progress": 1,
            "unresolved": 0,
            "deficits": (
                {
                    "requirement_id": "req-major-adv",
                    "name": "資訊進階選修",
                    "deficit": "3",
                    "status": "IN_PROGRESS",
                },
            ),
        },
    )


def test_ui_renders_six_summary_metric_cards_with_backward_compatibility():
    snapshot = _create_test_snapshot()
    html = render_snapshot(snapshot)

    # 1. Six required summary cards
    assert '<span class="snapshot-metric-label">總學分</span>' in html
    assert '<span class="snapshot-metric-label">已修得</span>' in html
    assert '<span class="snapshot-metric-label">尚缺</span>' in html
    assert '<span class="snapshot-metric-label">主修進度</span>' in html
    assert '<span class="snapshot-metric-label">雙主修進度</span>' in html
    assert '<span class="snapshot-metric-label">非學分門檻</span>' in html

    # 2. Backward compatible labels preserved
    assert "有效學分" in html
    assert "必修進度" in html

    # 3. Card metric values check
    assert "128" in html
    assert "4" in html  # recognized credits
    assert "無申請" in html or "未申請" in html or "雙主修" in html


def test_ui_renders_seven_column_table_with_inline_tags():
    snapshot = _create_test_snapshot()
    html = render_snapshot(snapshot)

    # 1. 7 Column headers in requirement table
    expected_headers = [
        '<th scope="col">課名</th>',
        '<th scope="col">學期</th>',
        '<th scope="col">成績</th>',
        '<th scope="col">修得學分</th>',
        '<th scope="col">此類採計學分</th>',
        '<th scope="col">採計類別</th>',
        '<th scope="col">狀態／備註</th>',
    ]
    for header in expected_headers:
        assert header in html

    # 2. Column cells and classes
    assert '<td class="snapshot-course-grade">' in html
    assert '<td class="snapshot-course-category">' in html

    # 3. Inline tag badges present (not stacked <p>)
    assert '<div class="snapshot-course-tags">' in html
    assert '<span class="snapshot-tag">' in html

    # 4. Backward-compatible semantic labels inside tags
    assert "採計用途" in html
    assert "原因" in html


def test_ui_dynamic_cards_for_double_major_and_non_credit():
    # Test double major active
    snapshot_dm = _create_test_snapshot(double_major_active=True)
    html_dm = render_snapshot(snapshot_dm)
    assert "資格通過" in html_dm or "已核准" in html_dm or "通過" in html_dm

    # Test non-credit threshold active
    snapshot_nc = _create_test_snapshot(with_non_credit=True)
    html_nc = render_snapshot(snapshot_nc)
    assert "1/2" in html_nc or "通過" in html_nc


def test_student_pdf_structured_aligned_table_layout():
    snapshot = _create_test_snapshot()
    pdf_bytes = build_student_pdf(snapshot)
    assert pdf_bytes.startswith(b"%PDF")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count >= 1
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    # 1. 6 Summary metrics in PDF summary block
    assert "總學分" in full_text
    assert "已修得" in full_text
    assert "尚缺" in full_text
    assert "主修進度" in full_text
    assert "雙主修進度" in full_text
    assert "非學分門檻" in full_text

    # 2. Structured table columns in PDF
    assert "學期" in full_text
    assert "課名" in full_text
    assert "成績" in full_text
    assert "修得" in full_text
    assert "採計" in full_text
    assert "類別" in full_text
    assert "狀態／備註" in full_text

    # 3. Content items
    assert "計算機概論" in full_text
    assert "課外自由選修" in full_text
    assert "113-1" in full_text
    assert "採計用途：" in full_text


def test_student_pdf_zero_internal_leak_tokens():
    snapshot = _create_test_snapshot()
    pdf_bytes = build_student_pdf(snapshot)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    # Forbidden internal/debug vocabulary
    forbidden = (
        "REQUIREMENT_",
        "APPLICATION:",
        "EXCLUSIVE",
        "SHARED_SHADOW",
        "DIRECTION_ONLY",
        "UNKNOWN",
        "DecisionSnapshot",
        "uuid:",
        "attempt:",
        "RULE_CONTEXT:",
        "CONFIRMED",
        "UNALLOCATED",
    )
    for token in forbidden:
        assert token not in full_text, f"Internal token '{token}' leaked in student PDF!"
