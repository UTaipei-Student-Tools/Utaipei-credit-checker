from __future__ import annotations

from collections import Counter, defaultdict, deque

from app.core.normalize import course_key
from app.models import AuditRequest, AuditResult, CourseRecord, CourseStatus, RequirementResult
from app.rules.catalog import (
    CHEM_DOUBLE_MAJOR,
    CS_DOUBLE_MAJOR,
    CS_MINOR,
    NamedRequirement,
    ProgramRule,
    earth_bio_major_rule,
)

PASSING_GRADES = {
    "抵免",
    "通過",
    "及格",
    "P",
    "PASS",
    "S",
    "A+",
    "A",
    "A-",
    "B+",
    "B",
    "B-",
    "C+",
    "C",
    "C-",
    "D+",
    "D",
    "D-",
}
FAILING_GRADES = {"F", "FAIL", "NP", "N", "U", "不及格", "不通過", "缺考", "曠考"}
INVALID_NOTE_KEYWORDS = ("先修未過", "擋修", "不得採計", "不採計", "無效")
WITHDRAWAL_MARKERS = ("退選", "停修")
FREE_EXCLUDED_KEYWORDS = (
    "通識",
    "體育",
    "軍訓",
    "全民國防",
    "校共同必修",
    "分類選修",
    "共同選修",
    "國文",
    "英文",
    "英語",
    "服務學習",
    "大學生活學習與輔導",
)


def infer_status(course: CourseRecord) -> CourseStatus:
    """Infer status conservatively; an unknown non-empty grade needs review."""

    text = " ".join(part for part in [course.grade, course.notes] if part)
    if any(keyword in text for keyword in INVALID_NOTE_KEYWORDS):
        return CourseStatus.NEEDS_REVIEW
    if any(marker in text for marker in WITHDRAWAL_MARKERS):
        return CourseStatus.INVALID

    grade = (course.grade or "").strip()
    normalized = grade.upper()
    if normalized == "W":
        return CourseStatus.INVALID

    if course.status in {CourseStatus.INVALID, CourseStatus.NEEDS_REVIEW}:
        return course.status
    if course.status == CourseStatus.IN_PROGRESS and not grade:
        return CourseStatus.IN_PROGRESS

    if grade:
        if normalized in PASSING_GRADES or grade in PASSING_GRADES:
            return CourseStatus.PASSED
        if normalized in FAILING_GRADES or grade in FAILING_GRADES:
            return CourseStatus.FAILED
        try:
            numeric_grade = float(normalized)
        except ValueError:
            return CourseStatus.NEEDS_REVIEW
        return CourseStatus.PASSED if numeric_grade >= 60 else CourseStatus.FAILED

    # Manual records without a grade may intentionally state their status.
    return course.status


