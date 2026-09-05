"""Focused source-contract checks for the Math secondary catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

import pytest

from curriculum_registry import get_curriculum
from graduation_service import _compile_requirements, _safe_curriculum

COHORTS = ("111", "112", "113", "114", "115")
ROLES = (("minor", "minor"), ("double_major", "target"))
SOFTWARE_BY_COHORT = {
    "111": {
        "數學軟體應用與實作(A)",
        "數學軟體應用與實作(B)",
        "數學軟體應用與實作(C)",
    },
    "112": {
        "數學軟體應用與實作(A)",
        "數學軟體應用與實作(B)",
        "數學軟體應用與實作(C)",
    },
    "113": {"Matlab程式設計", "Python程式設計"},
    "114": {"Matlab程式設計", "Python程式設計"},
    "115": {"Matlab程式設計", "Python程式設計"},
}


def _record(cohort: str, role: str) -> dict:
    curriculum_id = f"minor:{cohort}:math" if role == "minor" else f"target:double_major:{cohort}:math"
    return get_curriculum(curriculum_id)


def _elective_row(record: Mapping[str, object]) -> Mapping[str, object]:
    return next(
        row
        for row in record["course_catalog"]  # type: ignore[index]
        if isinstance(row, Mapping) and row.get("choice_group") == "math_secondary_elective"
    )


def _membership_assertion(metadata: Mapping[str, object], membership_id: str) -> Mapping[str, object]:
    assertions = metadata.get("membership_assertions", ())
    if isinstance(assertions, Mapping):
        assertions = (assertions,)
    return next(
        assertion
        for assertion in assertions  # type: ignore[union-attr]
        if isinstance(assertion, Mapping) and assertion.get("membership_id") == membership_id
    )


@pytest.mark.parametrize("cohort", COHORTS)
@pytest.mark.parametrize(("role", "scope"), ROLES)
def test_math_secondary_pool_has_source_backed_software_membership(
    cohort: str,
    role: str,
    scope: str,
) -> None:
    record = _record(cohort, role)
    row = _elective_row(record)
    row_id = str(row["requirement_id"])
    software_membership_id = f"math-secondary:{cohort}:software"
    expected_software = SOFTWARE_BY_COHORT[cohort]

    assert row["component"] == "quota"
    assert row["component_type"] == "quota"
    assert row["lecture_or_lab"] == "quota"
    assert row["is_lab"] is False
    candidates = set(row["eligible_course_names"])  # type: ignore[arg-type]
    assert expected_software <= candidates

    subset_constraints = tuple(row["subset_constraints"])  # type: ignore[arg-type]
    assert len(subset_constraints) == 2
    software_constraint = next(
        constraint
        for constraint in subset_constraints
        if constraint.get("membership_id") == software_membership_id
    )
    assert software_constraint["amount_semantics"] == "MAXIMUM"
    assert software_constraint["maximum_credits"] == 3
    assert software_constraint["maximum_course_count"] == 1
    assert tuple(software_constraint["observed_requirement_ids"]) == (row_id,)
    assert software_constraint["source_reference"]

    total_constraint = next(
        constraint
        for constraint in subset_constraints
        if constraint.get("membership_id") == f"math-secondary:{cohort}:eligible-target-credit"
    )
    assert total_constraint["amount_semantics"] == "MINIMUM"
    assert total_constraint["minimum_credits"] == (20.0 if role == "minor" else 40.0)
    row_ids = {
        str(item.get("requirement_id") or item.get("id"))
        for item in record["course_catalog"]  # type: ignore[index]
    }
    assert set(total_constraint["observed_requirement_ids"]) == row_ids
    assert total_constraint["source_reference"]

    metadata_by_name = row["candidate_metadata"]  # type: ignore[assignment]
    for software_name in expected_software:
        metadata = metadata_by_name[software_name]
        assert software_membership_id in metadata["membership_ids"]
        assertion = _membership_assertion(metadata, software_membership_id)
        assert assertion["state"] == "VERIFIED"
        assert assertion["kind"] == "official_handbook_membership"
        assert tuple(assertion["observed_requirement_ids"]) == (row_id,)
        assert assertion["source_reference"]

    ordinary_name = next(name for name in candidates if name not in expected_software)
    ordinary_assertion = _membership_assertion(metadata_by_name[ordinary_name], software_membership_id)
    assert ordinary_assertion["state"] == "NOT_MEMBER"
    assert ordinary_assertion["kind"] == "registry_negative"
    assert tuple(ordinary_assertion["observed_requirement_ids"]) == (row_id,)

    # The cap is evaluated on the observed subset, so two ordinary three-credit
    # software attempts cannot be represented as one allowed course.
    assert sum(float(metadata_by_name[name]["credits"]) for name in expected_software) >= 6
    assert software_constraint["maximum_credits"] < 6
    assert software_constraint["maximum_course_count"] < len(expected_software)
    assert scope in {"minor", "target"}


@pytest.mark.parametrize("cohort", COHORTS)
@pytest.mark.parametrize(("role", "scope"), ROLES)
def test_math_secondary_constraints_use_one_elective_consumer(
    cohort: str,
    role: str,
    scope: str,
) -> None:
    record = _record(cohort, role)
    specs, _metadata, _provenance = _compile_requirements(record, scope=scope)
    constrained_specs = [spec for spec in specs if spec.subset_constraints]

    assert len(constrained_specs) == 1
    elective = constrained_specs[0]
    expected_minimum = (
        Decimal("12")
        if role == "minor"
        else Decimal("18")
        if cohort in {"111", "112"}
        else Decimal("26")
    )
    expected_maximum = Decimal("20") if role == "minor" else Decimal("40")
    expected_total_minimum = Decimal("20") if role == "minor" else Decimal("40")
    assert elective.credits_required == expected_minimum
    assert elective.max_credits == expected_maximum
    assert len(elective.subset_constraints) == 2
    assert len({spec.requirement_id for spec in specs}) == len(specs)

    software_constraint = next(
        constraint
        for constraint in elective.subset_constraints
        if constraint.get("membership_id") == f"math-secondary:{cohort}:software"
    )
    total_constraint = next(
        constraint
        for constraint in elective.subset_constraints
        if constraint.get("membership_id") == f"math-secondary:{cohort}:eligible-target-credit"
    )
    assert software_constraint["maximum_credits"] == 3
    assert total_constraint["minimum_credits"] == expected_total_minimum
    assert software_constraint["source_reference"]
    assert total_constraint["source_reference"]


@pytest.mark.parametrize("cohort", ("111", "112"))
def test_math_primary_subset_observations_bind_to_department_consumer(cohort: str) -> None:
    record = get_curriculum(f"primary:{cohort}:math")
    department_row = next(
        row
        for row in record["course_catalog"]
        if row.get("bucket") == "math_department_elective"
    )
    raw_requirement_id = department_row["requirement_id"]
    policy_constraints = department_row["policy"]["subset_constraints"]

    assert len(policy_constraints) == 2
    assert all(tuple(item["observed_requirement_ids"]) == (raw_requirement_id,) for item in policy_constraints)

    safe_record = _safe_curriculum(record)
    safe_department_row = next(
        row
        for row in safe_record["course_catalog"]
        if row.get("bucket") == "math_department_elective"
    )
    assert safe_department_row["requirement_id"] == raw_requirement_id
    assert all(
        tuple(item["observed_requirement_ids"]) == (raw_requirement_id,)
        for item in safe_department_row["policy"]["subset_constraints"]
    )

    specs, _metadata, _provenance = _compile_requirements(record, scope="primary")
    department_spec = next(
        spec
        for spec in specs
        if spec.requirement_id.endswith("pool.math_department_elective")
    )
    assert all(
        tuple(item["observed_requirement_ids"]) == (department_spec.requirement_id,)
        for item in department_spec.subset_constraints
    )
