from decimal import Decimal

import pytest

from allocation_engine import (
    COMPLETE,
    CONFLICTED,
    FAIL,
    NOT_MEMBER,
    PASS,
    UNKNOWN,
    VERIFIED,
    AllocationResult,
    AttemptAllocation,
    CourseAttempt,
    CreditPortion,
    EquivalencyBinding,
    RequirementSpec,
    WaiverDecision,
    _subset_constraint_evaluations,
    allocate_credits,
    canonicalize_overflow_routes,
)


@pytest.mark.parametrize('evidence_kind,source,can_prove', [
    ('public_catalog', 'official:catalog', True),
    ('public_catalog', '', False),
    ('legacy', 'official:catalog', False),
])
def test_public_membership_without_named_identity_only_proves_aggregate(evidence_kind, source, can_prove):
    course = CourseAttempt('public', '', '公開分類課程', Decimal('2'), Decimal('2'), '112-1',
                           identity_status=UNKNOWN,
                           pool_membership_evidence=(('ge', VERIFIED, source, evidence_kind),))
    quota = RequirementSpec('quota', credits_required=2, eligible_pool_ids=('ge',), kind='AGGREGATE')
    result = allocate_credits((course,), (quota,))
    assert (result.status == PASS) is can_prove
    named = RequirementSpec('named', credits_required=2, eligible_pool_ids=('ge',), kind='NAMED_COURSE')
    assert allocate_credits((course,), (named,)).status != PASS


@pytest.mark.parametrize('required,expected', [(2, PASS), (4, UNKNOWN)])
def test_unused_unknown_candidate_does_not_poison_verified_completed_requirement(required, expected):
    good = CourseAttempt('good', '', '已核實課程', Decimal('2'), Decimal('2'), '112-1',
                         identity_status=UNKNOWN,
                         pool_membership_evidence=(('ge', VERIFIED, 'official:catalog', 'public_catalog'),))
    uncertain = CourseAttempt('uncertain', '', '待核對課程', Decimal('2'), Decimal('2'), '112-1',
                              identity_status=UNKNOWN,
                              pool_membership_evidence=(('ge', UNKNOWN, 'official:catalog', 'public_catalog'),))
    quota = RequirementSpec('quota', credits_required=required, eligible_pool_ids=('ge',), kind='AGGREGATE')
    result = allocate_credits((good, uncertain), (quota,))
    assert result.status == expected
    assert result.requirement_results[0].effective_credits == Decimal('2')
    assert result.feasible_witness is (expected == PASS)


def test_unverified_binding_still_blocks_an_otherwise_complete_requirement():
    good = CourseAttempt('good', 'official-course', '已核實課程', Decimal('2'), Decimal('2'), '112-1')
    uncertain = CourseAttempt('uncertain', '', '待核對課程', Decimal('2'), Decimal('2'), '112-1', identity_status=UNKNOWN)
    quota = RequirementSpec('quota', credits_required=2, eligible_course_ids=('official-course',))
    invalid = EquivalencyBinding(binding_id='pending', source_attempt_id='uncertain', target_requirement_id='quota',
                                 approved_credits=2, evidence_state=UNKNOWN)
    result = allocate_credits((good, uncertain), (quota,), (invalid,))
    assert result.status != PASS
    assert not result.feasible_witness


@pytest.mark.parametrize('free_minimum,can_pass', [(3, True), (4, False)])
def test_large_transcript_seed_preserves_exact_fit_and_checks_all_constraints(free_minimum, can_pass):
    fixed = tuple(CourseAttempt(f'fixed-{i}', f'course-{i}', f'必修{i}', 1, 1, '111-1') for i in range(25))
    fixed_requirements = tuple(RequirementSpec(f'fixed-{i}', credits_required=1,
                                              eligible_course_ids=(f'course-{i}',)) for i in range(25))
    courses = (*fixed, CourseAttempt('a-big', 'big', '三學分課', 3, 3, '111-1'),
               CourseAttempt('z-one-a', 'one-a', '一學分甲', 1, 1, '111-1'),
               CourseAttempt('z-one-b', 'one-b', '一學分乙', 1, 1, '111-1'))
    requirements = (*fixed_requirements,
                    RequirementSpec('a-alternative', credits_required=1, kind='AGGREGATE',
                                    eligible_course_ids=('big', 'one-a', 'one-b')),
                    RequirementSpec('b-alternative', credits_required=1, kind='AGGREGATE',
                                    eligible_course_ids=('one-a', 'one-b')),
                    RequirementSpec('free', credits_required=free_minimum, kind='AGGREGATE',
                                    eligible_course_ids=('big', 'one-a', 'one-b')))
    result = allocate_credits(courses, requirements, search_limit=1)
    assert result.credit_conservation
    assert result.feasible_witness is can_pass
    assert (result.status == PASS) is can_pass
    if can_pass:
        big = next(item for item in result.allocations if item.attempt_id == 'a-big')
        assert [(item.requirement_id, item.credits) for item in big.portions] == [('free', Decimal('3'))]
        assert result.optimality == 'BOUNDED_NOT_COMPLETE'


def attempt(
    attempt_id,
    course_id,
    credits,
    *,
    term="114-1",
    repeat_group_id=None,
    pools=(),
    course_kind="LECTURE",
    effective_attempt=False,
    repeat_selection_evidence_state="UNKNOWN",
):
    return CourseAttempt(
        attempt_id=attempt_id,
        course_id=course_id,
        course_name=course_id,
        credits=credits,
        earned_credits=credits,
        academic_term=term,
        repeat_group_id=repeat_group_id,
        pool_memberships=pools,
        course_kind=course_kind,
        identity_status=VERIFIED,
        grade_evidence_state=VERIFIED,
        effective_attempt=effective_attempt,
        repeat_selection_evidence_state=repeat_selection_evidence_state,
    )


def requirement(
    requirement_id,
    credits,
    *,
    eligible_course_ids=(),
    eligible_pool_ids=(),
    overflow_routes=(),
    max_credits=None,
    course_kind=None,
    coverage_state=COMPLETE,
    repeatable=False,
    repeat_policy="BEST_ATTEMPT_ONLY",
    waiver=False,
    required=True,
    owner="",
    domain="",
    subset_constraints=(),
    kind="",
    curriculum_version="",
    program_slug="",
    track_slug="",
):
    return RequirementSpec(
        requirement_id=requirement_id,
        name=requirement_id,
        credits_required=credits,
        max_credits=max_credits,
        eligible_course_ids=eligible_course_ids,
        eligible_pool_ids=eligible_pool_ids,
        overflow_routes=overflow_routes,
        course_kind=course_kind,
        coverage_state=coverage_state,
        evidence_state=VERIFIED,
        required=required,
        repeatable=repeatable,
        repeat_policy=repeat_policy,
        waiver=waiver,
        owner=owner,
        domain=domain,
        kind=kind,
        curriculum_version=curriculum_version,
        program_slug=program_slug,
        track_slug=track_slug,
        subset_constraints=subset_constraints,
    )


def allocation_for(result, requirement_id):
    return tuple(
        portion
        for allocation in result.allocations
        for portion in allocation.portions
        if portion.requirement_id == requirement_id
    )


def requirement_result(result, requirement_id):
    return next(item for item in result.requirement_results if item.requirement_id == requirement_id)


def test_dataclasses_are_frozen_and_credit_values_are_decimal():
    course = attempt("a", "A", "3")

    assert course.credits == Decimal("3")
    with pytest.raises((AttributeError, TypeError)):
        course.credits = Decimal("4")


def test_permuting_inputs_produces_identical_result():
    attempts = (
        attempt("b", "B", 3, pools=("core",)),
        attempt("a", "A", 3, pools=("core",)),
    )
    requirements = (
        requirement("r-b", 3, eligible_course_ids=("B",)),
        requirement("r-a", 3, eligible_course_ids=("A",)),
    )

    first = allocate_credits(attempts, requirements)
    second = allocate_credits(tuple(reversed(attempts)), tuple(reversed(requirements)))

    assert first == second
    assert first.allocations == second.allocations


def test_flexible_course_and_constrained_course_choose_gate_maximizing_assignment():
    flexible = attempt("flexible", "FLEX", 3, pools=("x", "y"))
    constrained = attempt("constrained", "ONLY-X", 3, pools=("x",))
    requirements = (
        requirement("X", 3, eligible_pool_ids=("x",)),
        requirement("Y", 3, eligible_pool_ids=("y",)),
    )

    result = allocate_credits((flexible, constrained), requirements)

    assert result.status == "PASS"
    assert allocation_for(result, "X")[0].attempt_id == "constrained"
    assert allocation_for(result, "Y")[0].attempt_id == "flexible"


def test_six_credit_attempt_respects_bucket_cap_and_explicit_overflow_route():
    source = attempt("six", "SIX", 6, pools=("core",))
    requirements = (
        requirement("core", 4, eligible_pool_ids=("core",), max_credits=4, overflow_routes=("elective",)),
        requirement("elective", 2, eligible_pool_ids=("elective",)),
    )

    result = allocate_credits((source,), requirements)

    portions = allocation_for(result, "core") + allocation_for(result, "elective")
    assert tuple(portion.credits for portion in portions) == (Decimal("4"), Decimal("2"))
    assert result.source_earned_credits == Decimal("6")
    assert result.recognized_credits == Decimal("6")
    assert result.unallocated_credits == Decimal("0")
    assert result.credit_conservation


