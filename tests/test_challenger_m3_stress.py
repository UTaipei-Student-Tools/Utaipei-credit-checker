from __future__ import annotations

import re
from decimal import Decimal
from dataclasses import replace

import pytest
from bs4 import BeautifulSoup

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
from snapshot_renderer import render_snapshot


def _make_base_snapshot(
    attempts=(),
    requirements=(),
    allocations=(),
    requirement_results=(),
    decisions=None,
    statistics=None,
    secondary_kind="",
    with_non_credit=None,
) -> DecisionSnapshot:
    if decisions is None:
        decisions = {
            "primary_graduation": {"status": "IN_PROGRESS", "reason": "進行中"},
            "double_major_qualification": {"status": "NOT_APPLICABLE", "reason": "非雙主修"},
            "formal_double_major_award": {"status": "NOT_APPLICABLE"},
            "overall": {"status": "IN_PROGRESS", "reason": "進行中"},
        }
    if with_non_credit is not None:
        decisions["non_credit_thresholds"] = {"items": with_non_credit}

    snapshot = build_decision_snapshot(
        {
            "attempts": tuple(attempts),
            "requirements": tuple(requirements),
            "secondary_kind": secondary_kind,
            "request": {"secondary_kind": secondary_kind} if secondary_kind else {},
            "input_confirmation": {
                "state": "CONFIRMED",
                "current_fingerprint": "stress-test-fp",
                "confirmed_fingerprint": "stress-test-fp",
                "formal_release_success": True,
                "row_count": len(attempts),
                "released_row_count": len(attempts),
            },
        },
        evaluated_at="2026-09-07T04:00:00Z",
    )

    total_source = sum((a.earned_credits for a in attempts), Decimal("0"))
    total_alloc = sum((r.effective_credits for r in requirement_results), Decimal("0"))

    allocation = AllocationResult(
        status="IN_PROGRESS",
        allocations=tuple(allocations),
        requirement_results=tuple(requirement_results),
        source_earned_credits=total_source,
        recognized_credits=total_alloc,
        unallocated_credits=max(Decimal("0"), total_source - total_alloc),
        credit_conservation=True,
        alternative_allocations=(),
    )

    stats = {
        "total_graduation_credits": "128",
        "recognized_credits": str(total_alloc),
        "effective_recognized_credits": str(total_alloc),
        "unallocated_credits": str(max(Decimal("0"), total_source - total_alloc)),
        "shared_shadow_credits": "0",
        "credit_conservation": True,
        "by_bucket": {"required": str(total_alloc)},
        "requirement_status_counts": {"PASS": 0, "IN_PROGRESS": 1},
        "course_status_counts": {"PASS": len(attempts), "IN_PROGRESS": 0},
        "completed": 0,
        "in_progress": 0,
        "unresolved": 0,
    }
    if statistics:
        stats.update(statistics)

    return replace(
        snapshot,
        allocation=allocation,
        snapshot_id="snapshot:stress-test",
        verdict="IN_PROGRESS",
        decisions=decisions,
        statistics=stats,
    )


