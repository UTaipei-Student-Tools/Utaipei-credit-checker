from __future__ import annotations

from collections import defaultdict

from app.core.normalize import course_key
from app.models import AuditRequest, AuditResult, CourseRecord, CourseStatus, RequirementResult
from app.rules.catalog import CS_DOUBLE_MAJOR, CHEM_DOUBLE_MAJOR, NamedRequirement, ProgramRule, earth_bio_major_rule


PASSING_GRADES = {"抵免", "通過", "及格", "P", "PASS"}
INVALID_NOTE_KEYWORDS = ("先修未過", "擋修", "不得採計", "不採計", "無效")
EXCLUDED_CATEGORIES = ("通識", "體育", "軍訓", "全民國防")


def infer_status(course: CourseRecord) -> CourseStatus:
    text = " ".join(part for part in [course.grade, course.notes] if part)
    if any(keyword in text for keyword in INVALID_NOTE_KEYWORDS):
        return CourseStatus.NEEDS_REVIEW
    if any(keyword in text for keyword in ("退選", "停修", "W")):
        return CourseStatus.INVALID
    if course.status == CourseStatus.IN_PROGRESS:
        return CourseStatus.IN_PROGRESS
    if course.grade:
        normalized = course.grade.strip().upper()
        if normalized in PASSING_GRADES:
            return CourseStatus.PASSED
        try:
            return CourseStatus.PASSED if float(normalized) >= 60 else CourseStatus.FAILED
        except ValueError:
            if "不及格" in course.grade:
                return CourseStatus.FAILED
    return course.status


def sanitize_courses(courses: list[CourseRecord]) -> list[CourseRecord]:
    sanitized = []
    for course in courses:
        status = infer_status(course)
        sanitized.append(course.model_copy(update={"status": status}))
    return sanitized


def _is_excluded_from_free(course: CourseRecord) -> bool:
    haystack = "".join(part or "" for part in [course.category, course.department, course.notes])
    return any(keyword in haystack for keyword in EXCLUDED_CATEGORIES)


def _match_named_requirement(
    requirement: NamedRequirement,
    available: list[CourseRecord],
    used: set[int],
) -> RequirementResult:
    matched: list[CourseRecord] = []
    missing_courses: list[str] = []

    if requirement.key == "school_common":
        for index, course in enumerate(available):
            haystack = "".join(part or "" for part in [course.category, course.department, course.notes])
            if index not in used and any(keyword in haystack for keyword in ("通識", "體育", "全民國防", "共同必修")):
                used.add(index)
                matched.append(course)
                if sum(item.credits for item in matched) >= requirement.required_credits:
                    break
    elif requirement.course_names:
        by_key = defaultdict(list)
        for index, course in enumerate(available):
            if index not in used:
                by_key[course_key(course.name)].append((index, course))
        for name in requirement.course_names:
            options = by_key.get(course_key(name), [])
            if options:
                index, course = options[0]
                used.add(index)
                matched.append(course)
            else:
                missing_courses.append(name)
    else:
        allowed = requirement.pool_keys
        for index, course in enumerate(available):
            if index in used:
                continue
            if allowed and course_key(course.name) not in allowed:
                continue
            if requirement.key == "free_elective" and _is_excluded_from_free(course):
                continue
            used.add(index)
            matched.append(course)
            if sum(item.credits for item in matched) >= requirement.required_credits:
                break

    earned = min(sum(course.credits for course in matched), requirement.required_credits)
    missing = max(requirement.required_credits - earned, 0)
    return RequirementResult(
        key=requirement.key,
        title=requirement.title,
        required_credits=requirement.required_credits,
        earned_credits=earned,
        missing_credits=missing,
        matched_courses=matched,
        missing_courses=missing_courses,
        warnings=list(requirement.warnings),
    )


def audit_program(courses: list[CourseRecord], rule: ProgramRule) -> AuditResult:
    sanitized = sanitize_courses(courses)
    available = [course for course in sanitized if course.status == CourseStatus.PASSED]
    in_progress = [course for course in sanitized if course.status == CourseStatus.IN_PROGRESS]
    needs_review = [course for course in sanitized if course.status == CourseStatus.NEEDS_REVIEW]
    excluded = [course for course in sanitized if course.status in {CourseStatus.FAILED, CourseStatus.INVALID}]

    used: set[int] = set()
    requirement_results = [
        _match_named_requirement(requirement, available, used)
        for requirement in rule.requirements
    ]

    earned_total = min(sum(result.earned_credits for result in requirement_results), rule.total_required_credits)
    return AuditResult(
        profile=rule.title,
        total_required_credits=rule.total_required_credits,
        total_earned_credits=earned_total,
        requirements=requirement_results,
        in_progress=in_progress,
        needs_review=needs_review,
        excluded=excluded,
        warnings=list(rule.warnings),
    )


def audit_all(courses: list[CourseRecord], request: AuditRequest) -> list[AuditResult]:
    rules: list[ProgramRule] = [earth_bio_major_rule(request.earth_bio_domain)]
    if request.include_chem_double_major:
        rules.append(CHEM_DOUBLE_MAJOR)
    if request.include_cs_double_major:
        rules.append(CS_DOUBLE_MAJOR)
    return [audit_program(courses, rule) for rule in rules]
