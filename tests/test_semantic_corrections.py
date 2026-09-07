from __future__ import annotations

from decimal import Decimal

import pytest

from allocation_engine import (
    COMPLETE,
    UNKNOWN,
    VERIFIED,
    CourseAttempt,
    EquivalencyBinding,
    RequirementSpec,
    WaiverDecision,
    allocate_credits,
)
from decision_snapshot import build_decision_snapshot
from graduation_service import EvaluationRequest, _compile_requirements, evaluate
from input_confirmation import NormalizedCourseRow, fingerprint_course_rows
from snapshot_exports import build_allocation_csv, build_audit_json, build_pdf
from snapshot_renderer import render_snapshot


def _attempt(
    attempt_id: str,
    course_id: str,
    *,
    name: str | None = None,
    kind: str = "LECTURE",
    group: str | None = None,
    grade: str = "A",
    grade_evidence_state: str = VERIFIED,
    pools: tuple[str, ...] = (),
):
    return CourseAttempt(
        attempt_id=attempt_id,
        course_id=course_id,
        course_name=name or course_id,
        credits=3,
        earned_credits=3,
        academic_term="114-1",
        repeat_group_id=group,
        identity_status=VERIFIED,
        course_kind=kind,
        pool_memberships=pools,
        grade=grade,
        grade_evidence_state=grade_evidence_state,
    )


def _requirement(requirement_id: str, *, names=(), ids=(), kind=None, repeat=False, waiver=False, owner="", domain=""):
    return RequirementSpec(
        requirement_id=requirement_id,
        name=requirement_id,
        credits_required=3,
        eligible_course_names=names,
        eligible_course_ids=ids,
        course_kind=kind,
        coverage_state=COMPLETE,
        evidence_state=VERIFIED,
        repeatable=repeat,
        waiver=waiver,
        owner=owner,
        domain=domain,
    )


def _confirmed_request(**kwargs):
    row = NormalizedCourseRow(
        course_code="X-001",
        course_name="X",
        credits=3,
        earned_credits=3,
        status="COMPLETED",
        term="114-1",
        grade="A",
        course_type="lecture",
    )
    rows = kwargs.pop("rows", (row,))
    fingerprint = fingerprint_course_rows(rows)
    return EvaluationRequest(
        admission_cohort="114",
        primary_curriculum_id="primary:114:apc:chemistry",
        confirmed_course_rows=rows,
        confirmed_course_fingerprint=fingerprint,
        transcript_confirmed=True,
        confirmation_state="CONFIRMED",
        **kwargs,
    )


def test_apc_chemistry_compiler_keeps_only_named_leaves_and_residual_quota():
    for cohort, residual in (("113", "24"), ("114", "24"), ("115", "20")):
        record = {
            "curriculum_id": f"target:double_major:{cohort}:apc:chemistry",
            "coverage_state": "PARTIAL",
            "evidence_state": "VERIFIED",
            "thresholds": {"total": 40, "base": 16, "other": int(residual)},
            "course_catalog": [],
        }
        from curriculum_registry import get_curriculum

        record = get_curriculum(record["curriculum_id"])
        specs, metadata, _ = _compile_requirements(record, scope="target")
        assert len(specs) == 9
        assert sum(not metadata[item.requirement_id]["generic"] for item in specs) == 8
        assert sum(metadata[item.requirement_id]["generic"] for item in specs) == 1
        assert not any("aggregate:" in item.requirement_id for item in specs)
        quota = [item for item in specs if metadata[item.requirement_id]["generic"]]
        assert len(quota) == 1
        assert quota[0].credits_required == Decimal(residual)
        assert not quota[0].eligible_course_ids
        names = {item.name for item in specs}
        if cohort == "115":
            assert "微積分(一)" in names and "微積分(二)" in names
            assert not any("物理實驗" in name for name in names)
            assert sum("化學實驗" in name for name in names) == 2
        else:
            assert not any("微積分" in name for name in names)


def test_apc_chemistry_111_to_114_do_not_inherit_115_calculus_rows():
    from curriculum_registry import get_curriculum

    for cohort in ("111", "112", "113", "114"):
        record = get_curriculum(f"target:double_major:{cohort}:apc:chemistry")
        specs, _metadata, _ = _compile_requirements(record, scope="target")
        assert not any("微積分" in item.name for item in specs)


