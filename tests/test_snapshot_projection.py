from __future__ import annotations

import re
from decimal import Decimal

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
from decision_snapshot import build_decision_snapshot
from snapshot_projection import (
    AGGREGATE_GATE_UNAVAILABLE,
    STATISTICS_SCHEMA_VERSION,
    build_chart_datasets,
    build_snapshot_projection,
    build_snapshot_statistics_projection,
    build_statistics_v2,
    snapshot_to_legacy_report,
    statistics_projection_from_payload,
)


def test_registry_total_progress_excludes_target_shadow_and_unallocated_credits():
    from snapshot_projection import _aggregate_gate

    descriptor = dict(required_credits="128", curriculum_id="primary:111:earth:earth_environment",
                      evidence_state="VERIFIED", coverage_state="COMPLETE", source_reference="handbook:111",
                      authority="PRIMARY_CURRICULUM_REGISTRY", non_consuming=True)
    decisions = {"primary_graduation": {"requirement_ids": ("primary-a", "primary-b"),
                                        "total_credit_requirement": descriptor}}
    metrics = tuple(dict(requirement_id=rid, owner=owner, owner_present=True,
                         exclusive_credits_present=True, exclusive_credits=amount)
                    for rid, owner, amount in (("primary-a", "PRIMARY", "100"),
                                               ("primary-b", "PRIMARY", "26"),
                                               ("target", "DOUBLE_MAJOR", "40")))
    ledger = dict(conservation=dict(ok=True, status="PASS"), unclassified_exclusive_credits="0",
                  exclusive_by_requirement={"primary-a": "100", "primary-b": "26", "target": "40"},
                  shared_shadow_credits="20", unallocated_credits="12")
    gate = _aggregate_gate(metrics, ledger, decisions)
    assert gate["available"]
    assert gate["completed_credits"] == "126"
    assert gate["missing_credits"] == "2"
    assert gate["numerator_source"] == "primary_requirement_scope.exclusive_credits"

    for field, value in (("source_reference", ""), ("evidence_state", "UNKNOWN"),
                         ("coverage_state", "PARTIAL"), ("non_consuming", False),
                         ("required_credits", "0"), ("authority", "CALLER")):
        invalid = {"primary_graduation": {**decisions["primary_graduation"],
                    "total_credit_requirement": {**descriptor, field: value}}}
        assert not _aggregate_gate(metrics, ledger, invalid)["available"]
    assert not _aggregate_gate(metrics, {**ledger, "conservation": dict(ok=False, status="UNKNOWN")}, decisions)["available"]
    assert not _aggregate_gate(({**metrics[0], "owner": "DOUBLE_MAJOR"}, *metrics[1:]), ledger, decisions)["available"]
    assert not _aggregate_gate(metrics, {**ledger, "unclassified_exclusive_credits": "1"}, decisions)["available"]


def _snapshot():
    return build_decision_snapshot(
        {
            "attempts": (
                CourseAttempt("a", "A", "A", Decimal("3"), Decimal("3"), "114-1"),
                CourseAttempt("b", "B", "B", Decimal("2"), Decimal("2"), "114-1"),
            ),
            "requirements": (
                RequirementSpec(
                    "req-a",
                    "A requirement",
                    Decimal("3"),
                    eligible_course_ids=("A",),
                    coverage_state=COMPLETE,
                    evidence_state=VERIFIED,
                    bucket="major",
                ),
            ),
            "input_confirmation": {
                "state": "CONFIRMED",
                "current_fingerprint": "snapshot-projection-fixture",
                "confirmed_fingerprint": "snapshot-projection-fixture",
                "formal_release_success": True,
                "row_count": 2,
                "released_row_count": 2,
            },
        },
        evaluated_at="2026-09-02T00:00:00Z",
    )


def test_projection_is_frozen_and_has_required_legacy_markers():
    report = snapshot_to_legacy_report(_snapshot())

    assert report["_snapshot_id"].startswith("snapshot:")
    assert report["_projection_schema"]
    assert report["_source"] == "DecisionSnapshot"
    assert report["summary"]["verdict"]
    assert report["allocation_buckets"]
    assert "allocation" in report
    with pytest.raises(TypeError):
        report["new"] = "nope"


def test_projection_allocation_buckets_conserve_exclusive_source_credits():
    snapshot = _snapshot()
    report = snapshot_to_legacy_report(snapshot)
    buckets = report["allocation_buckets"]
    bucket_total = sum(Decimal(str(item["credits"])) for item in buckets)
    assert bucket_total == snapshot.allocation.source_earned_credits
    assert Decimal(report["summary"]["source_earned_credits"]) == bucket_total
    assert Decimal(report["summary"]["exclusive_source_credits"]) == Decimal("3")
    assert Decimal(report["summary"]["unallocated_credits"]) + Decimal(report["summary"]["recognized_credits"]) == bucket_total


def test_projection_does_not_recompute_or_call_allocator(monkeypatch):
    snapshot = _snapshot()

    def explode(*_args, **_kwargs):
        raise AssertionError("projection must be pure")

    monkeypatch.setattr("allocation_engine.allocate_credits", explode)
    report = snapshot_to_legacy_report(snapshot)
    assert report["_snapshot_id"] == snapshot.snapshot_id


