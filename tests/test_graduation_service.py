"""Contract tests for the production evaluation service.

These tests deliberately exercise the public boundary rather than the legacy
Streamlit entry point.  A request is made from normalized, confirmed rows;
all rule/evidence decisions then flow through one immutable snapshot.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from course_input_adapter import adapt_legacy_result
from curriculum_registry import get_curriculum
from graduation_service import (
    EvaluationRequest,
    _compile_attempts,
    _compile_non_credit_results,
    _compile_requirements,
    _safe_curriculum,
    evaluate,
)
from input_confirmation import (
    NormalizedCourseRow,
    confirm_confirmation,
    fingerprint_course_rows,
    start_confirmation,
)


def _row(
    code: str = "X-001",
    name: str = "普通物理學(一)",
    *,
    credits: float = 3,
    earned: float = 3,
    status: str = "已修",
    term: str = "114-1",
    course_type: str = "lecture",
) -> NormalizedCourseRow:
    parsed = start_confirmation(
        [
            {
                "course_code": code,
                "course_name": name,
                "credits": credits,
                "earned_credits": earned,
                "status": status,
                "term": term,
                "course_type": course_type,
            }
        ]
    )
    assert parsed.valid
    return parsed.rows[0]


def _confirmed(*rows: NormalizedCourseRow):
    return confirm_confirmation(
        start_confirmation([row.as_dict() for row in rows]),
        fingerprint_course_rows(rows),
    )


def _request(*, confirmed: bool = True, rows: tuple[NormalizedCourseRow, ...] = ()) -> EvaluationRequest:
    confirmation = _confirmed(*rows)
    return EvaluationRequest(
        admission_cohort="114",
        primary_curriculum_id="primary:114:apc:chemistry",
        confirmed_course_rows=confirmation.rows,
        confirmed_course_fingerprint=confirmation.fingerprint if confirmed else "stale-fingerprint",
        transcript_confirmed=confirmed,
        program_type="單主修",
    )


def test_request_boundary_only_accepts_normalized_rows_and_redacts_forbidden_fields():
    row = _row()
    request = EvaluationRequest(
        admission_cohort="114",
        primary_curriculum_id="primary:114:apc:chemistry",
        confirmed_course_rows=(row,),
        confirmed_course_fingerprint=fingerprint_course_rows((row,)),
        transcript_confirmed=True,
    )

    assert "student_id" not in request.as_dict()
    assert "student_name" not in request.as_dict()
    assert "password" not in request.as_dict()
    assert request.as_dict()["confirmed_course_fingerprint"] == request.confirmed_course_fingerprint

    with pytest.raises((TypeError, ValueError)):
        EvaluationRequest(
            admission_cohort="114",
            primary_curriculum_id="primary:114:apc:chemistry",
            confirmed_course_rows=({"course_code": "secret"},),  # type: ignore[arg-type]
        )


def test_unconfirmed_or_stale_rows_are_not_released_as_attempts_or_pass():
    row = _row()
    snapshot = evaluate(_request(confirmed=False, rows=(row,)))

    assert snapshot.attempts == ()
    assert snapshot.verdict == "UNKNOWN"
    assert not snapshot.can_pass
    assert "INPUT_CONFIRMATION_REQUIRED" in snapshot.blockers
    assert snapshot.as_dict()["input_confirmation"]["state"] != "CONFIRMED"


def test_registry_partial_coverage_is_visible_and_cannot_be_promoted_to_pass(monkeypatch):
    # Keep this safety contract independent of real handbooks being completed.
    import curriculum_registry

    partial = get_curriculum("primary:114:apc:chemistry")
    partial["coverage_state"] = "PARTIAL"
    partial["automation_sufficiency"] = "PARTIAL"
    monkeypatch.setitem(curriculum_registry._REGISTRY, partial["curriculum_id"], partial)
    row = _row()
    snapshot = evaluate(_request(rows=(row,)))

    assert snapshot.verdict == "UNKNOWN"
    assert not snapshot.can_pass
    assert snapshot.rule_resolution["status"] in {"MANUAL_REVIEW", "CONFLICTED"}
    assert any("CURRICULUM" in blocker or "MANUAL" in blocker for blocker in snapshot.blockers)
    assert snapshot.rule_provenance
    assert all("raw_blob" not in str(item).lower() for item in snapshot.rule_provenance)


def test_target_version_is_independent_and_unscoped_selection_stays_unknown():
    row = _row()
    confirmation = _confirmed(row)
    request = EvaluationRequest(
        admission_cohort="112",
        primary_curriculum_id="primary:112:earth:earth_environment",
        confirmed_course_rows=confirmation.rows,
        confirmed_course_fingerprint=confirmation.fingerprint,
        transcript_confirmed=True,
        program_type="雙主修",
        target_program="資科",
        target_curriculum_id="target:double_major:114:cs",
        application_year="112",
        application_semester="2",
        application_status="已申請",
    )

    snapshot = evaluate(request)
    target = snapshot.rule_resolution["dimensions"]["target_curriculum_version"]
    assert target["status"] != "RESOLVED"
    assert target["value"] == "target:double_major:114:cs"
    assert snapshot.decisions["double_major_qualification"]["status"] != "PASS"
    assert snapshot.decisions["formal_double_major_award"]["status"] != "PASS"


def test_self_reported_approval_does_not_upgrade_independent_application_gates():
    row = _row()
    confirmation = _confirmed(row)
    request = EvaluationRequest(
        admission_cohort="114",
        primary_curriculum_id="primary:114:apc:chemistry",
        confirmed_course_rows=confirmation.rows,
        confirmed_course_fingerprint=confirmation.fingerprint,
        transcript_confirmed=True,
        program_type="雙主修",
        target_program="資科",
        target_curriculum_id="target:double_major:114:cs",
        application_term="114-1",
        application_status="已核准",
        school_approval_status="已核准",
        formal_qualification_status="已取得資格",
    )

    snapshot = evaluate(request)
    application = snapshot.decisions["double_major_qualification"]["application"]
    assert application["status"] != "PASS"
    assert snapshot.decisions["double_major_qualification"]["status"] != "PASS"
    assert snapshot.decisions["formal_double_major_award"]["status"] == "UNKNOWN"


def test_opaque_equivalency_evidence_is_required_and_raw_request_mappings_are_ignored():
    row = _row(name="普通物理")
    confirmation = _confirmed(row)
    request = EvaluationRequest(
        admission_cohort="114",
        primary_curriculum_id="primary:114:apc:chemistry",
        confirmed_course_rows=confirmation.rows,
        confirmed_course_fingerprint=confirmation.fingerprint,
        transcript_confirmed=True,
        program_type="雙主修",
        target_program="物化",
        target_track="化學組",
        target_curriculum_id="target:double_major:114:apc:chemistry",
        application_term="114-1",
        equivalency_evidence_ids=("eq-for-ordinary-physics",),
    )

    def resolver(record_id: str):
        assert record_id == "eq-for-ordinary-physics"
        return {
            "record_id": record_id,
            "record_type": "EQUIVALENCY_RECORD",
            "evidence_state": "VERIFIED",
            "authority": "物化系",
            "evidence_reference": "official:eq:114",
            "source_course_id": "X-001",
            "target_course_name": "普通物理學(一)",
            "approved_credits": 3,
            "shared": False,
        }

    snapshot = evaluate(request, evidence_resolver=resolver)
    assert snapshot.bindings
    assert snapshot.bindings[0]["binding_id"].startswith("binding:sha256:")
    assert snapshot.bindings[0]["decision"] == "PENDING"
    assert snapshot.allocation.shadow_allocations == ()
    assert any(item.startswith("EQUIVALENCY_UNRESOLVED:evidence:") for item in snapshot.blockers)
    assert "eq-for-ordinary-physics" not in str(snapshot.bindings)
    assert "student_id" not in str(snapshot)
    assert "raw_blob" not in str(snapshot).lower()


def test_explicit_zero_approved_credits_does_not_fallback_to_legacy_credits():
    row = _row(name="普通物理")
    confirmation = _confirmed(row)
    request = EvaluationRequest(
        admission_cohort="114",
        primary_curriculum_id="primary:114:apc:chemistry",
        confirmed_course_rows=confirmation.rows,
        confirmed_course_fingerprint=confirmation.fingerprint,
        transcript_confirmed=True,
        program_type="雙主修",
        target_program="物化",
        target_track="化學組",
        target_curriculum_id="target:double_major:114:apc:chemistry",
        application_term="114-1",
        equivalency_evidence_ids=("eq-zero-approved-credits",),
    )

    def resolver(record_id: str):
        assert record_id == "eq-zero-approved-credits"
        return {
            "record_id": record_id,
            "record_type": "EQUIVALENCY_RECORD",
            "evidence_state": "VERIFIED",
            "decision": "APPROVED",
            "authority": "物化系",
            "evidence_reference": "official:eq:114-zero",
            "source_course_id": "X-001",
            "target_requirement_id": "target:target:double_major:114:apc:chemistry:apc.dm.114.chemistry.physics_1",
            "approved_credits": 0,
            "credits": 3,
            "shared": False,
        }

    snapshot = evaluate(request, evidence_resolver=resolver)

    assert snapshot.bindings
    assert snapshot.bindings[0]["approved_credits"] == "0"
    assert snapshot.bindings[0]["source_attempt_id"] == ""
    assert snapshot.bindings[0]["target_requirement_id"] == ""
    assert snapshot.allocation.shadow_allocations == ()
    assert any(item.startswith("EQUIVALENCY_UNRESOLVED:evidence:") for item in snapshot.blockers)


def test_unresolved_equivalency_is_a_blocker_even_when_direct_course_credit_exists():
    row = _row(name="普通物理學(一)")
    confirmation = _confirmed(row)
    request = EvaluationRequest(
        admission_cohort="114",
        primary_curriculum_id="primary:114:apc:chemistry",
        confirmed_course_rows=confirmation.rows,
        confirmed_course_fingerprint=confirmation.fingerprint,
        transcript_confirmed=True,
        equivalency_evidence_ids=("missing-equivalency",),
    )

    snapshot = evaluate(request)
    assert snapshot.verdict != "PASS"
    assert any(item.startswith("EQUIVALENCY_UNRESOLVED:evidence:") for item in snapshot.blockers)
    assert "missing-equivalency" not in str(snapshot.blockers)


def test_snapshot_is_deterministic_under_course_reordering_and_exposes_shared_metadata():
    rows = (_row("X-001", "普通物理學(一)"), _row("X-002", "普通化學(一)", term="114-2"))
    first = evaluate(_request(rows=rows))
    second = evaluate(_request(rows=tuple(reversed(rows))))

    assert first.snapshot_id == second.snapshot_id
    projected = first.as_dict()
    assert projected["schema_version"]
    assert projected["engine_version"]
    assert projected["decisions"]
    assert projected["statistics"]
    assert "search_complete" in projected
    assert "optimality" in projected
    assert projected["input_confirmation"]["state"] == "CONFIRMED"


def test_service_emits_decision_statistics_v2_without_a_name_inferred_total():
    row = _row()
    snapshot = evaluate(_request(rows=(row,)))

    statistics = snapshot.statistics
    assert statistics["schema_version"] == "decision-statistics.v2"
    assert statistics["credit_ledger"]["additive"] is True
    assert statistics["requirement_metrics"]["additive"] is False
    assert statistics["program_progress"]["primary"]["status"] == snapshot.decisions["primary_graduation"]["status"]
    assert statistics["program_progress"]["primary"]["gate_count"]
    assert "total_graduation_credits" not in statistics
    assert statistics["remediation"]["status"] == "DIRECTION_ONLY"


def test_transcript_category_labels_do_not_block_exact_official_course_identity():
    curriculum = get_curriculum("primary:114:apc:chemistry")
    catalog_row = next(
        row
        for row in curriculum["course_catalog"]
        if row.get("official_course_identity")
        and row.get("credits", 0) > 0
        and row.get("component_type") == "lecture"
    )
    course_code = catalog_row["official_course_identity"]
    course_name = catalog_row["name"]
    credit = catalog_row["credits"]

    for category in ("系必修", "共同選修"):
        adapted = adapt_legacy_result(
            [
                {
                    "course_code": course_code,
                    "name": course_name,
                    "type": category,
                    "academic_year": "114",
                    "semester": "1",
                    "total_credit": credit,
                    "score": "80",
                }
            ]
        )
        assert adapted.valid
        assert adapted.rows[0]["course_type"] == category
        confirmation = confirm_confirmation(adapted.confirmation, adapted.confirmation.fingerprint)
        snapshot = evaluate(
            EvaluationRequest(
                admission_cohort="114",
                primary_curriculum_id="primary:114:apc:chemistry",
                confirmed_course_rows=confirmation.rows,
                confirmed_course_fingerprint=confirmation.fingerprint,
                transcript_confirmed=True,
                confirmation_state="CONFIRMED",
            )
        )
        attempt = next(item for item in snapshot.attempts if item.course_id == course_code)
        assert attempt.identity_status == "VERIFIED"
        assert attempt.course_kind == "LECTURE"
        requirement = next(item for item in snapshot.requirements if course_code in item.eligible_course_ids)
        requirement_result = snapshot.allocation.requirement_for(requirement.requirement_id)
        assert requirement_result is not None
        assert requirement_result.exclusive_credits == Decimal(str(credit))
        assert any(
            portion.requirement_id == requirement.requirement_id
            for allocation in snapshot.allocation.allocations
            for portion in allocation.portions
        )
        assert not any("COMPONENT_UNKNOWN" in blocker for blocker in snapshot.allocation.blockers)


def test_ag102_shape_uses_exact_pool_catalog_without_pdf_course_code_or_department():
    """A verified handbook pool can resolve the real transcript row shape."""

    record = {
        "curriculum_id": "primary:114:ag102:major",
        "coverage_state": "COMPLETE",
        "evidence_state": "VERIFIED",
        "course_catalog": [
            {
                "id": "ag102.core.analysis",
                "name": "分析化學",
                "credits": 3,
                "requirement_type": "named_course",
                "component_type": "lecture",
                "evidence_state": "VERIFIED",
            }
        ],
        "course_pools": [
            {
                "pool_id": "ag102:major:114",
                "year": "114",
                "program": "ag102",
                "scope": "primary",
                "allowed_components": ["lecture"],
                "identity_fields": ["raw_title", "credits", "lecture_or_lab"],
                "evidence_state": "VERIFIED",
                "candidate_courses": [
                    {
                        "course_id": "catalog:ag102:analysis",
                        "name": "分析化學",
                        "credits": 3,
                        "component_type": "lecture",
                        "evidence_state": "VERIFIED",
                    }
                ],
            }
        ],
    }

    requirements, metadata, _provenance = _compile_requirements(record, scope="primary")
    assert len(requirements) == 1
    requirement = requirements[0]
    assert requirement.eligible_pool_ids == ()
    assert requirement.eligible_course_ids == ("catalog:ag102:analysis",)
    assert not any(item.requirement_id.startswith("__pool_candidate__") for item in requirements)

    row = _row(code="", name="分析化學", credits=3, course_type="必")
    attempts, _safe_rows = _compile_attempts((row,), metadata)
    attempt = attempts[0]
    assert attempt.identity_status == "VERIFIED"
    assert attempt.pool_ids == ("ag102:major:114",)
    assert attempt.pool_evidence_state == "VERIFIED"
    assert attempt.course_kind == "LECTURE"

    from allocation_engine import allocate_credits

    allocation = allocate_credits(attempts, requirements)
    assert allocation.status == "PASS"
    assert allocation.pass_eligible
    assert allocation.credit_conservation


def test_unimplemented_quota_is_unknown_with_explicit_rule_reason():
    record = {
        "curriculum_id": "target:double_major:114:ag102",
        "coverage_state": "PARTIAL",
        "evidence_state": "VERIFIED",
        "course_catalog": [
            {
                "id": "ag102:quota",
                "name": "專業選修額度",
                "credits": 6,
                "requirement_type": "credit_quota",
            }
        ],
    }
    requirements, metadata, _provenance = _compile_requirements(record, scope="target")
    assert len(requirements) == 1
    assert metadata[requirements[0].requirement_id]["generic"]

    from allocation_engine import allocate_credits
    from graduation_service import _with_generic_unknown

    allocation = _with_generic_unknown(allocate_credits((), requirements), {requirements[0].requirement_id})
    assert allocation.status == "UNKNOWN"
    assert allocation.feasibility == "UNKNOWN"
    assert not allocation.feasible_witness
    assert any(item.startswith("RULE_NOT_IMPLEMENTED:") for item in allocation.blockers)


def test_explicit_wrong_component_does_not_verify_exact_official_course_identity():
    curriculum = get_curriculum("primary:114:apc:chemistry")
    catalog_row = next(
        row
        for row in curriculum["course_catalog"]
        if row.get("official_course_identity")
        and row.get("credits", 0) > 0
        and row.get("component_type") == "lecture"
    )
    course_code = catalog_row["official_course_identity"]
    course_name = catalog_row["name"]
    credit = catalog_row["credits"]
    adapted = adapt_legacy_result(
        [
            {
                "course_code": course_code,
                "name": course_name,
                "type": "lab",
                "academic_year": "114",
                "semester": "1",
                "total_credit": credit,
                "score": "80",
            }
        ]
    )
    assert adapted.valid
    confirmation = confirm_confirmation(adapted.confirmation, adapted.confirmation.fingerprint)
    snapshot = evaluate(
        EvaluationRequest(
            admission_cohort="114",
            primary_curriculum_id="primary:114:apc:chemistry",
            confirmed_course_rows=confirmation.rows,
            confirmed_course_fingerprint=confirmation.fingerprint,
            transcript_confirmed=True,
            confirmation_state="CONFIRMED",
        )
    )
    attempt = next(item for item in snapshot.attempts if item.course_id == course_code)
    assert attempt.identity_status == "UNKNOWN"
    assert attempt.course_kind == "LAB"
    requirement = next(item for item in snapshot.requirements if course_code in item.eligible_course_ids)
    assert not snapshot.allocation.allocation_for(requirement.requirement_id)


def test_category_only_exact_identity_requires_unique_catalog_component():
    row = _row(code="OFFICIAL-1", name="正式課程", course_type="系必修")
    metadata = {
        "lecture": {
            "requirement_id": "requirement:lecture",
            "course_name": "正式課程",
            "official_course_identity": "OFFICIAL-1",
            "course_kind": "LECTURE",
            "component_type": "lecture",
            "required_identity_dimensions": ("course_code", "course_kind"),
        },
        "lab": {
            "requirement_id": "requirement:lab",
            "course_name": "正式課程",
            "official_course_identity": "OFFICIAL-1",
            "course_kind": "LAB",
            "component_type": "lab",
            "required_identity_dimensions": ("course_code", "course_kind"),
        },
    }
    attempts, _safe_rows = _compile_attempts((row,), metadata)
    assert attempts[0].identity_status == "UNKNOWN"
    assert attempts[0].course_kind == "UNKNOWN"


@pytest.mark.parametrize("malformed_component", ("collaboration", "syllabus"))
def test_service_does_not_treat_component_substrings_as_catalog_identity(malformed_component):
    row = _row(code="OFFICIAL-1", name="正式課程", course_type=malformed_component)
    metadata = {
        "lecture": {
            "requirement_id": "requirement:lecture",
            "course_name": "正式課程",
            "official_course_identity": "OFFICIAL-1",
            "course_kind": "LECTURE",
            "component_type": "lecture",
            "required_identity_dimensions": ("course_code", "course_kind"),
        },
    }

    attempts, _safe_rows = _compile_attempts((row,), metadata)

    assert attempts[0].identity_status == "UNKNOWN"
    assert attempts[0].course_kind == "UNKNOWN"


def test_verified_open_policy_uses_exact_catalog_rows_and_observes_science_subset():
    from allocation_engine import allocate_credits

    policy = {
        "policy_id": "free-policy-115",
        "revision": "115.1",
        "applies_to": {
            "curriculum_versions": ("115",),
            "program_slugs": ("earth",),
            "track_slugs": ("earth_environment",),
            "roles": ("primary",),
        },
        "predicate": {
            "kind": "exclusive_open_elective",
            "minimum_credits": 15,
            "subset_constraints": (
                {
                    "constraint_id": "science-college-minimum",
                    "membership_id": "science_college",
                    "minimum_credits": 3,
                    "source_reference": "official:science",
                },
            ),
        },
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "source_reference": "official:free-policy",
    }
    record = {
        "curriculum_id": "primary:115:earth:synthetic",
        "version": "115",
        "curriculum_version": "115",
        "program_slug": "earth",
        "track_slug": "earth_environment",
        "kind": "primary",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "course_pools": (
            {"pool_id": "free", "selection_rule": "official_open_elective_policy", "policy": policy},
            {
                "pool_id": "catalog",
                "selection_rule": "exact_title_credit_component",
                "candidate_courses": tuple(
                    {
                        "course_id": f"official-{index}",
                        "course_name": f"Catalog Course {index}",
                        "credits": 3,
                        "component_type": "lecture",
                        "membership_ids": ("science_college",) if index == 0 else (),
                        "evidence_state": "VERIFIED",
                    }
                    for index in range(5)
                ),
            },
        ),
        "course_catalog": (
            {
                "id": "free-total",
                "name": "自由選修",
                "credits": 15,
                "requirement_type": "course_pool",
                "eligible_pool_ids": ("free",),
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
            },
        ),
    }
    requirements, metadata, _provenance = _compile_requirements(record, scope="primary")
    rows = tuple(
        NormalizedCourseRow(
            course_code="",
            course_name=f"Catalog Course {index}",
            credits=3,
            earned_credits=3,
            status="COMPLETED",
            term=f"114-{index + 1}",
            course_type="選",
        )
        for index in range(5)
    )
    attempts, _safe_rows = _compile_attempts(rows, metadata)
    allocation = allocate_credits(attempts, requirements, search_limit=100000)

    assert requirements[0].eligible_pool_ids == ("free",)
    assert metadata[requirements[0].requirement_id]["policy_state"] == "VERIFIED"
    assert all(attempt.identity_status == "VERIFIED" for attempt in attempts)
    assert all(
        any(record[0] == "free" and record[1] == "VERIFIED" for record in attempt.pool_membership_evidence)
        for attempt in attempts
    )
    assert allocation.status == "PASS"
    assert allocation.credit_conservation
    assert allocation.recognized_credits == Decimal("15")
    assert allocation.subset_results[0]["status"] == "PASS"
    assert allocation.subset_results[0]["verified_credits"] == Decimal("3")


def test_open_policy_exclusion_is_source_backed_and_does_not_accept_ge_category_hint():
    from allocation_engine import allocate_credits

    policy = {
        "policy_id": "free-policy-with-ge-exclusion",
        "revision": "115.1",
        "applies_to": {
            "curriculum_versions": ("115",),
            "program_slugs": ("earth",),
            "track_slugs": ("earth_environment",),
            "roles": ("primary",),
        },
        "predicate": {
            "kind": "exclusive_open_elective",
            "minimum_credits": 3,
            "exclude_course_types": ("通識",),
        },
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "source_reference": "official:free-exclusion",
    }
    record = {
        "curriculum_id": "primary:115:earth:synthetic-exclusion",
        "version": "115",
        "curriculum_version": "115",
        "program_slug": "earth",
        "track_slug": "earth_environment",
        "kind": "primary",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "course_pools": (
            {"pool_id": "free", "selection_rule": "official_open_elective_policy", "policy": policy},
            {
                "pool_id": "catalog",
                "selection_rule": "exact_title_credit_component",
                "candidate_courses": (
                    {
                        "course_id": "official-ge-course",
                        "course_name": "Official General Course",
                        "credits": 3,
                        "component_type": "lecture",
                        "evidence_state": "VERIFIED",
                    },
                ),
            },
        ),
        "course_catalog": (
            {
                "id": "free-total",
                "name": "自由選修",
                "credits": 3,
                "requirement_type": "course_pool",
                "eligible_pool_ids": ("free",),
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
            },
        ),
    }
    requirements, metadata, _provenance = _compile_requirements(record, scope="primary")
    rows = (
        NormalizedCourseRow(
            course_code="",
            course_name="Official General Course",
            credits=3,
            earned_credits=3,
            status="COMPLETED",
            term="115-1",
            course_type="通識",
        ),
    )
    attempts, _safe_rows = _compile_attempts(rows, metadata)
    allocation = allocate_credits(attempts, requirements, search_limit=100000)

    assert allocation.recognized_credits == Decimal("0")
    assert allocation.status == "FAIL"
    assert not any(
        record[0] == "free" and record[1] == "VERIFIED"
        for record in attempts[0].pool_membership_evidence
    )


def test_non_credit_pe_gate_requires_distinct_official_activity_and_terms():
    from allocation_engine import CourseAttempt

    requirement = {
        "requirement_id": "physical-education",
        "name": "體育",
        "kind": "DISTINCT_TERM_ITEM_COUNT",
        "requirement_type": "non_credit",
        "credits": 0,
        "is_zero_credit": True,
        "required_count": 4,
        "required_hours": 8,
        "hours_per_completion": 2,
        "max_completions_per_term": 1,
        "distinct_term_required": True,
        "distinct_activity_required": True,
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "scope_state": "VERIFIED",
        "match": {"exact_titles": ("體育",), "official_aliases": ("羽球", "籃球", "排球", "游泳")},
        "official_activity_aliases": {
            "badminton": {"canonical_id": "badminton", "aliases": ("羽球",)},
            "basketball": {"canonical_id": "basketball", "aliases": ("籃球",)},
            "volleyball": {"canonical_id": "volleyball", "aliases": ("排球",)},
            "swimming": {"canonical_id": "swimming", "aliases": ("游泳",)},
        },
        "completion_statuses": ("COMPLETED",),
    }

    attempts = tuple(
        CourseAttempt(
            attempt_id=f"pe-{index}",
            course_id=f"pe-{index}",
            course_name=name,
            credits=0,
            earned_credits=0,
            academic_term=term,
            status="PASS",
            course_kind="UNKNOWN",
        )
        for index, (name, term) in enumerate(
            (("羽球", "114-1"), ("籃球", "114-2"), ("排球", "115-1"), ("游泳", "115-2"))
        )
    )
    result = _compile_non_credit_results({"non_credit_requirements": (requirement,)}, attempts, scope="primary")[0]
    assert result.status == "PASS"
    assert result.completed_count == 4
    assert result.completed_hours == Decimal("8")
    assert result.affects_credit_ledger is False

    duplicate_attempts = tuple(
        CourseAttempt(
            attempt_id=f"pe-duplicate-{index}",
            course_id=f"pe-duplicate-{index}",
            course_name=name,
            credits=0,
            earned_credits=0,
            academic_term=term,
            status="PASS",
            course_kind="UNKNOWN",
        )
        for index, (name, term) in enumerate(
            (("羽球", "114-1"), ("羽球", "114-2"), ("排球", "115-1"), ("游泳", "115-2"))
        )
    )
    duplicate_result = _compile_non_credit_results(
        {"non_credit_requirements": (requirement,)},
        duplicate_attempts,
        scope="primary",
    )[0]
    assert duplicate_result.status == "FAIL"
    assert duplicate_result.completed_count == 3

    generic_attempts = duplicate_attempts[:0] + tuple(
        CourseAttempt(
            attempt_id=f"pe-generic-{index}",
            course_id=f"pe-generic-{index}",
            course_name=name,
            credits=0,
            earned_credits=0,
            academic_term=term,
            status="PASS",
            course_kind="UNKNOWN",
        )
        for index, (name, term) in enumerate(
            (("羽球", "114-1"), ("籃球", "114-2"), ("排球", "115-1"), ("體育", "115-2"))
        )
    )
    generic_result = _compile_non_credit_results(
        {"non_credit_requirements": (requirement,)},
        generic_attempts,
        scope="primary",
    )[0]
    assert generic_result.status == "UNKNOWN"
    assert generic_result.completed_count == 3


def test_it_direct_completion_uses_official_pool_membership_for_no_code_rows():
    """The 112-1 IT gate observes every confirmed attempt, including unallocated rows."""

    record = {
        "curriculum_id": "primary:112:earth:it-gate",
        "version": "112",
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "department",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "course_pools": (
            {
                "pool_id": "it-list:112-1",
                "allowed_components": ("lecture",),
                "identity_fields": ("raw_title", "credits", "lecture_or_lab"),
                "evidence_state": "VERIFIED",
                "source_reference": "official:it-list-112-1",
                "candidate_courses": (
                    {
                        "course_id": "it-112-1",
                        "name": "資料視覺化",
                        "credits": 2,
                        "component_type": "lecture",
                        "membership_ids": ("university_it_direct_completion",),
                        "membership_source_reference": "official:it-list-112-1",
                        "evidence_state": "VERIFIED",
                    },
                ),
            },
        ),
    }
    requirement = {
        "requirement_id": "it-direct",
        "name": "資訊應用與設計",
        "kind": "OFFICIAL_LISTED_COURSE_COMPLETION",
        "requirement_type": "non_credit",
        "credits": 0,
        "required_completions": 1,
        "min_earned_credits_per_completion": 2,
        "membership_id": "university_it_direct_completion",
        "term_bound": "VERIFIED",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "scope_state": "VERIFIED",
    }
    _specs, metadata, _provenance = _compile_requirements(record, scope="primary")
    rows = (
        _row(code="", name="資料視覺化", credits=2, earned=2, term="112-1", course_type="必"),
    )
    attempts, _safe_rows = _compile_attempts(rows, metadata)
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.identity_status == "VERIFIED"
    assert attempt.curriculum_version == "112"
    assert any(
        item[0] == "university_it_direct_completion"
        and item[1] == "VERIFIED"
        and item[2] == "official:it-list-112-1"
        for item in attempt.pool_membership_evidence
    )

    result = _compile_non_credit_results(
        {**record, "non_credit_requirements": (requirement,)},
        attempts,
        scope="primary",
    )[0]

    assert result.status == "PASS"
    assert result.completed_count == 1
    assert result.matched_attempt_ids == (attempt.attempt_id,)
    assert result.affects_credit_ledger is False


def test_evaluate_keeps_it_direct_completion_separate_from_unallocated_credit(monkeypatch):
    """A full service evaluation can pass the IT gate without spending its course twice."""

    record = {
        "curriculum_id": "primary:112:earth:it-service",
        "version": "112",
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "department",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "course_catalog": (
            {
                "id": "core-112",
                "name": "核心課程",
                "official_course_identity": "core-112",
                "credits": 3,
                "requirement_type": "named_course",
                "component_type": "lecture",
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
            },
        ),
        "course_pools": (
            {
                "pool_id": "it-list:112-1",
                "allowed_components": ("lecture",),
                "identity_fields": ("raw_title", "credits", "lecture_or_lab"),
                "evidence_state": "VERIFIED",
                "source_reference": "official:it-list-112-1",
                "candidate_courses": (
                    {
                        "course_id": "it-112-1",
                        "name": "資料視覺化",
                        "credits": 2,
                        "component_type": "lecture",
                        "membership_ids": ("university_it_direct_completion",),
                        "membership_source_reference": "official:it-list-112-1",
                        "evidence_state": "VERIFIED",
                    },
                ),
            },
        ),
        "non_credit_requirements": (
            {
                "requirement_id": "it-direct",
                "name": "資訊應用與設計",
                "kind": "OFFICIAL_LISTED_COURSE_COMPLETION",
                "requirement_type": "non_credit",
                "credits": 0,
                "required_completions": 1,
                "min_earned_credits_per_completion": 2,
                "membership_id": "university_it_direct_completion",
                "term_bound": "VERIFIED",
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
                "automatic_decision": True,
                "scope_state": "VERIFIED",
            },
        ),
    }
    monkeypatch.setattr("graduation_service.get_curriculum", lambda _curriculum_id: record)
    monkeypatch.setattr(
        "graduation_service.resolve_rule_context",
        lambda _request, *, evidence_resolver=None: {
            "status": "RESOLVED",
            "state": "RESOLVED",
            "can_pass": True,
            "primary_curriculum": record,
            "dimensions": {
                "primary_curriculum": {
                    "status": "RESOLVED",
                    "state": "RESOLVED",
                    "curriculum": record,
                },
                "target_curriculum_version": {"status": "NOT_APPLICABLE", "state": "NOT_APPLICABLE"},
            },
            "blocker_codes": (),
            "warnings": (),
        },
    )
    rows = (
        _row(code="core-112", name="核心課程", credits=3, earned=3, term="112-1", course_type="lecture"),
        _row(code="", name="資料視覺化", credits=2, earned=2, term="112-1", course_type="必"),
    )
    request = EvaluationRequest(
        admission_cohort="112",
        primary_curriculum_id=record["curriculum_id"],
        confirmed_course_rows=rows,
        confirmed_course_fingerprint=fingerprint_course_rows(rows),
        transcript_confirmed=True,
        confirmation_state="CONFIRMED",
        search_limit=100000,
    )

    snapshot = evaluate(request)

    assert snapshot.verdict == "PASS"
    assert snapshot.allocation.credit_conservation is True
    assert snapshot.allocation.recognized_credits == Decimal("3")
    assert snapshot.allocation.unallocated_credits == Decimal("2")
    assert snapshot.decisions["primary_graduation"]["non_credit_status"] == "PASS"
    assert snapshot.non_credit_results[0]["status"] == "PASS"
    assert snapshot.non_credit_results[0]["affects_credit_ledger"] is False


def test_it_direct_completion_does_not_combine_one_credit_attempts():
    from allocation_engine import CourseAttempt

    requirement = {
        "requirement_id": "it-direct",
        "name": "資訊應用與設計",
        "kind": "OFFICIAL_LISTED_COURSE_COMPLETION",
        "requirement_type": "non_credit",
        "credits": 0,
        "required_completions": 1,
        "min_earned_credits_per_completion": 2,
        "membership_id": "university_it_direct_completion",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "scope_state": "VERIFIED",
    }

    attempts = tuple(
        CourseAttempt(
            attempt_id=f"it-one-{index}",
            course_id=f"it-one-{index}",
            course_name="官方資訊課程",
            credits=1,
            earned_credits=1,
            academic_term=f"112-{index + 1}",
            status="PASS",
            identity_status="VERIFIED",
            pool_membership_evidence=(
                ("university_it_direct_completion", "VERIFIED", "official:it", "catalog"),
            ),
        )
        for index in range(2)
    )
    result = _compile_non_credit_results(
        {"non_credit_requirements": (requirement,)},
        attempts,
        scope="primary",
    )[0]

    assert result.status == "FAIL"
    assert result.completed_count == 0
    assert result.matched_attempt_ids == ()


def test_it_direct_completion_unknown_membership_or_scope_stays_unknown():
    from allocation_engine import CourseAttempt

    requirement = {
        "requirement_id": "it-direct",
        "name": "資訊應用與設計",
        "kind": "OFFICIAL_LISTED_COURSE_COMPLETION",
        "requirement_type": "non_credit",
        "credits": 0,
        "required_completions": 1,
        "min_earned_credits_per_completion": 2,
        "membership_id": "university_it_direct_completion",
        "term_bound": "VERIFIED",
        "curriculum_version": "112",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "scope_state": "VERIFIED",
    }
    attempt = CourseAttempt(
        attempt_id="it-unknown",
        course_id="it-unknown",
        course_name="可能為資訊課程",
        credits=2,
        earned_credits=2,
        academic_term="112-1",
        status="PASS",
        identity_status="VERIFIED",
        pool_membership_evidence=(
            ("university_it_direct_completion", "UNKNOWN", "official:pending", "catalog"),
        ),
        curriculum_version="112",
    )
    result = _compile_non_credit_results(
        {"non_credit_requirements": (requirement,)},
        (attempt,),
        scope="primary",
    )[0]

    assert result.status == "UNKNOWN"
    assert result.completed_count == 0
    assert any("EVIDENCE" in blocker or "UNKNOWN" in blocker for blocker in result.blockers)


def test_it_direct_completion_requires_exact_bound_waiver_and_cs_can_be_not_applicable():
    requirement = {
        "requirement_id": "it-direct",
        "name": "資訊應用與設計",
        "kind": "OFFICIAL_LISTED_COURSE_COMPLETION",
        "requirement_type": "non_credit",
        "credits": 0,
        "required_completions": 1,
        "min_earned_credits_per_completion": 2,
        "membership_id": "university_it_direct_completion",
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "department",
        "term_bound": "VERIFIED",
        "waiver_allowed": True,
        "waiver_authority_ids": ("official:genedu",),
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "scope_state": "VERIFIED",
    }
    approved = {
        "record_type": "NON_CREDIT_WAIVER_RECORD",
        "record_id": "waiver-it-112",
        "requirement_id": "it-direct",
        "decision": "APPROVED",
        "evidence_state": "VERIFIED",
        "authority": "official:genedu",
        "evidence_reference": "official:waiver-it-112",
        "subject_ref": "subject:test",
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "department",
    }
    waived = _compile_non_credit_results(
        {"version": "112", "non_credit_requirements": (requirement,)},
        (),
        scope="primary",
        waiver_records=(approved,),
        subject_ref="subject:test",
    )[0]
    assert waived.status == "PASS"
    assert waived.waived
    assert waived.completed_count == 0
    assert waived.affects_credit_ledger is False

    wrong_version = {**approved, "curriculum_version": "111"}
    unresolved = _compile_non_credit_results(
        {"version": "112", "non_credit_requirements": (requirement,)},
        (),
        scope="primary",
        waiver_records=(wrong_version,),
        subject_ref="subject:test",
    )[0]
    assert unresolved.status == "FAIL"
    assert not unresolved.waived

    not_applicable = _compile_non_credit_results(
        {
            "non_credit_requirements": (
                {
                    **requirement,
                    "requirement_id": "it-cs",
                    "applicability_state": "NOT_APPLICABLE",
                },
            )
        },
        (),
        scope="primary",
    )[0]
    assert not_applicable.status == "NOT_APPLICABLE"


def test_non_credit_waiver_missing_or_wrong_binding_fields_cannot_pass():
    requirement = {
        "requirement_id": "it-direct",
        "name": "資訊應用與設計",
        "kind": "OFFICIAL_LISTED_COURSE_COMPLETION",
        "requirement_type": "non_credit",
        "credits": 0,
        "required_completions": 1,
        "min_earned_credits_per_completion": 2,
        "membership_id": "university_it_direct_completion",
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "department",
        "term_bound": "VERIFIED",
        "waiver_allowed": True,
        "waiver_authority_ids": ("official:genedu",),
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "scope_state": "VERIFIED",
    }
    approved = {
        "record_type": "NON_CREDIT_WAIVER_RECORD",
        "record_id": "waiver-it-112",
        "requirement_id": "it-direct",
        "decision": "APPROVED",
        "evidence_state": "VERIFIED",
        "authority": "official:genedu",
        "evidence_reference": "official:waiver-it-112",
        "subject_ref": "subject:test",
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "department",
    }

    invalid_records = (
        {**approved, "subject_ref": "subject:other"},
        {**approved, "subject_ref": ""},
        {**approved, "curriculum_version": "111"},
        {key: value for key, value in approved.items() if key != "curriculum_version"},
        {**approved, "program_slug": "apc"},
        {key: value for key, value in approved.items() if key != "program_slug"},
        {**approved, "track_slug": "chemistry"},
        {key: value for key, value in approved.items() if key != "track_slug"},
        {**approved, "authority": "official:department"},
        {key: value for key, value in approved.items() if key != "authority"},
    )
    for record in invalid_records:
        result = _compile_non_credit_results(
            {"version": "112", "non_credit_requirements": (requirement,)},
            (),
            scope="primary",
            waiver_records=(record,),
            subject_ref="subject:test",
        )[0]
        assert result.status != "PASS"
        assert not result.waived


def test_service_snapshot_exposes_non_credit_and_subset_payloads_separately():
    snapshot = evaluate(_request(rows=(_row(),)))
    payload = snapshot.as_dict()

    assert "non_credit_results" in payload
    assert "subset_results" in payload
    assert "subset_results" in payload["allocation"]
    assert isinstance(payload["non_credit_results"], (list, tuple))
    assert all(item["affects_credit_ledger"] is False for item in payload["non_credit_results"])


def test_evaluate_entry_passes_verified_open_policy_for_no_code_rows_and_conserves(monkeypatch):
    """The public service path must carry policy membership into one snapshot."""

    policy = {
        "policy_id": "free.synthetic.115",
        "revision": "115.1",
        "applies_to": {
            "curriculum_versions": ("115",),
            "program_slugs": ("earth",),
            "track_slugs": ("earth_environment",),
            "roles": ("primary",),
        },
        "predicate": {
            "kind": "exclusive_open_elective",
            "minimum_credits": 15,
            "subset_constraints": (
                {"constraint_id": "science", "membership_id": "science_college", "minimum_credits": 3},
            ),
        },
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "source_reference": "official:synthetic-free",
    }
    record = {
        "curriculum_id": "primary:synthetic:earth",
        "version": "115",
        "curriculum_version": "115",
        "program_slug": "earth",
        "track_slug": "earth_environment",
        "kind": "primary",
        "coverage_state": "COMPLETE",
        "evidence_state": "VERIFIED",
        "course_pools": (
            {"pool_id": "free", "selection_rule": "official_open_elective_policy", "policy": policy},
            {
                "pool_id": "catalog",
                "selection_rule": "exact_title_credit_component",
                "candidate_courses": tuple(
                    {
                        "course_id": f"catalog-{index}",
                        "course_name": f"Open Course {index}",
                        "credits": 3,
                        "component_type": "lecture",
                        "membership_ids": ("science_college",) if index == 0 else (),
                        "evidence_state": "VERIFIED",
                    }
                    for index in range(5)
                ),
            },
        ),
        "course_catalog": (
            {
                "id": "free",
                "name": "自由選修",
                "credits": 15,
                "requirement_type": "course_pool",
                "eligible_pool_ids": ("free",),
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
            },
        ),
    }

    monkeypatch.setattr("graduation_service.get_curriculum", lambda _curriculum_id: record)
    monkeypatch.setattr(
        "graduation_service.resolve_rule_context",
        lambda _request, *, evidence_resolver=None: {
            "status": "RESOLVED",
            "state": "RESOLVED",
            "can_pass": True,
            "primary_curriculum": record,
            "dimensions": {
                "primary_curriculum": {"status": "RESOLVED", "state": "RESOLVED", "curriculum": record},
                "target_curriculum_version": {"status": "NOT_APPLICABLE", "state": "NOT_APPLICABLE"},
            },
            "blocker_codes": (),
            "warnings": (),
        },
    )
    rows = tuple(
        NormalizedCourseRow(
            "",
            f"Open Course {index}",
            3,
            3,
            "COMPLETED",
            f"SYN-{index}",
            course_type="選",
        )
        for index in range(5)
    )
    request = EvaluationRequest(
        admission_cohort="115",
        primary_curriculum_id=record["curriculum_id"],
        confirmed_course_rows=rows,
        confirmed_course_fingerprint=fingerprint_course_rows(rows),
        transcript_confirmed=True,
        confirmation_state="CONFIRMED",
        search_limit=100000,
    )

    snapshot = evaluate(request)

    assert snapshot.verdict == "PASS"
    assert snapshot.allocation.status == "PASS"
    assert snapshot.allocation.feasible_witness is True
    assert snapshot.allocation.credit_conservation is True
    assert snapshot.allocation.recognized_credits == Decimal("15")
    assert snapshot.subset_results[0]["status"] == "PASS"


def test_math_secondary_service_requires_composite_membership_and_drops_bare_identity():
    record = {
        "curriculum_id": "target:double_major:111:math",
        "curriculum_version": "111",
        "program_slug": "math",
        "track_slug": "department",
        "kind": "double_major_target",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "course_catalog": (
            {
                "requirement_id": "math-secondary-linear-1",
                "name": "線性代數(一)",
                "credits": 3,
                "official_course_identity": "target:double_major:111:math:linear-1",
                "component_type": "lecture",
                "requirement_type": "named_course",
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
                "source_reference": "handbook:111:math:secondary:linear-1",
            },
        ),
    }
    safe_record = _safe_curriculum(record)
    assert safe_record is not None
    requirements, metadata, _provenance = _compile_requirements(safe_record, scope="target")

    assert len(requirements) == 1
    assert requirements[0].eligible_course_ids == ()
    assert metadata[requirements[0].requirement_id]["math_secondary_composite_required"] is True

    row = _row(code="", name="線性代數(一)", credits=3, term="111-1", course_type="")
    attempts, _safe_rows = _compile_attempts((row,), metadata)
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.identity_status == "VERIFIED"
    assert "target:double_major:111:math:linear-1" not in attempt.pool_ids
    assert "math-secondary:111:線性代數_一" in attempt.pool_ids
    assert "math-secondary:111:eligible-target-credit" in attempt.pool_ids
    assert any(
        item[0] == "math-secondary:111:線性代數_一"
        and item[1] == "VERIFIED"
        and item[3] == "public_catalog"
        for item in attempt.pool_membership_evidence
    )


@pytest.mark.parametrize("curriculum_id", ("primary:111:math", "primary:112:math"))
def test_math_department_policy_constraints_lower_to_owner_requirement(curriculum_id):
    """The registry pool policy must become two executable subsets on one quota."""

    curriculum = _safe_curriculum(get_curriculum(curriculum_id))
    assert curriculum is not None
    requirements, metadata, _provenance = _compile_requirements(curriculum, scope="primary")

    elective = next(item for item in requirements if item.bucket == "math_department_elective")
    constraints = {item["membership_id"]: item for item in elective.subset_constraints}

    assert set(constraints) == {
        f"math_alpha:{curriculum_id.split(':')[1]}",
        "external_department_or_school_professional",
    }
    assert constraints[f"math_alpha:{curriculum_id.split(':')[1]}"]["minimum_credits"] == Decimal("15")
    assert constraints["external_department_or_school_professional"]["maximum_credits"] == Decimal("15")
    assert all(item["observed_requirement_ids"] == (elective.requirement_id,) for item in elective.subset_constraints)
    assert all(item["source_reference"] for item in elective.subset_constraints)
    assert metadata[elective.requirement_id]["subset_constraints"] == elective.subset_constraints


def test_math_department_subsets_reject_missing_alpha_and_external_over_cap():
    """A complete 64-credit pool cannot bypass its minimum or maximum subset."""

    from allocation_engine import CourseAttempt, allocate_credits

    curriculum = _safe_curriculum(get_curriculum("primary:111:math"))
    assert curriculum is not None
    requirements, _metadata, _provenance = _compile_requirements(curriculum, scope="primary")
    elective = next(item for item in requirements if item.bucket == "math_department_elective")
    pool_id = elective.eligible_pool_ids[0]

    def attempt(index, *, alpha=False, external=False):
        evidence = [(pool_id, "VERIFIED", "official:test", "registry")]
        if alpha:
            evidence.append(("math_alpha:111", "VERIFIED", "official:test", "registry"))
        evidence.append(
            (
                "external_department_or_school_professional",
                "VERIFIED" if external else "NOT_MEMBER",
                "official:test",
                "public_catalog" if external else "registry_negative",
            )
        )
        return CourseAttempt(
            attempt_id=f"math-subset-{index}",
            course_id=f"math-subset-course-{index}",
            course_name=f"Math subset course {index}",
            credits=Decimal("4"),
            earned_credits=Decimal("4"),
            academic_term=f"111-{index % 8 + 1}",
            identity_status="VERIFIED",
            course_kind="LECTURE",
            pool_ids=(pool_id,),
            pool_membership_evidence=tuple(evidence),
            status="PASS",
            grade_evidence_state="VERIFIED",
        )

    beta_only = tuple(attempt(index) for index in range(16))
    missing_alpha = allocate_credits(beta_only, (elective,), search_limit=10_000)
    assert missing_alpha.status != "PASS"

    alpha_and_external = tuple(
        attempt(index, alpha=index in range(4, 8), external=index < 4)
        for index in range(16)
    )
    over_cap = allocate_credits(alpha_and_external, (elective,), search_limit=10_000)
    assert over_cap.status != "PASS"
    external_result = next(
        item
        for item in over_cap.subset_results
        if item["membership_id"] == "external_department_or_school_professional"
    )
    assert external_result["status"] == "FAIL"


def test_sanitized_math_candidate_keeps_official_not_member_evidence():
    """A registry negative survives candidate projection and attempt compilation."""

    curriculum = _safe_curriculum(get_curriculum("primary:111:math"))
    assert curriculum is not None
    pool = next(
        item
        for item in curriculum["course_pools"]
        if item.get("bucket") == "math_department_elective"
    )
    candidate = next(
        item
        for item in pool["candidate_courses"]
        if not any("math_alpha:111" in str(subset) for subset in item.get("subset_ids", ()))
    )
    row = _row(code="", name=candidate["name"], credits=float(candidate["credits"]), course_type="")
    _requirements, metadata, _provenance = _compile_requirements(curriculum, scope="primary")
    attempts, _safe_rows = _compile_attempts((row,), metadata)

    assert len(attempts) == 1
    assert (
        "external_department_or_school_professional",
        "NOT_MEMBER",
        "handbook:111:primary:math:catalog:專業領域及其他選修:pool:math_department_elective",
        "registry_negative",
    ) in attempts[0].pool_membership_evidence


def test_raw_registry_math_candidate_negative_reaches_formal_attempt_compiler():
    """The production raw-record path keeps nested Math ownership negatives."""

    record = get_curriculum("primary:111:math")
    pool = next(item for item in record["course_pools"].values() if item.get("bucket") == "math_department_elective")
    candidate = next(
        item
        for item in pool["candidate_courses"]
        if item.get("course_metadata", {}).get("membership_assertions")
    )
    row = _row(code="", name=candidate["name"], credits=float(candidate["credits"]), term="111-1", course_type="")
    _requirements, metadata, _provenance = _compile_requirements(record, scope="primary")
    attempts, _safe_rows = _compile_attempts((row,), metadata)

    assert len(attempts) == 1
    assert any(
        item[0] == "external_department_or_school_professional"
        and item[1] == "NOT_MEMBER"
        and item[3] == "registry_negative"
        for item in attempts[0].pool_membership_evidence
    )


def test_primary_decision_exposes_verified_non_consuming_total_descriptor():
    snapshot = evaluate(_request(rows=(_row(),)))

    descriptor = snapshot.decisions["primary_graduation"]["total_credit_requirement"]
    assert descriptor["required_credits"] == Decimal("128")
    assert descriptor["curriculum_id"] == "primary:114:apc:chemistry"
    assert descriptor["curriculum_version"] == "114"
    assert descriptor["evidence_state"] == "VERIFIED"
    assert descriptor["coverage_state"] == "COMPLETE"
    assert descriptor["source_reference"]
    assert descriptor["authority"] == "PRIMARY_CURRICULUM_REGISTRY"
    assert descriptor["non_consuming"] is True


def test_primary_decision_omits_total_descriptor_without_official_source(monkeypatch):
    import graduation_service

    record = get_curriculum("primary:114:apc:chemistry")
    record["source_reference"] = ""
    monkeypatch.setattr(graduation_service, "get_curriculum", lambda _curriculum_id: record)
    monkeypatch.setattr(
        graduation_service,
        "resolve_rule_context",
        lambda _request, *, evidence_resolver=None: {
            "status": "RESOLVED",
            "state": "RESOLVED",
            "can_pass": True,
            "primary_curriculum": record,
            "dimensions": {
                "primary_curriculum": {"status": "RESOLVED", "state": "RESOLVED"},
                "target_curriculum_version": {"status": "NOT_APPLICABLE", "state": "NOT_APPLICABLE"},
            },
            "blocker_codes": (),
            "warnings": (),
        },
    )
    snapshot = graduation_service.evaluate(_request(rows=(_row(),)))

    assert "total_credit_requirement" not in snapshot.decisions["primary_graduation"]


@pytest.mark.parametrize("curriculum_id,expected_domains", [
    ("primary:111:cs", {"common", "software", "network"}),
    ("primary:115:cs", {"software", "network"}),
])
def test_cs_beta_count_constraints_survive_registry_sanitizer_and_compile(curriculum_id, expected_domains):
    curriculum = _safe_curriculum(get_curriculum(curriculum_id))
    assert curriculum is not None

    requirements, _metadata, _provenance = _compile_requirements(curriculum, scope="primary")
    beta = next(item for item in requirements if item.requirement_id.endswith("beta_remainder"))

    assert beta.credits_required == Decimal("22")
    constraints = {item["membership_id"]: item for item in beta.subset_constraints}
    assert {item.rsplit(":", 1)[-1] for item in constraints} == expected_domains
    assert all(item["minimum_course_count"] == 1 for item in constraints.values())
    assert all(item["observed_requirement_ids"] == (beta.requirement_id,) for item in constraints.values())
    assert all(item["source_reference"] for item in constraints.values())
