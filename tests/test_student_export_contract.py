"""Student media must retain courses that still need an allocation decision."""

import csv
import io
import re

import fitz
from bs4 import BeautifulSoup

from snapshot_exports import _student_unallocated_courses, build_student_allocation_csv, build_student_pdf
from snapshot_renderer import _public_context_markup, _subset_name, render_snapshot
from tests.test_snapshot_exports import _snapshot, _snapshot_with_conservation_failure


def _media(snapshot):
    csv_text = build_student_allocation_csv(snapshot).decode("utf-8-sig")
    with fitz.open(stream=build_student_pdf(snapshot), filetype="pdf") as document:
        pdf_text = "\n".join(page.get_text() for page in document)
    return list(csv.DictReader(io.StringIO(csv_text))), csv_text, pdf_text


def test_unallocated_earned_course_remains_visible_in_student_csv_and_pdf():
    rows, _, pdf_text = _media(_snapshot())
    assert any(row.get("課程名稱") == "普通課程" for row in rows)
    assert "普通課程" in pdf_text


def test_unnamed_formal_subset_does_not_expose_internal_identifiers():
    assert _subset_name({'membership_id': 'science_college', 'constraint_id': 'primary:free:science'}) == '理學院課程學分要求'
    assert _subset_name({'membership_id': 'internal:other', 'constraint_id': 'primary:other'}) == '學分採計條件'
    assert _subset_name({'membership_id': 'cs_beta_domain:115:network'}) == '資科系乙類選修：網路領域'


def test_math_canonical_context_uses_chinese_domain_label():
    label = _public_context_markup({'context': {'primary_curriculum_id': 'primary:114:math:data_science'}})
    assert label == '主修：數學（數據科學）'


def test_actual_cs_registry_groups_54_credits_without_an_extra_consumer():
    from graduation_service import EvaluationRequest, evaluate
    from snapshot_renderer import _cs_elective_rollup, build_snapshot_view

    snapshot = evaluate(EvaluationRequest(admission_cohort='115', primary_curriculum_id='primary:115:cs',
                                          program_type='單主修'))
    view = build_snapshot_view(snapshot)
    rollup = _cs_elective_rollup(view)
    assert rollup is not None
    assert len(rollup['alpha']) == 12
    assert len(rollup['beta']) == 1
    assert sum(float(row['required_credits']) for row in view['requirements']) == 128
    html = render_snapshot(snapshot)
    rows, csv_text, pdf_text = _media(snapshot)
    assert html.count('class="snapshot-card snapshot-cs-electives"') == 1
    assert '資科系選修：0／54 學分' in html
    assert '資科系選修：0／54 學分' in pdf_text
    assert any('甲類指定課程32' in row['要求類別'] for row in rows)
    assert any('乙類選修22' in row['要求類別'] for row in rows)
    assert not re.search(r'\b(?:cs_alpha_required|cs_elective_beta|UNKNOWN|PASS|FAIL)\b', csv_text+pdf_text)


def test_unallocated_earned_course_remains_visible_in_student_screen():
    html = render_snapshot(_snapshot())
    assert "普通課程" in html
    assert "尚未採計課程" in html


def test_student_media_preserves_report_identity_without_raw_status_codes():
    snapshot = _snapshot()
    _, csv_text, pdf_text = _media(snapshot)
    assert snapshot.snapshot_id in csv_text
    assert snapshot.snapshot_id in pdf_text
    assert not re.search(r"\b(?:UNKNOWN|PASS|FAIL|CREDIT_CONSERVATION_FAILED|NOT_APPLICABLE)\b", csv_text + pdf_text)


def test_unreconciled_requirement_is_not_exported_as_completed():
    rows, csv_text, pdf_text = _media(_snapshot_with_conservation_failure("cross_cancel"))
    requirement_rows = [row for row in rows if row.get("要求名稱") == "系必修"]
    assert requirement_rows
    assert all(row.get("要求狀態") != "已完成" for row in requirement_rows)
    assert not re.search(r"\b(?:UNKNOWN|CREDIT_CONSERVATION_FAILED)\b", csv_text + pdf_text)