def test_statistics_v2_rejects_malformed_in_progress_row_and_keeps_shadow_non_additive():
    attempts = (
        CourseAttempt("pass", "PASS", "已修", Decimal("3"), Decimal("3"), "114-1", status="PASS"),
        CourseAttempt("ip", "IP", "修習中", Decimal("2"), Decimal("0"), "115-1", status="IN_PROGRESS"),
    )
    requirements = (
        RequirementSpec("req", "正式要求", Decimal("3"), bucket="required", kind="NAMED_COURSE"),
    )
    allocation = AllocationResult(
        status="UNKNOWN",
        allocations=(
            AttemptAllocation("pass", Decimal("3"), (CreditPortion("pass", "req", Decimal("3")),), Decimal("0")),
            # A malformed in-progress portion must remain outside the ledger.
            AttemptAllocation("ip", Decimal("2"), (CreditPortion("ip", "req", Decimal("2")),), Decimal("0")),
        ),
        requirement_results=(
            RequirementResult("req", "PASS", Decimal("3"), Decimal("3"), Decimal("3"), Decimal("6"), Decimal("0"), "COMPLETE", "VERIFIED"),
        ),
        source_earned_credits=Decimal("3"),
        recognized_credits=Decimal("3"),
        unallocated_credits=Decimal("0"),
        credit_conservation=True,
        shadow_allocations=(CreditPortion("pass", "req", Decimal("3"), "SHARED_SHADOW"),),
    )
    statistics = build_statistics_v2(attempts, requirements, allocation)

    assert statistics["schema_version"] == STATISTICS_SCHEMA_VERSION
    ledger = statistics["credit_ledger"]
    assert ledger["additive"] is True
    assert ledger["ledger_basis"] == "EXCLUSIVE_PLUS_UNALLOCATED"
    assert ledger["source_earned_credits"] == "3"
    assert ledger["exclusive_allocated_credits"] == "3"
    assert ledger["unallocated_credits"] == "0"
    assert ledger["shared_shadow_credits"] == "3"
    assert ledger["shared_shadow"]["additive"] is False
    assert ledger["allocation_credit_conservation"] is False
    assert ledger["conservation"]["ok"] is False
    assert ledger["conservation"]["status"] == "UNKNOWN"
    assert statistics["effective_recognized_credits"] == "3"
    assert statistics["course_observations"]["in_progress_nominal_credits"] == "2"
    assert statistics["course_observations"]["completed_count"] == 1


def test_chart_projection_fails_closed_for_missing_total_gate_and_splits_f5_rows():
    requirements = tuple(
        RequirementSpec(f"req-{index}", f"要求 {index}", Decimal("1"), bucket="required", kind="NAMED_COURSE")
        for index in range(9)
    )
    results = tuple(
        RequirementResult(item.requirement_id, "PASS", Decimal("1"), Decimal("1"), Decimal("0"), Decimal("1"), Decimal("0"), "COMPLETE", "VERIFIED")
        for item in requirements
    )
    attempts = tuple(
        CourseAttempt(f"a-{index}", f"A-{index}", f"課程 {index}", Decimal("1"), Decimal("1"), "114-1", status="PASS")
        for index in range(9)
    )
    allocation = AllocationResult(
        status="PASS",
        allocations=tuple(AttemptAllocation(item.attempt_id, Decimal("1"), (CreditPortion(item.attempt_id, requirement.requirement_id, Decimal("1")),), Decimal("0")) for item, requirement in zip(attempts, requirements)),
        requirement_results=results,
        source_earned_credits=Decimal("9"),
        recognized_credits=Decimal("9"),
        unallocated_credits=Decimal("0"),
        credit_conservation=True,
    )
    statistics = build_statistics_v2(attempts, requirements, allocation)
    charts = build_chart_datasets(statistics, snapshot_id="snapshot:test")

    assert charts["f11"]["available"] is False
    assert charts["f11"]["reason_code"] == AGGREGATE_GATE_UNAVAILABLE
    assert len(charts["f5"]["groups"]) == 2
    assert all(group["row_count"] <= 8 for group in charts["f5"]["groups"])
    assert all(group["max_row_count"] == 8 for group in charts["f5"]["groups"])
    assert charts["f7"]["available"] is True
    assert len(charts["f7"]["rows"]) == 1


def test_verified_explicit_aggregate_gate_drives_f11_without_shadow_inflation():
    attempt = CourseAttempt("a", "A", "核心", Decimal("3"), Decimal("3"), "114-1", status="PASS")
    requirement = RequirementSpec(
        "total-gate",
        "總畢業學分",
        Decimal("128"),
        coverage_state=COMPLETE,
        evidence_state=VERIFIED,
        bucket="total",
        kind="AGGREGATE",
        owner="PRIMARY",
    )
    allocation = AllocationResult(
        status="PASS",
        allocations=(AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "total-gate", Decimal("3")),), Decimal("0")),),
        requirement_results=(
            RequirementResult("total-gate", "FAIL", Decimal("128"), Decimal("3"), Decimal("3"), Decimal("6"), Decimal("122"), "COMPLETE", "VERIFIED"),
        ),
        source_earned_credits=Decimal("3"),
        recognized_credits=Decimal("3"),
        unallocated_credits=Decimal("0"),
        credit_conservation=True,
        shadow_allocations=(CreditPortion("a", "total-gate", Decimal("3"), "SHARED_SHADOW"),),
    )

    statistics = build_statistics_v2(
        (attempt,),
        (requirement,),
        allocation,
        decisions={"primary_graduation": {"status": "FAIL", "requirement_ids": ("total-gate",)}},
    )
    charts = build_chart_datasets(statistics, snapshot_id="snapshot:aggregate")

    assert charts["f11"]["available"] is True
    assert charts["f11"]["completed"] == "3"
    assert charts["f11"]["required"] == "128"
    assert charts["f11"]["numerator_source"] == "primary_aggregate_requirement.exclusive_credits"
    assert charts["f11"]["shadow_excluded"] is True
    assert statistics["credit_ledger"]["shared_shadow_credits"] == "3"
    assert statistics["credit_ledger"]["source_earned_credits"] == "3"


