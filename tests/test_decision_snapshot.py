from decimal import Decimal

import pytest

from allocation_engine import (
    COMPLETE,
    NONE,
    UNKNOWN,
    VERIFIED,
    AllocationResult,
    CourseAttempt,
    RequirementSpec,
)
from decision_snapshot import DecisionSnapshot, build_decision_snapshot


def confirmed_input(**overrides):
    value = {
        "state": "CONFIRMED",
        "fingerprint": "confirmed:fingerprint",
        "confirmed_fingerprint": "confirmed:fingerprint",
        "formal_release_success": True,
        "row_count": 1,
        "released_row_count": 1,
    }
    value.update(overrides)
    return value


def test_snapshot_is_deeply_immutable_and_content_addressed():
    attempts = (
        CourseAttempt("b", "B", "B", Decimal("3"), Decimal("3"), "114-1"),
        CourseAttempt("a", "A", "A", Decimal("3"), Decimal("3"), "114-1"),
    )
    requirements = (
        RequirementSpec("r2", "R2", Decimal("3"), eligible_course_ids=("B",)),
        RequirementSpec("r1", "R1", Decimal("3"), eligible_course_ids=("A",)),
    )
    request = {
        "attempts": attempts,
        "requirements": requirements,
        "student_id": "SECRET-STUDENT",
        "evidence": {"raw_record": {"student_id": "OTHER"}},
    }

    first = build_decision_snapshot(request, evaluated_at="2026-09-02T12:00:00Z")
    second = build_decision_snapshot(
        {
            **request,
            "attempts": tuple(reversed(attempts)),
            "requirements": tuple(reversed(requirements)),
        },
        evaluated_at="2026-09-02T12:00:00Z",
    )

    assert isinstance(first, DecisionSnapshot)
    assert first.snapshot_id == second.snapshot_id
    assert first.evaluated_at == "2026-09-02T12:00:00Z"
    with pytest.raises((TypeError, AttributeError)):
        first.request["new"] = "value"
    with pytest.raises((AttributeError, TypeError)):
        first.allocation.status = "FAIL"
    assert "student_id" not in str(first)
    assert "raw_record" not in str(first)


@pytest.mark.parametrize(
    ("allocation_status", "allocation_pass_eligible", "blockers"),
    (
        ("PASS", True, ("MANUAL_REVIEW_REQUIRED",)),
        ("FAIL", True, ()),
        ("UNKNOWN", True, ()),
        ("PASS", False, ()),
    ),
)
def test_snapshot_pass_invariant_downgrades_inconsistent_verdict_and_syncs_overall(
    allocation_status,
    allocation_pass_eligible,
    blockers,
):
    allocation = AllocationResult(
        status=allocation_status,
        allocations=(),
        requirement_results=(),
        source_earned_credits=0,
        recognized_credits=0,
        unallocated_credits=0,
        credit_conservation=True,
        blockers=blockers,
        pass_eligible=allocation_pass_eligible,
    )

    snapshot = DecisionSnapshot(
        snapshot_id="snapshot:inconsistent-pass",
        evaluated_at="2026-09-02T12:00:00Z",
        request={},
        attempts=(),
        requirements=(),
        bindings=(),
        curriculum={},
        rule_resolution={},
        evidence=(),
        allocation=allocation,
        verdict="PASS",
        blockers=blockers,
        decisions={
            "overall": {
                "status": "PASS",
                "state": "PASS",
                "can_pass": True,
                "reason": "preserve this audit reason",
            },
            "keep": "value",
        },
        input_confirmation=confirmed_input(row_count=0, released_row_count=0),
    )

    assert snapshot.verdict == UNKNOWN
    assert snapshot.decisions["overall"] == {
        "status": UNKNOWN,
        "state": UNKNOWN,
        "can_pass": False,
        "reason": "preserve this audit reason",
    }
    assert snapshot.decisions["keep"] == "value"