def test_title_only_and_invalid_kind_are_candidate_only_and_cannot_pass():
    title_only = _attempt("a", "OTHER", name="same-name", kind="")
    invalid_kind = _attempt("b", "KNOWN", kind="not-a-component")
    requirement = _requirement("r", names=("same-name",), ids=("KNOWN",))
    result = allocate_credits((title_only, invalid_kind), (requirement,))
    assert result.status != "PASS"
    assert result.recognized_credits == Decimal("0")
    assert title_only.course_kind == UNKNOWN
    assert invalid_kind.course_kind == UNKNOWN


@pytest.mark.parametrize(
    ("malformed_component", "required_kind"),
    (
        ("collaboration", "LAB"),
        ("syllabus", "LAB"),
        ("required_course", "LECTURE"),
    ),
)
def test_component_matching_uses_exact_aliases_not_substrings(malformed_component, required_kind):
    source = _attempt("source", "SOURCE", kind=malformed_component)
    result = allocate_credits(
        (source,),
        (_requirement("target", ids=("SOURCE",), kind=required_kind),),
    )

    assert source.course_kind == UNKNOWN
    assert result.recognized_credits == Decimal("0")
    assert result.status != "PASS"


def test_lecture_and_lab_identity_are_not_interchangeable():
    lecture = _attempt("lecture", "C-1", kind="LECTURE")
    lab = _attempt("lab", "C-2", kind="LAB")
    result = allocate_credits(
        (lecture, lab),
        (
            _requirement("lecture-r", ids=("C-2",), kind="LECTURE"),
            _requirement("lab-r", ids=("C-1",), kind="LAB"),
        ),
    )
    assert result.recognized_credits == Decimal("0")
    assert result.status != "PASS"


def test_shared_binding_requires_exact_source_scope_and_projects_only_positive_source_allocation():
    source = _attempt("source", "S", pools=("primary",))
    primary = _requirement("primary", ids=("S",), owner="PRIMARY", domain="major")
    target = _requirement("target", ids=("T",), owner="TARGET", domain="double")
    valid = EquivalencyBinding(
        "valid", "source", "target", 3, VERIFIED, "department", "official:valid",
        "PRIMARY_TO_TARGET", True, source_requirement_id="primary", source_owner="PRIMARY",
        target_owner="TARGET", source_domain="major", target_domain="double", decision="APPROVED",
    )
    result = allocate_credits((source,), (primary, target), (valid,))
    assert sum(item.credits for item in result.shadow_allocations) == Decimal("3")

    bad = EquivalencyBinding(
        "bad", "source", "target", 3, VERIFIED, "department", "official:bad",
        "PRIMARY_TO_TARGET", True, source_requirement_id="missing", source_owner="PRIMARY",
        target_owner="TARGET", source_domain="major", target_domain="double",
    )
    rejected = allocate_credits((source,), (primary, target), (bad,))
    assert rejected.shadow_allocations == ()
    assert rejected.status == UNKNOWN


def test_any_allocation_ambiguity_is_unknown_even_with_numeric_deficit():
    source_a = _attempt("a", "A", pools=("pool",))
    source_b = _attempt("b", "B", pools=("pool",))
    result = allocate_credits(
        (source_a, source_b),
        (
            _requirement("r1", ids=("A", "B")),
            _requirement("r2", ids=("A", "B")),
            _requirement("impossible", ids=("NOT-TAKEN",)),
        ),
    )
    assert result.allocation_ambiguous
    assert result.status == UNKNOWN


def test_conflicting_attempt_and_waiver_ids_block_but_identical_duplicates_dedupe():
    first = _attempt("a", "A")
    duplicate = _attempt("a", "A")
    requirement = _requirement("r", ids=("A",))
    assert allocate_credits((first, duplicate), (requirement,)).status == "PASS"
    conflict = _attempt("a", "B")
    conflicted = allocate_credits((first, conflict), (requirement,))
    assert conflicted.status == UNKNOWN
    assert any("DUPLICATE_ATTEMPT_ID" in item for item in conflicted.blockers)

    waiver = _requirement("waiver", waiver=True)
    decision = WaiverDecision("wd", "waiver", VERIFIED, "registrar", "official:wd", decision="APPROVED")
    same = WaiverDecision("wd", "waiver", VERIFIED, "registrar", "official:wd", decision="APPROVED")
    assert allocate_credits((), (waiver,), waiver_decisions=(decision, same)).status == "PASS"
    other = WaiverDecision("wd", "other", VERIFIED, "registrar", "official:wd")
    conflicted_waiver = allocate_credits((), (waiver,), waiver_decisions=(decision, other))
    assert conflicted_waiver.status == UNKNOWN
    assert any("DUPLICATE_WAIVER_DECISION_ID" in item for item in conflicted_waiver.blockers)