def test_residual_without_explicit_overflow_route_stays_unallocated():
    source = attempt("four", "FOUR", 4, pools=("core",))
    result = allocate_credits(
        (source,),
        (requirement("core", 3, eligible_pool_ids=("core",), max_credits=3),),
    )

    assert allocation_for(result, "core")[0].credits == Decimal("3")
    assert result.unallocated_credits == Decimal("1")
    assert result.credit_conservation
    assert result.status == "PASS"


def test_one_attempt_cannot_satisfy_two_exclusive_requirements():
    source = attempt("one", "ONE", 3, pools=("a", "b"))
    result = allocate_credits(
        (source,),
        (
            requirement("A", 3, eligible_pool_ids=("a",)),
            requirement("B", 3, eligible_pool_ids=("b",)),
        ),
    )

    assert len(result.allocations) == 1
    assert sum((portion.credits for portion in result.allocations[0].portions), Decimal("0")) == Decimal("3")
    assert sum(item.status == "PASS" for item in result.requirement_results) == 1
    assert result.status == "UNKNOWN"
    assert "ALLOCATION_AMBIGUOUS" in result.blockers


def test_parser_duplicates_collapse_but_distinct_positive_fixed_repeats_stay_unknown():
    first = attempt("same-row", "CALC", 3, term="113-1", repeat_group_id="calc", pools=("math",))
    duplicate = attempt("same-row", "CALC", 3, term="113-1", repeat_group_id="calc", pools=("math",))
    later_repeat = attempt("later-row", "CALC", 3, term="114-1", repeat_group_id="calc", pools=("math",))
    result = allocate_credits(
        (later_repeat, duplicate, first),
        (requirement("calc", 3, eligible_course_ids=("CALC",)),),
    )

    assert len(result.allocations) == 2
    assert all(not allocation.portions for allocation in result.allocations)
    assert result.status == "UNKNOWN"
    assert result.requirement_for("calc").status == "UNKNOWN"
    assert result.source_earned_credits == Decimal("6")
    assert result.unallocated_credits == Decimal("6")
    assert result.credit_conservation


def test_repeatable_requirements_can_consume_multiple_attempts_in_one_repeat_group():
    first = attempt("repeat-1", "REPEAT", 3, term="113-1", repeat_group_id="repeat", pools=("repeatable",))
    second = attempt("repeat-2", "REPEAT", 3, term="114-1", repeat_group_id="repeat", pools=("repeatable",))
    result = allocate_credits(
        (first, second),
        (
            requirement(
                "repeatable",
                6,
                eligible_pool_ids=("repeatable",),
                max_credits=6,
                repeatable=True,
            ),
        ),
    )

    portions = allocation_for(result, "repeatable")
    assert result.status == "PASS"
    assert tuple(portion.attempt_id for portion in portions) == ("repeat-1", "repeat-2")
    assert result.source_earned_credits == Decimal("6")
    assert result.recognized_credits == Decimal("6")
    assert result.credit_conservation


def test_mixed_repeat_policies_cannot_straddle_one_group_to_pass_both_requirements():
    fixed_attempt = attempt("fixed-attempt", "REPEAT", 3, term="113-1", repeat_group_id="repeat", pools=("fixed",))
    repeatable_attempt = attempt("repeatable-attempt", "REPEAT", 3, term="114-1", repeat_group_id="repeat", pools=("repeatable",))
    result = allocate_credits(
        (fixed_attempt, repeatable_attempt),
        (
            requirement("fixed", 3, eligible_pool_ids=("fixed",)),
            requirement("repeatable", 3, eligible_pool_ids=("repeatable",), repeatable=True),
        ),
    )

    statuses = {item.requirement_id: item.status for item in result.requirement_results}
    assert sum(status == "PASS" for status in statuses.values()) == 1
    assert not (statuses["fixed"] == "PASS" and statuses["repeatable"] == "PASS")
    assert result.credit_conservation


def test_multiple_positive_fixed_repeat_attempts_do_not_choose_by_ordering():
    lower = CourseAttempt(
        "lower", "REPEAT", "REPEAT", Decimal("3"), Decimal("2"), "113-1", repeat_group_id="repeat", identity_status=VERIFIED, grade_evidence_state=VERIFIED
    )
    better = CourseAttempt(
        "better", "REPEAT", "REPEAT", Decimal("4"), Decimal("4"), "114-1", repeat_group_id="repeat", identity_status=VERIFIED, grade_evidence_state=VERIFIED
    )
    result = allocate_credits(
        (lower, better),
        (requirement("fixed", 3, eligible_course_ids=("REPEAT",)),),
    )

    assert result.status == "UNKNOWN"
    assert not allocation_for(result, "fixed")
    assert result.source_earned_credits == Decimal("6")
    assert result.recognized_credits == Decimal("0")
    assert result.unallocated_credits == Decimal("6")
    assert result.credit_conservation


def test_multiple_positive_fixed_repeat_attempts_need_verified_effective_selection():
    first = attempt("A", "REPEAT", 3, term="114-1", repeat_group_id="repeat")
    later = attempt("C", "REPEAT", 3, term="115-1", repeat_group_id="repeat")
    result = allocate_credits(
        (first, later),
        (requirement("fixed", 3, eligible_course_ids=("REPEAT",)),),
    )

    assert result.status == "UNKNOWN"
    assert requirement_result(result, "fixed").status == "UNKNOWN"


def test_verified_effective_repeat_selection_allows_one_fixed_winner():
    first = attempt(
        "A",
        "REPEAT",
        3,
        term="114-1",
        repeat_group_id="repeat",
        effective_attempt=True,
        repeat_selection_evidence_state=VERIFIED,
    )
    later = attempt("C", "REPEAT", 3, term="115-1", repeat_group_id="repeat")
    result = allocate_credits(
        (first, later),
        (requirement("fixed", 3, eligible_course_ids=("REPEAT",)),),
    )

    assert result.status == "PASS"
    assert allocation_for(result, "fixed")[0].attempt_id == "A"
    assert result.source_earned_credits == Decimal("3")
    assert result.credit_conservation


def test_waiver_is_visible_but_adds_zero_earned_credit():
    waiver = CourseAttempt(
        attempt_id="waiver",
        course_id="WAIVED",
        course_name="WAIVED",
        credits=3,
        earned_credits=3,
        status="WAIVER",
    )
    result = allocate_credits(
        (waiver,),
        (requirement("waiver-req", 3, eligible_course_ids=("WAIVED",), waiver=True),),
        waiver_decisions=(
            WaiverDecision(
                decision_id="waiver-decision",
                target_requirement_id="waiver-req",
                evidence_state=VERIFIED,
                authority="系所核准",
                evidence_reference="official:waiver-decision",
                decision="APPROVED",
            ),
        ),
    )

    assert result.allocations[0].portions[0].allocation_kind == "WAIVER"
    assert result.allocations[0].portions[0].credits == Decimal("0")
    assert result.source_earned_credits == Decimal("0")
    assert result.recognized_credits == Decimal("0")
    assert result.credit_conservation
    assert result.requirement_for("waiver-req").status == "PASS"
    assert result.requirement_for("waiver-req").waived


def test_partial_or_conflicted_coverage_cannot_pass_but_numeric_deficit_can_fail():
    source = attempt("known", "KNOWN", 3)
    partial = allocate_credits(
        (source,),
        (requirement("partial", 3, eligible_course_ids=("KNOWN",), coverage_state="PARTIAL"),),
    )
    conflict_deficit = allocate_credits(
        (),
        (requirement("conflict", 3, eligible_course_ids=("MISSING",), coverage_state="CONFLICTED"),),
    )

    assert partial.status == "UNKNOWN"
    assert not partial.pass_eligible
    assert conflict_deficit.status == "FAIL"


def test_aggregate_shared_numbers_without_exact_binding_count_zero():
    source = attempt("source", "PHYS", 3, pools=("primary",))
    result = allocate_credits(
        (source,),
        (
            requirement("primary", 3, eligible_pool_ids=("primary",)),
            requirement("target", 3, eligible_course_ids=("TARGET",)),
        ),
        bindings=(),
    )

    assert result.recognized_credits == Decimal("3")
    assert result.effective_recognized_credits == Decimal("3")
    assert result.shadow_allocations == ()
    assert result.requirement_for("target").shared_shadow_credits == Decimal("0")


def test_shared_shadow_requires_positive_exclusive_use_of_the_source_attempt():
    source = attempt("source", "PHYS", 3, pools=("primary",))
    binding = shared_binding("source-target", "source", "target", 3, source_requirement_id="primary")
    result = allocate_credits(
        (source,),
        (
            requirement("primary", 3, eligible_pool_ids=("other-primary",), owner="PRIMARY", domain="primary"),
            requirement("target", 3, eligible_course_ids=("TARGET",), owner="TARGET", domain="target"),
        ),
        (binding,),
    )

    assert result.shadow_allocations == ()
    assert result.requirement_for("target").shared_shadow_credits == Decimal("0")
    assert result.binding_assessments[0].status == "UNKNOWN"
    assert any(item.startswith("SHARED_SOURCE_USE_UNKNOWN:evidence:") for item in result.warnings)
    assert "source-target" not in str(result.warnings)
    assert result.status == "UNKNOWN"