@pytest.mark.parametrize(
    ("metadata", "expected_verdict", "expected_blocker"),
    (
        (
            {"search_complete": False, "optimality": "OPTIMAL", "feasible_witness": False},
            UNKNOWN,
            "SEARCH_INCOMPLETE",
        ),
        (
            {"search_complete": True, "optimality": "BOUNDED_NOT_COMPLETE", "feasible_witness": True},
            "PASS",
            None,
        ),
        (
            {"search_complete": True, "optimality": "NON_UNIQUE", "feasible_witness": True},
            "PASS",
            None,
        ),
        (
            {"search_complete": True, "optimality": "UNSPECIFIED", "feasible_witness": True},
            "PASS",
            None,
        ),
        (
            {"search_complete": True, "allocation_ambiguous": True, "feasible_witness": True},
            "PASS",
            None,
        ),
        (
            {"search_complete": True, "allocation_ambiguous": "false", "feasible_witness": True},
            UNKNOWN,
            "ALLOCATION_METADATA_INVALID",
        ),
    ),
)
def test_snapshot_distinguishes_search_and_allocation_metadata(metadata, expected_verdict, expected_blocker):
    allocation = AllocationResult(
        status="PASS",
        allocations=(),
        requirement_results=(),
        source_earned_credits=0,
        recognized_credits=0,
        unallocated_credits=0,
        credit_conservation=True,
        pass_eligible=True,
    )

    snapshot = DecisionSnapshot(
        snapshot_id="snapshot:metadata-uncertain",
        evaluated_at="2026-09-02T12:00:00Z",
        request={},
        attempts=(),
        requirements=(),
        bindings=(),
        curriculum={},
        rule_resolution={},
        evidence=(),
        allocation=allocation,
        verdict="PASS",
        decisions={
            "overall": {
                "status": "PASS",
                "state": "PASS",
                "can_pass": True,
                "reason": "retain audit explanation",
            }
        },
        input_confirmation=confirmed_input(row_count=0, released_row_count=0),
        **metadata,
    )

    assert snapshot.verdict == expected_verdict
    assert snapshot.decisions["overall"]["status"] == expected_verdict
    assert snapshot.decisions["overall"]["state"] == expected_verdict
    assert snapshot.decisions["overall"]["can_pass"] is (expected_verdict == "PASS")
    if expected_blocker:
        assert expected_blocker in snapshot.blockers
    else:
        assert not snapshot.blockers


def test_snapshot_keeps_canonical_overflow_route_candidates_and_witness_portions():
    attempt = CourseAttempt(
        "attempt:course-a",
        "COURSE-A",
        "COURSE-A",
        Decimal("4"),
        Decimal("4"),
        "114-1",
        pool_ids=("pool:core",),
    )
    requirements = (
        RequirementSpec(
            "primary:core",
            "Core",
            Decimal("3"),
            max_credits=Decimal("3"),
            eligible_course_ids=("COURSE-A",),
            overflow_routes=("primary:elective",),
            owner="PRIMARY",
        ),
        RequirementSpec(
            "primary:elective",
            "Elective",
            Decimal("1"),
            eligible_pool_ids=("pool:elective",),
            owner="PRIMARY",
        ),
    )

    snapshot = build_decision_snapshot(
        {
            "attempts": (attempt,),
            "requirements": requirements,
            "input_confirmation": confirmed_input(),
        },
        evaluated_at="2026-09-02T12:00:00Z",
    )
    projected = snapshot.as_dict()

    core = next(item for item in projected["requirements"] if item["requirement_id"] == "primary:core")
    assert core["overflow_routes"] == ("primary:elective",)
    assert any(
        portion["requirement_id"] == "primary:elective"
        for allocation in projected["allocation"]["allocations"]
        for portion in allocation["portions"]
    )
    assert projected["allocation"]["credit_conservation"]


def test_snapshot_pass_requires_literal_credit_conservation():
    allocation = AllocationResult(
        status="PASS",
        allocations=(),
        requirement_results=(),
        source_earned_credits=0,
        recognized_credits=0,
        unallocated_credits=0,
        credit_conservation="true",
        pass_eligible=True,
        search_exhausted=False,
        allocation_ambiguous=False,
    )

    snapshot = DecisionSnapshot(
        snapshot_id="snapshot:conservation-metadata",
        evaluated_at="2026-09-02T12:00:00Z",
        request={},
        attempts=(),
        requirements=(),
        bindings=(),
        curriculum={},
        rule_resolution={},
        evidence=(),
        allocation=allocation,
        verdict="PASS",
        input_confirmation=confirmed_input(row_count=0, released_row_count=0),
    )

    assert snapshot.allocation.credit_conservation is False
    assert snapshot.verdict == UNKNOWN
    assert not snapshot.can_pass
    assert "CREDIT_CONSERVATION_FAILED" in snapshot.blockers