def test_repeat_winner_without_verified_grade_evidence_is_unknown():
    lower = _attempt("lower", "R", group="repeat", grade="", grade_evidence_state=UNKNOWN)
    result = allocate_credits((lower,), (_requirement("r", ids=("R",)),))
    assert result.status == UNKNOWN


def test_confirmation_cardinality_mismatch_blocks_but_confirmed_zero_zero_is_valid_nonpassing():
    request = _confirmed_request()
    snapshot = evaluate(request)
    assert snapshot.input_confirmation["released_row_count"] <= snapshot.input_confirmation["row_count"]

    mismatched = build_decision_snapshot(
        {
            "attempts": (),
            "requirements": (),
            "input_confirmation": {
                "state": "CONFIRMED",
                "current_fingerprint": "same",
                "confirmed_fingerprint": "same",
                "release_allowed": True,
                "row_count": 1,
                "released_row_count": 2,
            },
        }
    )
    assert mismatched.verdict == UNKNOWN
    assert mismatched.input_confirmation["cardinality_consistent"] is False

    missing_attempt = build_decision_snapshot(
        {
            "attempts": (),
            "requirements": (),
            "input_confirmation": {
                "state": "CONFIRMED",
                "current_fingerprint": "same",
                "confirmed_fingerprint": "same",
                "release_allowed": True,
                "row_count": 1,
                "released_row_count": 1,
            },
        }
    )
    assert missing_attempt.verdict == UNKNOWN
    assert missing_attempt.input_confirmation["cardinality_consistent"] is False

    negative = build_decision_snapshot(
        {
            "attempts": (),
            "requirements": (),
            "input_confirmation": {
                "state": "CONFIRMED",
                "current_fingerprint": "same",
                "confirmed_fingerprint": "same",
                "release_allowed": True,
                "row_count": -1,
                "released_row_count": 0,
            },
        }
    )
    assert negative.verdict == UNKNOWN
    assert negative.input_confirmation["cardinality_consistent"] is False

    empty = evaluate(
        EvaluationRequest(
            admission_cohort="114",
            primary_curriculum_id="primary:114:apc:chemistry",
            confirmed_course_rows=(),
            confirmed_course_fingerprint=fingerprint_course_rows(()),
            transcript_confirmed=True,
            confirmation_state="CONFIRMED",
        )
    )
    assert empty.input_confirmation["state"] == "CONFIRMED"
    assert empty.verdict != "PASS"


def test_formal_release_marker_cannot_bypass_invalid_cardinality():
    snapshot = build_decision_snapshot(
        {
            "attempts": (),
            "requirements": (),
            "input_confirmation": {
                "state": "CONFIRMED",
                "current_fingerprint": "same",
                "confirmed_fingerprint": "same",
                "formal_release_marker": "FORMAL_RELEASE",
                "row_count": 0,
                "released_row_count": 99,
            },
        }
    )
    assert snapshot.input_confirmation["cardinality_consistent"] is False
    assert snapshot.input_confirmation["state"] == "UNCONFIRMED"
    assert snapshot.verdict == UNKNOWN


def test_official_qualification_is_separate_from_self_report_and_coursework():
    request = _confirmed_request(
        program_type="雙主修",
        target_program="資科",
        target_curriculum_id="target:double_major:114:cs",
        application_term="114-1",
        application_status="已核准",
        school_approval_status="已核准",
        formal_qualification_status="已取得資格",
        subject_ref="subject:opaque-1",
        formal_qualification_evidence_id="qualification-1",
    )
    record = {
        "record_id": "qualification-1",
        "record_type": "FORMAL_QUALIFICATION_RECORD",
        "evidence_state": "VERIFIED",
        "qualification_status": "QUALIFIED",
        "application_term": "114-1",
        "target_program": "cs",
        "subject_ref": "subject:opaque-1",
        "authority": "教務處",
        "evidence_reference": "official:qualification",
    }
    snapshot = evaluate(request, evidence_resolver=lambda key: record if key == "qualification-1" else None)
    decisions = snapshot.decisions
    assert decisions["application_self_report"]["status"] == UNKNOWN
    assert decisions["application_self_report"]["authoritative"] is False
    assert "已核准" in decisions["application_self_report"]["claimed_state"]
    rendered = render_snapshot(snapshot)
    assert 'application_self_report</span><span class="snapshot-badge is-pass"' not in rendered
    assert "使用者自述" in rendered
    assert decisions["formal_qualification"]["status"] == "PASS"
    assert decisions["target_coursework_completion"]["status"] != "PASS"
    assert decisions["award_eligibility"]["status"] != "PASS"
    assert "subject:opaque-1" not in str(snapshot.as_dict())


