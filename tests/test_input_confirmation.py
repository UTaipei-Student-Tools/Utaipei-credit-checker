"""Public behavior tests for the transcript input confirmation boundary."""

from dataclasses import FrozenInstanceError
from math import inf

import pytest

from input_confirmation import (
    ConfirmationState,
    SafeErrorCode,
    classify_user_error,
    confirm_confirmation,
    edit_confirmation,
    fingerprint_course_rows,
    mask_person_name,
    mask_student_id,
    normalize_course_rows,
    release_formal_attempts,
    start_confirmation,
)


def course(**overrides):
    row = {
        "course_code": "CS-101",
        "course_name": "資料結構",
        "credits": 3,
        "earned_credits": 3,
        "status": "COMPLETED",
        "term": "113-1",
    }
    row.update(overrides)
    return row


def test_normalization_keeps_only_explicit_analysis_fields_and_reports_unknowns():
    result = normalize_course_rows(
        [course(password="do-not-store", raw_pdf=b"secret", extra_note="不要進分析")]
    )

    assert result.valid is False
    assert len(result.rows) == 1
    assert set(result.rows[0].as_dict()) <= {
        "course_code",
        "course_name",
        "credits",
        "earned_credits",
        "status",
        "term",
        "academic_year",
        "semester",
        "grade",
        "attempt_group",
        "department",
        "course_type",
    }
    assert {diagnostic.code for diagnostic in result.diagnostics} >= {
        "FORBIDDEN_FIELD",
        "UNKNOWN_FIELD",
    }
    assert "do-not-store" not in repr(result)
    assert "secret" not in repr(result)


def test_nested_raw_values_are_rejected_without_stringifying_the_caller_value():
    class Explosive:
        def __str__(self):  # pragma: no cover - the test fails if called
            raise AssertionError("raw caller value was stringified")

        def __repr__(self):  # pragma: no cover - the test fails if called
            raise AssertionError("raw caller value was represented")

    result = normalize_course_rows([course(raw_record=Explosive(), source_blob={"x": 1})])

    assert result.valid is False
    assert {item.code for item in result.diagnostics} == {"FORBIDDEN_FIELD", "UNKNOWN_FIELD"}


def test_fingerprint_is_order_independent_but_changes_for_course_credit_status_or_term():
    rows = [course(), course(course_code="MATH-101", course_name="微積分", term="114-1")]
    original = fingerprint_course_rows(normalize_course_rows(rows).rows)

    assert original == fingerprint_course_rows(normalize_course_rows(list(reversed(rows))).rows)
    assert original != fingerprint_course_rows(normalize_course_rows([course(credits=4), rows[1]]).rows)
    assert original != fingerprint_course_rows(normalize_course_rows([course(status="IN_PROGRESS"), rows[1]]).rows)
    assert original != fingerprint_course_rows(normalize_course_rows([course(term="114-1"), rows[1]]).rows)


def test_confirmation_releases_only_the_exactly_confirmed_current_rows():
    parsed = start_confirmation([course()])

    assert parsed.state is ConfirmationState.PARSED
    confirmed = confirm_confirmation(parsed, parsed.fingerprint)
    assert confirmed.state is ConfirmationState.CONFIRMED
    assert release_formal_attempts(confirmed, confirmed.fingerprint) == confirmed.rows

    edited = edit_confirmation(confirmed, [course(credits=4)])
    assert edited.state is ConfirmationState.STALE
    assert edited.fingerprint != confirmed.fingerprint
    assert release_formal_attempts(edited, confirmed.fingerprint) == ()
    assert release_formal_attempts(edited, edited.fingerprint) == ()


def test_confirmation_fingerprint_mismatch_is_unconfirmed_and_releases_nothing():
    parsed = start_confirmation([course()])

    rejected = confirm_confirmation(parsed, "0" * 64)

    assert rejected.state is ConfirmationState.UNCONFIRMED
    assert release_formal_attempts(rejected, parsed.fingerprint) == ()


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"course_name": "   ", "course_code": ""}, "BLANK_COURSE"),
        ({"credits": -1}, "INVALID_CREDITS"),
        ({"credits": inf}, "INVALID_CREDITS"),
        ({"status": "MAYBE"}, "INVALID_STATUS"),
        ({"earned_credits": None}, "MISSING_EARNED_CREDITS"),
        ({"earned_credits": 4}, "EARNED_CREDITS_EXCEED_CREDITS"),
    ],
)
def test_invalid_manual_edits_are_diagnostics_and_never_formal_attempts(overrides, code):
    parsed = start_confirmation([course(**overrides)])

    assert parsed.state is ConfirmationState.UNCONFIRMED
    assert code in {diagnostic.code for diagnostic in parsed.diagnostics}
    assert release_formal_attempts(parsed, parsed.fingerprint) == ()


def test_duplicate_exact_rows_are_explicitly_rejected():
    parsed = start_confirmation([course(), course()])

    assert parsed.state is ConfirmationState.UNCONFIRMED
    assert any(item.code == "DUPLICATE_EXACT_ROW" for item in parsed.diagnostics)


def test_confirmation_objects_and_rows_are_immutable():
    confirmation = start_confirmation([course()])

    with pytest.raises(FrozenInstanceError):
        confirmation.state = ConfirmationState.CONFIRMED

    with pytest.raises(FrozenInstanceError):
        confirmation.rows[0].credits = 9


def test_privacy_helpers_mask_identifiers_without_echoing_them():
    assert mask_student_id("A123456789") == "A1••••89"
    assert mask_student_id("12") == "••"
    assert mask_person_name("王小明") == "王＊＊"
    assert mask_person_name("A") == "＊"
    assert mask_person_name(1234) == "＊＊"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ValueError("password=/tmp/secret?token=abc transcript=王小明"), SafeErrorCode.INPUT_INVALID),
        (TimeoutError("https://example.invalid/?session=secret"), SafeErrorCode.UPSTREAM_TIMEOUT),
        (PermissionError("Cookie: secret"), SafeErrorCode.PERMISSION_DENIED),
        (UnicodeError("raw transcript"), SafeErrorCode.INPUT_UNREADABLE),
        (RuntimeError("student id 12345678"), SafeErrorCode.GENERAL_FAILURE),
    ],
)
def test_user_error_classifier_returns_fixed_safe_messages(error, code):
    safe = classify_user_error(error)

    assert safe.code is code
    assert safe.message
    assert all(secret not in safe.message for secret in ("password", "secret", "transcript", "12345678"))
