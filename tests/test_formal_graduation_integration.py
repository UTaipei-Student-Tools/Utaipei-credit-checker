"""Full official-rule evaluation and student export use the same decision."""

import csv
import io
import re

import fitz
import pytest
from bs4 import BeautifulSoup

from graduation_service import EvaluationRequest, evaluate
from input_confirmation import confirm_confirmation, start_confirmation
from snapshot_exports import build_student_allocation_csv, build_student_pdf
from snapshot_projection import statistics_projection_from_payload
from snapshot_renderer import build_snapshot_view, render_snapshot
from tests.formal_transcript_fixture import build_rows


def evaluate_rows(rows):
    confirmation = start_confirmation(rows)
    assert confirmation.valid
    confirmation = confirm_confirmation(confirmation, confirmation.fingerprint)
    return evaluate(EvaluationRequest(
        admission_cohort='111', primary_curriculum_id='primary:111:earth:earth_environment',
        confirmed_course_rows=confirmation.rows, confirmed_course_fingerprint=confirmation.fingerprint,
        transcript_confirmed=True, course_confirmation=confirmation, program_type='單主修',
    ))


@pytest.fixture(scope='module')
def formal_snapshot():
    return evaluate_rows(build_rows())


def test_full_handbook_transcript_has_conservative_feasible_witness(formal_snapshot):
    payload = formal_snapshot.as_dict()
    assert formal_snapshot.verdict == 'PASS'
    assert payload['allocation']['credit_conservation']
    assert payload['allocation']['feasible_witness']
    assert float(payload['allocation']['source_earned_credits']) == 128
    assert float(payload['allocation']['recognized_credits']) == 128
    assert all(item['status'] == 'PASS' for item in payload['allocation']['requirement_results'])
    assert all(item['status'] == 'PASS' for item in payload['non_credit_results'])
    assert all(item['status'] == 'PASS' for item in payload['subset_results'])


def test_formal_statistics_preserve_the_authoritative_credit_ledger(formal_snapshot):
    view = build_snapshot_view(formal_snapshot)
    assert float(view['summary']['source_earned_credits']) == 128
    assert sum(float(value) for value in view['summary']['by_bucket'].values()) == 128
    assert view['summary']['credit_conservation']
    statistics = statistics_projection_from_payload(formal_snapshot.as_dict())
    assert statistics['statistics_validation']['valid']
    assert float(statistics['source_earned_credits']) == 128
    for key in ('f1', 'f5'):
        assert view['chart_datasets'][key]['available'], (key, view['presentation_warnings'])
    assert view['chart_datasets']['f7']['reason_code'] == 'TOO_MANY_GATE_CATEGORIES'
    assert view['chart_datasets']['f11']['available']
    assert float(view['chart_datasets']['f11']['completed']) == 128
    assert float(view['chart_datasets']['f11']['required']) == 128


def test_formal_student_media_keeps_gate_courses_and_chinese_status(formal_snapshot):
    payload = formal_snapshot.as_dict()
    html = render_snapshot(formal_snapshot)
    csv_text = build_student_allocation_csv(formal_snapshot).decode('utf-8-sig')
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    with fitz.open(stream=build_student_pdf(formal_snapshot), filetype='pdf') as document:
        pdf_text = '\n'.join(page.get_text() for page in document)
    for gate in payload['non_credit_results']:
        row = next(row for row in rows if row.get('要求名稱') == gate['name'])
        assert row['資料狀態'] == '規則資料完整；已核對'
        assert row['課程名稱']
    html_text = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)
    for media in (html_text, csv_text, pdf_text):
        assert '大學生活學習與輔導' in media
        assert '資訊應用與設計' in media
        assert not re.search(r'\b(?:UNKNOWN|PASS|FAIL|SEARCH_EXHAUSTED|RULE_NOT_IMPLEMENTED)\b', media)


def test_missing_named_course_cannot_pass_with_unrelated_replacement_credits():
    rows = [row for row in build_rows() if row['course_name'] != '地球環境變遷']
    rows.append(dict(course_code='', course_name='未經認定替代課程', credits=2,
                     earned_credits=2, status='COMPLETED', term='111-1', course_type=''))
    snapshot = evaluate_rows(rows)
    assert snapshot.verdict != 'PASS'
    requirement = next(item for item in snapshot.as_dict()['allocation']['requirement_results']
                       if item['requirement_id'].endswith('.地球環境變遷'))
    assert requirement['status'] != 'PASS'
    assert float(requirement['deficit']) == 2
