"""Admission cohort and the selected primary handbook are distinct facts."""

from curriculum_registry import resolve_rule_context
from graduation_service import EvaluationRequest, evaluate


def test_explicit_primary_handbook_version_is_preserved_when_it_differs_from_admission():
    result = resolve_rule_context(
        {
            "admission_cohort": "114",
            "primary_curriculum_id": "primary:115:earth:earth_environment",
            "primary_program": "earth",
            "primary_track": "earth_environment",
            "program_type": "單主修",
        }
    )

    primary = result["dimensions"]["primary_curriculum"]
    assert result["admission_cohort"] == "114"
    assert primary["curriculum_id"] == "primary:115:earth:earth_environment"
    assert primary["curriculum"]["version"] == "115"
    assert primary["status"] == "MANUAL_REVIEW"
    assert result["status"] == "MANUAL_REVIEW"


def test_explicit_primary_handbook_matching_admission_remains_resolved():
    result = resolve_rule_context(
        {
            "admission_cohort": "115",
            "primary_curriculum_id": "primary:115:earth:earth_environment",
            "primary_program": "earth",
            "primary_track": "earth_environment",
            "program_type": "單主修",
        }
    )

    primary = result["dimensions"]["primary_curriculum"]
    assert primary["curriculum_id"] == "primary:115:earth:earth_environment"
    assert primary["status"] == "RESOLVED"


def test_explicit_primary_identity_mismatch_is_not_repaired_by_admission_cohort():
    result = resolve_rule_context(
        {
            "admission_cohort": "115",
            "primary_curriculum_id": "primary:115:apc:physics",
            "primary_program": "earth",
            "primary_track": "earth_environment",
            "program_type": "單主修",
        }
    )

    primary = result["dimensions"]["primary_curriculum"]
    assert primary["curriculum_id"] == "primary:115:apc:physics"
    assert primary["status"] == "MANUAL_REVIEW"
    assert result["can_pass"] is False


def test_explicit_non_primary_id_fails_closed_without_cohort_fallback():
    result = resolve_rule_context(
        {
            "admission_cohort": "114",
            "primary_curriculum_id": "target:double_major:114:earth:earth_environment",
            "primary_program": "earth",
            "primary_track": "earth_environment",
            "program_type": "單主修",
        }
    )

    primary = result["dimensions"]["primary_curriculum"]
    assert primary["value"] == "target:double_major:114:earth:earth_environment"
    assert primary["status"] == "MISSING"
    assert result["can_pass"] is False


def test_evaluation_snapshot_keeps_admission_and_explicit_primary_handbook_separate():
    request = EvaluationRequest(
        admission_cohort="114",
        primary_curriculum_id="primary:115:earth:earth_environment",
    )

    payload = evaluate(request).as_dict()

    assert payload["request"]["admission_cohort"] == "114"
    assert payload["request"]["primary_curriculum_id"] == "primary:115:earth:earth_environment"
    assert payload["rule_resolution"]["admission_cohort"] == "114"
    assert payload["rule_resolution"]["primary_curriculum_id"] == "primary:115:earth:earth_environment"
    assert payload["rule_resolution"]["dimensions"]["primary_curriculum"]["status"] == "MANUAL_REVIEW"
    assert payload["verdict"] == "UNKNOWN"