def test_non_boolean_shared_flag_cannot_project_one_source_to_two_requirements():
    source = attempt("source", "PHYS", 3, pools=("primary",))
    binding = {
        "binding_id": "string-false-shared",
        "source_attempt_id": "source",
        "target_requirement_id": "target",
        "approved_credits": 3,
        "evidence_state": VERIFIED,
        "authority": "系所核准",
        "evidence_reference": "official:string-false-shared",
        "direction": "PRIMARY_TO_TARGET",
        "shared": "false",
        "source_requirement_id": "primary",
        "source_owner": "PRIMARY",
        "target_owner": "TARGET",
        "source_domain": "primary",
        "target_domain": "target",
        "decision": "APPROVED",
    }

    result = allocate_credits(
        (source,),
        (
            requirement("primary", 3, eligible_pool_ids=("primary",), owner="PRIMARY", domain="primary"),
            requirement("target", 3, eligible_course_ids=("TARGET",), owner="TARGET", domain="target"),
        ),
        (binding,),
    )

    primary_used = sum((portion.credits for portion in allocation_for(result, "primary")), Decimal("0"))
    target_used = result.requirement_for("target").effective_credits
    assert not (primary_used >= Decimal("3") and target_used >= Decimal("3"))
    assert result.status != "PASS"


def test_shared_shadows_are_capped_by_positive_exclusive_credits_per_source_attempt():
    source = attempt("source", "PHYS", 6, pools=("primary",))
    bindings = (
        shared_binding("source-target-a", "source", "target-a", 4, source_requirement_id="primary"),
        shared_binding("source-target-b", "source", "target-b", 4, source_requirement_id="primary"),
    )
    result = allocate_credits(
        (source,),
        (
            requirement("primary", 3, eligible_pool_ids=("primary",), max_credits=3, owner="PRIMARY", domain="primary"),
            requirement("target-a", 4, eligible_course_ids=("TARGET-A",), owner="TARGET", domain="target"),
            requirement("target-b", 4, eligible_course_ids=("TARGET-B",), owner="TARGET", domain="target"),
        ),
        bindings,
    )

    source_exclusive = sum(
        (
            portion.credits
            for portion in result.allocations[0].portions
            if portion.allocation_kind == "EXCLUSIVE"
        ),
    )
    source_shadows = sum((portion.credits for portion in result.shadow_allocations), Decimal("0"))
    assert source_exclusive == Decimal("3")
    assert source_shadows == Decimal("3")
    assert source_shadows <= source_exclusive
    assert result.credit_conservation
    assert any(item.startswith("SHARED_SOURCE_CAP:evidence:") for item in result.warnings)
    assert ":source" not in str(result.warnings)


def shared_binding(binding_id, source_id, target_id, credits, direction="PRIMARY_TO_TARGET", source_requirement_id="", **kwargs):
    default_source_owner = "TARGET" if direction == "TARGET_TO_PRIMARY" else "PRIMARY"
    default_target_owner = "PRIMARY" if direction == "TARGET_TO_PRIMARY" else "TARGET"
    default_source_domain = "target" if direction == "TARGET_TO_PRIMARY" else "primary"
    default_target_domain = "primary" if direction == "TARGET_TO_PRIMARY" else "target"
    return EquivalencyBinding(
        binding_id=binding_id,
        source_attempt_id=source_id,
        target_requirement_id=target_id,
        approved_credits=credits,
        evidence_state="VERIFIED",
        authority="系所核准",
        evidence_reference=f"official:{binding_id}",
        direction=direction,
        shared=True,
        source_requirement_id=source_requirement_id,
        source_owner=kwargs.pop("source_owner", default_source_owner),
        target_owner=kwargs.pop("target_owner", default_target_owner),
        source_domain=kwargs.pop("source_domain", default_source_domain),
        target_domain=kwargs.pop("target_domain", default_target_domain),
        decision=kwargs.pop("decision", "APPROVED"),
        **kwargs,
    )


def test_exact_verified_shared_reuse_has_separate_direction_ledgers_and_six_credit_cap():
    attempts = (
        attempt("p1", "P1", 3, pools=("primary",)),
        attempt("p2", "P2", 3, pools=("primary",)),
        attempt("p3", "P3", 1, pools=("primary",)),
        attempt("t1", "T1", 3, pools=("target",)),
    )
    requirements = (
        requirement("primary", 10, eligible_pool_ids=("primary",), owner="PRIMARY", domain="primary"),
        # t1 has a real exclusive target allocation before its reverse shared
        # projection; the larger cap leaves room for the six primary shadows.
        requirement("target", 6, max_credits=9, eligible_course_ids=("TARGET", "T1"), owner="TARGET", domain="target"),
    )
    bindings = (
        shared_binding("p1-target", "p1", "target", 3, source_requirement_id="primary"),
        shared_binding("p2-target", "p2", "target", 3, source_requirement_id="primary"),
        shared_binding("p3-target", "p3", "target", 1, source_requirement_id="primary"),
        shared_binding("t1-primary", "t1", "primary", 3, direction="TARGET_TO_PRIMARY", source_requirement_id="target"),
    )

    result = allocate_credits(attempts, requirements, bindings)

    assert result.shared_ledger("PRIMARY_TO_TARGET").used_credits == Decimal("6")
    assert result.shared_ledger("PRIMARY_TO_TARGET").blocked_credits == Decimal("1")
    assert result.shared_ledger("TARGET_TO_PRIMARY").used_credits == Decimal("3")
    assert sum((item.credits for item in result.shadow_allocations if item.direction == "PRIMARY_TO_TARGET"), Decimal("0")) == Decimal("6")
    assert result.credit_conservation
    assert result.status == "UNKNOWN"
    assert any(item.startswith("SHARED_LEDGER_CAP:PRIMARY_TO_TARGET:evidence:") for item in result.warnings)
    assert "p3-target" not in str(result.warnings)


def test_pending_or_unverified_equivalency_does_not_count():
    source = attempt("source", "PHYS", 3)
    pending = EquivalencyBinding(
        binding_id="pending",
        source_attempt_id="source",
        target_requirement_id="target",
        approved_credits=3,
        evidence_state="MANUAL_REVIEW",
        authority="系所",
        evidence_reference="pending:binding",
        direction="PRIMARY_TO_TARGET",
        shared=True,
    )
    result = allocate_credits(
        (source,),
        (requirement("target", 3, eligible_course_ids=("TARGET",)),),
        (pending,),
    )

    assert result.effective_recognized_credits == Decimal("0")
    assert result.shadow_allocations == ()
    assert result.status == "UNKNOWN"
    assert any(item.startswith("UNVERIFIED_EQUIVALENCY:evidence:") for item in result.warnings)
    assert "pending" not in str(result.warnings)


def test_exact_lecture_mapping_never_satisfies_lab_requirement():
    source = attempt("lecture", "PHYS", 3, course_kind="LECTURE")
    binding = EquivalencyBinding(
        binding_id="lecture-to-lab",
        source_attempt_id="lecture",
        target_requirement_id="lab",
        approved_credits=3,
        evidence_state="VERIFIED",
        authority="APC",
        evidence_reference="official:lecture-to-lab",
        source_course_id="PHYS",
        direction="",
        shared=False,
        decision="APPROVED",
    )
    result = allocate_credits(
        (source,),
        (requirement("lab", 3, eligible_course_ids=("TARGET-LAB",), course_kind="LAB"),),
        (binding,),
    )

    assert result.requirement_for("lab").status == "UNKNOWN"
    assert result.recognized_credits == Decimal("0")
    assert result.credit_conservation


def test_four_credit_source_to_three_credit_target_leaves_only_explicit_overflow():
    source = attempt("calc", "CALC-I", 4, pools=("calculus",))
    requirements = (
        requirement("calculus-i", 3, eligible_course_ids=("CALC-I",), max_credits=3, overflow_routes=("free",)),
        requirement("free", 1, eligible_pool_ids=("free",)),
    )
    no_route = allocate_credits((source,), (requirement("calculus-i", 3, eligible_course_ids=("CALC-I",)),))
    with_route = allocate_credits((source,), requirements)

    assert no_route.recognized_credits == Decimal("3")
    assert no_route.unallocated_credits == Decimal("1")
    assert with_route.recognized_credits == Decimal("4")
    assert with_route.unallocated_credits == Decimal("0")


def test_same_owner_overflow_suffix_is_canonicalized_and_visible_in_witness():
    source = attempt("calc", "CALC-I", 4, pools=("core",))
    requirements = (
        requirement(
            "primary:core",
            3,
            eligible_course_ids=("CALC-I",),
            max_credits=3,
            overflow_routes=("elective",),
            owner="PRIMARY",
        ),
        requirement(
            "primary:elective",
            1,
            eligible_pool_ids=("free",),
            owner="PRIMARY",
        ),
    )

    result = allocate_credits((source,), requirements)

    assert result.status == "PASS"
    assert result.pass_eligible
    assert result.credit_conservation
    assert allocation_for(result, "primary:elective")[0].credits == Decimal("1")


def test_invalid_overflow_routes_are_explicit_rule_errors():
    requirements = (
        requirement("primary:a", 1, owner="PRIMARY", overflow_routes=("b",)),
        requirement("target:b", 1, owner="TARGET", overflow_routes=("primary:a",)),
    )

    canonical, issues = canonicalize_overflow_routes(requirements)

    assert canonical[0].overflow_routes == ()
    assert canonical[1].overflow_routes == ()
    assert "OVERFLOW_ROUTE_CROSS_OWNER:primary:a:target:b" in issues
    assert "OVERFLOW_ROUTE_CROSS_OWNER:target:b:primary:a" in issues


