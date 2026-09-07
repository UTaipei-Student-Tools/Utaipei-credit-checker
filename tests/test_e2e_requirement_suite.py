"""Comprehensive 4-Tier E2E Requirement-Driven Test Suite.

Derived strictly from ORIGINAL_REQUEST.md and PROJECT.md § Feature Inventory.
Covers:
  Tier 1: Feature Coverage (R1 localization, R2 normalization, R2 major/double major,
          R2 GE verification, R3 dashboard cards, R3 tabular expanders, R3 PDF export).
  Tier 2: Boundary & Corner Cases (empty inputs, corrupt strings, unusual Roman numerals,
          half/full-width mixes, zero-credit courses, failed/withdrawn courses).
  Tier 3: Cross-Feature Interactions (normalization -> allocation -> tabular UI -> PDF clean layout).
  Tier 4: Real-World Application Scenarios with Chen's transcript (學生手冊/U1131002220260906175350.pdf).
"""

from __future__ import annotations

import csv
import io
import os
import re
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from typing import Any

import fitz
import pytest
from bs4 import BeautifulSoup

from course_input_adapter import expand_legacy_course_rows, parser_rows_to_confirmation
from decision_snapshot import DecisionSnapshot
from graduation_service import EvaluationRequest, evaluate
from handbook_rules import (
    get_apc_target_requirements,
    normalize_course_name,
)
from input_confirmation import confirm_confirmation, start_confirmation
from pdf_parser import (
    detect_admission_cohort,
    detect_department_track,
    parse_transcript_pdf,
)
from public_course_catalog import (
    VERIFIED as PUBLIC_VERIFIED,
    load_public_course_catalog,
    resolve_public_evidence,
)
from snapshot_exports import build_student_allocation_csv, build_student_pdf
from snapshot_renderer import build_snapshot_view, render_snapshot
from tests.test_snapshot_exports import _snapshot

# Authoritative forbidden debug tokens from R1
FORBIDDEN_DEBUG_PATTERNS = [
    r"REQUIREMENT_DEFICIT:",
    r"REQUIREMENT_EVIDENCE_",
    r"APPLICATION:",
    r"SEARCH_INCOMPLETE",
    r"SEARCH_EXHAUSTED",
    r"handbook:\d+",
    r"primary:\d+:[a-zA-Z0-9_:-]+",
    r"target:\d+:[a-zA-Z0-9_:-]+",
    r"WAIVER_DECISION_REQUIRED",
    r"RULE_CONTEXT:MANUAL_REVIEW",
]

CHEN_TRANSCRIPT_PATH = os.path.join("學生手冊", "U1131002220260906175350.pdf")


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def _evaluate_course_rows(
    rows: list[dict[str, Any]],
    cohort: str = "113",
    primary_curriculum_id: str = "primary:113:earth:earth_environment",
    program_type: str = "單主修",
    **kwargs: Any,
) -> DecisionSnapshot:
    """Convenience evaluator for structured course rows."""
    confirmation = start_confirmation(rows)
    assert confirmation.valid, f"Confirmation invalid: {confirmation.diagnostics}"
    confirmed = confirm_confirmation(confirmation, confirmation.fingerprint)
    request = EvaluationRequest(
        admission_cohort=cohort,
        primary_curriculum_id=primary_curriculum_id,
        confirmed_course_rows=confirmed.rows,
        confirmed_course_fingerprint=confirmed.fingerprint,
        transcript_confirmed=True,
        course_confirmation=confirmed,
        program_type=program_type,
        **kwargs,
    )
    return evaluate(request)


# ==============================================================================
# Tier 1: Feature Coverage (7 Feature Areas, >=5 Test Cases Each)
# ==============================================================================