def sanitize_courses(courses: list[CourseRecord]) -> list[CourseRecord]:
    sanitized: list[CourseRecord] = []
    seen: set[tuple[str, float, str | None, str | None, CourseStatus, str]] = set()
    for course in courses:
        status = infer_status(course)
        normalized = course.model_copy(update={"status": status})
        fingerprint = (
            course_key(normalized.name),
            normalized.credits,
            normalized.semester,
            normalized.grade,
            normalized.status,
            normalized.source,
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        sanitized.append(normalized)
    return sanitized


def _deduplicate_passed_attempts(
    available: list[CourseRecord],
    rule: ProgramRule,
) -> tuple[list[CourseRecord], list[CourseRecord]]:
    """Keep one passed attempt per course unless a named rule requires repeats.

    This prevents a retake from being credited twice in elective pools while
    retaining official year-long requirements such as General Biology.
    """

    multiplicity: Counter[str] = Counter()
    for requirement in rule.requirements:
        counts = Counter(course_key(name) for name in requirement.course_names)
        for key, count in counts.items():
            multiplicity[key] = max(multiplicity[key], count)

    grouped: dict[str, list[tuple[int, CourseRecord]]] = defaultdict(list)
    for index, course in enumerate(available):
        grouped[course_key(course.name)].append((index, course))

    keep_indices: set[int] = set()
    duplicates: list[CourseRecord] = []
    for key, items in grouped.items():
        limit = max(1, multiplicity.get(key, 1))
        # Prefer the attempt carrying more credits; retain source order on ties.
        ranked = sorted(items, key=lambda item: (-item[1].credits, item[0]))
        keep_indices.update(index for index, _ in ranked[:limit])
        duplicates.extend(course for _, course in ranked[limit:])

    return (
        [course for index, course in enumerate(available) if index in keep_indices],
        duplicates,
    )


def _classification_text(course: CourseRecord, *, include_name: bool = False) -> str:
    parts = [course.category, course.department, course.notes]
    if include_name:
        parts.insert(0, course.name)
    return " ".join(part or "" for part in parts)


def _is_excluded_from_free(course: CourseRecord) -> bool:
    haystack = _classification_text(course, include_name=True)
    return any(keyword in haystack for keyword in FREE_EXCLUDED_KEYWORDS)


def _match_named_requirement(
    requirement: NamedRequirement,
    available: list[CourseRecord],
    used: set[int],
) -> RequirementResult:
    matched: list[CourseRecord] = []
    missing_courses: list[str] = []
    warnings = list(requirement.warnings)
    verification_required = False

    if requirement.category_keywords:
        accepted_categories = {course_key(value) for value in requirement.category_keywords}
        has_category_metadata = False
        for index, course in enumerate(available):
            if index in used:
                continue
            category = (course.category or "").strip()
            if category:
                has_category_metadata = True
            if course_key(category) in accepted_categories:
                used.add(index)
                matched.append(course)
                if sum(item.credits for item in matched) >= requirement.required_credits:
                    break
        if not has_category_metadata:
            verification_required = True
            warnings.append("來源未提供課程類別，這一類學分無法可靠自動歸類。")
        elif sum(item.credits for item in matched) < requirement.required_credits:
            warnings.append("目前可辨認的課程類別不足，請對照正式成績單或人工核對。")
    elif requirement.course_names:
        by_key: dict[str, deque[tuple[int, CourseRecord]]] = defaultdict(deque)
        for index, course in enumerate(available):
            if index not in used:
                by_key[course_key(course.name)].append((index, course))
        for options in by_key.values():
            ranked = sorted(options, key=lambda item: (-item[1].credits, item[0]))
            options.clear()
            options.extend(ranked)
        for name in requirement.course_names:
            options = by_key.get(course_key(name))
            while options and options[0][0] in used:
                options.popleft()
            if options:
                index, course = options.popleft()
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
        if requirement.key == "free_elective" and matched:
            verification_required = True
            warnings.append("已列出可採計候選課程，但排除通識／體育及理學院至少3學分條件仍需人工確認。")

    raw_earned = sum(course.credits for course in matched)
    earned = min(raw_earned, requirement.required_credits) if requirement.required_credits > 0 else 0
    missing = max(requirement.required_credits - earned, 0)
    complete = missing == 0 and not missing_courses and not verification_required
    return RequirementResult(
        key=requirement.key,
        title=requirement.title,
        required_credits=requirement.required_credits,
        earned_credits=earned,
        missing_credits=missing,
        complete=complete,
        verification_required=verification_required,
        matched_courses=matched,
        missing_courses=missing_courses,
        warnings=warnings,
    )


def audit_program(courses: list[CourseRecord], rule: ProgramRule) -> AuditResult:
    sanitized = sanitize_courses(courses)
    passed = [course for course in sanitized if course.status == CourseStatus.PASSED]
    available, duplicate_attempts = _deduplicate_passed_attempts(passed, rule)
    in_progress = [course for course in sanitized if course.status == CourseStatus.IN_PROGRESS]
    needs_review = [course for course in sanitized if course.status == CourseStatus.NEEDS_REVIEW]
    excluded = [course for course in sanitized if course.status in {CourseStatus.FAILED, CourseStatus.INVALID}]

    used: set[int] = set()
    requirement_results = [
        _match_named_requirement(requirement, available, used)
        for requirement in rule.requirements
    ]

    earned_total = min(sum(result.earned_credits for result in requirement_results), rule.total_required_credits)
    complete = all(result.complete for result in requirement_results) and not needs_review and not rule.provisional
    warnings = list(rule.warnings)
    if duplicate_attempts:
        names = "、".join(dict.fromkeys(course.name for course in duplicate_attempts))
        warnings.append(f"重複及格紀錄未自動重複採計：{names}。可重複採計的特殊課程請人工確認。")

    metadata = rule.metadata
    return AuditResult(
        profile=rule.title,
        rule_version=metadata.get("rule_version", rule.key),
        source_title=metadata.get("source_title"),
        source_url=metadata.get("source_url"),
        reviewed_at=metadata.get("reviewed_at"),
        provisional=rule.provisional,
        complete=complete,
        total_required_credits=rule.total_required_credits,
        total_earned_credits=earned_total,
        requirements=requirement_results,
        in_progress=in_progress,
        needs_review=needs_review,
        excluded=excluded,
        warnings=warnings,
    )


def audit_all(courses: list[CourseRecord], request: AuditRequest) -> list[AuditResult]:
    rules: list[ProgramRule] = [
        earth_bio_major_rule(request.earth_bio_domain, request.admission_year)
    ]
    if request.include_chem_double_major:
        rules.append(CHEM_DOUBLE_MAJOR)
    if request.include_cs_double_major:
        rules.append(CS_DOUBLE_MAJOR)
    if request.include_cs_minor:
        rules.append(CS_MINOR)
    return [audit_program(courses, rule) for rule in rules]