# --------------------------------------------------------------------------
# Edge Case 1: Fresh student with 0 credits
# --------------------------------------------------------------------------
def test_edge_case_1_fresh_student_zero_credits():
    snapshot = _make_base_snapshot(
        attempts=(),
        requirements=(
            RequirementSpec(
                requirement_id="req-core",
                name="必修學分",
                required_credits=Decimal("32"),
                eligible_course_ids=(),
                coverage_state=COMPLETE,
                evidence_state=VERIFIED,
                bucket="required",
                kind="必修",
            ),
        ),
        requirement_results=(
            RequirementResult(
                requirement_id="req-core",
                status="IN_PROGRESS",
                required_credits=Decimal("32"),
                exclusive_credits=Decimal("0"),
                shared_shadow_credits=Decimal("0"),
                effective_credits=Decimal("0"),
                deficit=Decimal("32"),
                coverage_state="COMPLETE",
                evidence_state="VERIFIED",
            ),
        ),
    )

    html = render_snapshot(snapshot)

    # Assert 6 summary cards
    assert '<span class="snapshot-metric-label">總學分</span>' in html
    assert '<span class="snapshot-metric-label">已修得</span>' in html
    assert '<span class="snapshot-metric-label">尚缺</span>' in html
    assert '<span class="snapshot-metric-label">主修進度</span>' in html
    assert '<span class="snapshot-metric-label">雙主修進度</span>' in html
    assert '<span class="snapshot-metric-label">非學分門檻</span>' in html

    soup = BeautifulSoup(html, "html.parser")
    metrics = {
        card.select_one(".snapshot-metric-label").text.strip(): card.select_one(".snapshot-metric-value").text.strip()
        for card in soup.select(".snapshot-metric")
    }

    assert metrics["總學分"] == "128 學分"
    assert metrics["已修得"] == "0 學分"
    assert metrics["尚缺"] == "128 學分"
    assert metrics["雙主修進度"] == "未申請"
    assert metrics["非學分門檻"] == "審查通過"


# --------------------------------------------------------------------------
# Edge Case 2: Double Major variations (Passed vs In-Progress vs Minor vs NA)
# --------------------------------------------------------------------------
def test_edge_case_2_double_major_passed():
    decisions = {
        "primary_graduation": {"status": "IN_PROGRESS", "reason": "主修進行中"},
        "double_major_qualification": {"status": "PASS", "reason": "已達標"},
        "formal_double_major_award": {"status": "PASS"},
        "overall": {"status": "IN_PROGRESS", "reason": "進行中"},
    }
    snapshot = _make_base_snapshot(decisions=decisions, secondary_kind="double_major")
    html = render_snapshot(snapshot)

    soup = BeautifulSoup(html, "html.parser")
    dm_card = next(c for c in soup.select(".snapshot-metric") if "雙主修進度" in c.text)
    val = dm_card.select_one(".snapshot-metric-value").text.strip()
    assert val == "資格通過" or "通過" in val


def test_edge_case_2_double_major_in_progress():
    decisions = {
        "primary_graduation": {"status": "IN_PROGRESS", "reason": "主修進行中"},
        "double_major_qualification": {"status": "IN_PROGRESS", "reason": "修習中"},
        "formal_double_major_award": {"status": "IN_PROGRESS"},
        "overall": {"status": "IN_PROGRESS", "reason": "進行中"},
    }
    stats = {
        "program_progress": {
            "double_major": {"completed_credits": "20", "required_credits": "40"}
        }
    }
    snapshot = _make_base_snapshot(decisions=decisions, secondary_kind="double_major", statistics=stats)
    html = render_snapshot(snapshot)

    soup = BeautifulSoup(html, "html.parser")
    dm_card = next(c for c in soup.select(".snapshot-metric") if "雙主修進度" in c.text)
    val = dm_card.select_one(".snapshot-metric-value").text.strip()
    assert val == "20／40 學分"


def test_edge_case_2_minor():
    decisions = {
        "primary_graduation": {"status": "IN_PROGRESS", "reason": "主修進行中"},
        "minor_coursework_completion": {"status": "IN_PROGRESS", "reason": "輔系修習中"},
        "double_major_qualification": {"status": "NOT_APPLICABLE"},
        "overall": {"status": "IN_PROGRESS", "reason": "進行中"},
    }
    snapshot = _make_base_snapshot(decisions=decisions, secondary_kind="minor")
    html = render_snapshot(snapshot)

    soup = BeautifulSoup(html, "html.parser")
    dm_card = next(c for c in soup.select(".snapshot-metric") if "雙主修進度" in c.text)
    val = dm_card.select_one(".snapshot-metric-value").text.strip()
    assert val == "輔系修習中"
    subtext = dm_card.select_one("small").text.strip()
    assert "未加修雙主修" in subtext