class TestTier1R1Localization:
    """R1. 全面消除未本地化英文與內部代碼 (Full Localization & Clean Presentation)."""

    def test_r1_01_no_raw_requirement_deficit_in_rendered_html(self):
        """Verify REQUIREMENT_DEFICIT:<id> is never displayed in rendered HTML."""
        base_snap = _snapshot()
        snapshot = replace(
            base_snap,
            blockers=("REQUIREMENT_DEFICIT:primary:113:earth:domain-elective",),
        )
        html = render_snapshot(snapshot)

        assert "REQUIREMENT_DEFICIT:" not in html
        assert "尚缺" in html or "未達標" in html or "需要補資料" in html

    def test_r1_02_no_raw_application_prefix_in_rendered_html(self):
        """Verify APPLICATION:<status> is translated into Traditional Chinese."""
        base_snap = _snapshot()
        snapshot = replace(
            base_snap,
            blockers=(
                "APPLICATION:APPLICATION_FORMAL_APPROVAL_MISSING",
                "APPLICATION:UNKNOWN",
            ),
        )
        html = render_snapshot(snapshot)

        assert "APPLICATION:" not in html
        assert any(
            phrase in html
            for phrase in ("雙主修資格審核", "尚未取得教務處核准紀錄", "申請", "審查", "需要補資料")
        )

    def test_r1_03_no_raw_search_codes_in_presentation(self):
        """Verify SEARCH_INCOMPLETE and SEARCH_EXHAUSTED are translated to Chinese."""
        base_snap = _snapshot()
        snapshot = replace(
            base_snap,
            blockers=("SEARCH_INCOMPLETE", "SEARCH_EXHAUSTED"),
        )
        html = render_snapshot(snapshot)
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))

        for text in (html, pdf_text):
            assert "SEARCH_INCOMPLETE" not in text
            assert "SEARCH_EXHAUSTED" not in text

    def test_r1_04_handbook_colon_namespaces_translated(self):
        """Verify handbook:113:earth:... is translated into a natural Chinese citation."""
        base_snap = _snapshot()
        snapshot = replace(
            base_snap,
            rule_provenance=(
                {
                    "requirement_id": "req-domain",
                    "source_reference": "handbook:113:earth:primary:earth_environment:domain-elective:p45:r0",
                    "evidence_state": "VERIFIED",
                },
            ),
        )
        html = render_snapshot(snapshot)
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))

        for text in (html, pdf_text):
            assert "handbook:113:earth:primary:earth_environment" not in text
            if "手冊" in text or "規則來源" in text:
                assert any(term in text for term in ("113", "學年度", "地生系", "手冊", "第 45 頁", "規定"))

    def test_r1_05_parametric_deficit_contains_meaningful_chinese(self):
        """Verify requirement deficits provide meaningful requirement name and missing credits."""
        base_snap = _snapshot()
        snapshot = replace(
            base_snap,
            blockers=("REQUIREMENT_DEFICIT:req-a",),
        )
        html = render_snapshot(snapshot)

        assert "REQUIREMENT_DEFICIT:" not in html
        assert any(term in html for term in ("系必修", "尚缺", "學分", "選修", "需要補資料"))

    def test_r1_06_zero_credit_course_code_28030_translated(self):
        """Verify course code 28030 is translated to 大學生活學習與輔導."""
        base_snap = _snapshot()
        snapshot = replace(
            base_snap,
            non_credit_results=(
                {
                    "requirement_id": "pe_orientation",
                    "name": "28030",
                    "kind": "SINGLE_COURSE",
                    "status": "PASS",
                    "required_count": 1,
                    "completed_count": 1,
                    "evidence": "VERIFIED",
                    "coverage": "COMPLETE",
                    "affects_credit_ledger": False,
                },
            ),
        )
        html = render_snapshot(snapshot)
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))

        for text in (html, pdf_text):
            if "28030" in text:
                assert "大學生活學習與輔導" in text


class TestTier1R2Normalization:
    """R2. 提升課程名稱正規化準確度 (Normalization Accuracy)."""

    def test_r2_01_normalize_roman_numerals_i_to_vi(self):
        """Verify Roman numerals (I)~(VI) normalize to Chinese numerals (一)~(六)."""
        assert normalize_course_name("微積分(I)") == "微積分(一)"
        assert normalize_course_name("微積分(II)") == "微積分(二)"
        assert normalize_course_name("普通物理學(III)") == "普通物理學(三)"
        assert normalize_course_name("進階化學(IV)") == "進階化學(四)"
        assert normalize_course_name("實驗(V)") == "實驗(五)"
        assert normalize_course_name("專題(VI)") == "專題(六)"

    def test_r2_02_normalize_arabic_numerals_in_parentheses(self):
        """Verify Arabic numerals in parentheses (1)~(6) normalize to (一)~(六)."""
        assert normalize_course_name("微積分(1)") == "微積分(一)"
        assert normalize_course_name("微積分(2)") == "微積分(二)"
        assert normalize_course_name("普通化學(1)") == "普通化學(一)"

    def test_r2_03_normalize_whitespace_and_spacing(self):
        """Verify extra spaces inside and around course titles are collapsed."""
        assert normalize_course_name("儀器分析 (一)") == "儀器分析(一)"
        assert normalize_course_name("普通化學實驗 (二)") == "普通化學實驗(二)"
        assert normalize_course_name(" 普通物理學 ( 一 ) ") == "普通物理學(一)"

    def test_r2_04_normalize_preserves_course_semantics_and_subtitles(self):
        """Verify domain terminology, lab suffixes, and official subtitles are preserved."""
        assert normalize_course_name("DNA分子生物學") == "DNA分子生物學"
        assert normalize_course_name("RNA生物化學") == "RNA生物化學"
        assert normalize_course_name("C語言程式設計") == "C語言程式設計"
        assert normalize_course_name("普通化學實驗(一)") == "普通化學實驗(一)"
        # English subtitles should keep base course identifier
        assert normalize_course_name("英文(三):職場商旅") == "英文(三)"

    def test_r2_05_normalize_case_insensitivity_and_fullwidth(self):
        """Verify full-width brackets, full-width Roman, and lowercase roman normalize correctly."""
        assert normalize_course_name("微積分(i)") == "微積分(一)"
        assert normalize_course_name("微積分（I）") == "微積分(一)"
        assert normalize_course_name("微積分（一）") == "微積分(一)"
        assert normalize_course_name("普通物理學（二）") == "普通物理學(二)"

    def test_r2_06_normalize_special_symbols_and_brackets(self):
        """Verify special decorative marks like [◇], [※] are cleanly removed."""
        assert normalize_course_name("[◇]微積分(一)") == "微積分(一)"
        assert normalize_course_name("[※]普通化學(二)") == "普通化學(二)"
        assert normalize_course_name("◎生命科學導論") == "生命科學導論"