def test_snapshot_recursively_removes_identity_fields_before_repr_and_as_dict_storage():
    allocation = AllocationResult(
        status="PASS",
        allocations=(),
        requirement_results=(),
        source_earned_credits=0,
        recognized_credits=0,
        unallocated_credits=0,
        credit_conservation=True,
        pass_eligible=True,
    )
    nested_identity = {
        "student_id": "RAW_STUDENT_ID_NESTED",
        "subject_id": "RAW_SUBJECT_ID_NESTED",
        "subject_ref": "RAW_SUBJECT_REF_NESTED",
        "student_number": "RAW_STUDENT_NUMBER_NESTED",
        "student_no": "RAW_STUDENT_NO_NESTED",
        "student-id": "RAW_STUDENT_ID_HYPHEN_NESTED",
        "student id": "RAW_STUDENT_ID_SPACE_NESTED",
        "Subject-Ref": "RAW_SUBJECT_REF_CASE_NESTED",
        "child": {"studentId": "RAW_STUDENT_ID_CAMEL_NESTED"},
    }
    snapshot = DecisionSnapshot(
        snapshot_id="snapshot:privacy-nested",
        evaluated_at="2026-09-02T12:00:00Z",
        request={"nested": nested_identity},
        attempts=(),
        requirements=(),
        bindings=(),
        curriculum={"primary": {"nested": nested_identity}},
        rule_resolution={"target": {"nested": nested_identity}},
        evidence=({"nested": nested_identity},),
        allocation=allocation,
        verdict="PASS",
        decisions={"overall": {"status": "PASS"}, "nested": nested_identity},
        input_confirmation=confirmed_input(row_count=0, released_row_count=0),
    )

    public = snapshot.as_dict()
    rendered = repr(snapshot)
    public_rendered = repr(public)
    for sentinel in (
        "RAW_STUDENT_ID_NESTED",
        "RAW_SUBJECT_ID_NESTED",
        "RAW_SUBJECT_REF_NESTED",
        "RAW_STUDENT_NUMBER_NESTED",
        "RAW_STUDENT_NO_NESTED",
        "RAW_STUDENT_ID_HYPHEN_NESTED",
        "RAW_STUDENT_ID_SPACE_NESTED",
        "RAW_SUBJECT_REF_CASE_NESTED",
        "RAW_STUDENT_ID_CAMEL_NESTED",
    ):
        assert sentinel not in rendered
        assert sentinel not in public_rendered

    def assert_no_identity_keys(value):
        if isinstance(value, dict):
            normalized = {"".join(char for char in str(key).casefold() if char.isalnum()) for key in value}
            assert not normalized.intersection(
                {"studentid", "subjectid", "subjectref", "studentnumber", "studentno"}
            )
            for child in value.values():
                assert_no_identity_keys(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                assert_no_identity_keys(child)

    assert_no_identity_keys(public)


def test_snapshot_removes_nested_identity_containers_and_account_identifiers_but_keeps_labels():
    allocation = AllocationResult(
        status="PASS",
        allocations=(),
        requirement_results=(),
        source_earned_credits=0,
        recognized_credits=0,
        unallocated_credits=0,
        credit_conservation=True,
        pass_eligible=True,
    )
    payload = {
        "student": {"id": "RAW_NESTED_STUDENT_ID", "name": "RAW_NESTED_STUDENT_NAME"},
        "subject": {"id": "RAW_NESTED_SUBJECT_ID"},
        "uid": "RAW_UID",
        "username": "RAW_USERNAME",
        "account": {"account_id": "RAW_ACCOUNT_ID", "name": "RAW_ACCOUNT_NAME"},
        "account_number": "RAW_ACCOUNT_NUMBER",
        "course": {"id": "COURSE_ID_KEEP", "name": "保留課程名稱"},
        "requirement": {"id": "REQUIREMENT_ID_KEEP", "name": "保留畢業要求名稱"},
    }
    snapshot = DecisionSnapshot(
        snapshot_id="snapshot:privacy-containers",
        evaluated_at="2026-09-02T12:00:00Z",
        request={},
        attempts=(),
        requirements=(),
        bindings=(),
        curriculum={"identity_payload": payload},
        rule_resolution={"identity_payload": payload},
        evidence=({"identity_payload": payload},),
        allocation=allocation,
        verdict="PASS",
        decisions={"overall": {"status": "PASS"}, "identity_payload": payload},
        statistics={"identity_payload": payload},
        input_confirmation=confirmed_input(row_count=0, released_row_count=0),
    )

    public = snapshot.as_dict()
    rendered = repr(snapshot)
    public_rendered = repr(public)
    for sentinel in (
        "RAW_NESTED_STUDENT_ID",
        "RAW_NESTED_STUDENT_NAME",
        "RAW_NESTED_SUBJECT_ID",
        "RAW_UID",
        "RAW_USERNAME",
        "RAW_ACCOUNT_ID",
        "RAW_ACCOUNT_NAME",
        "RAW_ACCOUNT_NUMBER",
    ):
        assert sentinel not in rendered
        assert sentinel not in public_rendered

    for projection in (
        public["curriculum"],
        public["rule_resolution"],
        public["evidence"][0],
        public["decisions"],
        public["statistics"],
    ):
        identity_payload = projection["identity_payload"]
        assert "student" not in identity_payload
        assert "subject" not in identity_payload
        assert "account" not in identity_payload
        assert "uid" not in identity_payload
        assert "username" not in identity_payload
        assert "account_number" not in identity_payload
        assert identity_payload["course"]["name"] == "保留課程名稱"
        assert identity_payload["requirement"]["name"] == "保留畢業要求名稱"


def test_snapshot_uses_opaque_resolver_ids_and_projects_only_safe_provenance():
    calls = []

    def curriculum_resolver(record_id):
        calls.append(("curriculum", record_id))
        return {
            "curriculum_id": record_id,
            "kind": "primary",
            "version": "114",
            "evidence_state": "VERIFIED",
            "coverage_state": "PARTIAL",
            "authority": "官方手冊",
            "source_reference": "official:handbook:114",
            "student_id": "DO-NOT-STORE",
            "raw_catalog": {"secret": "DO-NOT-STORE"},
        }

    def evidence_resolver(record_id):
        calls.append(("evidence", record_id))
        return {
            "evidence_id": record_id,
            "evidence_state": "VERIFIED",
            "authority": "系所",
            "source_reference": "official:rule:114",
            "application_term": "114-1",
            "raw_blob": {"student_id": "DO-NOT-STORE"},
        }

    snapshot = build_decision_snapshot(
        {
            "curriculum_id": "primary:114:math",
            "evidence_record_ids": ("rule:114:math",),
            "trusted_evidence_store": {"rule:114:math": {"trusted": True}},
            "student_id": "SECRET-STUDENT",
            "attempts": (),
            "requirements": (),
        },
        curriculum_resolver=curriculum_resolver,
        evidence_resolver=evidence_resolver,
        evaluated_at="2026-09-02T12:00:00Z",
    )

    assert calls == [("curriculum", "primary:114:math"), ("evidence", "rule:114:math")]
    assert snapshot.curriculum["primary"]["curriculum_id"] == "primary:114:math"
    assert snapshot.evidence[0]["evidence_id"].startswith("evidence:sha256:")
    assert "rule:114:math" not in str(snapshot.evidence)
    assert "trusted_evidence_store" not in str(snapshot)
    assert "DO-NOT-STORE" not in str(snapshot)
    assert "SECRET-STUDENT" not in str(snapshot)
    with pytest.raises(TypeError):
        snapshot.as_dict()["request"] = {}


def test_raw_evidence_without_injected_resolver_remains_unresolved_and_cannot_change_allocation():
    snapshot = build_decision_snapshot(
        {
            "evidence_record_ids": ("rule:forged",),
            "evidence": {"evidence_state": "VERIFIED", "authority": "forged"},
            "attempts": (),
            "requirements": (),
        },
        evaluated_at="2026-09-02T12:00:00Z",
    )

    assert snapshot.evidence[0]["resolution_state"] == "UNRESOLVED"
    assert any(item.startswith("EVIDENCE_UNRESOLVED:") and ":evidence:" in item for item in snapshot.blockers)
    assert "rule:forged" not in str(snapshot.blockers)
    assert not snapshot.can_pass


def test_mapping_adapters_default_to_unknown_trust_and_explicit_trust_can_pass():
    raw = build_decision_snapshot(
        {
            "attempts": [
                {
                    "attempt_id": "raw-attempt",
                    "course_id": "RAW-COURSE",
                    "course_name": "RAW-COURSE",
                    "credits": 3,
                    "earned_credits": 3,
                },
            ],
            "requirements": [
                {
                    "requirement_id": "raw-requirement",
                    "credits_required": 3,
                    "eligible_course_ids": ["RAW-COURSE"],
                },
            ],
            "input_confirmation": confirmed_input(),
            "bindings": [
                {
                    "binding_id": "raw-binding",
                    "source_attempt_id": "raw-attempt",
                    "target_requirement_id": "raw-requirement",
                    "approved_credits": 3,
                },
            ],
        },
        evaluated_at="2026-09-02T12:00:00Z",
    )

    assert raw.attempts[0].identity_status == UNKNOWN
    assert raw.requirements[0].coverage_state == NONE
    assert raw.requirements[0].evidence_state == UNKNOWN
    assert raw.bindings[0]["evidence_state"] == UNKNOWN
    assert raw.verdict == UNKNOWN
    assert not raw.can_pass

    trusted = build_decision_snapshot(
        {
            "attempts": [
                {
                    "attempt_id": "trusted-attempt",
                    "course_id": "TRUSTED-COURSE",
                    "course_name": "TRUSTED-COURSE",
                    "credits": 3,
                    "earned_credits": 3,
                    "identity_status": VERIFIED,
                    "course_kind": "LECTURE",
                },
            ],
            "requirements": [
                {
                    "requirement_id": "trusted-requirement",
                    "credits_required": 3,
                    "eligible_course_ids": ["TRUSTED-COURSE"],
                    "coverage_state": COMPLETE,
                    "evidence_state": VERIFIED,
                },
            ],
            "input_confirmation": confirmed_input(),
        },
        evaluated_at="2026-09-02T12:00:00Z",
    )

    assert trusted.attempts[0].identity_status == VERIFIED
    assert trusted.requirements[0].coverage_state == COMPLETE
    assert trusted.requirements[0].evidence_state == VERIFIED
    assert trusted.verdict == "PASS"
    assert trusted.can_pass


def test_as_dict_projects_complete_safe_allocation_details_and_is_deeply_immutable():
    snapshot = build_decision_snapshot(
        {
            "attempts": (
                CourseAttempt("a", "A", "A", Decimal("3"), Decimal("3"), "114-1"),
            ),
            "requirements": (
                RequirementSpec("req", "Required", Decimal("3"), eligible_course_ids=("A",)),
            ),
            "student_name": "DO-NOT-STORE",
            "student_id": "DO-NOT-STORE",
            "transcript_bytes": b"PRIVATE",
            "input_confirmation": confirmed_input(),
        },
        evaluated_at="2026-09-02T12:00:00Z",
    )

    projected = snapshot.as_dict()

    assert projected["snapshot_id"] == snapshot.snapshot_id
    assert projected["attempts"][0]["attempt_id"] == "a"
    assert projected["requirements"][0]["requirement_id"] == "req"
    assert projected["allocation"]["allocations"][0]["portions"][0]["requirement_id"] == "req"
    assert projected["allocation"]["allocations"][0]["unallocated_credits"] == "0"
    assert projected["allocation"]["requirement_results"][0]["effective_credits"] == "3"
    assert "student_name" not in str(projected)
    assert "DO-NOT-STORE" not in str(projected)
    assert "PRIVATE" not in str(projected)
    with pytest.raises((TypeError, AttributeError)):
        projected["allocation"]["allocations"][0]["portions"] = ()


def test_unconfirmed_snapshot_hides_formal_attempts_and_forces_unknown():
    snapshot = build_decision_snapshot(
        {
            "attempts": (CourseAttempt("a", "A", "A", Decimal("3"), Decimal("3"), "114-1"),),
            "requirements": (RequirementSpec("req", "Required", Decimal("3"), eligible_course_ids=("A",)),),
        },
        evaluated_at="2026-09-02T12:00:00Z",
    )

    assert snapshot.attempts == ()
    assert snapshot.verdict == UNKNOWN
    assert not snapshot.can_pass
    assert "INPUT_UNCONFIRMED" in snapshot.blockers
    assert snapshot.as_dict()["allocation"]["allocations"] == ()


def test_confirmation_projection_is_privacy_safe_and_export_is_single_snapshot_data():
    snapshot = build_decision_snapshot(
        {
            "attempts": (CourseAttempt("a", "A", "A", Decimal("3"), Decimal("3"), "114-1"),),
            "requirements": (RequirementSpec("req", "Required", Decimal("3"), eligible_course_ids=("A",)),),
            "input_confirmation": confirmed_input(
                student_name="DO-NOT-STORE",
                student_id="DO-NOT-STORE",
                raw_transcript=b"PRIVATE",
                current_fingerprint="confirmed:fingerprint",
            ),
        },
        evaluated_at="2026-09-02T12:00:00Z",
    )

    projected = snapshot.as_dict()
    assert projected["input_confirmation"]["state"] == "CONFIRMED"
    assert projected["input_confirmation"]["formal_release_success"] is True
    assert "student_name" not in str(projected)
    assert "student_id" not in str(projected)
    assert "PRIVATE" not in str(projected)
    assert "raw_transcript" not in str(projected)