def test_edge_case_2_not_applicable():
    decisions = {
        "primary_graduation": {"status": "IN_PROGRESS", "reason": "主修進行中"},
        "double_major_qualification": {"status": "NOT_APPLICABLE"},
        "overall": {"status": "IN_PROGRESS", "reason": "進行中"},
    }
    snapshot = _make_base_snapshot(decisions=decisions, secondary_kind="")
    html = render_snapshot(snapshot)

    soup = BeautifulSoup(html, "html.parser")
    dm_card = next(c for c in soup.select(".snapshot-metric") if "雙主修進度" in c.text)
    val = dm_card.select_one(".snapshot-metric-value").text.strip()
    assert val == "未申請"
    subtext = dm_card.select_one("small").text.strip()
    assert "無申請雙主修" in subtext


# --------------------------------------------------------------------------
# Edge Case 3: Non-credit results (Passed vs Missing vs Partial)
# --------------------------------------------------------------------------
def test_edge_case_3_non_credit_passed():
    items = (
        {"name": "英文檢定", "status": "PASS"},
        {"name": "服務學習", "status": "PASS"},
    )
    snapshot = _make_base_snapshot(with_non_credit=items)
    html = render_snapshot(snapshot)

    soup = BeautifulSoup(html, "html.parser")
    nc_card = next(c for c in soup.select(".snapshot-metric") if "非學分門檻" in c.text)
    val = nc_card.select_one(".snapshot-metric-value").text.strip()
    assert val == "2/2 項"
    subtext = nc_card.select_one("small").text.strip()
    assert "全數通過畢業門檻" in subtext


def test_edge_case_3_non_credit_missing():
    snapshot = _make_base_snapshot(with_non_credit=None)
    html = render_snapshot(snapshot)

    soup = BeautifulSoup(html, "html.parser")
    nc_card = next(c for c in soup.select(".snapshot-metric") if "非學分門檻" in c.text)
    val = nc_card.select_one(".snapshot-metric-value").text.strip()
    assert val == "審查通過"
    subtext = nc_card.select_one("small").text.strip()
    assert "全數通過 · 無額外門檻" in subtext


def test_edge_case_3_non_credit_partial():
    items = (
        {"name": "英文檢定", "status": "PASS"},
        {"name": "服務學習", "status": "IN_PROGRESS"},
        {"name": "體育畢業門檻", "status": "FAIL"},
    )
    snapshot = _make_base_snapshot(with_non_credit=items)
    html = render_snapshot(snapshot)

    soup = BeautifulSoup(html, "html.parser")
    nc_card = next(c for c in soup.select(".snapshot-metric") if "非學分門檻" in c.text)
    val = nc_card.select_one(".snapshot-metric-value").text.strip()
    assert val == "1/3 項"
    subtext = nc_card.select_one("small").text.strip()
    assert "1 項審查通過 · 尚有 2 項待完成" in subtext