def test_unclassified_categories_make_additive_and_gate_charts_unavailable():
    attempts = (CourseAttempt("a", "A", "未分類", Decimal("3"), Decimal("3"), "114-1", status="PASS"),)
    requirements = (RequirementSpec("unknown", "未分類要求", Decimal("3"), bucket="UNCLASSIFIED", kind="NAMED_COURSE"),)
    allocation = AllocationResult(
        status="UNKNOWN",
        allocations=(AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "unknown", Decimal("3")),), Decimal("0")),),
        requirement_results=(
            RequirementResult("unknown", "UNKNOWN", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "PARTIAL", "UNKNOWN"),
        ),
        source_earned_credits=Decimal("3"),
        recognized_credits=Decimal("3"),
        unallocated_credits=Decimal("0"),
        credit_conservation=True,
    )

    charts = build_chart_datasets(build_statistics_v2(attempts, requirements, allocation))

    assert charts["f1"]["available"] is False
    assert charts["f7"]["available"] is False


def test_failed_credit_conservation_disables_additive_and_aggregate_charts():
    attempt = CourseAttempt("a", "A", "核心", Decimal("3"), Decimal("3"), "114-1", status="PASS")
    requirement = RequirementSpec(
        "total-gate",
        "總畢業學分",
        Decimal("128"),
        coverage_state=COMPLETE,
        evidence_state=VERIFIED,
        bucket="total",
        kind="AGGREGATE",
    )
    allocation = AllocationResult(
        status="UNKNOWN",
        allocations=(AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "total-gate", Decimal("4")),), Decimal("0")),),
        requirement_results=(
            RequirementResult("total-gate", "FAIL", Decimal("128"), Decimal("4"), Decimal("0"), Decimal("4"), Decimal("124"), "COMPLETE", "VERIFIED"),
        ),
        source_earned_credits=Decimal("3"),
        recognized_credits=Decimal("4"),
        unallocated_credits=Decimal("0"),
        credit_conservation=False,
    )

    charts = build_chart_datasets(
        build_statistics_v2((attempt,), (requirement,), allocation, decisions={"primary_graduation": {"status": "FAIL"}})
    )

    assert charts["f1"]["available"] is False
    assert charts["f1"]["reason_code"] == "CREDIT_CONSERVATION_FAILED"
    assert charts["f11"]["available"] is False
    assert charts["f11"]["completed"] == ""
    assert charts["f11"]["required"] == ""


def test_missing_allocation_row_fails_source_conservation_and_disables_f1_f11():
    attempts = (
        CourseAttempt("a", "A", "甲", Decimal("3"), Decimal("3"), "114-1", status="PASS"),
        CourseAttempt("b", "B", "乙", Decimal("3"), Decimal("3"), "114-1", status="PASS"),
    )
    requirements = (
        RequirementSpec("req-a", "甲要求", Decimal("3"), bucket="required", kind="NAMED_COURSE"),
        RequirementSpec("req-b", "乙要求", Decimal("3"), bucket="required", kind="NAMED_COURSE"),
    )
    allocation = AllocationResult(
        status="UNKNOWN",
        allocations=(AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "req-a", Decimal("3")),), Decimal("0")),),
        requirement_results=(
            RequirementResult("req-a", "PASS", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "COMPLETE", "VERIFIED"),
            RequirementResult("req-b", "UNKNOWN", Decimal("3"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("3"), "COMPLETE", "VERIFIED"),
        ),
        source_earned_credits=Decimal("6"),
        recognized_credits=Decimal("3"),
        unallocated_credits=Decimal("0"),
        credit_conservation=True,
    )

    statistics = build_statistics_v2(attempts, requirements, allocation)
    ledger = statistics["credit_ledger"]
    charts = build_chart_datasets(statistics, snapshot_id="snapshot:missing-row")

    assert ledger["source_earned_credits"] == "6"
    assert ledger["recomputed_source_credits"] == "3"
    assert ledger["source_rows_match"] is False
    assert ledger["allocation_credit_conservation"] is False
    assert ledger["conservation"]["ok"] is False
    assert ledger["conservation"]["status"] == "UNKNOWN"
    assert charts["f1"]["available"] is False
    assert charts["f11"]["available"] is False


def test_per_attempt_conservation_rejects_cross_cancellation_between_rows():
    attempts = (
        CourseAttempt("a", "A", "甲", Decimal("3"), Decimal("3"), "114-1", status="PASS"),
        CourseAttempt("b", "B", "乙", Decimal("3"), Decimal("3"), "114-1", status="PASS"),
    )
    requirement = RequirementSpec("req", "要求", Decimal("6"), bucket="required", kind="NAMED_COURSE")
    allocation = AllocationResult(
        status="UNKNOWN",
        allocations=(
            AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "req", Decimal("4")),), Decimal("0")),
            AttemptAllocation("b", Decimal("3"), (CreditPortion("b", "req", Decimal("2")),), Decimal("0")),
        ),
        requirement_results=(RequirementResult("req", "PASS", Decimal("6"), Decimal("6"), Decimal("0"), Decimal("6"), Decimal("0"), "COMPLETE", "VERIFIED"),),
        source_earned_credits=Decimal("6"), recognized_credits=Decimal("6"), unallocated_credits=Decimal("0"), credit_conservation=True,
    )

    statistics = build_statistics_v2(attempts, (requirement,), allocation)
    ledger = statistics["credit_ledger"]
    charts = build_chart_datasets(statistics)

    assert ledger["allocation_credit_conservation"] is False
    assert ledger["allocation_rows_valid"] is False
    assert ledger["allocation_row_checks"][0]["reason_codes"] == ("ALLOCATION_ROW_PARTS_MISMATCH",)
    assert ledger["conservation"]["status"] == "UNKNOWN"
    assert "ALLOCATION_ROW_PARTS_MISMATCH" in ledger["conservation"]["reason_codes"]
    assert charts["f1"]["available"] is False
    assert charts["f5"]["available"] is False
    assert charts["f11"]["available"] is False
    assert statistics["requirement_metrics"]["items"][0]["status"] == "UNKNOWN"