def test_apc_chemistry_calculus_one_and_two_are_distinct_target_requirements():
    calculus_one = attempt("calc-one", "CALC-I", 4)
    calculus_two = attempt("calc-two", "CALC-II", 4)
    requirements = (
        requirement("apc-chemistry-calculus-i", 4, eligible_course_ids=("CALC-I",)),
        requirement("apc-chemistry-calculus-ii", 4, eligible_course_ids=("CALC-II",)),
    )
    result = allocate_credits((calculus_two, calculus_one), requirements)

    assert result.status == "PASS"
    assert result.allocation_for("apc-chemistry-calculus-i")[0].attempt_id == "calc-one"
    assert result.allocation_for("apc-chemistry-calculus-ii")[0].attempt_id == "calc-two"


def test_old_apc_context_cannot_auto_allocate_to_new_target_requirement():
    old_context_course = attempt("old-calc", "CALC-I", 4, term="114-1")
    result = allocate_credits(
        (old_context_course,),
        (requirement("apc-115-chemistry-calculus-i", 4, eligible_course_ids=("APC115-CALC-I",)),),
    )

    assert result.status == "FAIL"
    assert result.recognized_credits == Decimal("0")


def test_search_limit_exhaustion_is_unknown_even_if_first_branch_looks_complete():
    source = attempt("source", "SOURCE", 3, pools=("x", "y"))
    result = allocate_credits(
        (source,),
        (
            requirement("x", 3, eligible_pool_ids=("x",)),
            requirement("y", 3, eligible_pool_ids=("y",)),
        ),
        search_limit=1,
    )

    assert result.search_exhausted
    assert result.status == "UNKNOWN"
    assert not result.pass_eligible
    assert "SEARCH_EXHAUSTED" in result.blockers


def test_equally_optimal_course_assignments_expose_a_feasible_witness():
    attempts = (
        attempt("a", "A", 3, pools=("shared-pool",)),
        attempt("b", "B", 3, pools=("shared-pool",)),
    )
    requirements = (
        requirement("r1", 3, eligible_pool_ids=("shared-pool",)),
        requirement("r2", 3, eligible_pool_ids=("shared-pool",)),
    )

    result = allocate_credits(attempts, requirements)

    assert result.status == "PASS"
    assert result.pass_eligible
    assert result.feasibility == "FEASIBLE"
    assert result.feasible_witness
    assert result.search_complete
    assert result.optimality == "NON_UNIQUE"
    assert result.allocation_ambiguous
    assert "ALLOCATION_AMBIGUOUS" not in result.blockers
    assert any(item.startswith("ALLOCATION_ALTERNATIVES:") for item in result.warnings)
    assert len(result.alternative_allocations) >= 2
    assert result.alternative_allocations[0] != result.alternative_allocations[1]


def test_reordered_inputs_keep_alternative_metadata_deterministic():
    attempts = (
        attempt("b", "B", 3, pools=("shared-pool",)),
        attempt("a", "A", 3, pools=("shared-pool",)),
    )
    requirements = (
        requirement("r2", 3, eligible_pool_ids=("shared-pool",)),
        requirement("r1", 3, eligible_pool_ids=("shared-pool",)),
    )

    first = allocate_credits(attempts, requirements)
    second = allocate_credits(tuple(reversed(attempts)), tuple(reversed(requirements)))

    assert first.alternative_allocations == second.alternative_allocations


def test_failed_withdrawn_in_progress_and_zero_credit_attempts_never_mint_credit():
    attempts = (
        CourseAttempt("failed", "FAILED", "FAILED", 3, 3, status="FAILED"),
        CourseAttempt("withdrawn", "WITHDRAWN", "WITHDRAWN", 3, 3, status="WITHDRAWN"),
        CourseAttempt("current", "CURRENT", "CURRENT", 3, 3, status="IN_PROGRESS"),
        CourseAttempt("zero", "ZERO", "ZERO", 0, 0, status="PASS"),
    )
    result = allocate_credits(
        attempts,
        (requirement("any", 3, eligible_course_ids=("FAILED", "WITHDRAWN", "CURRENT", "ZERO")),),
    )

    assert result.source_earned_credits == Decimal("0")
    assert result.recognized_credits == Decimal("0")
    assert result.unallocated_credits == Decimal("0")
    assert result.credit_conservation
    assert result.status == "FAIL"


def test_direct_mapping_inputs_are_unknown_without_explicit_evidence():
    result = allocate_credits(
        ({"attempt_id": "raw", "course_id": "RAW", "credits": 3, "earned_credits": 3},),
        ({"requirement_id": "req", "credits_required": 3, "eligible_course_ids": ("RAW",)},),
    )

    assert result.status == "UNKNOWN"
    assert not result.pass_eligible


def test_exclusive_equivalency_is_capped_and_keeps_binding_identity():
    source = attempt("source", "PHYS", 5)
    binding = EquivalencyBinding(
        binding_id="exclusive-binding",
        source_attempt_id="source",
        target_requirement_id="target",
        approved_credits=2,
        evidence_state=VERIFIED,
        authority="系所核准",
        evidence_reference="official:exclusive-binding",
        shared=False,
        decision="APPROVED",
    )

    result = allocate_credits(
        (source,),
        (requirement("target", 4, eligible_course_ids=("TARGET",)),),
        (binding,),
    )

    portions = allocation_for(result, "target")
    assert tuple(portion.credits for portion in portions) == (Decimal("2"),)
    assert portions[0].binding_id == "exclusive-binding"
    assert result.recognized_credits == Decimal("2")
    assert result.unallocated_credits == Decimal("3")
    assert result.credit_conservation
    assert result.status == "FAIL"


@pytest.mark.parametrize(
    ("binding_kwargs", "expected_warning"),
    (
        ({}, "SHARED_SCOPE_UNKNOWN:scope-missing"),
        ({"source_requirement_id": "target"}, "SHARED_SCOPE_UNKNOWN:scope-same"),
        ({"source_requirement_id": "primary", "source_domain": "wrong"}, "SHARED_SCOPE_UNKNOWN:scope-domain"),
        ({"source_requirement_id": "primary", "direction": "TARGET_TO_PRIMARY"}, "SHARED_SCOPE_UNKNOWN:scope-direction"),
    ),
)
def test_shared_binding_requires_explicit_source_scope_and_matching_direction(
    binding_kwargs,
    expected_warning,
):
    source = attempt("source", "PHYS", 3, pools=("primary",))
    target_id = "same" if expected_warning.endswith("scope-same") else "target"
    requirements = (
        requirement("primary", 3, eligible_pool_ids=("primary",), owner="PRIMARY", domain="primary"),
        requirement(target_id, 3, eligible_course_ids=("TARGET",), owner="TARGET", domain="target"),
    )
    binding_id = expected_warning.split(":", 1)[1]
    binding = shared_binding(binding_id, "source", target_id, 3, **binding_kwargs)

    result = allocate_credits((source,), requirements, (binding,))

    assert result.shadow_allocations == ()
    assert result.requirement_for(target_id).shared_shadow_credits == Decimal("0")
    expected_prefix = expected_warning.split(":", 1)[0] + ":evidence:"
    assert any(item.startswith(expected_prefix) for item in result.warnings)
    assert binding_id not in str(result.warnings)
    assert result.status == "UNKNOWN"


def test_shared_binding_cannot_self_shadow_even_when_source_requirement_is_positive():
    source = attempt("source", "PHYS", 3, pools=("primary",))
    requirement_spec = requirement("primary", 3, eligible_pool_ids=("primary",), owner="PRIMARY", domain="primary")
    binding = shared_binding("self-shadow", "source", "primary", 3, source_requirement_id="primary")

    result = allocate_credits((source,), (requirement_spec,), (binding,))

    assert result.shadow_allocations == ()
    assert result.requirement_for("primary").shared_shadow_credits == Decimal("0")
    assert any(item.startswith("SHARED_SCOPE_UNKNOWN:evidence:") for item in result.warnings)
    assert "self-shadow" not in str(result.warnings)


def test_one_repeat_route_cannot_mix_fixed_and_repeatable_requirement_policies():
    source = attempt("retake", "RETAKE", 6, repeat_group_id="retake-group", pools=("fixed",))
    result = allocate_credits(
        (source,),
        (
            requirement("fixed", 3, eligible_pool_ids=("fixed",), overflow_routes=("repeatable",)),
            requirement("repeatable", 3, eligible_pool_ids=("repeatable",), repeatable=True),
        ),
    )

    assert result.status != "PASS"
    assert not (
        allocation_for(result, "fixed")
        and allocation_for(result, "repeatable")
        and sum((portion.credits for portion in allocation_for(result, "fixed")), Decimal("0")) > 0
        and sum((portion.credits for portion in allocation_for(result, "repeatable")), Decimal("0")) > 0
    )
    assert result.credit_conservation


def test_waiver_flag_alone_is_not_a_student_waiver_decision():
    result = allocate_credits(
        (),
        (requirement("waiver-only", 3, waiver=True),),
    )

    requirement_outcome = result.requirement_for("waiver-only")
    assert requirement_outcome.waived is False
    assert requirement_outcome.status == "UNKNOWN"
    assert requirement_outcome.deficit == Decimal("3")
    assert "WAIVER_DECISION_REQUIRED:waiver-only" in result.blockers
    assert not result.pass_eligible


