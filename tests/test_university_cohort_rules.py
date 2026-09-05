"""Regression checks for year-scoped university common-course policies."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from allocation_engine import VERIFIED, CourseAttempt, allocate_credits
from curriculum_registry import get_curriculum

ROOT = Path(__file__).resolve().parents[1]


def _primary(cohort: str, program: str = "earth", track: str | None = "earth_environment"):
    if program == "math" and track is None and cohort not in {"111", "112"}:
        track = "math_scientific_computing"
    suffix = f":{track}" if track else ""
    return get_curriculum(f"primary:{cohort}:{program}{suffix}")


def _ge_rows(curriculum: dict) -> list[dict]:
    return [
        row
        for row in curriculum["university_requirements"]
        if str(row.get("bucket", "")).startswith("ge_")
    ]


def _non_credit(curriculum: dict, requirement_id: str) -> dict:
    return next(
        row
        for row in curriculum["non_credit_requirements"]
        if row.get("requirement_id") == requirement_id
    )


def test_111_common_course_compile_contract_uses_flex_instead_of_english_three():
    curriculum = _primary("111")
    named = [
        row
        for row in curriculum["university_requirements"]
        if row.get("bucket") == "university_compulsory"
    ]
    assert {row["name"] for row in named} == {
        "國文(一):閱讀與思辨",
        "國文(二):語文表達",
        "英文(一)",
        "英文(二)",
    }
    assert sum(float(row["credits"]) for row in named) == 8
    assert all(row["name"] != "英文(三)" for row in curriculum["course_catalog"])

    ge_rows = _ge_rows(curriculum)
    source_rows = [row for row in ge_rows if row["bucket"] != "ge_flex"]
    flex = next(row for row in ge_rows if row["bucket"] == "ge_flex")
    assert len(source_rows) == 5
    assert {row["bucket"] for row in source_rows} == {
        "ge_藝術與美感",
        "ge_人文與文化思考",
        "ge_公民素養與社會探索",
        "ge_自然、生命與科技",
        "ge_common_elective",
    }
    assert flex["required_credits"] == 2
    assert set(flex["eligible_pool_ids"]) == {
        pool_id
        for row in source_rows
        for pool_id in row["eligible_pool_ids"]
    }
    assert flex["policy"]["exclusive"] is True
    assert flex["policy"]["predicate"]["overflow_only"] is True
    assert all(row["excluded_from_free"] is True for row in (*source_rows, flex))
    assert all(row["overflow_routes"] == (flex["requirement_id"],) for row in source_rows)


@pytest.mark.parametrize("cohort", ["112", "113", "114", "115"])
def test_later_cohorts_keep_ten_credit_language_and_have_no_flex(cohort: str):
    curriculum = _primary(cohort)
    named = [
        row
        for row in curriculum["university_requirements"]
        if row.get("bucket") == "university_compulsory"
    ]
    assert len(named) == 5
    assert {row["name"] for row in named} >= {"英文(三)"}
    assert sum(float(row["credits"]) for row in named) == 10
    ge_rows = _ge_rows(curriculum)
    assert not any(row["bucket"] == "ge_flex" for row in ge_rows)
    assert all(row["overflow_routes"] == () for row in ge_rows)


def test_111_flex_allocator_splits_three_credit_source_and_saturates_at_two():
    curriculum = _primary("111")
    ge_rows = _ge_rows(curriculum)
    source = next(row for row in ge_rows if row["bucket"] == "ge_藝術與美感")
    flex = next(row for row in ge_rows if row["bucket"] == "ge_flex")
    pool_ids = tuple(source["eligible_pool_ids"])

    def attempt(attempt_id: str, term: str) -> CourseAttempt:
        return CourseAttempt(
            attempt_id=attempt_id,
            course_id=f"course-{attempt_id}",
            course_name=f"課程{attempt_id}",
            credits=3,
            earned_credits=3,
            academic_term=term,
            identity_status=VERIFIED,
            grade_evidence_state=VERIFIED,
            pool_memberships=pool_ids,
            pool_membership_evidence=tuple(
                (pool_id, VERIFIED, "official:test:ge", "policy")
                for pool_id in pool_ids
            ),
        )

    # A category with two credits remaining routes the residual one credit
    # to the same 111 flex consumer and preserves the three-credit source.
    residual_source = copy.deepcopy(source)
    residual_source["credits"] = 2
    residual_source["required_credits"] = 2
    split_result = allocate_credits((attempt("split", "111-1"),), (residual_source, flex))
    split_portions = {
        portion.requirement_id: portion.credits
        for allocation in split_result.allocations
        for portion in allocation.portions
    }
    assert split_portions[residual_source["requirement_id"]] == 2
    assert split_portions[flex["requirement_id"]] == 1
    assert sum(split_portions.values()) == 3

    saturation_result = allocate_credits(
        (attempt("first", "111-1"), attempt("second", "111-2")),
        (source, flex),
    )
    flex_total = sum(
        portion.credits
        for allocation in saturation_result.allocations
        for portion in allocation.portions
        if portion.requirement_id == flex["requirement_id"]
    )
    assert flex_total == 2
    assert all(allocation.unallocated_credits == 0 for allocation in saturation_result.allocations)


def test_english_three_cannot_replace_111_named_language_requirement_by_name():
    curriculum = _primary("111")
    attempt = CourseAttempt(
        attempt_id="english-three",
        course_id="english-three",
        course_name="英文(三)",
        credits=2,
        earned_credits=2,
        academic_term="111-1",
        identity_status=VERIFIED,
        grade_evidence_state=VERIFIED,
    )
    result = allocate_credits((attempt,), curriculum["university_requirements"])
    assert not any(
        portion.attempt_id == attempt.attempt_id
        for allocation in result.allocations
        for portion in allocation.portions
    )


@pytest.mark.parametrize(
    ("program", "track"),
    [
        ("earth", "earth_environment"),
        ("earth", "life_science"),
        ("apc", "physics"),
        ("apc", "chemistry"),
        ("cs", None),
        ("math", None),
    ],
)
@pytest.mark.parametrize("cohort", ["111", "112", "113", "114", "115"])
def test_primary_it_gate_is_formal_and_pe_keeps_official_memberships(
    cohort: str,
    program: str,
    track: str | None,
):
    curriculum = _primary(cohort, program, track)
    it = _non_credit(curriculum, "university.it_application_design")
    pe = next(row for row in curriculum["non_credit_requirements"] if row["name"] == "體育")

    assert it["kind"] == "OFFICIAL_LISTED_COURSE_COMPLETION"
    assert it["requirement_type"] == "non_credit"
    assert it["required_completions"] == 1
    assert it["min_earned_credits_per_completion"] == 2
    assert it["membership_id"] == "university_it_direct_completion"
    assert it["affects_credit_ledger"] is False
    assert it["waiver_allowed"] is True
    assert it["waiver_authority_ids"] == ("official:genedu",)
    assert it["membership_program_required"] is False
    assert it["membership_track_required"] is False
    assert it["membership_version_required"] is False
    assert it["curriculum_version"] == cohort
    assert it["program_slug"] == program
    expected_track_slug = curriculum.get("track_slug") or "department"
    assert it["track_slug"] == expected_track_slug
    assert it["waiver_requirement_version"] == cohort
    assert it["waiver_program_slug"] == program
    assert it["waiver_track_slug"] == expected_track_slug
    assert it["evidence_state"] == "VERIFIED"
    assert it["coverage_state"] == "COMPLETE"
    assert it["automatic_decision"] is True
    assert it["source_url"].startswith("https://genedu.utaipei.edu.tw/")

    if program == "cs":
        assert it["required"] is False
        assert it["applicability_state"] == "NOT_APPLICABLE"
    else:
        assert it["required"] is True
        assert it["applicability_state"] == "VERIFIED"

    assert pe["membership_id"] == "university_physical_education_completion"
    assert pe["activity_membership_prefix"] == "university_physical_education_activity:"
    assert pe["affects_credit_ledger"] is False
    assert pe["excluded_from_free"] is True
    assert pe["semesters_required"] == 4
    assert pe["required_count"] == 4
    if cohort in {"111", "112", "113"}:
        assert pe["required_hours"] == 0
        assert pe["max_completions_per_term"] is None
    else:
        assert pe["required_hours"] == 8
        assert pe["max_completions_per_term"] == 1


def test_common_policy_source_contract_uses_pdf_page_four_for_111_and_112():
    config = json.loads((ROOT / "rules_config.json").read_text(encoding="utf-8"))
    evidence = config["shared"]["university_common"]["evidence_by_cohort"]
    assert evidence["111"]["pdf_page"] == "PDF p.4"
    assert evidence["112"]["pdf_page"] == "PDF p.4"
    assert evidence["111"]["source_reference"].endswith(":p.4")
    assert evidence["112"]["source_reference"].endswith(":p.4")
    assert evidence["111"]["compulsory_total"] == 8
    assert evidence["111"]["flex_credits"] == 2
    assert evidence["112"]["compulsory_total"] == 10
    assert evidence["112"]["flex_credits"] == 0