def test_portion_parent_attempt_mismatch_fails_closed_even_when_row_totals_match():
    attempts = (
        CourseAttempt("a", "A", "甲", Decimal("3"), Decimal("3"), "114-1", status="PASS"),
        CourseAttempt("b", "B", "乙", Decimal("3"), Decimal("3"), "114-1", status="PASS"),
    )
    requirement = RequirementSpec("req", "要求", Decimal("6"), bucket="required", kind="NAMED_COURSE")
    allocation = AllocationResult(
        status="UNKNOWN",
        allocations=(
            AttemptAllocation("a", Decimal("3"), (CreditPortion("b", "req", Decimal("3")),), Decimal("0")),
            AttemptAllocation("b", Decimal("3"), (CreditPortion("b", "req", Decimal("3")),), Decimal("0")),
        ),
        requirement_results=(RequirementResult("req", "PASS", Decimal("6"), Decimal("6"), Decimal("0"), Decimal("6"), Decimal("0"), "COMPLETE", "VERIFIED"),),
        source_earned_credits=Decimal("6"), recognized_credits=Decimal("6"), unallocated_credits=Decimal("0"), credit_conservation=True,
    )

    statistics = build_statistics_v2(attempts, (requirement,), allocation)
    ledger = statistics["credit_ledger"]

    assert ledger["allocation_rows_valid"] is False
    assert "ALLOCATION_PORTION_ATTEMPT_ID_MISMATCH" in ledger["allocation_row_checks"][0]["reason_codes"]
    assert ledger["conservation"]["status"] == "UNKNOWN"

    charts = build_chart_datasets(statistics)
    assert charts["f5"]["available"] is False
    assert statistics["requirement_metrics"]["items"][0]["status"] == "UNKNOWN"


def test_malformed_per_attempt_numbers_fail_closed_without_zero_coercion():
    attempts = (CourseAttempt("a", "A", "甲", Decimal("3"), Decimal("3"), "114-1", status="PASS"),)
    requirement = RequirementSpec("req", "要求", Decimal("3"), bucket="required", kind="NAMED_COURSE")
    allocation = {
        "status": "UNKNOWN",
        "allocations": (
            {
                "attempt_id": "a",
                "source_credits": "NaN",
                "unallocated_credits": "0",
                "portions": (
                    {"attempt_id": "a", "requirement_id": "req", "credits": "3", "allocation_kind": "EXCLUSIVE"},
                ),
            },
        ),
        "requirement_results": (
            {"requirement_id": "req", "status": "UNKNOWN", "required_credits": "3", "exclusive_credits": "0", "shared_shadow_credits": "0", "effective_credits": "0", "deficit": "3", "coverage_state": "COMPLETE", "evidence_state": "VERIFIED"},
        ),
        "source_earned_credits": "3",
        "credit_conservation": True,
    }

    statistics = build_statistics_v2(attempts, (requirement,), allocation)
    ledger = statistics["credit_ledger"]
    charts = build_chart_datasets(statistics)

    assert ledger["allocation_rows_valid"] is False
    assert "ALLOCATION_ROW_SOURCE_INVALID" in ledger["allocation_row_checks"][0]["reason_codes"]
    assert ledger["conservation"]["status"] == "UNKNOWN"
    assert charts["f1"]["available"] is False
    assert charts["f5"]["available"] is False
    assert statistics["requirement_metrics"]["items"][0]["status"] == "UNKNOWN"


def test_malformed_shared_shadow_fails_closed_without_negative_coercion():
    attempts = (CourseAttempt("a", "A", "甲", Decimal("3"), Decimal("3"), "114-1", status="PASS"),)
    requirement = RequirementSpec("req", "要求", Decimal("3"), bucket="required", kind="NAMED_COURSE")
    allocation = {
        "status": "PASS",
        "allocations": (
            {
                "attempt_id": "a",
                "source_credits": "3",
                "unallocated_credits": "0",
                "portions": (
                    {"attempt_id": "a", "requirement_id": "req", "credits": "3", "allocation_kind": "EXCLUSIVE"},
                ),
            },
        ),
        "shadow_allocations": (
            {"attempt_id": "a", "requirement_id": "req", "credits": "-1", "allocation_kind": "SHARED_SHADOW"},
        ),
        "requirement_results": (
            {"requirement_id": "req", "status": "PASS", "required_credits": "3", "exclusive_credits": "3", "shared_shadow_credits": "0", "effective_credits": "3", "deficit": "0", "coverage_state": "COMPLETE", "evidence_state": "VERIFIED"},
        ),
        "source_earned_credits": "3",
        "credit_conservation": True,
    }

    statistics = build_statistics_v2(attempts, (requirement,), allocation)
    ledger = statistics["credit_ledger"]

    assert ledger["shadow_rows_valid"] is False
    assert "SHARED_SHADOW_CREDITS_INVALID" in ledger["shadow_row_checks"][0]["reason_codes"]
    assert ledger["conservation"]["status"] == "UNKNOWN"