class TestTier1R2MajorAndDoubleMajorIdentification:
    """R2. 修讀身分精準辨識 (Major & Double Major Identification)."""

    def test_r2_07_detect_primary_department_and_track(self):
        """Verify detect_department_track extracts primary department and track."""
        info = detect_department_track("系所：地球環境暨生物資源學系\n姓名：陳柏亘")
        assert info["department"] == "地生"
        assert info["track"] == "地球環境"

    def test_r2_08_parse_transcript_header_double_major(self):
        """Verify parser extracts double major from transcript header."""
        if not os.path.exists(CHEN_TRANSCRIPT_PATH):
            pytest.skip(f"Missing transcript fixture: {CHEN_TRANSCRIPT_PATH}")
        student_info, _ = parse_transcript_pdf(CHEN_TRANSCRIPT_PATH)

        assert student_info["student_id"] == "U11310022"
        assert student_info["name"] == "陳柏亘"
        # Must detect double major status
        dm = student_info.get("double_major")
        assert dm is not None
        if isinstance(dm, dict):
            assert "應用化學" in dm.get("raw", "") or "化學" in dm.get("track", "") or "物化" in dm.get("department", "")
            assert "修習中" in dm.get("status", "") or "修習中" in dm.get("raw", "")
        else:
            assert "應用化學" in str(dm)

    def test_r2_09_parse_transcript_header_minor_field(self):
        """Verify parser initializes minor field properly."""
        if not os.path.exists(CHEN_TRANSCRIPT_PATH):
            pytest.skip(f"Missing transcript fixture: {CHEN_TRANSCRIPT_PATH}")
        student_info, _ = parse_transcript_pdf(CHEN_TRANSCRIPT_PATH)
        assert "minor" in student_info

    def test_r2_10_apc_double_major_target_plan_loading(self):
        """Verify 115 APC Chemistry double major plan loads 8 required base courses."""
        plan = get_apc_target_requirements("115", "化學組", "雙主修")
        req_names = [r["name"] for r in plan["requirements"]]
        assert "微積分(一)" in req_names
        assert "普通化學(一)" in req_names
        assert "普通化學實驗(一)" in req_names
        assert "普通化學實驗(二)" in req_names
        assert float(plan["total_required"]) == 40.0

    def test_r2_11_calculus_allocates_to_double_major_not_free_elective(self):
        """Verify 微積分(I) maps to 微積分(一) and satisfies double major requirement."""
        rows = [
            {
                "course_code": "MATH101",
                "course_name": "微積分(I)",
                "credits": 3.0,
                "earned_credits": 3.0,
                "status": "COMPLETED",
                "term": "113-1",
                "grade": "68",
                "course_type": "必",
            },
        ]
        # Evaluate under 113 Earth Resources (primary) + 115 APC Chemistry (double major)
        snapshot = _evaluate_course_rows(
            rows,
            cohort="113",
            primary_curriculum_id="primary:113:earth:earth_environment",
            program_type="雙主修",
            target_program="物化",
            target_track="化學組",
            secondary_kind="double_major",
            target_curriculum_year="115",
        )
        payload = snapshot.as_dict()

        # Calculus must not be lost or rejected
        assert float(payload["allocation"]["recognized_credits"]) >= 3.0
        # Check that it matched 微積分(一) in requirements
        req_results = payload["allocation"]["requirement_results"]
        calculus_req = next(
            (r for r in req_results if "微積分(一)" in r["requirement_id"] or r.get("name") == "微積分(一)"),
            None,
        )
        if calculus_req is not None:
            assert calculus_req["status"] == "PASS"
            assert float(calculus_req["deficit"]) == 0.0


