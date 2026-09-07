"""Focused contracts for the source-backed Mathematics primary plans."""

from __future__ import annotations

import pytest

from curriculum_registry import COMPLETE, get_curriculum, list_curriculum_ids
from handbook_rules import get_handbook_config

_EXPECTED_IDS = {
    "primary:111:math",
    "primary:112:math",
    "primary:113:math:math_scientific_computing",
    "primary:113:math:data_science",
    "primary:113:math:math_education",
    "primary:114:math:math_scientific_computing",
    "primary:114:math:data_science",
    "primary:114:math:math_education",
    "primary:115:math:math_scientific_computing",
    "primary:115:math:data_science",
}

_EXPECTED_DOMAIN_MINIMUMS = {
    "math_scientific_computing": 7,
    "data_science": 6,
    "math_education": 3,
}

_SOURCE_HASHES = {
    "111": "25bac8d90f75e7710bbbdb55cc82d7b2a97ebec131e29cf5fc4cb68dabb3597c",
    "112": "afbfc8dc79dc6cc54b9bcc65a4bf8f1fb64b81597b162ed2e04a2d1bf6357c59",
    "113": "bd2a6d5c0892490826654acce97fd6d5d99793042b64aee155805be79d29206a",
    "114": "568d5e5917ccf816b3bdfde29bc7ef6f0b6137b067569e6f199b16afcd9cceed",
    "115": "aece94be62bdfbd41d23ec40b29e89a1a42537b0934378fc4adbdc97e8dbbde3",
}


def _pool(curriculum: dict, suffix: str) -> dict:
    return next(
        pool
        for pool_id, pool in curriculum["course_pools"].items()
        if pool_id.endswith(suffix)
    )


def test_math_primary_ids_are_year_scoped_and_fail_closed_without_a_domain():
    actual = {
        curriculum_id
        for curriculum_id in list_curriculum_ids()
        if curriculum_id.startswith("primary:") and ":math" in curriculum_id
    }
    assert actual == _EXPECTED_IDS

    for invalid_id in (
        "primary:113:math",
        "primary:113:math:department",
        "primary:115:math:math_education",
    ):
        with pytest.raises(KeyError):
            get_curriculum(invalid_id)


def test_math_primary_totals_and_selected_domain_quota_are_source_scoped():
    for curriculum_id in _EXPECTED_IDS:
        curriculum = get_curriculum(curriculum_id)
        year = curriculum["version"]
        track = curriculum.get("track_slug")
        thresholds = curriculum["thresholds"]

        assert curriculum["program_slug"] == "math"
        assert curriculum["student_type"] == "non_teacher"
        assert curriculum["coverage_state"] == COMPLETE
        assert curriculum["pass_eligible"] is True
        assert thresholds["total"] == 128

        if year in {"111", "112"}:
            assert track is None
            assert thresholds["program_common"] == 36
            assert thresholds["program_elective"] == 64
            assert thresholds["department_elective_minimum"] == 64
            assert thresholds["department_alpha_minimum"] == 15
            assert thresholds["free_requirement_minimum"] is None
            assert thresholds["free_amount_semantics"] == "MAXIMUM"
            assert thresholds["free_subset_maxima"][
                "external_department_or_school_professional"
            ] == {"non_teacher": 15, "teacher": 11}
            continue

        assert track in _EXPECTED_DOMAIN_MINIMUMS
        domain_minimum = _EXPECTED_DOMAIN_MINIMUMS[track]
        assert thresholds["program_common"] == 20
        assert thresholds["domain_required"] == domain_minimum
        assert thresholds["domain_required_by_track"][track] == domain_minimum
        assert thresholds["professional_total"] == 65
        assert thresholds["department_elective_minimum"] == 65 - domain_minimum
        assert thresholds["free_requirement_minimum"] == 15
        assert thresholds["free_amount_semantics"] == "MINIMUM"
        assert thresholds["free_subset_maxima"][
            "external_department_or_school_professional"
        ] == {"non_teacher": 15, "teacher": 15}

        required_pool = _pool(curriculum, ":math_domain_required")
        elective_pool = _pool(curriculum, ":math_department_elective")
        assert required_pool["required_credits"] == domain_minimum
        assert elective_pool["required_credits"] == 65 - domain_minimum
        assert required_pool["policy"]["domain"] == track
        assert required_pool["policy"]["student_type"] == "non_teacher"