def _shadow_validation_fixture(*, shadow_kind="SHARED_SHADOW", target_id="req", shadow_credits="1", result_shared="1", result_effective="4"):
    attempt = CourseAttempt("a", "A", "甲", Decimal("3"), Decimal("3"), "114-1", status="PASS")
    requirement = RequirementSpec("req", "要求", Decimal("3"), bucket="required", kind="NAMED_COURSE")
    allocation = AllocationResult(
        status="PASS",
        allocations=(AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "req", Decimal("3")),), Decimal("0")),),
        requirement_results=(
            RequirementResult("req", "PASS", Decimal("3"), Decimal("3"), Decimal(result_shared), Decimal(result_effective), Decimal("0"), "COMPLETE", "VERIFIED"),
        ),
        source_earned_credits=Decimal("3"),
        recognized_credits=Decimal("3"),
        unallocated_credits=Decimal("0"),
        credit_conservation=True,
        shadow_allocations=(CreditPortion("a", target_id, Decimal(shadow_credits), shadow_kind),),
    )
    return (attempt,), (requirement,), allocation


@pytest.mark.parametrize(
    ("case_name", "kwargs", "reason_code"),
    (
        ("over_cap", {"shadow_credits": "4", "result_shared": "4", "result_effective": "7"}, "SHARED_SHADOW_EXCEEDS_EXCLUSIVE_SOURCE"),
        ("wrong_kind", {"shadow_kind": "SHARED_REUSE"}, "SHARED_SHADOW_KIND_INVALID"),
        ("unknown_target", {"target_id": "missing-target", "result_shared": "0", "result_effective": "3"}, "SHARED_SHADOW_UNKNOWN_TARGET_REQUIREMENT"),
        ("result_mismatch", {"result_shared": "0", "result_effective": "3"}, "SHARED_SHADOW_RESULT_SHARED_MISMATCH"),
    ),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_shadow_reconciliation_failures_demote_requirements_and_disable_f5(case_name, kwargs, reason_code):
    del case_name
    attempts, requirements, allocation = _shadow_validation_fixture(**kwargs)
    statistics = build_statistics_v2(attempts, requirements, allocation)
    ledger = statistics["credit_ledger"]
    charts = build_chart_datasets(statistics)

    assert ledger["conservation"]["status"] == "UNKNOWN"
    assert reason_code in ledger["conservation"]["reason_codes"]
    assert statistics["requirement_metrics"]["items"][0]["status"] == "UNKNOWN"
    assert charts["f5"]["available"] is False


def test_course_and_requirement_counts_are_separate_when_unknown_counts_differ():
    attempts = (
        CourseAttempt("a", "A", "已修", Decimal("3"), Decimal("3"), "114-1", status="PASS"),
        CourseAttempt("b", "B", "待確認一", Decimal("2"), Decimal("0"), "114-1", status="UNKNOWN"),
        CourseAttempt("c", "C", "待確認二", Decimal("2"), Decimal("0"), "114-1", status="UNKNOWN"),
    )
    requirement = RequirementSpec("req", "待確認要求", Decimal("3"), bucket="required", kind="NAMED_COURSE")
    allocation = AllocationResult(
        status="UNKNOWN",
        allocations=(AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "req", Decimal("3")),), Decimal("0")),),
        requirement_results=(RequirementResult("req", "UNKNOWN", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "PARTIAL", "UNKNOWN"),),
        source_earned_credits=Decimal("3"), recognized_credits=Decimal("3"), unallocated_credits=Decimal("0"), credit_conservation=True,
    )
    statistics = build_statistics_v2(attempts, (requirement,), allocation)

    assert statistics["course_counts"]["UNKNOWN"] == 2
    assert statistics["requirement_counts"]["UNKNOWN"] == 1
    assert statistics["requirement_counts"]["deficit_count"] == 0


def _requirement_reconciliation_fixture():
    attempts = (
        CourseAttempt("a", "A", "甲", Decimal("3"), Decimal("3"), "114-1", status="PASS"),
        CourseAttempt("b", "B", "乙", Decimal("2"), Decimal("2"), "114-1", status="PASS"),
    )
    requirements = (
        RequirementSpec("req-a", "甲要求", Decimal("3"), bucket="required", kind="NAMED_COURSE"),
        RequirementSpec("req-b", "乙要求", Decimal("2"), bucket="elective", kind="NAMED_COURSE"),
    )
    allocation = AllocationResult(
        status="PASS",
        allocations=(
            AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "req-a", Decimal("3")),), Decimal("0")),
            AttemptAllocation("b", Decimal("2"), (CreditPortion("b", "req-b", Decimal("2")),), Decimal("0")),
        ),
        requirement_results=(
            RequirementResult("req-a", "PASS", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "COMPLETE", "VERIFIED"),
            RequirementResult("req-b", "PASS", Decimal("2"), Decimal("2"), Decimal("0"), Decimal("2"), Decimal("0"), "COMPLETE", "VERIFIED"),
        ),
        source_earned_credits=Decimal("5"),
        recognized_credits=Decimal("5"),
        unallocated_credits=Decimal("0"),
        credit_conservation=True,
    )
    return attempts, requirements, allocation