def test_empty_and_conflicting_duplicate_inputs_fail_closed_but_identical_duplicates_dedupe():
    empty = allocate_credits((), ())
    assert empty.status == "UNKNOWN"
    assert not empty.pass_eligible
    assert "EMPTY_INPUT" in empty.blockers

    source = attempt("source", "SOURCE", 3)
    spec = requirement("req", 3, eligible_course_ids=("SOURCE",))
    deduped = allocate_credits((source,), (spec, spec))
    assert deduped.status == "PASS"
    assert len(deduped.requirement_results) == 1
    conflicting = allocate_credits(
        (source,),
        (spec, requirement("req", 4, eligible_course_ids=("SOURCE",))),
    )
    assert conflicting.status == "UNKNOWN"
    assert not conflicting.pass_eligible
    assert "DUPLICATE_REQUIREMENT_ID:req" in conflicting.blockers


@pytest.mark.parametrize("invalid_required", ("-3", "not-a-number", "NaN", "Infinity", True, None))
def test_invalid_required_credits_cannot_be_normalized_into_a_false_pass(invalid_required):
    invalid = RequirementSpec(
        requirement_id="invalid-negative",
        credits_required=invalid_required,
        coverage_state=COMPLETE,
        evidence_state=VERIFIED,
    )

    result = allocate_credits((), (invalid,))

    assert result.status == "UNKNOWN"
    assert not result.pass_eligible
    assert "INVALID_REQUIREMENT_CREDITS:invalid-negative" in result.blockers


def test_required_zero_credit_gate_needs_explicit_completion_evidence():
    zero_gate = requirement("zero-gate", 0, eligible_course_ids=("ZERO-COURSE",))

    result = allocate_credits((), (zero_gate,))

    assert result.status == "UNKNOWN"
    assert not result.pass_eligible
    assert "ZERO_CREDIT_GATE_EVIDENCE_REQUIRED:zero-gate" in result.blockers


def test_equivalent_binding_branches_are_not_false_allocation_ambiguity():
    source = attempt("source", "PHYS", 3)
    target = requirement("target", 3, eligible_course_ids=("TARGET",))
    bindings = (
        EquivalencyBinding(
            binding_id="evidence-a",
            source_attempt_id="source",
            target_requirement_id="target",
            approved_credits=3,
            evidence_state=VERIFIED,
            authority="系所核准",
            evidence_reference="official:evidence-a",
            decision="APPROVED",
        ),
        EquivalencyBinding(
            binding_id="evidence-b",
            source_attempt_id="source",
            target_requirement_id="target",
            approved_credits=3,
            evidence_state=VERIFIED,
            authority="系所核准",
            evidence_reference="official:evidence-b",
            decision="APPROVED",
        ),
    )

    result = allocate_credits((source,), (target,), bindings)

    assert result.status == "PASS"
    assert result.pass_eligible
    assert result.allocation_ambiguous is False
    assert len(result.alternative_allocations) == 1


def test_allocation_result_rejects_malformed_boolean_metadata_before_pass():
    result = AllocationResult(
        status="PASS",
        allocations=(),
        requirement_results=(),
        source_earned_credits=0,
        recognized_credits=0,
        unallocated_credits=0,
        credit_conservation="true",
        pass_eligible="true",
        search_exhausted="false",
        allocation_ambiguous="false",
    )

    assert result.credit_conservation is False
    assert result.search_exhausted is True
    assert result.allocation_ambiguous is True
    assert result.pass_eligible is False
    assert result.status == "UNKNOWN"


def test_allocation_result_pass_requires_literal_conservation_true():
    result = AllocationResult(
        status="PASS",
        allocations=(),
        requirement_results=(),
        source_earned_credits=0,
        recognized_credits=0,
        unallocated_credits=0,
        credit_conservation=False,
        pass_eligible=True,
        search_exhausted=False,
        allocation_ambiguous=False,
    )

    assert result.credit_conservation is False
    assert result.pass_eligible is False
    assert result.status == "UNKNOWN"


def test_allocation_result_recomputes_credit_conservation_from_exclusive_totals():
    result = AllocationResult(
        status="PASS",
        allocations=(),
        requirement_results=(),
        source_earned_credits=3,
        recognized_credits=4,
        unallocated_credits=0,
        credit_conservation=True,
        pass_eligible=True,
        search_exhausted=False,
        allocation_ambiguous=False,
    )

    assert result.credit_conservation is False
    assert result.pass_eligible is False
    assert result.status == "UNKNOWN"
    assert "CREDIT_CONSERVATION_FAILED" in result.blockers


def test_allocation_result_rejects_six_credit_portion_from_three_credit_source():
    result = AllocationResult(
        status="PASS",
        allocations=(
            AttemptAllocation(
                attempt_id="source",
                source_credits=3,
                portions=(CreditPortion("source", "requirement", 6, "EXCLUSIVE"),),
                unallocated_credits=0,
            ),
        ),
        requirement_results=(),
        source_earned_credits=3,
        recognized_credits=3,
        unallocated_credits=0,
        credit_conservation=True,
        pass_eligible=True,
        search_exhausted=False,
        allocation_ambiguous=False,
    )

    assert result.credit_conservation is False
    assert result.pass_eligible is False
    assert result.status == "UNKNOWN"
    assert "CREDIT_CONSERVATION_FAILED" in result.blockers


def test_allocation_result_rejects_embedded_positive_shared_shadow_portion():
    result = AllocationResult(
        status="PASS",
        allocations=(
            AttemptAllocation(
                attempt_id="source",
                source_credits=3,
                portions=(CreditPortion("source", "target", 3, "SHARED_SHADOW"),),
                unallocated_credits=3,
            ),
        ),
        requirement_results=(),
        source_earned_credits=3,
        recognized_credits=0,
        unallocated_credits=3,
        credit_conservation=True,
        pass_eligible=True,
        search_exhausted=False,
        allocation_ambiguous=False,
    )

    assert result.credit_conservation is False
    assert result.pass_eligible is False
    assert result.status == "UNKNOWN"
    assert "CREDIT_CONSERVATION_FAILED" in result.blockers


def test_allocation_result_rejects_positive_unknown_nonexclusive_portion():
    result = AllocationResult(
        status="PASS",
        allocations=(
            AttemptAllocation(
                attempt_id="source",
                source_credits=3,
                portions=(CreditPortion("source", "target", 3, "NOT_A_SOURCE_PORTION"),),
                unallocated_credits=3,
            ),
        ),
        requirement_results=(),
        source_earned_credits=3,
        recognized_credits=0,
        unallocated_credits=3,
        credit_conservation=True,
        pass_eligible=True,
        search_exhausted=False,
        allocation_ambiguous=False,
    )

    assert result.credit_conservation is False
    assert result.pass_eligible is False
    assert result.status == "UNKNOWN"
    assert "CREDIT_CONSERVATION_FAILED" in result.blockers


def test_allocation_result_accepts_separate_shadow_allocations():
    result = AllocationResult(
        status="PASS",
        allocations=(
            AttemptAllocation(
                attempt_id="source",
                source_credits=3,
                portions=(CreditPortion("source", "primary", 3, "EXCLUSIVE"),),
                unallocated_credits=0,
            ),
        ),
        requirement_results=(),
        source_earned_credits=3,
        recognized_credits=3,
        unallocated_credits=0,
        credit_conservation=True,
        shadow_allocations=(CreditPortion("source", "target", 3, "SHARED_SHADOW"),),
        pass_eligible=True,
        search_exhausted=False,
        allocation_ambiguous=False,
    )

    assert result.credit_conservation is True
    assert result.pass_eligible is True
    assert result.status == "PASS"


def test_equivalency_binding_requires_an_explicit_approved_decision():
    source = attempt("source", "SOURCE", 3)
    target = requirement("target", 3, eligible_course_ids=("TARGET",))
    common = {
        "binding_id": "unapproved-binding",
        "source_attempt_id": "source",
        "target_requirement_id": "target",
        "approved_credits": 3,
        "evidence_state": VERIFIED,
        "authority": "系所核准",
        "evidence_reference": "official:unapproved-binding",
    }

    omitted = EquivalencyBinding(**common)
    blank = EquivalencyBinding(**common, decision=" ")

    assert omitted.decision == "PENDING"
    assert blank.decision == "PENDING"
    for binding in (omitted, blank):
        result = allocate_credits((source,), (target,), (binding,))
        assert result.effective_recognized_credits == Decimal("0")
        assert result.status == "UNKNOWN"


def test_mapping_equivalency_without_decision_is_not_approved_by_default():
    result = allocate_credits(
        (attempt("source", "SOURCE", 3),),
        (requirement("target", 3, eligible_course_ids=("TARGET",)),),
        (
            {
                "binding_id": "mapping-binding",
                "source_attempt_id": "source",
                "target_requirement_id": "target",
                "approved_credits": 3,
                "evidence_state": VERIFIED,
                "authority": "系所核准",
                "evidence_reference": "official:mapping-binding",
            },
        ),
    )

    assert result.effective_recognized_credits == Decimal("0")
    assert result.status == "UNKNOWN"


