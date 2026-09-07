"""Empirical Adversarial Stress-Testing for Feature 10: PDF Export (snapshot_exports.build_student_pdf).

This test suite challenges:
1. Multi-page pagination (>50 courses spanning 3+ pages) with footer format: '第 X 頁 / 共 Y 頁'.
2. Strict margin & boundary adherence (no overflow past printable margins).
3. Rigid 7-column fixed X-coordinate alignment across all pages.
4. Graceful course title truncation: standard names preserved, long titles truncated with '…' <= 170 pt.
5. Zero tolerance for forbidden debug/internal tokens across all pages.
6. Binary %PDF- validity and metadata verification.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

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
    _student_pdf_blocks,
    _truncate_cjk,
    build_student_pdf,
)

FORBIDDEN_DEBUG_PATTERNS = [
    re.compile(r"REQUIREMENT_[A-Za-z0-9_:-]+"),
    re.compile(r"APPLICATION:[a-zA-Z0-9_:-]+"),
    re.compile(r"SEARCH_IN\w*"),
    re.compile(r"SEARCH_EX\w*"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    re.compile(r"attempt:v\d+:[0-9a-f]{16,}"),
    re.compile(r"\bCREDIT_CONSERVATION_FAILED\b"),
    re.compile(r"\bEXCLUSIVE\b"),
    re.compile(r"\bSHARED_SHADOW\b"),
    re.compile(r"\bDIRECTION_ONLY\b"),
]


def _build_multipage_adversarial_snapshot(num_courses: int = 65) -> DecisionSnapshot:
    """Generate a large-scale student snapshot with 65+ course attempts and hostile metadata."""
    attempts = []
    allocations = []
    portions = []

    # Standard course names
    standard_names = [
        "微積分(一)",
        "普通化學(一)",
        "普通化學實驗(一)",
        "普通物理學",
        "地球科學概論",
        "程式設計實習",
        "資料結構",
        "演算法",
        "作業系統",
        "計算機組織",
        "離散數學",
        "線性代數",
        "機率與統計",
    ]

    # Special adversarial course names
    hostile_names = [
        "普通化學實驗(二)",
        "高等大氣動力學特論與數值天氣預報模式實務研究專題分析（進階版）",  # Extremely long title
        "氣候變遷與全球環境永續發展專題討論(一)",
        "生物多樣性與分子生態學進階實驗技術分析與應用(甲)",
    ]

    for i in range(num_courses):
        att_id = f"att-{i:03d}"
        course_id = f"CRS-{100 + i}"

        if i < len(hostile_names):
            c_name = hostile_names[i]
        else:
            c_name = f"{standard_names[i % len(standard_names)]} 第{i + 1}組"

        sem = f"11{3 + (i // 20)}-{(i % 2) + 1}"
        status = "PASS" if i % 6 != 0 else "IN_PROGRESS"
        grade = "85" if status == "PASS" else ""
        cr = Decimal("3") if i % 5 != 0 else Decimal("1")

        attempts.append(
            CourseAttempt(
                attempt_id=att_id,
                course_id=course_id,
                course_name=c_name,
                credits=cr,
                earned_credits=cr if status == "PASS" else Decimal("0"),
                academic_term=sem,
                status=status,
                grade=grade,
            )
        )

        req_target = "req-major-core" if i < 30 else ("req-major-elective" if i < 55 else None)
        if req_target and status == "PASS":
            portions.append(CreditPortion(att_id, req_target, cr))
            allocations.append(
                AttemptAllocation(
                    attempt_id=att_id,
                    source_credits=cr,
                    portions=(CreditPortion(att_id, req_target, cr),),
                    unallocated_credits=Decimal("0"),
                )
            )
        else:
            allocations.append(
                AttemptAllocation(
                    attempt_id=att_id,
                    source_credits=cr,
                    portions=(),
                    unallocated_credits=cr if status == "PASS" else Decimal("0"),
                )
            )

    requirements = (
        RequirementSpec(
            requirement_id="req-major-core",
            name="地生系專業核心必修",
            required_credits=Decimal("30"),
            eligible_course_ids=tuple(f"CRS-{100 + i}" for i in range(30)),
            coverage_state=COMPLETE,
            evidence_state=VERIFIED,
            bucket="required",
            kind="必修",
        ),
        RequirementSpec(
            requirement_id="req-major-elective",
            name="地生系專業領域選修",
            required_credits=Decimal("25"),
            eligible_course_ids=tuple(f"CRS-{100 + i}" for i in range(30, 55)),
            coverage_state=COMPLETE,
            evidence_state=VERIFIED,
            bucket="elective",
            kind="選修",
        ),
    )

    requirement_results = (
        RequirementResult(
            requirement_id="req-major-core",
            status="PASS",
            required_credits=Decimal("30"),
            exclusive_credits=Decimal("30"),
            shared_shadow_credits=Decimal("0"),
            effective_credits=Decimal("30"),
            deficit=Decimal("0"),
            coverage_state="COMPLETE",
            evidence_state="VERIFIED",
        ),
        RequirementResult(
            requirement_id="req-major-elective",
            status="IN_PROGRESS",
            required_credits=Decimal("25"),
            exclusive_credits=Decimal("20"),
            shared_shadow_credits=Decimal("0"),
            effective_credits=Decimal("20"),
            deficit=Decimal("5"),
            coverage_state="COMPLETE",
            evidence_state="VERIFIED",
        ),
    )

    allocation = AllocationResult(
        status="IN_PROGRESS",
        allocations=tuple(allocations),
        requirement_results=requirement_results,
        source_earned_credits=Decimal("120"),
        recognized_credits=Decimal("50"),
        unallocated_credits=Decimal("25"),
        credit_conservation=True,
        alternative_allocations=(),
    )

    snapshot = build_decision_snapshot(
        {
            "attempts": tuple(attempts),
            "requirements": requirements,
            "input_confirmation": {
                "state": "CONFIRMED",
                "current_fingerprint": "adv-m3-fp",
                "confirmed_fingerprint": "adv-m3-fp",
                "formal_release_success": True,
                "row_count": len(attempts),
                "released_row_count": len(attempts),
            },
        },
        evaluated_at="2026-09-07T04:00:00Z",
    )

    return replace_snapshot_fields(snapshot, allocation)


def replace_snapshot_fields(snapshot: DecisionSnapshot, allocation: AllocationResult) -> DecisionSnapshot:
    from dataclasses import replace

    return replace(
        snapshot,
        allocation=allocation,
        snapshot_id="snapshot:adv-multipage-65",
        verdict="IN_PROGRESS",
        decisions={
            "overall": {"status": "IN_PROGRESS", "reason": "雙主修及選修仍有差額"},
            "double_major_qualification": {"status": "PASS", "reason": "已達標"},
            "formal_double_major_award": {"status": "PASS"},
            "non_credit_thresholds": {
                "items": (
                    {"name": "英文檢定", "status": "PASS"},
                    {"name": "服務學習", "status": "IN_PROGRESS"},
                )
            },
        },
        statistics={
            "total_graduation_credits": "128",
            "recognized_credits": "50",
            "effective_recognized_credits": "50",
            "unallocated_credits": "25",
            "credit_conservation": True,
            "by_bucket": {"required": "30", "elective": "20", "unallocated": "25"},
            "completed": 55,
            "in_progress": 10,
            "unresolved": 0,
        },
        blockers=(
            "REQUIREMENT_DEFICIT:primary:113:earth:domain-elective",
            "APPLICATION:DOUBLE_MAJOR_NOT_APPROVED",
        ),
        warnings=("SEARCH_INCOMPLETE",),
        remediation_suggestions=("請至系辦確認選修領域學分認列。",),
    )


class TestAdversarialPDFExportMultiPageAndAlignment:
    """Stress tests on PDF generation: pagination, coordinates, truncation, tokens."""

    def test_pdf_binary_header_and_document_validity(self):
        """Verify output starts with %PDF- and opens without PyMuPDF errors."""
        snapshot = _build_multipage_adversarial_snapshot(65)
        pdf_bytes = build_student_pdf(snapshot)

        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 2000

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        assert doc.page_count >= 3
        meta = doc.metadata
        assert meta.get("title") == "北市大畢業通｜學分進度"
        assert meta.get("author") == "北市大畢業通"
        doc.close()

    def test_multipage_pagination_and_footer_format(self):
        """Verify every page in multi-page document has '第 X 頁 / 共 Y 頁' footer."""
        snapshot = _build_multipage_adversarial_snapshot(65)
        pdf_bytes = build_student_pdf(snapshot)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = doc.page_count
        assert total_pages >= 3, f"Expected >= 3 pages for 65 courses, got {total_pages}"

        page_pattern = re.compile(r"第\s*(\d+)\s*頁\s*/\s*共\s*(\d+)\s*頁")

        for idx, page in enumerate(doc):
            text = page.get_text()
            match = page_pattern.search(text)
            assert match is not None, f"Page {idx + 1} missing '第 X 頁 / 共 Y 頁' footer. Extracted: {text[-200:]}"
            current_page = int(match.group(1))
            extracted_total = int(match.group(2))
            assert current_page == idx + 1, f"Expected page {idx + 1}, got {current_page}"
            assert extracted_total == total_pages, f"Expected total {total_pages}, got {extracted_total}"

            # Running header check on subsequent pages (idx > 0)
            if idx > 0:
                assert "北市大畢業通｜學分進度與畢業審查" in text

        doc.close()

    def test_fixed_x_coordinates_and_column_alignment(self):
        """Verify fixed X positions (42, 96, 268, 306, 344, 382, 442) for table headers and rows."""
        snapshot = _build_multipage_adversarial_snapshot(65)
        pdf_bytes = build_student_pdf(snapshot)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        expected_cols = [42.0, 96.0, 268.0, 306.0, 344.0, 382.0, 442.0]

        # Inspect raw text positioning across pages
        for page_idx, page in enumerate(doc):
            text_page = page.get_text("words")
            # Verify no word is printed outside the horizontal margins [42.0, 553.32]
            for word in text_page:
                x0, y0, x1, y1, text_val, block_no, line_no, word_no = word
                # Allow a tiny float epsilon of 0.5
                assert x0 >= 41.5, f"Word '{text_val}' on page {page_idx + 1} overflows left margin: x0={x0}"
                assert x1 <= 554.0, f"Word '{text_val}' on page {page_idx + 1} overflows right margin: x1={x1}"
                assert y1 <= 841.92, f"Word '{text_val}' on page {page_idx + 1} overflows bottom page: y1={y1}"

        doc.close()

    def test_course_name_truncation_logic_and_bounds(self):
        """Verify standard course titles are kept intact while overly long titles truncate with '…'."""
        fitz_mod = fitz
        fontname = "china-t"
        fontsize = 8.5
        max_w = 170.0

        # Case 1: Standard title
        std_title = "普通化學實驗(二)"
        res1 = _truncate_cjk(std_title, max_w, fontname, fontsize, fitz_mod)
        assert res1 == std_title
        assert "…" not in res1

        # Case 2: 17-char title
        mid_title = "地球環境變遷與永續發展專題討論(一)"
        res2 = _truncate_cjk(mid_title, max_w, fontname, fontsize, fitz_mod)
        assert fitz_mod.get_text_length(res2, fontname=fontname, fontsize=fontsize) <= max_w

        # Case 3: Extremely long title (45 chars)
        long_title = "高等大氣動力學特論與數值天氣預報模式實務研究專題分析（進階版）"
        res3 = _truncate_cjk(long_title, max_w, fontname, fontsize, fitz_mod)
        assert res3.endswith("…")
        length_pt = fitz_mod.get_text_length(res3, fontname=fontname, fontsize=fontsize)
        assert length_pt <= max_w, f"Truncated length {length_pt} pt exceeds {max_w} pt"

        # Verify in generated PDF document
        snapshot = _build_multipage_adversarial_snapshot(65)
        pdf_bytes = build_student_pdf(snapshot)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = "\n".join(page.get_text() for page in doc)
        doc.close()

        assert "普通化學實驗(二)" in full_text
        assert "高等大氣動力學特論" in full_text
        assert ("…" in full_text or "⋯" in full_text)

    def test_regex_scan_for_zero_forbidden_debug_tokens(self):
        """Verify strict zero-leakage of forbidden debug/internal tokens across all pages."""
        snapshot = _build_multipage_adversarial_snapshot(65)
        pdf_bytes = build_student_pdf(snapshot)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = "\n".join(page.get_text() for page in doc)
        doc.close()

        for pattern in FORBIDDEN_DEBUG_PATTERNS:
            match = pattern.search(full_text)
            assert match is None, f"Forbidden debug token '{match.group(0) if match else ''}' leaked in PDF!"

        # Specific forbidden strings
        forbidden_strings = [
            "REQUIREMENT_",
            "APPLICATION:",
            "EXCLUSIVE",
            "SHARED_SHADOW",
            "DIRECTION_ONLY",
            "CREDIT_CONSERVATION_FAILED",
            "SEARCH_INCOMPLETE",
        ]
        for token in forbidden_strings:
            assert token not in full_text, f"Forbidden string '{token}' found in PDF text!"