def test_unallocated_course_matching_keeps_distinct_terms_with_same_course_code():
    view = {
        "attempts": (
            {"attempt_id": "term-1", "course_id": "DUP-101", "course_name": "重複代碼課程", "academic_term": "114-1"},
            {"attempt_id": "term-2", "course_id": "DUP-101", "course_name": "重複代碼課程", "academic_term": "115-1"},
        ),
        "requirements": (
            {"courses": ({"attempt_id": "term-1", "course_id": "DUP-101", "academic_term": "114-1"},)},
        ),
        "allocations": (),
    }

    items = _student_unallocated_courses(view)
    assert [item["attempt"]["attempt_id"] for item in items] == ["term-2"]


def test_optional_non_credit_and_subset_results_are_preserved_across_student_media(monkeypatch):
    snapshot = _snapshot()
    original_as_dict = type(snapshot).as_dict

    def as_dict_with_additional_gates(self):
        payload = dict(original_as_dict(self))
        payload["non_credit_results"] = (
            {
                "requirement_id": "pe",
                "name": "體育",
                "kind": "DISTINCT_TERM_ITEM_COUNT",
                "status": "UNKNOWN",
                "required_count": 4,
                "completed_count": 3,
                "completed_terms": ("114-1", "114-2", "115-1"),
                "in_progress_terms": ("115-2",),
                "matched_attempt_ids": ("b",),
                "blockers": ("NON_CREDIT_DEFICIT:pe",),
                "coverage": "COMPLETE",
                "evidence": "VERIFIED",
                "provenance": ({"source_reference": "official:pe:p5"},),
                "affects_credit_ledger": False,
            },
        )
        payload["subset_results"] = (
            {
                "constraint_id": "science_college_minimum",
                "name": "理學院自由學分下限",
                "status": "PASS",
                "required_credits": "3",
                "verified_credits": "3",
                "unknown_candidate_credits": "0",
                "source_reference": "official:free:p12",
            },
            {
                "constraint_id": "math_external_cap",
                "name": "數學系外系採計上限",
                "status": "PASS",
                "required_credits": "0",
                "maximum_credits": "15",
                "verified_credits": "12",
                "unknown_candidate_credits": "0",
                "source_reference": "official:math:111:p69",
            },
            {
                "constraint_id": "cs_beta_domain:115:network",
                "membership_id": "cs_beta_domain:115:network",
                "status": "PASS",
                "minimum_course_count": 1,
                "verified_course_count": 1,
                "required_credits": "0",
                "verified_credits": "3",
                "source_reference": "official:cs:115:p124",
            },
        )
        return payload

    monkeypatch.setattr(type(snapshot), "as_dict", as_dict_with_additional_gates)
    html = render_snapshot(snapshot)
    rows, csv_text, pdf_text = _media(snapshot)

    gate_row = next(row for row in rows if row["要求類別"] == "非學分門檻")
    assert "普通課程｜114-2｜已完成｜2 學分" in gate_row["課程名稱"]
    assert gate_row["資料狀態"] == "規則資料完整；已核對"
    subset_rows = [row for row in rows if row["要求類別"] == "學分採計條件"]
    assert all(row["資料狀態"] == "依列示規則來源" for row in subset_rows)
    table_rows = [row.get_text(" ", strip=True) for row in BeautifulSoup(html, "html.parser").select("table tr")]
    assert any(all(value in row for value in ("普通課程", "114-2", "已完成", "2")) for row in table_rows)

    for media in (html, csv_text, pdf_text):
        assert "體育" in media
        assert "3／4 學期／項目" in media
        assert "理學院自由學分下限" in media
        assert "3／3 學分" in media
        assert "已採計 12 學分／上限 15 學分" in media
        assert "12／0 學分" not in media
        assert "official:pe:p5" in media
        assert "official:free:p12" in media
        assert "NON_CREDIT_DEFICIT" not in media
        if media != html:
            assert "普通課程｜114-2｜已完成｜2 學分" in media
        assert "資科系乙類選修：網路領域" in media
        assert "1／1 門課程" in media