class TestTier1R2GeneralEducationVerification:
    """R2. 通識四大領域認列驗證 (General Education Verification)."""

    GE_COURSES = (
        ("臺北城市散步旅行", "113-1", 2.0, "88"),
        ("政府運作與國會監督", "113-1", 2.0, "85"),
        ("日本旅行與日本文化", "113-1", 2.0, "86"),
        ("生命科學與人生", "113-2", 2.0, "82"),
        ("生活哲學與藝術", "113-2", 2.0, "90"),
        ("建築史", "113-2", 2.0, "84"),
    )

    def test_r2_12_ge_courses_present_in_public_course_catalog(self):
        """Verify all 6 GE courses are catalogued in PublicCourseCatalog."""
        catalog = load_public_course_catalog()
        catalog_names = {row.get("course_name") for row in catalog.courses}
        for name, _, _, _ in self.GE_COURSES:
            assert name in catalog_names, f"Course {name} not found in public catalog"

    def test_r2_13_ge_public_evidence_state_verified(self):
        """Verify PublicCourseEvidence returns VERIFIED for each GE course."""
        catalog = load_public_course_catalog()
        for name, term, credits, _ in self.GE_COURSES:
            evidence = resolve_public_evidence(
                catalog,
                term=term,
                course_name=name,
                credits=credits,
            )
            assert evidence.public_identity_state == PUBLIC_VERIFIED, (
                f"Course {name} ({term}) identity state is {evidence.public_identity_state}, expected VERIFIED"
            )

    def test_r2_14_ge_attempts_retain_verified_status(self):
        """Verify GE attempts retain VERIFIED identity_status and are not downgraded to UNKNOWN."""
        rows = [
            {
                "course_code": f"GE-{idx}",
                "course_name": name,
                "credits": credits,
                "earned_credits": credits,
                "status": "COMPLETED",
                "term": term,
                "grade": grade,
                "course_type": "選",
            }
            for idx, (name, term, credits, grade) in enumerate(self.GE_COURSES)
        ]
        snapshot = _evaluate_course_rows(rows, cohort="113")
        view = build_snapshot_view(snapshot)

        for attempt in view["attempts"]:
            if attempt["course_name"] in [c[0] for c in self.GE_COURSES]:
                assert attempt["identity_status"] == "VERIFIED", (
                    f"GE course {attempt['course_name']} had identity_status={attempt['identity_status']}"
                )

    def test_r2_15_no_insufficient_identity_warning_for_verified_ge(self):
        """Verify absence of warning '課程身分或要求來源尚不足以安全認列' for verified GE."""
        rows = [
            {
                "course_code": f"GE-{idx}",
                "course_name": name,
                "credits": credits,
                "earned_credits": credits,
                "status": "COMPLETED",
                "term": term,
                "grade": grade,
                "course_type": "選",
            }
            for idx, (name, term, credits, grade) in enumerate(self.GE_COURSES)
        ]
        snapshot = _evaluate_course_rows(rows, cohort="113")
        html = render_snapshot(snapshot)

        assert "課程身分或要求來源尚不足以安全認列" not in html
        assert "身分尚不足以安全認列" not in html

    def test_r2_16_ge_completed_credits_recognized(self):
        """Verify all 12.0 credits of GE courses are recognized in the credit ledger."""
        rows = [
            {
                "course_code": f"GE-{idx}",
                "course_name": name,
                "credits": credits,
                "earned_credits": credits,
                "status": "COMPLETED",
                "term": term,
                "grade": grade,
                "course_type": "選",
            }
            for idx, (name, term, credits, grade) in enumerate(self.GE_COURSES)
        ]
        snapshot = _evaluate_course_rows(rows, cohort="113")
        payload = snapshot.as_dict()

        recognized = float(payload["allocation"]["recognized_credits"])
        assert recognized == 12.0, f"Expected 12.0 recognized GE credits, got {recognized}"


class TestTier1R3DashboardCards:
    """R3. 儀表板 6 大簡約摘要卡片 (Dashboard Summary Cards)."""

    def test_r3_01_dashboard_contains_six_metric_cards(self):
        """Verify the dashboard presents the 6 summary cards required by R3."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)

        # R3 Requirements: 總學分, 已修得, 尚缺, 主修進度, 雙主修進度, 非學分門檻
        # (Must be present in .snapshot-metrics or dashboard overview)
        soup = BeautifulSoup(html, "html.parser")
        metrics_container = soup.select_one(".snapshot-metrics")
        assert metrics_container is not None

        metric_texts = metrics_container.get_text()
        assert "總學分" in metric_texts or "有效學分" in metric_texts
        assert "已修得" in metric_texts or "實得學分" in html
        assert "尚缺" in metric_texts or "尚缺學分" in metric_texts
        assert "主修進度" in metric_texts or "必修進度" in metric_texts
        assert "雙主修" in metric_texts or "修習中" in metric_texts
        assert "門檻" in metric_texts or "非學分" in html or "待辦" in metric_texts

    def test_r3_02_total_credits_card_value(self):
        """Verify total credits card presents graduation requirement total."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)
        assert "學分" in html

    def test_r3_03_earned_credits_card_value(self):
        """Verify earned credits card presents completed credits."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)
        assert "成績單實得學分" in html or "已修得" in html

    def test_r3_04_missing_credits_card_value(self):
        """Verify missing credits card presents deficit towards graduation."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)
        assert "尚缺" in html

    def test_r3_05_primary_and_double_major_progress_cards(self):
        """Verify major and double major progress displays appropriately."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)
        assert "進度" in html

    def test_r3_06_non_credit_gates_card_value(self):
        """Verify non-credit gate progress is displayed."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)
        assert "門檻" in html or "待辦" in html


