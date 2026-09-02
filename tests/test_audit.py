import pytest
from pydantic import ValidationError

from app.core.audit import audit_all, infer_status, sanitize_courses
from app.models import AuditRequest, CourseRecord, CourseStatus


def test_grade_statuses_are_conservative():
    assert infer_status(CourseRecord(name="課程A", credits=1, grade="F")) == CourseStatus.FAILED
    assert infer_status(CourseRecord(name="課程B", credits=1, grade="NP")) == CourseStatus.FAILED
    assert infer_status(CourseRecord(name="課程C", credits=1, grade="A-")) == CourseStatus.PASSED
    assert infer_status(CourseRecord(name="課程D", credits=1, grade="未知")) == CourseStatus.NEEDS_REVIEW
    assert infer_status(CourseRecord(name="課程E", credits=1, grade="W")) == CourseStatus.INVALID


def test_exact_duplicate_records_are_removed_but_semester_records_remain():
    courses = [
        CourseRecord(name="普通生物學", credits=3, semester="114-一", grade="80", source="transcript_pdf"),
        CourseRecord(name="普通生物學", credits=3, semester="114-一", grade="80", source="transcript_pdf"),
        CourseRecord(name="普通生物學", credits=3, semester="114-二", grade="82", source="transcript_pdf"),
    ]
    sanitized = sanitize_courses(courses)
    assert len(sanitized) == 2


def test_year_long_courses_consume_distinct_records():
    courses = [
        CourseRecord(name="普通生物學", credits=3, semester="114-一", grade="80"),
        CourseRecord(name="普通生物學", credits=3, semester="114-二", grade="82"),
        CourseRecord(name="普通生物學實驗", credits=1, semester="114-一", grade="85"),
        CourseRecord(name="地球科學實驗", credits=1, semester="114-二", grade="85"),
        CourseRecord(name="地球科學", credits=3, semester="114-一", grade="80"),
        CourseRecord(name="地球科學", credits=3, semester="114-二", grade="80"),
        CourseRecord(name="資料處理與分析", credits=3, grade="80"),
        CourseRecord(name="書報討論", credits=2, grade="80"),
        CourseRecord(name="基礎生態學", credits=3, grade="80"),
        CourseRecord(name="環境影響評估", credits=2, grade="80"),
    ]
    result = audit_all(courses, AuditRequest())[0]
    common = next(item for item in result.requirements if item.key == "earth_common_required")
    assert common.complete is True
    assert common.earned_credits == 24
    assert len(common.matched_courses) == 10


def test_missing_second_semester_is_reported():
    courses = [CourseRecord(name="普通生物學", credits=3, semester="114-一", grade="80")]
    result = audit_all(courses, AuditRequest())[0]
    common = next(item for item in result.requirements if item.key == "earth_common_required")
    assert common.complete is False
    assert common.missing_courses.count("普通生物學") == 1


def test_zero_credit_completion_requirements_use_occurrences():
    courses = [
        *[
            CourseRecord(name="大學生活學習與輔導", credits=0, semester=f"semester-{index}", grade="P")
            for index in range(8)
        ],
        CourseRecord(name="服務學習", credits=0, semester="114-一", grade="P"),
        CourseRecord(name="服務學習", credits=0, semester="114-二", grade="P"),
    ]
    result = audit_all(courses, AuditRequest())[0]
    guidance = next(item for item in result.requirements if item.key == "college_guidance")
    service = next(item for item in result.requirements if item.key == "service_learning")
    assert guidance.complete is True
    assert len(guidance.matched_courses) == 8
    assert service.complete is True
    assert len(service.matched_courses) == 2


def test_other_department_courses_accept_opposite_domain_courses():
    courses = [
        CourseRecord(name="脊椎動物學", credits=3, grade="80"),
        CourseRecord(name="古生物學", credits=3, grade="80"),
    ]
    result = audit_all(courses, AuditRequest())[0]
    other_department = next(
        item for item in result.requirements if item.key == "earth_department_elective"
    )
    assert {course.name for course in other_department.matched_courses} == {"脊椎動物學"}
    assert other_department.earned_credits == 3


def test_invalid_and_in_progress_not_counted():
    courses = [
        CourseRecord(name="計算機概論", credits=3, grade="59"),
        CourseRecord(name="C 程式設計", credits=3, status=CourseStatus.IN_PROGRESS),
        CourseRecord(name="Java 程式設計", credits=3, notes="先修未過"),
    ]
    result = audit_all(
        courses,
        AuditRequest(include_cs_double_major=True),
    )[1]
    assert result.requirements[0].earned_credits == 0
    assert len(result.excluded) == 1
    assert len(result.in_progress) == 1
    assert len(result.needs_review) == 1


def test_double_major_is_explicitly_provisional():
    result = audit_all([], AuditRequest(include_cs_double_major=True))[1]
    assert result.provisional is True
    assert result.complete is False
    assert any("兼充" in warning for warning in result.warnings)


def test_unsupported_admission_year_is_rejected():
    with pytest.raises(ValidationError):
        AuditRequest(admission_year=113)


def test_retake_does_not_double_count_in_elective_pool():
    courses = [
        CourseRecord(name="資料庫系統", credits=3, semester="113-一", grade="70"),
        CourseRecord(name="資料庫系統", credits=3, semester="114-一", grade="85"),
    ]
    result = audit_all(courses, AuditRequest(include_cs_double_major=True))[1]
    other = next(item for item in result.requirements if item.key == "cs_double_other")
    assert other.earned_credits == 3
    assert any("重複及格紀錄" in warning for warning in result.warnings)


def test_school_common_categories_cannot_substitute_for_each_other():
    courses = [
        CourseRecord(name="某分類通識", credits=20, grade="80", category="分類選修"),
        CourseRecord(name="某共同選修", credits=2, grade="80", category="共同選修"),
    ]
    result = audit_all(courses, AuditRequest())[0]
    common_required = next(item for item in result.requirements if item.key == "school_common_required")
    category_elective = next(item for item in result.requirements if item.key == "school_category_elective")
    common_elective = next(item for item in result.requirements if item.key == "school_common_elective")
    assert common_required.earned_credits == 0
    assert common_required.complete is False
    assert category_elective.earned_credits == 16
    assert category_elective.complete is True
    assert common_elective.earned_credits == 2
    assert common_elective.complete is True


def test_free_elective_is_estimated_but_requires_manual_verification():
    courses = [CourseRecord(name=f"跨系選修{index}", credits=3, grade="80") for index in range(5)]
    result = audit_all(courses, AuditRequest())[0]
    free = next(item for item in result.requirements if item.key == "free_elective")
    assert free.earned_credits == 15
    assert free.verification_required is True
    assert free.complete is False


def test_department_common_elective_is_not_misclassified_as_school_common():
    courses = [
        CourseRecord(name="地生系專題選修", credits=3, grade="80", category="系共同選修"),
    ]
    result = audit_all(courses, AuditRequest())[0]
    school_common = next(item for item in result.requirements if item.key == "school_common_elective")
    assert school_common.earned_credits == 0
    assert school_common.complete is False


def test_school_common_without_category_metadata_requires_verification():
    courses = [CourseRecord(name="國文", credits=2, grade="80")]
    result = audit_all(courses, AuditRequest())[0]
    common_required = next(item for item in result.requirements if item.key == "school_common_required")
    assert common_required.earned_credits == 0
    assert common_required.verification_required is True