def test_requirement_result_reconciliation_accepts_valid_multi_requirement_control():
    attempts, requirements, allocation = _requirement_reconciliation_fixture()

    statistics = build_statistics_v2(attempts, requirements, allocation)
    reconciliation = statistics["credit_ledger"]["requirement_reconciliation"]

    assert reconciliation["ok"] is True
    assert statistics["credit_ledger"]["conservation"]["ok"] is True
    assert [item["status"] for item in statistics["requirement_metrics"]["items"]] == ["PASS", "PASS"]


def test_requirement_result_pass_on_wrong_requirement_fails_closed():
    attempts, requirements, allocation = _requirement_reconciliation_fixture()
    wrong_results = (
        RequirementResult("req-a", "PASS", Decimal("3"), Decimal("2"), Decimal("0"), Decimal("2"), Decimal("0"), "COMPLETE", "VERIFIED"),
        RequirementResult("req-b", "PASS", Decimal("2"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "COMPLETE", "VERIFIED"),
    )
    allocation = AllocationResult(
        status=allocation.status,
        allocations=allocation.allocations,
        requirement_results=wrong_results,
        source_earned_credits=allocation.source_earned_credits,
        recognized_credits=allocation.recognized_credits,
        unallocated_credits=allocation.unallocated_credits,
        credit_conservation=True,
    )

    statistics = build_statistics_v2(attempts, requirements, allocation)
    ledger = statistics["credit_ledger"]

    assert ledger["conservation"]["status"] == "UNKNOWN"
    assert "REQUIREMENT_RESULT_EXCLUSIVE_MISMATCH" in ledger["conservation"]["reason_codes"]
    assert all(item["status"] == "UNKNOWN" for item in statistics["requirement_metrics"]["items"])
    assert build_chart_datasets(statistics)["f5"]["available"] is False


def test_unknown_exclusive_requirement_target_invalidates_reconciliation():
    attempts = (CourseAttempt("a", "A", "甲", Decimal("3"), Decimal("3"), "114-1", status="PASS"),)
    requirements = (RequirementSpec("req-a", "甲要求", Decimal("3"), bucket="required", kind="NAMED_COURSE"),)
    allocation = {
        "status": "PASS",
        "allocations": (
            {
                "attempt_id": "a",
                "source_credits": "3",
                "unallocated_credits": "0",
                "portions": (
                    {"attempt_id": "a", "requirement_id": "unknown", "credits": "3", "allocation_kind": "EXCLUSIVE"},
                ),
            },
        ),
        "requirement_results": (
            {"requirement_id": "req-a", "status": "FAIL", "required_credits": "3", "exclusive_credits": "0", "shared_shadow_credits": "0", "effective_credits": "0", "deficit": "3", "coverage_state": "COMPLETE", "evidence_state": "VERIFIED"},
        ),
        "source_earned_credits": "3",
        "credit_conservation": True,
    }

    statistics = build_statistics_v2(attempts, requirements, allocation)
    ledger = statistics["credit_ledger"]

    assert ledger["conservation"]["status"] == "UNKNOWN"
    assert "ALLOCATION_PORTION_UNKNOWN_REQUIREMENT" in ledger["conservation"]["reason_codes"]
    assert statistics["requirement_metrics"]["items"][0]["status"] == "UNKNOWN"


def test_duplicate_requirement_result_ids_invalidate_reconciliation():
    attempts, requirements, allocation = _requirement_reconciliation_fixture()
    duplicate_results = allocation.requirement_results + (allocation.requirement_results[0],)
    allocation = {
        "status": "PASS",
        "allocations": allocation.allocations,
        "requirement_results": duplicate_results,
        "source_earned_credits": "5",
        "credit_conservation": True,
    }

    statistics = build_statistics_v2(attempts, requirements, allocation)
    reconciliation = statistics["credit_ledger"]["requirement_reconciliation"]

    assert reconciliation["ok"] is False
    assert "REQUIREMENT_RESULT_ID_DUPLICATE" in reconciliation["reason_codes"]
    assert statistics["credit_ledger"]["conservation"]["status"] == "UNKNOWN"
    assert all(item["status"] == "UNKNOWN" for item in statistics["requirement_metrics"]["items"])


@pytest.mark.parametrize(
    ("extra_result", "reason_code"),
    (
        ({"requirement_id": "not-known", "status": "UNKNOWN"}, "REQUIREMENT_RESULT_UNKNOWN_ID"),
        ({"requirement_id": "", "status": "UNKNOWN"}, "REQUIREMENT_RESULT_ID_MISSING"),
    ),
)
def test_unknown_or_missing_requirement_result_ids_fail_closed(extra_result, reason_code):
    attempts, requirements, allocation = _requirement_reconciliation_fixture()
    allocation = {
        "status": "PASS",
        "allocations": allocation.allocations,
        "requirement_results": allocation.requirement_results + (extra_result,),
        "source_earned_credits": "5",
        "credit_conservation": True,
    }

    statistics = build_statistics_v2(attempts, requirements, allocation)
    reconciliation = statistics["credit_ledger"]["requirement_reconciliation"]

    assert reconciliation["ok"] is False
    assert reason_code in reconciliation["reason_codes"]
    assert statistics["credit_ledger"]["conservation"]["status"] == "UNKNOWN"
    assert all(item["status"] == "UNKNOWN" for item in statistics["requirement_metrics"]["items"])


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    (
        ("required_credits", "NaN", "REQUIREMENT_RESULT_REQUIRED_CREDITS_INVALID"),
        ("exclusive_credits", "-1", "REQUIREMENT_RESULT_EXCLUSIVE_CREDITS_INVALID"),
    ),
)
def test_nonfinite_or_negative_requirement_result_fields_fail_closed(field, value, reason_code):
    attempts, requirements, allocation = _requirement_reconciliation_fixture()
    result = {
        "requirement_id": "req-a",
        "status": "PASS",
        "required_credits": "3",
        "exclusive_credits": "3",
        "shared_shadow_credits": "0",
        "effective_credits": "3",
        "deficit": "0",
        "coverage_state": "COMPLETE",
        "evidence_state": "VERIFIED",
    }
    result[field] = value
    allocation = {
        "status": "PASS",
        "allocations": allocation.allocations,
        "requirement_results": (result, allocation.requirement_results[1]),
        "source_earned_credits": "5",
        "credit_conservation": True,
    }

    statistics = build_statistics_v2(attempts, requirements, allocation)
    ledger = statistics["credit_ledger"]

    assert ledger["conservation"]["status"] == "UNKNOWN"
    assert reason_code in ledger["requirement_reconciliation"]["reason_codes"]
    assert all(item["status"] == "UNKNOWN" for item in statistics["requirement_metrics"]["items"])


