"""Execute the actual compiled secondary constraints on synthetic credit ledgers."""

from decimal import Decimal

import pytest

from allocation_engine import FAIL, NOT_MEMBER, PASS, VERIFIED, CourseAttempt, EquivalencyBinding, allocate_credits
from curriculum_registry import get_curriculum
from graduation_service import _compile_requirements


def _context(role):
    curriculum_id = "minor:111:math" if role == "minor" else "target:double_major:111:math"
    specs, _, _ = _compile_requirements(get_curriculum(curriculum_id), scope=role)
    quota = next(spec for spec in specs if spec.subset_constraints)
    return specs, quota


def _attempt(key, name, amount, *, pools=(), software=False):
    memberships = [
        ("math-secondary:111:eligible-target-credit", VERIFIED, "official:test-total-membership", "catalog"),
        ("math-secondary:111:software", VERIFIED if software else NOT_MEMBER,
         "official:test-software-membership", "catalog" if software else "registry_negative"),
        *((pool, VERIFIED, "official:test-elective-pool", "catalog") for pool in pools),
    ]
    return CourseAttempt(key, key, name, amount, amount, "111-1", pool_membership_evidence=tuple(memberships))


def _named_attempts(specs, quota):
    return tuple(_attempt(f"named-{i}", spec.name, spec.credits_required)
                 for i, spec in enumerate(specs) if spec.requirement_id != quota.requirement_id)


@pytest.mark.parametrize(("role", "total", "expected"), [
    ("target", 39, FAIL), ("target", 40, PASS), ("minor", 19, FAIL), ("minor", 20, PASS),
])
def test_compiled_total_observes_named_and_elective_credits_without_an_extra_consumer(role, total, expected):
    specs, quota = _context(role)
    named = _named_attempts(specs, quota)
    remainder = Decimal(total) - sum(item.credits for item in named)
    elective = _attempt("ordinary", "測試用已核實選修學分", remainder, pools=quota.eligible_pool_ids)
    result = allocate_credits((*named, elective), specs, search_limit=100000)
    total_gate = next(item for item in result.subset_results if item["constraint_id"].endswith(":total"))
    assert total_gate["status"] == expected
    assert result.status == expected
    assert result.feasible_witness is (expected == PASS)
    assert result.credit_conservation
    assert result.recognized_credits == Decimal(total)
    assert set(total_gate["observed_requirement_ids"]) == {spec.requirement_id for spec in specs}


@pytest.mark.parametrize(("amounts", "expected"), [((3,), PASS), ((2, 1), FAIL)])
def test_compiled_optional_software_cap_counts_distinct_partially_approved_attempts(amounts, expected):
    specs, quota = _context("minor")
    named = _named_attempts(specs, quota)
    ordinary = _attempt("ordinary", "測試用其他選修學分", 9, pools=quota.eligible_pool_ids)
    # No direct elective membership: each software source uses the exact
    # approved partial binding, so the solver cannot replace 2+1 with 3+0.
    software = tuple(_attempt(f"software-{i}", f"測試軟體課{i}", 3, software=True) for i in range(len(amounts)))
    bindings = tuple(EquivalencyBinding(
        binding_id=f"approval-{i}", source_attempt_id=source.attempt_id,
        target_requirement_id=quota.requirement_id, approved_credits=amount,
        evidence_state=VERIFIED, authority="系所核准測試資料", evidence_reference=f"official:test-approval-{i}",
        decision="APPROVED",
    ) for i, (source, amount) in enumerate(zip(software, amounts, strict=True)))
    result = allocate_credits((*named, ordinary, *software), specs, bindings, search_limit=100000)
    cap = next(item for item in result.subset_results if item["constraint_id"].endswith(":software-max"))
    assert cap["maximum_course_count"] == 1
    assert cap["verified_course_count"] == len(amounts)
    assert cap["verified_credits"] == 3
    assert cap["status"] == expected
    assert result.status == expected
    assert result.feasible_witness is (expected == PASS)
    assert result.credit_conservation
