"""Source-backed primary non-credit series contracts."""

from __future__ import annotations

import pytest

from curriculum_registry import get_curriculum

PRIMARY_SCOPES = tuple(
    (program, track)
    for program, tracks in (
        ("earth", ("earth_environment", "life_science")),
        ("apc", ("physics", "chemistry")),
        ("math", (None,)),
        ("cs", (None,)),
    )
    for track in tracks
)
COHORTS = ("111", "112", "113", "114", "115")
SERVICE_SCOPES = {
    ("apc", cohort)
    for cohort in ("111", "112", "113", "114")
} | {
    ("earth", cohort)
    for cohort in ("111", "112", "113", "114")
} | {
    ("math", cohort)
    for cohort in ("111", "112")
} | {
    ("cs", cohort)
    for cohort in ("111", "112", "113")
}


def _curriculum(cohort: str, program: str, track: str | None):
    if program == "math" and track is None and cohort not in {"111", "112"}:
        track = "math_scientific_computing"
    suffix = f":{track}" if track else ""
    return get_curriculum(f"primary:{cohort}:{program}{suffix}")


def _series(curriculum: dict, bucket: str) -> list[dict]:
    return [row for row in curriculum["non_credit_requirements"] if row.get("bucket") == bucket]


@pytest.mark.parametrize("cohort", COHORTS)
@pytest.mark.parametrize(("program", "track"), PRIMARY_SCOPES)
def test_primary_life_guidance_is_one_zero_credit_eight_term_gate(
    cohort: str,
    program: str,
    track: str | None,
):
    curriculum = _curriculum(cohort, program, track)
    rows = _series(curriculum, "life_guidance")

    assert len(rows) == 1
    row = rows[0]
    track_slug = track or "department"
    requirement_id = f"{program}.primary.{cohort}.{track_slug}.life_guidance"
    membership_id = f"university_primary_life_guidance:{cohort}:{program}:{track_slug}"

    assert row["requirement_id"] == requirement_id
    assert row["kind"] == "OFFICIAL_LISTED_COURSE_COMPLETION"
    assert row["requirement_type"] == "non_credit_course_series"
    assert row["credits"] == 0
    assert row["required_count"] == 8
    assert row["required_completions"] == 8
    assert row["distinct_term_required"] is True
    assert row["max_completions_per_term"] == 1
    assert row["require_zero_credits"] is True
    assert row["completion_statuses"] == ("COMPLETED",)
    assert row["membership_id"] == membership_id
    assert row["membership_ids"] == (membership_id,)
    assert row["eligible_course_ids"] == ("28030",)
    assert row["affects_credit_ledger"] is False
    assert row["excluded_from_free"] is True
    assert row["waiver_allowed"] is False
    assert row["automatic_decision"] is True
    assert row["evidence_state"] == "VERIFIED"
    assert row["coverage_state"] == "COMPLETE"
    assert row["scope_state"] == "VERIFIED"
    assert row["applicable_curriculum_version"] == cohort
    assert row["applicable_program_slug"] == program
    assert row["applicable_track_slug"] == track_slug
    assert row["membership_program_required"] is False
    assert row["membership_track_required"] is False
    assert row["membership_version_required"] is False
    # These are applicability descriptors, not attempt-level offering fields.
    assert "program_slug" not in row
    assert "track_slug" not in row
    assert "curriculum_version" not in row
    assert "official_course_identity" not in row
    assert row["source_file"]
    assert row["source_url"].startswith("https://")
    assert row["pdf_page"].startswith("PDF ")
    assert row["table_location"]
    assert row["original_clause"]
    assert row["policy_source"]["source_reference"]

    names = tuple(row["eligible_course_names"])
    if program == "cs":
        assert names == tuple(
            f"大學生活學習與輔導 Part {index}" for index in range(1, 9)
        )
    else:
        assert names == ("大學生活學習與輔導",)
    assert tuple(option["name"] for option in row["eligible_course_options"]) == names
    assert row["predicate"]["require_zero_credits"] is True
    assert row["predicate"]["membership_id"] == membership_id


@pytest.mark.parametrize("cohort", COHORTS)
@pytest.mark.parametrize(("program", "track"), PRIMARY_SCOPES)
def test_service_learning_presence_is_cohort_and_program_scoped(
    cohort: str,
    program: str,
    track: str | None,
):
    curriculum = _curriculum(cohort, program, track)
    rows = _series(curriculum, "service_learning")
    expected = (program, cohort) in SERVICE_SCOPES

    assert bool(rows) is expected
    if not expected:
        return

    assert len(rows) == 1
    row = rows[0]
    track_slug = track or "department"
    membership_id = f"university_primary_service_learning:{cohort}:{program}:{track_slug}"
    assert row["kind"] == "OFFICIAL_LISTED_COURSE_COMPLETION"
    assert row["requirement_type"] == "non_credit_course_series"
    assert row["required_count"] == 2
    assert row["distinct_term_required"] is True
    assert row["max_completions_per_term"] == 1
    assert row["require_zero_credits"] is True
    assert row["eligible_course_names"] == ("服務學習",)
    assert row["eligible_course_ids"] == ("07140",)
    assert row["membership_id"] == membership_id
    assert row["membership_ids"] == (membership_id,)
    assert row["affects_credit_ledger"] is False
    assert row["automatic_decision"] is True
    assert row["applicable_curriculum_version"] == cohort
    assert row["applicable_program_slug"] == program
    assert row["applicable_track_slug"] == track_slug
    assert row["membership_program_required"] is False
    assert row["membership_track_required"] is False
    assert row["membership_version_required"] is False
    if program == "earth":
        assert "required_hours" not in row
        assert "hours_per_completion" not in row
        assert "minimum_public_service_hours_per_completion" not in row
    else:
        assert row["required_hours"] == 48
        assert row["hours_per_completion"] == 24
        assert row["minimum_public_service_hours_per_completion"] == 12
        assert row["hours_evidence_semantics"] == "official_course_completion_certifies_policy_minimum"


@pytest.mark.parametrize("cohort", COHORTS)
@pytest.mark.parametrize("track", ("earth_environment", "life_science"))
def test_earth_primary_catalog_does_not_duplicate_zero_credit_series(
    cohort: str,
    track: str,
):
    curriculum = _curriculum(cohort, "earth", track)
    zero_catalog_names = {
        row["name"]
        for row in curriculum["course_catalog"]
        if row.get("is_zero_credit")
    }
    assert zero_catalog_names == set()
    non_credit_names = [row["name"] for row in curriculum["non_credit_requirements"]]
    assert "大學生學習與生涯發展" not in non_credit_names
    assert non_credit_names.count("大學生活學習與輔導") == 1
    assert non_credit_names.count("服務學習") == (1 if cohort != "115" else 0)


def test_primary_zero_credit_descriptors_do_not_leak_into_secondary_records():
    for curriculum_id in (
        "minor:111:earth",
        "minor:115:earth",
        "minor:111:apc:physics",
        "minor:111:cs",
        "minor:111:math",
    ):
        curriculum = get_curriculum(curriculum_id)
        rows = curriculum["non_credit_requirements"]
        assert not any(
            row.get("bucket") in {"life_guidance", "service_learning"}
            for row in rows
        )
        assert not any(
            str(row.get("membership_id", "")).startswith("university_primary_")
            for row in rows
        )


def test_math_113_service_learning_deletion_is_not_an_empty_required_row():
    curriculum = _curriculum("113", "math", None)
    assert _series(curriculum, "service_learning") == []
    life = _series(curriculum, "life_guidance")
    assert len(life) == 1
    assert life[0]["required_count"] == 8