def test_requirement_result_deficit_and_status_mismatch_fail_closed():
    attempts, requirements, allocation = _requirement_reconciliation_fixture()
    mismatch = {
        "requirement_id": "req-a",
        "status": "PASS",
        "required_credits": "3",
        "exclusive_credits": "3",
        "shared_shadow_credits": "0",
        "effective_credits": "3",
        "deficit": "1",
        "coverage_state": "COMPLETE",
        "evidence_state": "VERIFIED",
    }
    allocation = {
        "status": "PASS",
        "allocations": allocation.allocations,
        "requirement_results": (mismatch, allocation.requirement_results[1]),
        "source_earned_credits": "5",
        "credit_conservation": True,
    }

    statistics = build_statistics_v2(attempts, requirements, allocation)
    reconciliation = statistics["credit_ledger"]["requirement_reconciliation"]

    assert reconciliation["ok"] is False
    assert "REQUIREMENT_RESULT_DEFICIT_MISMATCH" in reconciliation["reason_codes"]
    assert "REQUIREMENT_RESULT_STATUS_MISMATCH" in reconciliation["reason_codes"]
    assert all(item["status"] == "UNKNOWN" for item in statistics["requirement_metrics"]["items"])


def test_target_only_aggregate_is_not_a_primary_f11_gate():
    attempt = CourseAttempt("a", "A", "目標", Decimal("3"), Decimal("3"), "114-1", status="PASS")
    requirement = RequirementSpec(
        "target-total", "目標總學分", Decimal("30"), bucket="total", kind="AGGREGATE", owner="TARGET",
        coverage_state=COMPLETE, evidence_state=VERIFIED,
    )
    allocation = AllocationResult(
        status="PASS",
        allocations=(AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "target-total", Decimal("3")),), Decimal("0")),),
        requirement_results=(RequirementResult("target-total", "FAIL", Decimal("30"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("27"), "COMPLETE", "VERIFIED"),),
        source_earned_credits=Decimal("3"), recognized_credits=Decimal("3"), unallocated_credits=Decimal("0"), credit_conservation=True,
    )

    statistics = build_statistics_v2(
        (attempt,), (requirement,), allocation,
        decisions={"primary_graduation": {"status": "FAIL", "requirement_ids": ("target-total",)}},
    )
    gate = statistics["program_progress"]["primary"]["aggregate_credit_progress"]

    assert gate["available"] is False
    assert gate["detail_code"] == "PRIMARY_AGGREGATE_OWNER_INVALID"
    assert build_chart_datasets(statistics)["f11"]["available"] is False


def test_cross_owner_exclusive_credits_cannot_inflate_primary_f11_numerator():
    attempt = CourseAttempt("a", "A", "跨域", Decimal("5"), Decimal("5"), "114-1", status="PASS")
    requirements = (
        RequirementSpec("primary-total", "主修總學分", Decimal("128"), bucket="total", kind="AGGREGATE", owner="PRIMARY", coverage_state=COMPLETE, evidence_state=VERIFIED),
        RequirementSpec("target-req", "雙主修要求", Decimal("3"), bucket="double_major", kind="NAMED_COURSE", owner="TARGET", coverage_state=COMPLETE, evidence_state=VERIFIED),
    )
    allocation = AllocationResult(
        status="FAIL",
        allocations=(
            AttemptAllocation("a", Decimal("5"), (
                CreditPortion("a", "primary-total", Decimal("2")),
                CreditPortion("a", "target-req", Decimal("3")),
            ), Decimal("0")),
        ),
        requirement_results=(
            RequirementResult("primary-total", "FAIL", Decimal("128"), Decimal("2"), Decimal("0"), Decimal("2"), Decimal("126"), "COMPLETE", "VERIFIED"),
            RequirementResult("target-req", "PASS", Decimal("3"), Decimal("3"), Decimal("2"), Decimal("5"), Decimal("0"), "COMPLETE", "VERIFIED"),
        ),
        source_earned_credits=Decimal("5"), recognized_credits=Decimal("5"), unallocated_credits=Decimal("0"), credit_conservation=True,
        shadow_allocations=(CreditPortion("a", "target-req", Decimal("2"), "SHARED_SHADOW"),),
    )

    statistics = build_statistics_v2(
        (attempt,), requirements, allocation,
        decisions={"primary_graduation": {"status": "FAIL", "requirement_ids": ("primary-total",)}},
    )
    charts = build_chart_datasets(statistics)

    assert charts["f11"]["available"] is True
    assert charts["f11"]["completed"] == "2"
    assert charts["f11"]["completed"] != statistics["credit_ledger"]["exclusive_allocated_credits"]
    assert statistics["credit_ledger"]["shared_shadow_credits"] == "2"