def test_waiver_requires_an_explicit_approved_decision():
    waiver_requirement = requirement("waiver", 3, waiver=True)
    common = {
        "decision_id": "unapproved-waiver",
        "target_requirement_id": "waiver",
        "evidence_state": VERIFIED,
        "authority": "教務處",
        "evidence_reference": "official:unapproved-waiver",
    }

    omitted = WaiverDecision(**common)
    blank = WaiverDecision(**common, decision=" ")

    assert omitted.decision == "PENDING"
    assert blank.decision == "PENDING"
    for decision in (omitted, blank):
        result = allocate_credits((), (waiver_requirement,), waiver_decisions=(decision,))
        assert result.requirement_for("waiver").waived is False
        assert result.status == "UNKNOWN"


def test_mapping_waiver_without_decision_is_not_approved_by_default():
    result = allocate_credits(
        (),
        (requirement("waiver", 3, waiver=True),),
        waiver_decisions=(
            {
                "decision_id": "mapping-waiver",
                "target_requirement_id": "waiver",
                "evidence_state": VERIFIED,
                "authority": "教務處",
                "evidence_reference": "official:mapping-waiver",
            },
        ),
    )

    assert result.requirement_for("waiver").waived is False
    assert result.status == "UNKNOWN"


def test_free_total_subset_uses_one_exclusive_ledger_and_finds_verified_witness():
    attempts = []
    for index in range(5):
        evidence = (("free", VERIFIED, "official:free", "policy"),)
        if index == 0:
            evidence += (("science_college", VERIFIED, "official:science", "policy"),)
        attempts.append(
            CourseAttempt(
                attempt_id=f"free-{index}",
                course_id=f"free-course-{index}",
                course_name=f"Free {index}",
                credits=Decimal("3"),
                earned_credits=Decimal("3"),
                academic_term=f"114-{index + 1}",
                identity_status=VERIFIED,
                course_kind="LECTURE",
                pool_ids=("free",),
                pool_evidence_state=VERIFIED,
                pool_membership_evidence=evidence,
            )
        )
    result = allocate_credits(
        tuple(attempts),
        (
            requirement(
                "free-total",
                15,
                eligible_pool_ids=("free",),
                subset_constraints=(
                    {
                        "constraint_id": "science-college-minimum",
                        "membership_id": "science_college",
                        "minimum_credits": 3,
                        "source_reference": "official:science",
                    },
                ),
            ),
        ),
        search_limit=100000,
    )

    assert result.status == PASS
    assert result.feasibility == "FEASIBLE"
    assert result.search_complete
    assert result.feasible_witness
    assert result.credit_conservation
    assert result.recognized_credits == Decimal("15")
    assert sum((portion.credits for allocation in result.allocations for portion in allocation.portions), Decimal("0")) == Decimal("15")
    subset = result.subset_results[0]
    assert subset["status"] == PASS
    assert subset["verified_credits"] == Decimal("3")


def test_free_total_unknown_subset_does_not_become_pass_or_mint_shadow_credit():
    attempts = tuple(
        CourseAttempt(
            attempt_id=f"free-unknown-{index}",
            course_id=f"free-course-unknown-{index}",
            course_name=f"Free Unknown {index}",
            credits=Decimal("3"),
            earned_credits=Decimal("3"),
            academic_term=f"115-{index + 1}",
            identity_status=VERIFIED,
            course_kind="LECTURE",
            pool_ids=("free",),
            pool_evidence_state=VERIFIED,
            pool_membership_evidence=(
                ("free", VERIFIED, "official:free", "policy"),
                ("science_college", UNKNOWN, "official:science", "policy"),
            ),
        )
        for index in range(5)
    )
    result = allocate_credits(
        attempts,
        (
            requirement(
                "free-total",
                15,
                eligible_pool_ids=("free",),
                subset_constraints=(
                    {
                        "constraint_id": "science-college-minimum",
                        "membership_id": "science_college",
                        "minimum_credits": 3,
                    },
                ),
            ),
        ),
        search_limit=100000,
    )

    assert result.status == UNKNOWN
    assert result.recognized_credits == Decimal("15")
    assert result.credit_conservation
    assert not result.pass_eligible
    assert result.subset_results[0]["status"] == UNKNOWN
    assert result.subset_results[0]["unknown_candidate_credits"] == Decimal("15")


def _membership_attempt(
    attempt_id,
    credits,
    memberships,
    *,
    term="115-1",
    identity_status=VERIFIED,
    pool_evidence_state=VERIFIED,
):
    evidence = tuple(
        (
            item[0],
            item[1],
            item[2] if len(item) > 2 else f"official:{item[0]}",
            item[3] if len(item) > 3 else "catalog",
        )
        for item in memberships
    )
    return CourseAttempt(
        attempt_id=attempt_id,
        course_id=attempt_id,
        course_name=attempt_id,
        credits=credits,
        earned_credits=credits,
        academic_term=term,
        identity_status=identity_status,
        pool_ids=tuple(item[0] for item in memberships),
        pool_evidence_state=pool_evidence_state,
        pool_membership_evidence=evidence,
    )


def test_zero_consumption_subset_gate_observes_union_once_and_passes_with_requirement_rows():
    attempts = (
        _membership_attempt("ge-subset", 2, (("ge-a", VERIFIED), ("subset-membership", VERIFIED))),
        _membership_attempt("ge-other", 2, (("ge-b", VERIFIED),)),
    )
    requirements = (
        requirement("ge-a", 2, eligible_pool_ids=("ge-a",)),
        requirement("ge-b", 2, eligible_pool_ids=("ge-b",)),
        requirement(
            "it-gate",
            0,
            waiver=True,
            kind="CREDIT_SUBSET_GATE",
            subset_constraints=(
                {
                    "constraint_id": "it2",
                    "membership_id": "subset-membership",
                    "minimum_credits": 2,
                    "observed_requirement_ids": ("ge-a", "ge-b"),
                    "source_reference": "official:it2",
                },
            ),
        ),
    )

    result = allocate_credits(attempts, requirements, search_limit=100000)

    assert result.status == PASS
    assert result.requirement_for("it-gate").status == PASS
    assert allocation_for(result, "it-gate") == ()
    assert result.recognized_credits == Decimal("4")
    assert result.credit_conservation
    subset = next(item for item in result.subset_results if item["requirement_id"] == "it-gate")
    assert subset["status"] == PASS
    assert subset["observed_requirement_ids"] == ("ge-a", "ge-b")
    assert subset["verified_credits"] == Decimal("2")


def test_zero_consumption_subset_gate_unknown_does_not_block_ge_requirement_status():
    attempts = (_membership_attempt("ge-it-unknown", 2, (("ge-a", VERIFIED),)),)
    requirements = (
        requirement("ge-a", 2, eligible_pool_ids=("ge-a",)),
        requirement(
            "it-gate",
            0,
            waiver=True,
            kind="CREDIT_SUBSET_GATE",
            subset_constraints=(
                {
                    "constraint_id": "it2",
                    "membership_id": "subset-membership",
                    "minimum_credits": 2,
                    "observed_requirement_ids": ("ge-a",),
                },
            ),
        ),
    )

    result = allocate_credits(attempts, requirements, search_limit=100000)

    assert result.requirement_for("ge-a").status == PASS
    assert result.requirement_for("it-gate").status == UNKNOWN
    assert result.status == UNKNOWN
    assert result.subset_results[0]["status"] == UNKNOWN
    assert result.credit_conservation


def test_subject_version_bound_subset_gate_waiver_does_not_fill_ge_requirement():
    attempts = (_membership_attempt("ge-26", 26, (("ge", VERIFIED),)),)
    requirements = (
        requirement("ge-total", 28, eligible_pool_ids=("ge",)),
        RequirementSpec(
            requirement_id="it-gate",
            name="資訊應用與設計",
            credits_required=0,
            required=True,
            waiver=True,
            kind="CREDIT_SUBSET_GATE",
            curriculum_version="115",
            subset_constraints=(
                {
                    "constraint_id": "it2",
                        "membership_id": "subset-membership",
                    "minimum_credits": 2,
                    "observed_requirement_ids": ("ge-total",),
                },
            ),
        ),
    )
    waiver = WaiverDecision(
        decision_id="it-waiver-115",
        target_requirement_id="it-gate",
        evidence_state=VERIFIED,
        authority="official:genedu",
        evidence_reference="official:it-waiver-115",
        decision="APPROVED",
        subject_ref="subject:test",
        curriculum_version="115",
    )

    result = allocate_credits(attempts, requirements, waiver_decisions=(waiver,), search_limit=100000)

    assert result.requirement_for("it-gate").status == PASS
    assert result.requirement_for("it-gate").waived
    assert result.requirement_for("ge-total").status == FAIL
    assert result.credit_conservation
    assert allocation_for(result, "it-gate") == ()


def test_cs_subset_gate_can_be_not_applicable_without_proving_it_membership():
    requirements = (
        requirement(
            "it-gate-cs",
            0,
            required=False,
            kind="CREDIT_SUBSET_GATE",
            subset_constraints=(
                {
                    "constraint_id": "it2",
                    "membership_id": "subset-membership",
                    "minimum_credits": 2,
                },
            ),
        ),
    )

    result = allocate_credits((), requirements, search_limit=100000)

    assert result.status == PASS
    assert result.requirement_for("it-gate-cs").status == "NOT_APPLICABLE"
    assert result.subset_results[0]["status"] == "NOT_APPLICABLE"