# --------------------------------------------------------------------------
# Edge Case 4: Extremely long course names, special characters, roman numerals
# --------------------------------------------------------------------------
def test_edge_case_4_long_names_special_chars_roman_numerals():
    extremely_long_name = "超長課程名稱" * 12 + "（高等巨量資料結構與分散式並行計算進階專題研究實作課程五十六）"  # 80+ chars
    special_char_name = '<script>alert("xss")</script> & "微積分"\' <special>'
    roman_name = "微積分(I)與普通化學實驗(II)"

    attempts = (
        CourseAttempt(
            attempt_id="att-long",
            course_id="LONG-01",
            course_name=extremely_long_name,
            credits=Decimal("3"),
            earned_credits=Decimal("3"),
            academic_term="113-1",
            status="PASS",
        ),
        CourseAttempt(
            attempt_id="att-xss",
            course_id="XSS-02",
            course_name=special_char_name,
            credits=Decimal("2"),
            earned_credits=Decimal("2"),
            academic_term="113-2",
            status="PASS",
        ),
        CourseAttempt(
            attempt_id="att-roman",
            course_id="ROMAN-03",
            course_name=roman_name,
            credits=Decimal("4"),
            earned_credits=Decimal("4"),
            academic_term="114-1",
            status="PASS",
        ),
    )

    requirements = (
        RequirementSpec(
            requirement_id="req-complex",
            name="特殊綜合課程組",
            required_credits=Decimal("9"),
            eligible_course_ids=("LONG-01", "XSS-02", "ROMAN-03"),
            coverage_state=COMPLETE,
            evidence_state=VERIFIED,
            bucket="required",
            kind="必修",
        ),
    )

    allocations = (
        AttemptAllocation("att-long", Decimal("3"), (CreditPortion("att-long", "req-complex", Decimal("3")),), Decimal("0")),
        AttemptAllocation("att-xss", Decimal("2"), (CreditPortion("att-xss", "req-complex", Decimal("2")),), Decimal("0")),
        AttemptAllocation("att-roman", Decimal("4"), (CreditPortion("att-roman", "req-complex", Decimal("4")),), Decimal("0")),
    )

    req_results = (
        RequirementResult("req-complex", "PASS", Decimal("9"), Decimal("9"), Decimal("0"), Decimal("9"), Decimal("0"), "COMPLETE", "VERIFIED"),
    )

    snapshot = _make_base_snapshot(
        attempts=attempts,
        requirements=requirements,
        allocations=allocations,
        requirement_results=req_results,
    )

    html = render_snapshot(snapshot)

    # 1. Verify XSS injection is safely escaped
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html

    # 2. Verify long name is present and safely contained
    assert "超長課程名稱" in html

    # 3. Verify roman numerals preserved or normalized
    assert "微積分" in html


# --------------------------------------------------------------------------
# Edge Case 5: Table notes cell contains 0 <p> tags (assert <= 2 <p> tags)
# --------------------------------------------------------------------------
def test_edge_case_5_notes_cell_zero_p_tags():
    attempts = (
        CourseAttempt(
            attempt_id="att-test-1",
            course_id="CS-101",
            course_name="計算機概論",
            credits=Decimal("3"),
            earned_credits=Decimal("3"),
            academic_term="113-1",
            status="PASS",
        ),
        CourseAttempt(
            attempt_id="att-test-2",
            course_id="CS-102",
            course_name="資料結構",
            credits=Decimal("3"),
            earned_credits=Decimal("3"),
            academic_term="113-2",
            status="PASS",
        ),
    )
    requirements = (
        RequirementSpec(
            requirement_id="req-core",
            name="系核心必修",
            required_credits=Decimal("6"),
            eligible_course_ids=("CS-101", "CS-102"),
            coverage_state=COMPLETE,
            evidence_state=VERIFIED,
            bucket="required",
            kind="必修",
        ),
    )
    allocations = (
        AttemptAllocation("att-test-1", Decimal("3"), (CreditPortion("att-test-1", "req-core", Decimal("3")),), Decimal("0")),
        AttemptAllocation("att-test-2", Decimal("3"), (CreditPortion("att-test-2", "req-core", Decimal("3")),), Decimal("0")),
    )
    req_results = (
        RequirementResult("req-core", "PASS", Decimal("6"), Decimal("6"), Decimal("0"), Decimal("6"), Decimal("0"), "COMPLETE", "VERIFIED"),
    )
    snapshot = _make_base_snapshot(
        attempts=attempts,
        requirements=requirements,
        allocations=allocations,
        requirement_results=req_results,
    )

    html = render_snapshot(snapshot)
    soup = BeautifulSoup(html, "html.parser")

    notes_cells = soup.select("td.snapshot-course-notes")
    assert len(notes_cells) >= 2, "Should have rendered course rows with notes cells"

    for idx, cell in enumerate(notes_cells):
        p_tags = cell.find_all("p")
        # Worker M3 designed notes cell to use .snapshot-course-tags without ANY <p> tag
        assert len(p_tags) == 0, f"Notes cell #{idx} contains {len(p_tags)} <p> tags, expected 0!"
        # Verify tag badges are used instead
        assert cell.select(".snapshot-course-tags"), f"Notes cell #{idx} missing .snapshot-course-tags"
        assert cell.select(".snapshot-tag"), f"Notes cell #{idx} missing .snapshot-tag badges"