def test_nonunique_primary_aggregate_fails_closed():
    attempts = (CourseAttempt("a", "A", "核心", Decimal("3"), Decimal("3"), "114-1", status="PASS"),)
    requirements = (
        RequirementSpec("total-a", "總學分 A", Decimal("128"), bucket="total", kind="AGGREGATE", owner="PRIMARY", coverage_state=COMPLETE, evidence_state=VERIFIED),
        RequirementSpec("total-b", "總學分 B", Decimal("128"), bucket="total", kind="AGGREGATE", owner="PRIMARY", coverage_state=COMPLETE, evidence_state=VERIFIED),
    )
    allocation = AllocationResult(
        status="FAIL",
        allocations=(AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "total-a", Decimal("3")),), Decimal("0")),),
        requirement_results=(
            RequirementResult("total-a", "FAIL", Decimal("128"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("125"), "COMPLETE", "VERIFIED"),
            RequirementResult("total-b", "FAIL", Decimal("128"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("128"), "COMPLETE", "VERIFIED"),
        ),
        source_earned_credits=Decimal("3"), recognized_credits=Decimal("3"), unallocated_credits=Decimal("0"), credit_conservation=True,
    )
    statistics = build_statistics_v2(
        attempts, requirements, allocation,
        decisions={"primary_graduation": {"status": "FAIL", "requirement_ids": ("total-a", "total-b")}},
    )

    gate = statistics["program_progress"]["primary"]["aggregate_credit_progress"]
    assert gate["available"] is False
    assert gate["detail_code"] == "PRIMARY_AGGREGATE_NOT_UNIQUE"


def test_incomplete_requirement_evidence_forces_f5_unknown_at_apparent_100_percent():
    attempt = CourseAttempt("a", "A", "待核實", Decimal("3"), Decimal("3"), "114-1", status="PASS")
    requirement = RequirementSpec(
        "partial", "待核實要求", Decimal("3"), bucket="required", kind="NAMED_COURSE",
        coverage_state="PARTIAL", evidence_state=VERIFIED,
    )
    allocation = AllocationResult(
        status="UNKNOWN",
        allocations=(AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "partial", Decimal("3")),), Decimal("0")),),
        requirement_results=(RequirementResult("partial", "PASS", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "PARTIAL", "VERIFIED"),),
        source_earned_credits=Decimal("3"), recognized_credits=Decimal("3"), unallocated_credits=Decimal("0"), credit_conservation=True,
    )
    statistics = build_statistics_v2((attempt,), (requirement,), allocation)
    row = statistics["requirement_metrics"]["items"][0]

    assert row["status"] == "UNKNOWN"
    assert row["status_reason_code"] == "INCOMPLETE_EVIDENCE_OR_COVERAGE"
    assert build_chart_datasets(statistics)["f5"]["groups"][0]["rows"][0]["status"] == "UNKNOWN"


def test_stale_v2_statistics_payload_fails_closed_instead_of_redigesting():
    attempt = CourseAttempt("a", "A", "核心", Decimal("3"), Decimal("3"), "114-1", status="PASS")
    requirement = RequirementSpec("req", "要求", Decimal("3"), bucket="required", kind="NAMED_COURSE")
    allocation = AllocationResult(
        status="PASS",
        allocations=(AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "req", Decimal("3")),), Decimal("0")),),
        requirement_results=(RequirementResult("req", "PASS", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "COMPLETE", "VERIFIED"),),
        source_earned_credits=Decimal("3"), recognized_credits=Decimal("3"), unallocated_credits=Decimal("0"), credit_conservation=True,
    )
    valid = build_statistics_v2((attempt,), (requirement,), allocation)
    stale = dict(valid)
    stale["credit_ledger"] = {**valid["credit_ledger"], "source_earned_credits": "999"}
    normalized = statistics_projection_from_payload(
        {
            "attempts": (attempt,), "requirements": (requirement,), "allocation": allocation,
            "decisions": {}, "statistics": stale,
        }
    )

    assert normalized["statistics_validation"]["valid"] is False
    assert normalized["statistics_validation"]["reason_code"] == "STALE_STATISTICS_PAYLOAD"
    assert normalized["credit_ledger"]["source_earned_credits"] != "999"
    assert normalized["credit_ledger"]["conservation"]["ok"] is False
    assert build_chart_datasets(normalized)["f1"]["available"] is False


def test_projection_namespace_wrapper_returns_same_screen_view():
    snapshot = _snapshot()

    from snapshot_renderer import build_snapshot_projection as renderer_projection

    via_projection = build_snapshot_projection(snapshot)
    via_renderer = renderer_projection(snapshot)

    assert via_projection == via_renderer
    assert via_projection["statistics_digest"] == via_projection["chart_datasets"]["statistics_digest"]
    assert re.fullmatch(r"sha256:[0-9a-f]{24}", via_projection["statistics_digest"])


def test_statistics_projection_uses_the_same_chart_dataset_identity():
    snapshot = _snapshot()
    statistics_view = build_snapshot_statistics_projection(snapshot)
    screen_view = build_snapshot_projection(snapshot)

    assert statistics_view["schema_version"] == STATISTICS_SCHEMA_VERSION
    assert statistics_view["statistics_digest"] == screen_view["statistics_digest"]
    assert statistics_view["chart_datasets"] == screen_view["chart_datasets"]