def test_maximum_subset_chooses_replacement_route_and_preserves_parent_requirement():
    attempts = (
        _membership_attempt("external-18", 18, (("math", VERIFIED), ("external_or_cross_school_professional", VERIFIED))),
        _membership_attempt(
            "internal-49",
            49,
            (
                ("math", VERIFIED),
                (
                    "external_or_cross_school_professional",
                    NOT_MEMBER,
                    "official:math-internal",
                    "official_negative",
                ),
            ),
        ),
    )
    requirements = (
        requirement(
            "math-elective",
            64,
            eligible_pool_ids=("math",),
            subset_constraints=(
                {
                    "constraint_id": "external-cap",
                    "membership_id": "external_or_cross_school_professional",
                    "maximum_credits": 15,
                    "observed_requirement_ids": ("math-elective",),
                    "excluded_membership_id": "approved_credit_program_cap_exempt",
                    "source_reference": "official:math-cap",
                },
            ),
        ),
    )

    result = allocate_credits(attempts, requirements, search_limit=100000)

    assert result.status == PASS
    assert result.requirement_for("math-elective").status == PASS
    assert result.recognized_credits == Decimal("64")
    assert result.unallocated_credits == Decimal("3")
    assert result.credit_conservation
    subset = result.subset_results[0]
    assert subset["status"] == PASS
    assert subset["verified_credits"] == Decimal("15")
    assert subset["maximum_credits"] == Decimal("15")


def test_maximum_subset_distinguishes_excess_from_unknown_and_official_exemption():
    def make_requirement(requirement_id):
        return requirement(
            requirement_id,
            18,
            eligible_pool_ids=("math",),
            subset_constraints=(
                {
                    "constraint_id": "external-cap",
                    "membership_id": "external_or_cross_school_professional",
                    "maximum_credits": 15,
                    "excluded_membership_id": "approved_credit_program_cap_exempt",
                },
            ),
        )

    verified_external = _membership_attempt(
        "external-over", 18, (("math", VERIFIED), ("external_or_cross_school_professional", VERIFIED))
    )
    failed = allocate_credits((verified_external,), (make_requirement("over"),), search_limit=100000)
    assert failed.status == FAIL
    assert failed.subset_results[0]["status"] == FAIL

    unknown_external = _membership_attempt(
        "external-unknown", 12, (("math", VERIFIED), ("external_or_cross_school_professional", UNKNOWN))
    )
    bounded_unknown = allocate_credits(
        (
            unknown_external,
            _membership_attempt(
                "internal-6",
                6,
                (
                    ("math", VERIFIED),
                    (
                        "external_or_cross_school_professional",
                        NOT_MEMBER,
                        "official:math-internal",
                        "official_negative",
                    ),
                ),
            ),
        ),
        (make_requirement("unknown"),),
        search_limit=100000,
    )
    assert bounded_unknown.status == PASS
    assert bounded_unknown.subset_results[0]["status"] == PASS
    assert bounded_unknown.subset_results[0]["unknown_candidate_credits"] == Decimal("12")

    exemption = _membership_attempt(
        "external-exempt",
        18,
        (
            ("math", VERIFIED),
            ("external_or_cross_school_professional", VERIFIED),
            ("approved_credit_program_cap_exempt", VERIFIED),
        ),
    )
    exempted = allocate_credits((exemption,), (make_requirement("exempt"),), search_limit=100000)
    assert exempted.status == PASS
    assert exempted.subset_results[0]["status"] == PASS
    assert exempted.subset_results[0]["exempted_credits"] == Decimal("18")

    potentially_over = _membership_attempt(
        "external-unknown-over", 18, (("math", VERIFIED), ("external_or_cross_school_professional", UNKNOWN))
    )
    unresolved = allocate_credits((potentially_over,), (make_requirement("unknown-over"),), search_limit=100000)
    assert unresolved.status == UNKNOWN
    assert unresolved.subset_results[0]["status"] == UNKNOWN


def test_maximum_subset_counts_verified_target_membership_across_observed_requirements_only():
    """Internal credit must not consume an external cap in another bucket."""

    external_membership = "external_or_cross_school_professional"
    internal_a = _membership_attempt(
        "a-internal",
        10,
        (
            ("a-pool", VERIFIED),
            (external_membership, NOT_MEMBER, "official:math-internal", "official_negative"),
        ),
    )
    external_b = _membership_attempt(
        "b-external",
        20,
        (("b-pool", VERIFIED), (external_membership, VERIFIED)),
    )
    internal_b = _membership_attempt(
        "b-internal",
        5,
        (
            ("b-pool", VERIFIED),
            (external_membership, NOT_MEMBER, "official:math-internal", "official_negative"),
        ),
    )
    requirements = (
        requirement("a", 10, eligible_pool_ids=("a-pool",)),
        requirement(
            "b",
            20,
            eligible_pool_ids=("b-pool",),
            subset_constraints=(
                {
                    "constraint_id": "external-cap",
                    "membership_id": external_membership,
                    "maximum_credits": 15,
                    "observed_requirement_ids": ("a", "b"),
                    "source_reference": "official:math-cap",
                },
            ),
        ),
    )

    result = allocate_credits((internal_a, external_b, internal_b), requirements, search_limit=100000)

    assert result.status == PASS
    assert result.requirement_for("a").status == PASS
    assert result.requirement_for("b").status == PASS
    assert result.credit_conservation
    subset = next(item for item in result.subset_results if item["constraint_id"] == "external-cap")
    assert subset["status"] == PASS
    assert subset["verified_credits"] == Decimal("15")
    assert subset["unknown_candidate_credits"] == Decimal("0")
    assert result.unallocated_credits == Decimal("5")


def test_maximum_subset_missing_target_membership_is_unknown_without_server_owned_negative():
    missing = _membership_attempt("math-only", 18, (("math", VERIFIED),))
    requirement_spec = requirement(
        "math-elective",
        18,
        eligible_pool_ids=("math",),
        subset_constraints=(
            {
                "constraint_id": "external-cap",
                "membership_id": "external_or_cross_school_professional",
                "maximum_credits": 15,
                "source_reference": "official:math-cap",
            },
        ),
    )

    result = allocate_credits((missing,), (requirement_spec,), search_limit=100000)

    assert result.status == UNKNOWN
    subset = result.subset_results[0]
    assert subset["status"] == UNKNOWN
    assert subset["unknown_candidate_credits"] == Decimal("18")


def test_maximum_subset_untrusted_not_member_marker_remains_unknown():
    untrusted = _membership_attempt(
        "math-untrusted-negative",
        18,
        (
            ("math", VERIFIED),
            (
                "external_or_cross_school_professional",
                NOT_MEMBER,
                "student:assertion",
                "catalog",
            ),
        ),
    )
    requirement_spec = requirement(
        "math-elective",
        18,
        eligible_pool_ids=("math",),
        subset_constraints=(
            {
                "constraint_id": "external-cap",
                "membership_id": "external_or_cross_school_professional",
                "maximum_credits": 15,
                "source_reference": "official:math-cap",
            },
        ),
    )

    result = allocate_credits((untrusted,), (requirement_spec,), search_limit=100000)

    assert result.status == UNKNOWN
    assert result.subset_results[0]["status"] == UNKNOWN


def _course_count_requirement(
    requirement_id="beta",
    credits=6,
    *,
    membership_id="domain",
    observed_requirement_ids=None,
    minimum_course_count=1,
    maximum_course_count=None,
):
    constraint = {
        "constraint_id": membership_id,
        "membership_id": membership_id,
        "minimum_course_count": minimum_course_count,
        "observed_requirement_ids": observed_requirement_ids or (requirement_id,),
        "source_reference": "official:cs-beta-domain",
    }
    if maximum_course_count is not None:
        constraint["maximum_course_count"] = maximum_course_count
    return requirement(
        requirement_id,
        credits,
        eligible_pool_ids=("beta",),
        kind="AGGREGATE",
        subset_constraints=(constraint,),
    )


def test_course_count_subset_requires_distinct_verified_beta_attempts():
    attempts = (
        _membership_attempt("common-course", 2, (("beta", VERIFIED), ("domain", VERIFIED))),
        _membership_attempt("software-course", 2, (("beta", VERIFIED), ("domain", VERIFIED))),
        _membership_attempt("network-course", 2, (("beta", VERIFIED), ("domain", VERIFIED))),
    )
    result = allocate_credits(
        attempts,
        (_course_count_requirement(credits=6),),
        search_limit=100000,
    )

    assert result.status == PASS
    assert result.requirement_for("beta").status == PASS
    assert result.recognized_credits == Decimal("6")
    assert result.credit_conservation
    subset = result.subset_results[0]
    assert subset["minimum_course_count"] == 1
    assert subset["verified_course_count"] == 3
    assert subset["unknown_candidate_course_count"] == 0
    assert subset["status"] == PASS


def test_course_count_subset_deduplicates_one_attempt_split_across_observed_requirements():
    split = _membership_attempt("split-course", 4, (("beta", VERIFIED), ("domain", VERIFIED)))
    requirements = (
        requirement("beta-a", 2, eligible_pool_ids=("beta",), kind="AGGREGATE"),
        requirement(
            "beta-b",
            2,
            eligible_pool_ids=("beta",),
            kind="AGGREGATE",
            subset_constraints=(
                {
                    "constraint_id": "domain",
                    "membership_id": "domain",
                    "minimum_course_count": 1,
                    "observed_requirement_ids": ("beta-a", "beta-b"),
                    "source_reference": "official:cs-beta-domain",
                },
            ),
        ),
    )
    allocations = (
        AttemptAllocation(
            "split-course",
            Decimal("4"),
            (
                CreditPortion("split-course", "beta-a", Decimal("2")),
                CreditPortion("split-course", "beta-b", Decimal("2")),
            ),
        ),
    )
    subset_results, statuses, _blockers = _subset_constraint_evaluations(
        requirements,
        (split,),
        allocations,
    )

    assert statuses["beta-b"] == PASS
    subset = next(item for item in subset_results if item["requirement_id"] == "beta-b")
    assert subset["verified_course_count"] == 1
    assert subset["matched_attempt_ids"] == ("split-course",)