def test_math_primary_catalogues_keep_named_courses_and_candidate_evidence():
    for curriculum_id in _EXPECTED_IDS:
        curriculum = get_curriculum(curriculum_id)
        common_pool = _pool(curriculum, ":math_common_compulsory")
        elective_pool = _pool(curriculum, ":math_department_elective")

        assert common_pool["candidate_courses"]
        assert elective_pool["candidate_courses"]
        for course in (*common_pool["candidate_courses"], *elective_pool["candidate_courses"]):
            assert course["candidate_only"] is True
            assert course["requirement_type"] == "candidate_course"
            assert course["curriculum_version"] == curriculum["version"]
            assert course["source_url"].startswith("https://curr.utaipei.edu.tw/")
            assert course["source_reference"]
            assert course["evidence_state"] == "VERIFIED"
            assert course["verification_status"] == "VERIFIED"
            assert course["original_clause"]

        names = {course["name"] for course in common_pool["candidate_courses"]}
        if curriculum["version"] == "111" or curriculum["version"] == "112":
            assert "計算機概論" in names
            assert "資訊科學與科學計算" not in names
        else:
            assert "資訊科學與科學計算" in names
            assert "計算機概論" not in names

        if curriculum["version"] in {"114", "115"}:
            assert "Python程式設計" in names


def test_math_alpha_and_external_cap_have_explicit_membership_metadata():
    curriculum = get_curriculum("primary:111:math")
    elective_pool = _pool(curriculum, ":math_department_elective")
    policy = elective_pool["policy"]
    constraints = {item["subset_id"]: item for item in policy["subset_constraints"]}

    assert constraints["math_alpha:111"]["minimum_credits"] == 15
    assert constraints["math_alpha:111"]["observed_requirement_ids"]
    assert constraints["external_department_or_school_professional"]["maximum_credits"] == 15

    alpha_courses = [
        course
        for course in elective_pool["candidate_courses"]
        if "math_alpha:111" in course.get("subset_ids", ())
    ]
    assert alpha_courses
    for course in alpha_courses:
        assertions = {
            item["membership_id"]: item
            for item in course["membership_assertions"]
        }
        assert assertions["external_department_or_school_professional"]["state"] == "NOT_MEMBER"
        assert assertions["external_department_or_school_professional"]["observed_requirement_ids"]

    modern = get_curriculum("primary:113:math:data_science")
    modern_elective = _pool(modern, ":math_department_elective")
    assert not modern_elective["policy"].get("subset_constraints")
    free_pool = _pool(modern, ":free_elective")
    assert free_pool["policy"]["active_subset_maxima"] == {
        "external_department_or_school_professional": {"non_teacher": 15}
    }


def test_math_primary_catalogue_hashes_and_source_sections_are_pinned():
    for year, expected_hash in _SOURCE_HASHES.items():
        catalog = get_handbook_config(year)["math_rules"]["primary_catalog"]
        assert catalog["source_pdf_sha256"] == expected_hash
        assert catalog["source_research_file"] == "tmp/math-primary-source-tables-111-115.json"
        assert catalog["sources"]["common"]["evidence_state"] == "VERIFIED"
        assert catalog["sources"]["professional"]["evidence_state"] == "VERIFIED"
        assert catalog["sources"]["common"]["pdf_page"]
        assert catalog["sources"]["professional"]["pdf_page"]


def test_math_domain_named_rows_are_single_credit_consumers_in_compiler():
    """A domain pool exposes candidates without duplicating named requirements."""

    from graduation_service import _compile_requirements

    for curriculum_id in _EXPECTED_IDS:
        curriculum = get_curriculum(curriculum_id)
        specs, _metadata, _provenance = _compile_requirements(curriculum, scope="primary")
        assert sum(spec.credits_required for spec in specs) == 128
        if curriculum["version"] in {"111", "112"}:
            continue
        domain_specs = [
            spec
            for spec in specs
            if spec.domain.endswith(":required")
            or ":math_domain_required" in spec.requirement_id
        ]
        assert domain_specs
        assert all(spec.kind != "AGGREGATE" for spec in domain_specs)
        assert all(":math_domain_required" not in spec.requirement_id for spec in specs)


def test_modern_math_department_can_overflow_only_into_its_primary_free_requirement():
    from graduation_service import _compile_requirements, _safe_curriculum

    for curriculum_id in _EXPECTED_IDS:
        record = get_curriculum(curriculum_id)
        specs, _, _ = _compile_requirements(_safe_curriculum(record), scope="primary")
        department = next(spec for spec in specs if spec.bucket == "math_department_elective")
        if record["version"] in {"111", "112"}:
            assert not department.overflow_routes
            continue
        free = next(spec for spec in specs if spec.bucket == "free_elective")
        assert department.overflow_routes == (free.requirement_id,)
        assert not free.overflow_routes