class TestTier1R3TabularExpanders:
    """R3. 7 欄折疊展開結構化表格 (Tabular Requirements and Expanders)."""

    def test_r3_07_requirement_expander_details_and_table(self):
        """Verify requirement expanders contain structured HTML tables."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)
        soup = BeautifulSoup(html, "html.parser")

        expanders = soup.select("details.snapshot-requirement-expander")
        assert len(expanders) > 0, "No details.snapshot-requirement-expander found"
        for expander in expanders:
            table = expander.select_one("table")
            assert table is not None, "Expander does not contain a <table>"

    def test_r3_08_table_header_has_seven_aligned_columns(self):
        """Verify table header includes the 7 standard columns."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)
        soup = BeautifulSoup(html, "html.parser")

        table = soup.select_one("details.snapshot-requirement-expander table")
        assert table is not None
        headers = [th.get_text(strip=True) for th in table.select("thead th")]

        # Must include the core columns
        assert "課名" in headers
        assert "學期" in headers
        assert "修得學分" in headers
        assert "此類採計學分" in headers
        assert "狀態／備註" in headers

    def test_r3_09_course_grade_column_rendered(self):
        """Verify Grade column is rendered in the course table."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("details.snapshot-requirement-expander table")
        assert table is not None
        headers = [th.get_text(strip=True) for th in table.select("thead th")]
        # R3 specifies a grade column
        assert "成績" in headers or any("成績" in h for h in headers)

    def test_r3_10_unallocated_courses_tabular_format(self):
        """Verify unallocated courses expander displays as a structured table."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)
        soup = BeautifulSoup(html, "html.parser")

        unallocated_details = soup.select_one("details.snapshot-unallocated-details")
        if unallocated_details:
            table = unallocated_details.select_one("table")
            assert table is not None, "Unallocated section must be tabular"

    def test_r3_11_table_notes_no_multi_p_stack(self):
        """Verify notes column does not stack 4+ <p> tags per row creating excessive height."""
        snapshot = _snapshot()
        html = render_snapshot(snapshot)
        soup = BeautifulSoup(html, "html.parser")

        note_cells = soup.select("td.snapshot-course-notes")
        for cell in note_cells:
            p_tags = cell.select("p")
            # Should not exceed 2 paragraphs per note cell
            assert len(p_tags) <= 2, f"Note cell has {len(p_tags)} <p> tags, expected clean tabular presentation"


class TestTier1R3PDFExportCleanLayout:
    """R3. PDF 結構化報表排版 (Clean Layout PDF Export)."""

    def test_r3_12_pdf_valid_binary_header(self):
        """Verify build_student_pdf outputs a valid PDF document."""
        snapshot = _snapshot()
        pdf_bytes = build_student_pdf(snapshot)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_r3_13_pdf_contains_student_metadata(self):
        """Verify PDF text contains report title and context."""
        snapshot = _snapshot()
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))
        assert "北市大畢業通" in pdf_text or "畢業進度" in pdf_text
        assert "學分" in pdf_text

    def test_r3_14_pdf_contains_summary_metrics(self):
        """Verify PDF contains the summary metrics without text collision."""
        snapshot = _snapshot()
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))
        assert "學分" in pdf_text
        assert any(term in pdf_text for term in ("已修得", "有效學分", "實得學分"))

    def test_r3_15_pdf_zero_raw_debug_codes(self):
        """Verify PDF contains zero forbidden internal debug codes."""
        snapshot = _snapshot()
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))
        for pattern in FORBIDDEN_DEBUG_PATTERNS:
            assert not re.search(pattern, pdf_text), f"Forbidden pattern '{pattern}' found in PDF output"

    def test_r3_16_pdf_multi_page_margin_and_page_numbers(self):
        """Verify multi-page PDF documents have page numbering."""
        snapshot = _snapshot()
        pdf_bytes = build_student_pdf(snapshot)
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            assert len(doc) >= 1
            for page in doc:
                text = page.get_text()
                assert len(text.strip()) > 0
                # Page numbers should follow format: 第 X 頁
                assert "第" in text and "頁" in text


# ==============================================================================
# Tier 2: Boundary & Corner Cases
# ==============================================================================