def test_one_verified_dual_domain_attempt_satisfies_both_count_constraints_once():
    dual = _membership_attempt(
        "dual-domain-course",
        4,
        (
            ("beta", VERIFIED),
            ("common", VERIFIED),
            ("software", VERIFIED),
        ),
    )
    beta = requirement(
        "beta",
        4,
        eligible_pool_ids=("beta",),
        kind="AGGREGATE",
        subset_constraints=(
            {
                "constraint_id": "common",
                "membership_id": "common",
                "minimum_course_count": 1,
                "observed_requirement_ids": ("beta",),
                "source_reference": "official:cs-beta-domain",
            },
            {
                "constraint_id": "software",
                "membership_id": "software",
                "minimum_course_count": 1,
                "observed_requirement_ids": ("beta",),
                "source_reference": "official:cs-beta-domain",
            },
        ),
    )
    result = allocate_credits((dual,), (beta,), search_limit=100000)

    assert result.status == PASS
    assert result.recognized_credits == Decimal("4")
    assert result.credit_conservation
    assert {item["constraint_id"] for item in result.subset_results} == {"common", "software"}
    assert all(item["verified_course_count"] == 1 for item in result.subset_results)
    assert all(item["status"] == PASS for item in result.subset_results)


@pytest.mark.parametrize("membership_state", (UNKNOWN, CONFLICTED))
def test_course_count_unknown_or_conflicted_membership_cannot_prove_pass(membership_state):
    attempt_with_unknown_domain = _membership_attempt(
        "uncertain-domain-course",
        2,
        (("beta", VERIFIED), ("domain", membership_state, "official:cs-beta-domain", "catalog")),
    )
    result = allocate_credits(
        (attempt_with_unknown_domain,),
        (_course_count_requirement(credits=2),),
        search_limit=100000,
    )

    assert result.status == UNKNOWN
    assert not result.feasible_witness
    subset = result.subset_results[0]
    assert subset["verified_course_count"] == 0
    assert subset["unknown_candidate_course_count"] == 1
    assert subset["status"] == UNKNOWN


def test_course_count_trusted_not_member_is_definite_count_deficit():
    attempt_without_domain = _membership_attempt(
        "officially-outside-domain",
        2,
        (
            ("beta", VERIFIED),
            ("domain", NOT_MEMBER, "official:cs-not-domain", "registry_negative"),
        ),
    )
    result = allocate_credits(
        (attempt_without_domain,),
        (_course_count_requirement(credits=2),),
        search_limit=100000,
    )

    assert result.status == FAIL
    assert not result.feasible_witness
    subset = result.subset_results[0]
    assert subset["verified_course_count"] == 0
    assert subset["unknown_candidate_course_count"] == 0
    assert subset["status"] == FAIL


def test_course_count_ignores_alpha_free_and_unallocated_attempts():
    beta_without_domain = _membership_attempt("beta-no-domain", 2, (("beta", VERIFIED),))
    alpha = _membership_attempt("alpha-domain", 2, (("alpha", VERIFIED), ("domain", VERIFIED)))
    free = _membership_attempt("free-domain", 2, (("free", VERIFIED), ("domain", VERIFIED)))
    outside = _membership_attempt("unallocated-domain", 2, (("outside", VERIFIED), ("domain", VERIFIED)))
    result = allocate_credits(
        (beta_without_domain, alpha, free, outside),
        (
            _course_count_requirement(credits=2),
            requirement("alpha", 2, eligible_pool_ids=("alpha",), kind="AGGREGATE"),
            requirement("free", 2, eligible_pool_ids=("free",), kind="AGGREGATE"),
        ),
        search_limit=100000,
    )

    assert result.status == UNKNOWN
    subset = next(item for item in result.subset_results if item["requirement_id"] == "beta")
    assert subset["verified_course_count"] == 0
    assert subset["unknown_candidate_course_count"] == 1
    assert subset["matched_attempt_ids"] == ("beta-no-domain",)


def test_course_count_ignores_shared_shadow_and_requires_exclusive_beta_portion():
    source = attempt("source", "PHYS", 3, pools=("primary",))
    target = requirement(
        "target",
        3,
        eligible_pool_ids=("target",),
        owner="TARGET",
        domain="target",
        kind="AGGREGATE",
        subset_constraints=(
            {
                "constraint_id": "domain",
                "membership_id": "domain",
                "minimum_course_count": 1,
                "observed_requirement_ids": ("target",),
                "source_reference": "official:cs-beta-domain",
            },
        ),
    )
    result = allocate_credits(
        (source,),
        (
            requirement("primary", 3, eligible_pool_ids=("primary",), owner="PRIMARY", domain="primary"),
            target,
        ),
        (shared_binding("source-target", "source", "target", 3, source_requirement_id="primary"),),
        search_limit=100000,
    )

    assert result.shadow_allocations
    assert result.requirement_for("target").effective_credits == Decimal("3")
    subset = next(item for item in result.subset_results if item["requirement_id"] == "target")
    assert subset["verified_course_count"] == 0
    assert subset["status"] == FAIL
    assert result.status == FAIL
    assert result.credit_conservation


def test_maximum_course_count_allows_one_verified_attempt_with_full_credit():
    attempt_three = _membership_attempt(
        "software-three",
        3,
        (("beta", VERIFIED), ("software", VERIFIED)),
    )
    result = allocate_credits(
        (attempt_three,),
        (
            _course_count_requirement(
                credits=3,
                membership_id="software",
                minimum_course_count=None,
                maximum_course_count=1,
            ),
        ),
        search_limit=100000,
    )

    assert result.status == PASS
    subset = result.subset_results[0]
    assert subset["maximum_course_count"] == 1
    assert subset["verified_course_count"] == 1
    assert subset["unknown_candidate_course_count"] == 0
    assert subset["status"] == PASS
    assert result.credit_conservation


def test_maximum_course_count_rejects_two_verified_attempts_even_when_credits_fit():
    attempts = (
        _membership_attempt("software-two", 2, (("beta", VERIFIED), ("software", VERIFIED))),
        _membership_attempt("software-one", 1, (("beta", VERIFIED), ("software", VERIFIED))),
    )
    result = allocate_credits(
        attempts,
        (
            _course_count_requirement(
                credits=3,
                membership_id="software",
                minimum_course_count=None,
                maximum_course_count=1,
            ),
        ),
        search_limit=100000,
    )

    assert result.status == FAIL
    subset = result.subset_results[0]
    assert subset["verified_course_count"] == 2
    assert subset["maximum_course_count"] == 1
    assert subset["status"] == FAIL
    assert any("COUNT_EXCESS" in blocker for blocker in result.blockers)
    assert result.credit_conservation


def test_maximum_course_count_unknown_candidate_cannot_prove_cap():
    attempts = (
        _membership_attempt("software-two", 2, (("beta", VERIFIED), ("software", VERIFIED))),
        _membership_attempt("software-unknown", 1, (("beta", VERIFIED), ("software", UNKNOWN))),
    )
    result = allocate_credits(
        attempts,
        (
            _course_count_requirement(
                credits=3,
                membership_id="software",
                minimum_course_count=None,
                maximum_course_count=1,
            ),
        ),
        search_limit=100000,
    )

    assert result.status == UNKNOWN
    assert not result.feasible_witness
    subset = result.subset_results[0]
    assert subset["verified_course_count"] == 1
    assert subset["unknown_candidate_course_count"] == 1
    assert subset["status"] == UNKNOWN


def test_maximum_course_count_deduplicates_split_portions_of_one_attempt():
    split = _membership_attempt(
        "software-split",
        3,
        (("beta", VERIFIED), ("software", VERIFIED)),
    )
    requirements = (
        requirement("beta-a", 2, eligible_pool_ids=("beta",), kind="AGGREGATE"),
        requirement(
            "beta-b",
            1,
            eligible_pool_ids=("beta",),
            kind="AGGREGATE",
            subset_constraints=(
                {
                    "constraint_id": "software",
                    "membership_id": "software",
                    "maximum_course_count": 1,
                    "observed_requirement_ids": ("beta-a", "beta-b"),
                    "source_reference": "official:cs-beta-domain",
                },
            ),
        ),
    )
    allocations = (
        AttemptAllocation(
            "software-split",
            Decimal("3"),
            (
                CreditPortion("software-split", "beta-a", Decimal("2")),
                CreditPortion("software-split", "beta-b", Decimal("1")),
            ),
        ),
    )

    subset_results, statuses, _blockers = _subset_constraint_evaluations(
        requirements,
        (split,),
        allocations,
    )

    assert statuses["beta-b"] == PASS
    subset = next(item for item in subset_results if item["requirement_id"] == "beta-b")
    assert subset["maximum_course_count"] == 1
    assert subset["verified_course_count"] == 1
    assert subset["status"] == PASS