# --------------------------------------------------------------------------
# Edge Case 6: Check for any internal debug leaks
# --------------------------------------------------------------------------
def test_edge_case_6_zero_internal_debug_leaks():
    # Construct a hostile snapshot carrying internal codes in blockers, reasons, etc.
    decisions = {
        "primary_graduation": {"status": "IN_PROGRESS", "reason": "RULE_CONTEXT:MANUAL_REVIEW"},
        "double_major_qualification": {"status": "NOT_APPLICABLE", "reason": "APPLICATION:DOUBLE_MAJOR_NOT_APPROVED"},
        "formal_double_major_award": {"status": "NOT_APPLICABLE"},
        "overall": {"status": "IN_PROGRESS", "reason": "SEARCH_INCOMPLETE"},
    }
    attempts = (
        CourseAttempt(
            attempt_id="att-uuid-550e8400-e29b-41d4-a716-446655440000",
            course_id="113:earth:earth_environment:pool:common",
            course_name="環境科學概論",
            credits=Decimal("3"),
            earned_credits=Decimal("3"),
            academic_term="113-1",
            status="PASS",
        ),
    )
    requirements = (
        RequirementSpec(
            requirement_id="primary:113:earth:required_core",
            name="地生系核心必修",
            required_credits=Decimal("3"),
            eligible_course_ids=("113:earth:earth_environment:pool:common",),
            coverage_state=COMPLETE,
            evidence_state=VERIFIED,
            bucket="required",
            kind="必修",
        ),
    )
    allocations = (
        AttemptAllocation(
            "att-uuid-550e8400-e29b-41d4-a716-446655440000",
            Decimal("3"),
            (CreditPortion("att-uuid-550e8400-e29b-41d4-a716-446655440000", "primary:113:earth:required_core", Decimal("3")),),
            Decimal("0"),
        ),
    )
    req_results = (
        RequirementResult(
            "primary:113:earth:required_core",
            "PASS",
            Decimal("3"),
            Decimal("3"),
            Decimal("0"),
            Decimal("3"),
            Decimal("0"),
            "COMPLETE",
            "VERIFIED",
            blockers=("REQUIREMENT_DEFICIT:113:earth:required_core", "REQUIREMENT_EVIDENCE_UNKNOWN:primary:113:earth"),
        ),
    )
    snapshot = _make_base_snapshot(
        attempts=attempts,
        requirements=requirements,
        allocations=allocations,
        requirement_results=req_results,
        decisions=decisions,
    )

    html = render_snapshot(snapshot)

    # 1. No raw REQUIREMENT_ tokens
    assert "REQUIREMENT_" not in html, "Leaked REQUIREMENT_ token!"

    # 2. No raw APPLICATION: tokens
    assert "APPLICATION:" not in html, "Leaked APPLICATION: token!"

    # 3. No raw SEARCH_ tokens
    assert "SEARCH_INCOMPLETE" not in html
    assert "SEARCH_EXHAUSTED" not in html
    assert "SEARCH_IN" not in html

    # 4. No raw UUIDs (e.g. 550e8400-e29b-41d4-a716-446655440000)
    assert "550e8400-e29b-41d4-a716-446655440000" not in html

    # 5. No raw attempt: or uuid: or custom:
    assert "attempt:" not in html
    assert "uuid:" not in html

    # 6. No internal curriculum colons leaked to text
    assert "113:earth:earth_environment:pool:common" not in html