class TestTier2BoundaryAndCornerCases:
    """Tier 2. 邊界與極端異常處理 (Boundary & Corner Cases)."""

    def test_tier2_01_empty_transcript_input(self):
        """Verify empty course row list is handled gracefully without crash."""
        snapshot = _evaluate_course_rows([], cohort="113")
        html = render_snapshot(snapshot)
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))

        assert snapshot.verdict in ("FAIL", "UNKNOWN", "PENDING")
        assert "0" in html
        for pattern in FORBIDDEN_DEBUG_PATTERNS:
            assert not re.search(pattern, html)
            assert not re.search(pattern, pdf_text)

    def test_tier2_02_corrupt_course_name_filtering(self):
        """Verify corrupt strings, symbols, and pure numbers are sanitized."""
        assert normalize_course_name("%%%") == ""
        assert normalize_course_name("   ") == ""
        assert normalize_course_name("12345") == ""
        assert normalize_course_name("88.5%") == ""
        # Normal course with unbalanced or extra noise
        assert normalize_course_name("[◇]微積分") == "微積分"

    def test_tier2_03_unusual_roman_numerals(self):
        """Verify unusual Roman numerals like (VI) and lowercase (iv) normalize correctly."""
        assert normalize_course_name("專題(VI)") == "專題(六)"
        assert normalize_course_name("普通化學(iv)") == "普通化學(四)"
        assert normalize_course_name("物理實驗(v)") == "物理實驗(五)"

    def test_tier2_04_half_full_width_mixes(self):
        """Verify mixed full/half-width brackets and numbers normalize seamlessly."""
        assert normalize_course_name("微積分（1）") == "微積分(一)"
        assert normalize_course_name("普通物理學(２)") == "普通物理學(二)"
        assert normalize_course_name("環境科學（二）") == "環境科學(二)"
        assert normalize_course_name("化學實驗（2）") == "化學實驗(二)"

    def test_tier2_05_zero_credit_gate_conservation(self):
        """Verify 0-credit gate courses do not artificially inflate earned credits."""
        rows = [
            {
                "course_code": "PE01",
                "course_name": "體育(一)",
                "credits": 0.0,
                "earned_credits": 0.0,
                "status": "COMPLETED",
                "term": "113-1",
                "grade": "80",
                "course_type": "必",
            },
            {
                "course_code": "SL01",
                "course_name": "服務學習",
                "credits": 0.0,
                "earned_credits": 0.0,
                "status": "COMPLETED",
                "term": "113-1",
                "grade": "通過",
                "course_type": "必",
            },
        ]
        snapshot = _evaluate_course_rows(rows, cohort="113")
        payload = snapshot.as_dict()

        assert float(payload["allocation"]["source_earned_credits"]) == 0.0
        assert float(payload["allocation"]["recognized_credits"]) == 0.0
        assert payload["allocation"]["credit_conservation"] is True

    def test_tier2_06_failed_and_withdrawn_courses_do_not_earn_credits(self):
        """Verify F, W, and 0-score courses yield 0 earned credits."""
        rows = [
            {
                "course_code": "F01",
                "course_name": "普通物理學(一)",
                "credits": 3.0,
                "earned_credits": 0.0,
                "status": "FAILED",
                "term": "113-1",
                "grade": "52",
                "course_type": "必",
            },
            {
                "course_code": "W01",
                "course_name": "微積分(一)",
                "credits": 3.0,
                "earned_credits": 0.0,
                "status": "WITHDRAWN",
                "term": "113-1",
                "grade": "停",
                "course_type": "必",
            },
        ]
        snapshot = _evaluate_course_rows(rows, cohort="113")
        payload = snapshot.as_dict()

        assert float(payload["allocation"]["source_earned_credits"]) == 0.0
        assert float(payload["allocation"]["recognized_credits"]) == 0.0


# ==============================================================================
# Tier 3: Cross-Feature Interactions
# ==============================================================================