def test_public_diagnostics_do_not_echo_opaque_evidence_identifiers():
    request = _confirmed_request(equivalency_evidence_ids=("secret-evidence-id",))
    snapshot = evaluate(request)
    public = f"{snapshot.blockers!r} {snapshot.warnings!r}"
    assert "secret-evidence-id" not in public


def test_opaque_ids_do_not_enter_snapshot_or_public_exports():
    sentinel = "RAW-SENSITIVE-EVIDENCE-SENTINEL-9f31"
    snapshot = evaluate(_confirmed_request(equivalency_evidence_ids=(sentinel,)))
    public_values = (
        repr(snapshot),
        repr(snapshot.as_dict()),
        render_snapshot(snapshot),
        build_allocation_csv(snapshot).decode("utf-8", errors="ignore"),
        build_audit_json(snapshot).decode("utf-8", errors="ignore"),
    )
    assert all(sentinel not in value for value in public_values)
    assert sentinel.encode("utf-8") not in build_pdf(snapshot)


def test_private_subject_evidence_source_reference_is_not_publicized():
    private_reference = "https://untrusted.example/qualification/RAW-SOURCE-REFERENCE-SENTINEL-9f31"
    public_reference = "https://reg.utaipei.edu.tw/var/file/31/1031/attach/42/pta_129168_9101728_61974.pdf"
    request = _confirmed_request(
        program_type="雙主修",
        target_program="資科",
        target_curriculum_id="target:double_major:114:cs",
        application_term="114-1",
        application_status="已核准",
        formal_qualification_status="已取得資格",
        subject_ref="subject:private-source-ref",
        formal_qualification_evidence_id="qualification-private-source-ref",
    )
    record = {
        "record_id": "qualification-private-source-ref",
        "record_type": "FORMAL_QUALIFICATION_RECORD",
        "evidence_state": "VERIFIED",
        "qualification_status": "QUALIFIED",
        "application_term": "114-1",
        "target_program": "cs",
        "subject_ref": "subject:private-source-ref",
        "authority": "教務處",
        "source_reference": private_reference,
    }
    snapshot = evaluate(
        request,
        evidence_resolver=lambda key: record if key == "qualification-private-source-ref" else None,
    )
    public_values = (
        repr(snapshot),
        repr(snapshot.as_dict()),
        render_snapshot(snapshot),
        build_allocation_csv(snapshot).decode("utf-8", errors="ignore"),
        build_audit_json(snapshot).decode("utf-8", errors="ignore"),
    )
    assert all(private_reference not in value for value in public_values)
    assert private_reference.encode("utf-8") not in build_pdf(snapshot)
    assert public_reference in repr(snapshot.as_dict())


def test_subject_ref_is_not_present_in_request_repr():
    request = _confirmed_request(subject_ref="RAW-SUBJECT-REF-SENTINEL")
    assert "RAW-SUBJECT-REF-SENTINEL" not in repr(request)


def test_cs_department_candidates_do_not_become_individually_required():
    from curriculum_registry import get_curriculum

    record = get_curriculum("target:double_major:114:cs")
    specs, metadata, _ = _compile_requirements(record, scope="target")
    assert specs
    named_specs = [item for item in specs if not metadata[item.requirement_id]["generic"]]
    generic_specs = [item for item in specs if metadata[item.requirement_id]["generic"]]
    assert len(named_specs) == 5
    assert len(generic_specs) == 1
    assert generic_specs[0].credits_required == Decimal("25")
    assert all(item.eligible_course_names for item in named_specs)
    assert generic_specs[0].eligible_course_names == ()
    assert all(
        item.requirement_id not in {candidate["name"] for candidate in record["course_pools"]["pool:double_major:114:cs:department:other_required"]["candidate_courses"]}
        for item in specs
    )
