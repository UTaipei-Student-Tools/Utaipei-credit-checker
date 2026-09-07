"""TDD contract tests for the versioned minor-program DecisionSnapshot path."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import replace

from curriculum_registry import get_curriculum, list_curriculum_ids, resolve_rule_context
from graduation_service import EvaluationRequest, evaluate
from input_confirmation import NormalizedCourseRow, confirm_confirmation, fingerprint_course_rows, start_confirmation
from snapshot_exports import (
    build_snapshot_export_payload,
    export_snapshot_audit_json,
    export_snapshot_csv,
    export_snapshot_pdf,
)
from snapshot_renderer import build_snapshot_projection, render_snapshot


def _row(name: str, *, code: str | None = None, credits: float = 3, course_type: str = "lecture") -> NormalizedCourseRow:
    parsed = start_confirmation(
        [
            {
                "course_code": code or name,
                "course_name": name,
                "credits": credits,
                "earned_credits": credits,
                "status": "已修",
                "term": "115-1",
                "grade": "A",
                "course_type": course_type,
            }
        ]
    )
    assert parsed.valid
    return parsed.rows[0]


def _request(*, rows: tuple[NormalizedCourseRow, ...] = (), **kwargs) -> EvaluationRequest:
    confirmation = confirm_confirmation(start_confirmation([item.as_dict() for item in rows]), fingerprint_course_rows(rows))
    return EvaluationRequest(
        admission_cohort="114",
        primary_curriculum_id="primary:114:apc:chemistry",
        confirmed_course_rows=confirmation.rows,
        confirmed_course_fingerprint=confirmation.fingerprint,
        transcript_confirmed=True,
        confirmation_state="CONFIRMED",
        **kwargs,
    )


def _minor_request(*, year: str = "115", program: str = "apc", track: str = "chemistry", rows=(), **kwargs) -> EvaluationRequest:
    target = kwargs.pop("target_curriculum_id", f"minor:{year}:{program}:{track if program == 'apc' else 'department'}")
    return _request(
        rows=tuple(rows),
        secondary_kind="minor",
        target_curriculum_id=target,
        target_program=program,
        target_track=track if program == "apc" else None,
        **kwargs,
    )


def test_minor_registry_has_exact_25_year_scopes_and_stable_ids():
    ids = list_curriculum_ids(kind="minor")
    assert len(ids) == 25
    assert set(ids) == {
        *(f"minor:{year}:apc:{track}" for year in ("111", "112", "113", "114", "115") for track in ("physics", "chemistry")),
        *(f"minor:{year}:{program}:department" for year in ("111", "112", "113", "114", "115") for program in ("earth", "cs", "math")),
    }
    assert all(get_curriculum(item)["kind"] == "minor_target" for item in ids)


def test_minor_rules_keep_scope_specific_provenance_and_do_not_inherit_neighbor_years():
    old_apc = get_curriculum("minor:114:apc:chemistry")
    new_apc = get_curriculum("minor:115:apc:chemistry")
    assert old_apc["coverage_state"] == "COMPLETE"
    assert old_apc["thresholds"]["fixed_base_credits"] == 16
    assert old_apc["thresholds"]["remaining_required_credits"] == 4
    assert "微積分(一)" not in {row["name"] for row in old_apc["course_catalog"]}
    assert "微積分(一)" in {row["name"] for row in new_apc["course_catalog"]}
    assert {row["component_type"] for row in new_apc["course_catalog"] if "實驗" in row["name"]} == {"lab"}
    for row in new_apc["course_catalog"]:
        assert row["source_url"]
        assert row["pdf_page"]
        assert row["printed_page"]
        assert row["original_clause"]
        assert row["verification_status"] == "VERIFIED"
        assert "automatic_decision" in row


def test_minor_catalog_excludes_primary_zero_credit_gates_and_keeps_year_specific_choices():
    earth112 = get_curriculum("minor:112:earth:department")
    earth113 = get_curriculum("minor:113:earth:department")
    earth114 = get_curriculum("minor:114:earth:department")
    assert earth112["thresholds"]["credit_total"] == 24
    assert earth112["thresholds"]["zero_credit_gate"] is False
    assert all(row["credits"] > 0 and not row["is_zero_credit"] for row in earth112["course_catalog"])
    assert any(set(row["eligible_course_names"]) == {"專題研究(一)", "專業實習(一)"} for row in earth112["course_catalog"])
    assert any(set(row["eligible_course_names"]) == {"專題研究(二)", "專業實習(二)"} for row in earth112["course_catalog"])
    assert any("專題研究" in row["name"] and "專業實習" in row["name"] and row["credits"] == 2 for row in earth113["course_catalog"])
    assert any(row["name"] == "書報討論" for row in earth114["course_catalog"])
    assert not any(row["name"] == "服務學習學年課" for row in get_curriculum("minor:115:earth:department")["course_catalog"])


def test_minor_named_earth_and_cs_rows_have_verified_complete_official_sources():
    for year in ("111", "112", "113", "114", "115"):
        earth = get_curriculum(f"minor:{year}:earth:department")
        cs = get_curriculum(f"minor:{year}:cs:department")
        for curriculum in (earth, cs):
            named_rows = [
                row for row in curriculum["course_catalog"]
                if row["credits"] > 0 and not row["is_zero_credit"] and row["requirement_type"] != "credit_quota"
            ]
            assert named_rows
            assert all(row["verification_status"] == "VERIFIED" for row in named_rows)
            assert all(row["coverage_state"] == "COMPLETE" for row in named_rows)
        assert earth["coverage_state"] == "COMPLETE"
        assert cs["coverage_state"] == "COMPLETE"
        assert {row["name"] for row in cs["course_catalog"] if row["requirement_type"] == "named_course"} == {
            "計算機概論", "C程式設計",
        }


def test_minor_math_catalog_is_exactly_year_scoped_and_uses_official_names():
    math111 = get_curriculum("minor:111:math:department")
    math113 = get_curriculum("minor:113:math:department")
    math114 = get_curriculum("minor:114:math:department")
    math115 = get_curriculum("minor:115:math:department")

    def names(curriculum):
        return {name for row in curriculum["course_catalog"] for name in row["eligible_course_names"]}

    assert {"數學軟體應用與實作(A)", "數學軟體應用與實作(B)", "數學軟體應用與實作(C)"} <= names(math111)
    assert {"Matlab程式設計", "Python程式設計"}.isdisjoint(names(math111))
    assert {"Matlab程式設計", "Python程式設計"} <= names(math114)
    assert "數學遊戲教學設計與實務" in names(math114)
    assert "數學遊戲數位設計與實務" not in names(math114)
    assert "數學遊戲數位設計與實務" in names(math115)
    assert "數學遊戲教學設計與實務" not in names(math115)
    assert "程式設計與資料庫" in names(math113)
    assert "應用統計方法(一)" in names(math114)
    assert "應用統計" not in names(math113)
    math113_revision = math113["credit_revision_history"]["數學導論"]
    assert math113["conflicted_course_names"] == ()
    assert math113_revision["current_credits"] == 3
    assert math113_revision["previous_credits"] == 4


def test_minor_math_one_of_waiver_and_113_revision_are_explicit():
    math111 = get_curriculum("minor:111:math:department")
    math115 = get_curriculum("minor:115:math:department")
    math113 = get_curriculum("minor:113:math:department")
    for record, expected in (
        (math111, {"數學軟體應用與實作(A)", "數學軟體應用與實作(B)", "數學軟體應用與實作(C)"}),
        (math115, {"Matlab程式設計", "Python程式設計"}),
    ):
        pool = next(row for row in record["course_catalog"] if row["name"] == "數學表列選修")
        assert expected <= set(pool["eligible_course_names"])
        cap = next(rule for rule in pool["subset_constraints"] if rule["membership_id"].endswith(":software"))
        assert cap["maximum_credits"] == 3
        assert cap["maximum_course_count"] == 1
        assert not cap.get("minimum_course_count")
    calculus = next(row for row in math111["course_catalog"] if row["name"] == "微積分(一)")
    assert calculus["waiver"] is True
    assert calculus["waiver_generates_credits"] is False
    elective = next(row for row in math113["course_catalog"] if row["name"] == "數學表列選修")
    assert any(
        option["name"] == "數學導論" and option["credits"] == 3
        for option in elective["eligible_course_options"]
    )
    assert math113["credit_revision_history"]["數學導論"]["revision_state"] == "CURRENT_VALUE_VERIFIED"


def test_minor_resolution_requires_explicit_target_version_and_uses_minor_id():
    unresolved = resolve_rule_context(
        {
            "admission_cohort": "114",
            "primary_program": "apc",
            "primary_track": "chemistry",
            "secondary_kind": "minor",
            "target_program": "apc",
            "target_track": "chemistry",
        }
    )
    assert unresolved["dimensions"]["target_curriculum_version"]["status"] in {"MISSING", "MANUAL_REVIEW"}
    assert "TARGET_SCOPE_INCOMPLETE" in str(unresolved)

    selected = resolve_rule_context(
        {
            "admission_cohort": "114",
            "primary_program": "apc",
            "primary_track": "chemistry",
            "secondary_kind": "minor",
            "target_program": "apc",
            "target_track": "chemistry",
            "target_curriculum_version": "minor:115:apc:chemistry",
        }
    )
    assert selected["target_curriculum_id"] == "minor:115:apc:chemistry"
    assert selected["target_curriculum"]["kind"] == "minor_target"
    assert selected["dimensions"]["target_curriculum_version"]["status"] != "RESOLVED"


def test_minor_self_report_never_qualifies_and_approval_chain_is_separate():
    snapshot = evaluate(
        _minor_request(
            target_curriculum_id="minor:115:apc:chemistry",
            application_year="114",
            application_semester="2",
            application_status="已申請",
        )
    )
    decisions = snapshot.as_dict()["decisions"]
    assert decisions["minor_application_or_qualification"]["status"] != "PASS"
    assert decisions["minor_application_or_qualification"]["self_report"]["status"] == "UNKNOWN"
    assert decisions["minor_coursework_completion"]["status"] == "UNKNOWN"
    assert decisions["formal_minor_award"]["status"] == "UNKNOWN"

    records = {
        "target-evidence": {"record_id": "target-evidence", "evidence_state": "VERIFIED", "authority": "系所", "source_reference": "official:target", "curriculum_id": "minor:115:apc:chemistry", "admission_cohort": "114", "target_program": "apc", "target_track": "chemistry", "application_year": "114", "application_semester": "2"},
        "department-evidence": {"record_id": "department-evidence", "evidence_state": "VERIFIED", "authority": "應物化系", "source_reference": "official:department", "record_type": "MINOR_APPROVAL", "admission_cohort": "114", "target_program": "apc", "target_track": "chemistry", "application_year": "114", "application_semester": "2"},
        "registrar-evidence": {"record_id": "registrar-evidence", "evidence_state": "VERIFIED", "authority": "教務處", "source_reference": "official:registrar", "record_type": "MINOR_REGISTRATION", "admission_cohort": "114", "target_program": "apc", "target_track": "chemistry", "application_year": "114", "application_semester": "2"},
        "award-evidence": {"record_id": "award-evidence", "evidence_state": "VERIFIED", "authority": "教務處", "source_reference": "official:award", "record_type": "MINOR_AWARD", "admission_cohort": "114", "target_program": "apc", "target_track": "chemistry"},
    }

    def resolver(record_id):
        return records.get(record_id)

    approved = evaluate(
        _minor_request(
            target_curriculum_id="minor:115:apc:chemistry",
            target_curriculum_evidence_id="target-evidence",
            application_year="114",
            application_semester="2",
            application_status="已申請",
            department_decision_evidence_id="department-evidence",
            registrar_registration_evidence_id="registrar-evidence",
            formal_award_evidence_id="award-evidence",
        ),
        evidence_resolver=resolver,
    )
    approved_decisions = approved.as_dict()["decisions"]
    # These records used to be treated as positive solely because their
    # ``record_type`` looked official.  They are intentionally unbound to a
    # student and omit explicit decision states, so the safe result is UNKNOWN.
    assert approved_decisions["minor_application_or_qualification"]["status"] == "UNKNOWN"
    assert approved_decisions["formal_minor_award"]["status"] == "UNKNOWN"
    assert approved_decisions["minor_coursework_completion"]["status"] != "PASS"

    valid_records = {
        "target-evidence": records["target-evidence"],
        "department-evidence": {
            **records["department-evidence"],
            "subject_ref": "subject-current",
            "decision": "APPROVED",
        },
        "registrar-evidence": {
            **records["registrar-evidence"],
            "subject_ref": "subject-current",
            "registration_status": "REGISTERED",
        },
        "award-evidence": {
            **records["award-evidence"],
            "subject_ref": "subject-current",
            "application_term": "114-2",
            "award_state": "GRANTED",
        },
    }

    def valid_resolver(record_id):
        return valid_records.get(record_id)

    verified = evaluate(
        _minor_request(
            target_curriculum_id="minor:115:apc:chemistry",
            target_curriculum_evidence_id="target-evidence",
            application_year="114",
            application_semester="2",
            application_status="已申請",
            subject_ref="subject-current",
            department_decision_evidence_id="department-evidence",
            registrar_registration_evidence_id="registrar-evidence",
            formal_award_evidence_id="award-evidence",
        ),
        evidence_resolver=valid_resolver,
    )
    verified_decisions = verified.as_dict()["decisions"]
    assert verified_decisions["minor_application_or_qualification"]["status"] == "PASS"
    assert verified_decisions["formal_minor_award"]["status"] == "PASS"
    assert verified_decisions["minor_coursework_completion"]["status"] != "PASS"


def test_minor_apc115_uses_actual_exclusive_allocations_for_all_lecture_and_lab_rows():
    rows = tuple(
        _row(name, code=f"S-{index}", credits=credits, course_type=course_type)
        for index, (name, credits, course_type) in enumerate(
            (
                ("普通物理學(一)", 3, "lecture"),
                ("普通化學(一)", 3, "lecture"),
                ("普通化學實驗(一)", 1, "lab"),
                ("微積分(一)", 3, "lecture"),
                ("普通物理學(二)", 3, "lecture"),
                ("普通化學(二)", 3, "lecture"),
                ("普通化學實驗(二)", 1, "lab"),
                ("微積分(二)", 3, "lecture"),
            )
        )
    )
    request = _minor_request(
        year="115",
        program="apc",
        track="chemistry",
        rows=rows,
        target_curriculum_evidence_id="minor-target-version",
        application_year="114",
        application_semester="2",
    )
    records = {
        "minor-target-version": {
            "record_id": "minor-target-version",
            "record_type": "CURRICULUM_APPLICABILITY",
            "evidence_state": "VERIFIED",
            "authority": "教務處",
            "source_reference": "official:minor-target-version",
            "curriculum_id": "minor:115:apc:chemistry",
            "admission_cohort": "114",
            "target_program": "apc",
            "target_track": "chemistry",
            "application_year": "114",
            "application_semester": "2",
        }
    }

    def resolver(record_id):
        return records.get(record_id)

    unbound = evaluate(request, evidence_resolver=resolver)
    attempts_by_name = {attempt.course_name: attempt.attempt_id for attempt in unbound.attempts}
    requirements_by_name = {
        requirement.name: requirement.requirement_id
        for requirement in unbound.requirements
        if requirement.requirement_id.startswith("minor:")
    }
    for index, (name, attempt_id) in enumerate(sorted(attempts_by_name.items())):
        record_id = f"minor-equivalency-{index}"
        records[record_id] = {
            "record_id": record_id,
            "record_type": "EQUIVALENCY_RECORD",
            "evidence_state": "VERIFIED",
            "decision": "APPROVED",
            "authority": "物化系",
            "source_reference": "official:minor-equivalency",
            "source_attempt_id": attempt_id,
            "target_requirement_id": requirements_by_name[name],
            "approved_credits": next(
                requirement.credits_required
                for requirement in unbound.requirements
                if requirement.requirement_id == requirements_by_name[name]
            ),
        }
    bound = evaluate(
        replace(
            request,
            equivalency_evidence_ids=tuple(
                record_id for record_id in records if record_id.startswith("minor-equivalency-")
            ),
        ),
        evidence_resolver=resolver,
    )
    payload = bound.as_dict()
    target_results = [
        result
        for result in bound.allocation.requirement_results
        if result.requirement_id.startswith("minor:")
    ]
    target_portions = [
        portion
        for allocation in bound.allocation.allocations
        for portion in allocation.portions
        if portion.requirement_id.startswith("minor:")
    ]
    assert payload["decisions"]["minor_coursework_completion"]["status"] == "PASS"
    assert target_results and all(result.status == "PASS" for result in target_results)
    assert sum((portion.credits for portion in target_portions), 0) == 20
    assert target_portions and all(portion.allocation_kind == "EXCLUSIVE" for portion in target_portions)
    assert payload["statistics"]["minor_credits"] == "20"
    assert not payload["allocation"]["shadow_allocations"]
    assert "MINOR_SHARED_CREDIT_FORBIDDEN" not in payload["blockers"]


def test_math113_official_equivalencies_apply_to_current_elective_pool():
    safe_rows = tuple(
        _row(name, code=f"M-{index}", credits=3)
        for index, name in enumerate(
            ("線性代數(一)", "線性代數(二)", "集合與邏輯", "Matlab程式設計")
        )
    )
    with_conflict = (*safe_rows, _row("數學導論", code="M-intro", credits=3))
    request = _minor_request(
        year="113",
        program="math",
        track="department",
        rows=with_conflict,
        target_curriculum_evidence_id="math113-target-version",
        application_year="114",
        application_semester="1",
    )
    records = {
        "math113-target-version": {
            "record_id": "math113-target-version",
            "record_type": "CURRICULUM_APPLICABILITY",
            "evidence_state": "VERIFIED",
            "authority": "教務處",
            "source_reference": "official:math113-target-version",
            "curriculum_id": "minor:113:math:department",
            "admission_cohort": "114",
            "target_program": "math",
            "application_year": "114",
            "application_semester": "1",
        }
    }

    def resolver(record_id):
        return records.get(record_id)

    unbound = evaluate(request, evidence_resolver=resolver)
    attempt_ids = {attempt.course_name: attempt.attempt_id for attempt in unbound.attempts}
    other_requirement = next(
        requirement for requirement in unbound.requirements if requirement.name == "數學表列選修"
    )
    for index, name in enumerate(("線性代數(一)", "線性代數(二)", "集合與邏輯")):
        record_id = f"math113-equivalency-{index}"
        records[record_id] = {
            "record_id": record_id,
            "record_type": "EQUIVALENCY_RECORD",
            "evidence_state": "VERIFIED",
            "decision": "APPROVED",
            "authority": "數學系",
            "source_reference": "official:math113-minor-equivalency",
            "source_attempt_id": attempt_ids[name],
            "target_requirement_id": other_requirement.requirement_id,
            "approved_credits": 3,
        }
    records["math113-equivalency-software"] = {
        "record_id": "math113-equivalency-software",
        "record_type": "EQUIVALENCY_RECORD",
        "evidence_state": "VERIFIED",
        "decision": "APPROVED",
        "authority": "數學系",
        "source_reference": "official:math113-minor-equivalency",
        "source_attempt_id": attempt_ids["Matlab程式設計"],
        "target_requirement_id": other_requirement.requirement_id,
        "approved_credits": 3,
    }
    bound = evaluate(
        replace(
            request,
            equivalency_evidence_ids=tuple(
                record_id for record_id in records if record_id.startswith("math113-equivalency")
            ),
        ),
        evidence_resolver=resolver,
    )
    payload = bound.as_dict()
    assert "MINOR_SOURCE_CONFLICT_USED" not in payload["blockers"]
    bound_results = {
        result.requirement_id: result
        for result in bound.allocation.requirement_results
        if result.requirement_id.startswith("minor:")
    }
    assert bound_results[other_requirement.requirement_id].effective_credits >= 12
    assert bound.allocation.credit_conservation


def test_nonminor_minor_decisions_are_not_applicable_and_no_shared_minor_shadow_credit():
    snapshot = evaluate(_request(rows=(_row("X", code="X"),), program_type="單主修"))
    decisions = snapshot.as_dict()["decisions"]
    assert decisions["minor_application_or_qualification"]["status"] == "NOT_APPLICABLE"
    assert decisions["minor_coursework_completion"]["status"] == "NOT_APPLICABLE"
    assert decisions["formal_minor_award"]["status"] == "NOT_APPLICABLE"
    assert not any(item.get("target_owner") == "MINOR" for item in snapshot.as_dict()["bindings"] if isinstance(item, dict))


def test_minor_snapshot_projection_renderer_and_exports_share_decisions_and_provenance():
    snapshot = evaluate(_minor_request(target_curriculum_id="minor:114:apc:chemistry"))
    payload = snapshot.as_dict()
    projection = build_snapshot_projection(snapshot)
    export_payload = build_snapshot_export_payload(snapshot)
    audit = json.loads(export_snapshot_audit_json(snapshot).decode("utf-8"))
    csv_rows = list(csv.DictReader(io.StringIO(export_snapshot_csv(snapshot).decode("utf-8-sig"))))
    html = render_snapshot(snapshot)
    assert payload["snapshot_id"] == projection["snapshot_id"] == export_payload["snapshot_id"] == audit["snapshot_id"]
    assert projection["decisions"] == export_payload["decisions"] == audit["decisions"]
    assert "輔系申請與資格" in html
    assert "minor_application_or_qualification" not in html
    assert payload["rule_provenance"]
    assert csv_rows and all(row["snapshot_id"] == payload["snapshot_id"] for row in csv_rows)
    pdf = export_snapshot_pdf(snapshot)
    assert pdf.startswith(b"%PDF")