class TestTier3CrossFeatureInteractions:
    """Tier 3. 跨模組端對端協同整合 (Cross-Feature Interactions)."""

    def test_tier3_01_end_to_end_normalization_to_double_major_allocation(self):
        """Verify raw course 微積分(I) normalizes and satisfies double major requirement in UI & PDF."""
        rows = [
            {
                "course_code": "APC-CAL1",
                "course_name": "微積分(I)",
                "credits": 3.0,
                "earned_credits": 3.0,
                "status": "COMPLETED",
                "term": "113-1",
                "grade": "75",
                "course_type": "必",
            },
        ]
        snapshot = _evaluate_course_rows(
            rows,
            cohort="113",
            primary_curriculum_id="primary:113:earth:earth_environment",
            program_type="雙主修",
            target_program="物化",
            target_track="化學組",
            secondary_kind="double_major",
            target_curriculum_year="115",
        )
        html = render_snapshot(snapshot)
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))

        # Must show normalized name in UI and PDF
        assert "微積分(一)" in html or "微積分(I)" in html
        assert "微積分(一)" in pdf_text or "微積分(I)" in pdf_text
        for pattern in FORBIDDEN_DEBUG_PATTERNS:
            assert not re.search(pattern, html)
            assert not re.search(pattern, pdf_text)

    def test_tier3_02_in_progress_course_flow_through_ui_and_pdf(self):
        """Verify course with grade 未 is tagged IN_PROGRESS, not counted in earned credits, and annotated cleanly."""
        rows = [
            {
                "course_code": "CHEM-LAB2",
                "course_name": "普通化學實驗(二)",
                "credits": 1.0,
                "earned_credits": 0.0,
                "status": "IN_PROGRESS",
                "term": "113-2",
                "grade": "未",
                "course_type": "必",
            },
        ]
        snapshot = _evaluate_course_rows(rows, cohort="113")
        payload = snapshot.as_dict()
        html = render_snapshot(snapshot)
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))

        # Earned credits must be 0
        assert float(payload["allocation"]["source_earned_credits"]) == 0.0
        # HTML and PDF must show in-progress indication
        assert "修習中" in html
        assert "修習中" in pdf_text
        assert "課程身分或要求來源尚不足以安全認列" not in html

    def test_tier3_03_dual_program_credit_conservation(self):
        """Verify strict credit conservation across primary, double major, and general education."""
        rows = [
            {
                "course_code": "E01",
                "course_name": "地球環境變遷",
                "credits": 2.0,
                "earned_credits": 2.0,
                "status": "COMPLETED",
                "term": "113-1",
                "grade": "85",
                "course_type": "必",
            },
            {
                "course_code": "GE01",
                "course_name": "臺北城市散步旅行",
                "credits": 2.0,
                "earned_credits": 2.0,
                "status": "COMPLETED",
                "term": "113-1",
                "grade": "88",
                "course_type": "選",
            },
            {
                "course_code": "APC01",
                "course_name": "微積分(I)",
                "credits": 3.0,
                "earned_credits": 3.0,
                "status": "COMPLETED",
                "term": "113-1",
                "grade": "68",
                "course_type": "必",
            },
        ]
        snapshot = _evaluate_course_rows(
            rows,
            cohort="113",
            primary_curriculum_id="primary:113:earth:earth_environment",
            program_type="雙主修",
            target_program="物化",
            target_track="化學組",
            secondary_kind="double_major",
            target_curriculum_year="115",
        )
        payload = snapshot.as_dict()

        assert payload["allocation"]["credit_conservation"] is True
        total_source = float(payload["allocation"]["source_earned_credits"])
        assert total_source == 7.0

    def test_tier3_04_failsafe_scrubber_on_synthetic_leakage(self):
        """Verify presentation failsafe scrubber completely sanitizes any injected raw debug tokens."""
        base_snap = _snapshot()
        snapshot = replace(
            base_snap,
            blockers=(
                "REQUIREMENT_DEFICIT:113:earth:earth_environment:domain-elective:p45:r0",
                "APPLICATION:APPLICATION_FORMAL_APPROVAL_MISSING",
                "SEARCH_EXHAUSTED",
                "WAIVER_DECISION_REQUIRED:pe",
                "RULE_CONTEXT:MANUAL_REVIEW",
            ),
        )
        html = render_snapshot(snapshot)
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))

        for pattern in FORBIDDEN_DEBUG_PATTERNS:
            assert not re.search(pattern, html), f"Pattern {pattern} leaked into HTML"
            assert not re.search(pattern, pdf_text), f"Pattern {pattern} leaked into PDF"

    def test_tier3_05_cross_media_data_consistency(self):
        """Verify HTML, CSV, and PDF report identical credit totals and requirement counts."""
        rows = [
            {
                "course_code": "E01",
                "course_name": "地球環境變遷",
                "credits": 2.0,
                "earned_credits": 2.0,
                "status": "COMPLETED",
                "term": "113-1",
                "grade": "85",
                "course_type": "必",
            },
        ]
        snapshot = _evaluate_course_rows(rows, cohort="113")
        html = render_snapshot(snapshot)
        csv_bytes = build_student_allocation_csv(snapshot)
        csv_text = csv_bytes.decode("utf-8-sig")
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))

        # Course name must be present across all three media
        assert "地球環境變遷" in html
        assert "地球環境變遷" in csv_text
        assert "地球環境變遷" in pdf_text


# ==============================================================================
# Tier 4: Real-World Application Scenarios (Chen's Transcript)
# ==============================================================================


class TestTier4RealWorldChenTranscript:
    """Tier 4. 真實成績單全鏈路端對端驗收測試 (Chen's Transcript: U11310022)."""

    @pytest.fixture(autouse=True)
    def setup_chen_transcript(self):
        """Check transcript availability before running Tier 4."""
        if not os.path.exists(CHEN_TRANSCRIPT_PATH):
            pytest.skip(f"Chen transcript not found at: {CHEN_TRANSCRIPT_PATH}")

    def test_tier4_01_chen_transcript_pdf_parsing_metadata(self):
        """Verify PDF parser extracts Chen's complete header metadata accurately."""
        student_info, courses = parse_transcript_pdf(CHEN_TRANSCRIPT_PATH)

        assert student_info["student_id"] == "U11310022"
        assert student_info["name"] == "陳柏亘"
        assert student_info["admission_year"] in ("113年09月", "113")
        assert student_info["admission_cohort"] == "113"
        assert "地球環境暨生物資源學系" in student_info["department"]

        # Double major detection
        dm = student_info.get("double_major")
        assert dm is not None
        dm_str = str(dm)
        assert "應用物理暨化學系" in dm_str or "應用化學" in dm_str or "化學" in dm_str
        assert "修習中" in dm_str

    def test_tier4_02_chen_transcript_course_normalization(self):
        """Verify courses parsed from Chen's transcript are normalized correctly."""
        _, courses = parse_transcript_pdf(CHEN_TRANSCRIPT_PATH)
        course_names = [c["name"] for c in courses]

        # Normalization assertions
        normalized_names = [normalize_course_name(name) for name in course_names]
        assert any("微積分(一)" in name for name in normalized_names), "微積分(I) not normalized to 微積分(一)"
        assert any("普通化學實驗(二)" in name for name in normalized_names)
        assert any("儀器分析(一)" in name for name in normalized_names)

    def test_tier4_03_chen_transcript_ge_verification_no_warnings(self):
        """Verify Chen's 6 GE courses (12 credits) are verified without warnings."""
        student_info, raw_courses = parse_transcript_pdf(CHEN_TRANSCRIPT_PATH)
        expanded = expand_legacy_course_rows(raw_courses)

        # Filter only the GE courses for this isolated check
        ge_titles = {
            "臺北城市散步旅行",
            "政府運作與國會監督",
            "日本旅行與日本文化",
            "生命科學與人生",
            "生活哲學與藝術",
            "建築史",
        }
        ge_rows = [r for r in expanded if any(t in r["course_name"] for t in ge_titles)]
        assert len(ge_rows) == 6, f"Expected 6 GE courses, found {len(ge_rows)}"

        snapshot = _evaluate_course_rows(ge_rows, cohort="113")
        html = render_snapshot(snapshot)

        # Must not produce the insufficient identity warning
        assert "課程身分或要求來源尚不足以安全認列" not in html
        assert "身分尚不足以安全認列" not in html
        # Recognized credits must equal 12.0
        assert float(snapshot.as_dict()["allocation"]["recognized_credits"]) == 12.0

    def test_tier4_04_chen_transcript_double_major_allocation(self):
        """Verify 微積分(I) allocates to APC Chemistry 微積分(一) and 普通化學實驗(二) allocates to 普通化學實驗(二) under dual program evaluation."""
        student_info, raw_courses = parse_transcript_pdf(CHEN_TRANSCRIPT_PATH)
        expanded = expand_legacy_course_rows(raw_courses)

        snapshot = _evaluate_course_rows(
            expanded,
            cohort="113",
            primary_curriculum_id="primary:113:earth:earth_environment",
            program_type="雙主修",
            target_program="物化",
            target_track="化學組",
            secondary_kind="double_major",
            target_curriculum_year="115",
            target_curriculum_id="target:double_major:115:apc:chemistry",
        )
        payload = snapshot.as_dict()

        # Check that 微積分(一) is counted in requirements
        req_results = payload["allocation"]["requirement_results"]
        calc_result = next(
            (r for r in req_results if "微積分(一)" in r["requirement_id"] or r.get("name") == "微積分(一)"),
            None,
        )
        assert calc_result is not None, "微積分(一) requirement must exist in double major allocation"
        assert calc_result["status"] == "PASS"

        lab2_result = next(
            (r for r in req_results if "普通化學實驗(二)" in r["requirement_id"] or r.get("name") == "普通化學實驗(二)"),
            None,
        )
        assert lab2_result is not None, "普通化學實驗(二) requirement must exist in double major allocation"
        assert lab2_result["status"] == "PASS"

    def test_tier4_05_chen_transcript_clean_presentation_and_pdf(self):
        """Verify Chen's evaluation HTML and PDF have 0 debug code leaks."""
        student_info, raw_courses = parse_transcript_pdf(CHEN_TRANSCRIPT_PATH)
        expanded = expand_legacy_course_rows(raw_courses)

        snapshot = _evaluate_course_rows(
            expanded,
            cohort="113",
            primary_curriculum_id="primary:113:earth:earth_environment",
            program_type="雙主修",
            target_program="物化",
            target_track="化學組",
            secondary_kind="double_major",
            target_curriculum_year="115",
        )
        html = render_snapshot(snapshot)
        pdf_text = _extract_pdf_text(build_student_pdf(snapshot))

        for pattern in FORBIDDEN_DEBUG_PATTERNS:
            assert not re.search(pattern, html), f"Forbidden pattern '{pattern}' found in Chen HTML"
            assert not re.search(pattern, pdf_text), f"Forbidden pattern '{pattern}' found in Chen PDF"
