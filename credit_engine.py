"""
Graduation Credit Evaluation Engine — v2
新增：體育追蹤、通識/校必修分離、自由選修正確溢流
"""

import re
from copy import deepcopy

from handbook_rules import (
    get_apc_target_requirements,
    get_credit_requirements,
    get_rule_sets,
    get_rules_meta,
    normalize_course_name,
)
from equivalency_audit import (
    apply_equivalency_audit_to_report,
    audit_equivalency_decisions,
    source_attempt_id,
)
from policy_audit import (
    GRADUATION_UNKNOWN,
    GRADUATION_NOT_SATISFIED,
    GRADUATION_SATISFIED,
    UNKNOWN,
    assess_cohort_match,
    assess_cs_manual_gate,
    assess_double_major_eligibility,
    get_double_structure,
    get_primary_requirements,
    normalize_primary_program,
)

# 匹配除錯開關：出問題時可打開以取得匹配決策輸出
DEBUG_MATCHING = False

# Shared-credit reuse is an aggregate policy allowance.  The deterministic
# course slices below are useful for planning math, but they must never be
# presented as department-approved course identities.
_SHARED_REUSE_APPROVAL_SCOPE = "aggregate_allowance_only"
_SHARED_REUSE_ALLOCATION_TYPE = "simulated"
_SHARED_REUSE_COURSE_IDENTITY_STATUS = "not_official"
_SHARED_REUSE_SELECTION_BASIS = "deterministic_planning_only"
_SHARED_REUSE_OFFICIAL_IDENTITY_NOTE = (
    "共同修課核准僅代表合計額度；列出的課名只是規劃用模擬配置，不代表系所已核准該課程身分。"
    "正式共同修課科目身分須由系所證據確認。"
)


def dbg(msg):
    if DEBUG_MATCHING:
        try:
            print("[MATCH_DBG]", msg)
        except Exception:
            pass


def _normalized_names(course_map):
    return {normalize_course_name(name) for name in course_map if normalize_course_name(name)}


def _collect_rule_names(rule_sets):
    """Collect exact program titles for the selected handbook only."""
    earth = rule_sets["earth_life_major"]
    apc = rule_sets["apc_rules"]
    cs = rule_sets["cs_rules"]
    names = set()
    names.update(_normalized_names(rule_sets["university_common"]["compulsory"]))
    names.update(_normalized_names(earth["common_compulsory"]))
    for group in earth.get("common_alternatives", []):
        names.update(_normalized_names(group.get("options", {})))
    for mapping in earth.get("domains", {}).values():
        names.update(_normalized_names(mapping))
    for mapping in earth.get("domain_electives", {}).values():
        names.update(_normalized_names(mapping))
    names.update(_normalized_names(apc.get("basic_core", {})))
    names.update(_normalized_names(apc.get("shared_other_required", {})))
    for division in apc.get("divisions", {}).values():
        names.update(_normalized_names(division.get("compulsory", {})))
    names.update(_normalized_names(cs.get("department_courses", {})))
    for scope_aliases in rule_sets.get("course_aliases", {}).values():
        for official, aliases in scope_aliases.items():
            names.add(normalize_course_name(official))
            names.update(normalize_course_name(alias) for alias in aliases)
    return {name for name in names if name}


def _collect_major_names(earth_rules):
    names = _normalized_names(earth_rules.get("common_compulsory", {}))
    for group in earth_rules.get("common_alternatives", []):
        names.update(_normalized_names(group.get("options", {})))
    for mapping in earth_rules.get("domains", {}).values():
        names.update(_normalized_names(mapping))
    for mapping in earth_rules.get("domain_electives", {}).values():
        names.update(_normalized_names(mapping))
    return names


def _collect_major_compulsory(earth_rules):
    names = _normalized_names(earth_rules.get("common_compulsory", {}))
    for group in earth_rules.get("common_alternatives", []):
        names.update(_normalized_names(group.get("options", {})))
    for mapping in earth_rules.get("domains", {}).values():
        names.update(_normalized_names(mapping))
    return names


def _is_in_program_rules(name_norm, raw_norm, rule_names):
    """Use exact normalized identity; substring matches are intentionally forbidden."""
    return name_norm in rule_names or raw_norm in rule_names


def _course_credit_matches(course, expected_credit):
    if expected_credit is None:
        return True
    try:
        return abs(float(course.get("total_credit") or 0.0) - float(expected_credit)) < 1e-6
    except (TypeError, ValueError):
        return False


def _course_matches_rule(course, rule_name, expected_credit=None, aliases=()):
    accepted = {normalize_course_name(rule_name)}
    accepted.update(normalize_course_name(alias) for alias in aliases)
    accepted.discard("")
    course_name = normalize_course_name(course.get("name", "") or "")
    raw_name = normalize_course_name(course.get("raw_name", "") or "")
    return (course_name in accepted or raw_name in accepted) and _course_credit_matches(course, expected_credit)


def _explicit_aliases(alias_sets, scope, rule_name):
    return alias_sets.get(scope, {}).get(rule_name, [])


def _find_best_alternative(courses, options, consumed_set):
    candidates = []
    for option_name, expected_credit in options.items():
        for course in courses:
            if id(course) in consumed_set:
                continue
            if _course_matches_rule(course, option_name, expected_credit):
                rank = 2 if course.get("is_completed") else 1 if course.get("is_in_progress") else 0
                candidates.append((rank, option_name, course))
    if not candidates:
        return None
    _, _, selected = max(
        candidates,
        key=lambda item: (item[0], _record_quality(item[2]), normalize_course_name(item[1]), _course_stable_key(item[2])),
    )
    consumed_set.add(id(selected))
    return selected


def _earned_and_in_progress(course):
    completed = max(0.0, float(course.get("completed_credit") or 0.0))
    in_progress = 0.0
    if course.get("is_in_progress"):
        in_progress = max(0.0, float(course.get("total_credit") or 0.0) - completed)
    return completed, in_progress


def _allocation_copy(course, completed, in_progress, note):
    """Create a reporting-only slice without mutating the parsed transcript row."""
    allocated = dict(course)
    attempt_id = course.get("attempt_id") or _stable_attempt_id(course)
    allocated["attempt_id"] = attempt_id
    allocated["_origin_id"] = course.get("_origin_id", attempt_id)
    allocated["total_credit"] = completed + in_progress
    allocated["completed_credit"] = completed
    allocated["is_completed"] = completed > 0
    allocated["is_in_progress"] = in_progress > 0
    allocated["allocation_note"] = note
    allocated["allocation_id"] = f"{attempt_id}|{note}|{completed:.6f}|{in_progress:.6f}"
    return allocated


def _cap_course_bucket(courses, credit_limit, label):
    """Cap a requirement bucket while preserving every earned/planned credit.

    Completed credits fill the quota before in-progress credits.  If the last
    course crosses the threshold, reporting-only course slices make the exact
    recognized and overflow amounts visible instead of showing e.g. 23/20.
    """
    limit = max(0.0, float(credit_limit or 0.0))
    allocations = [{"completed": 0.0, "ip": 0.0} for _ in courses]
    remaining = limit

    for index, item in enumerate(courses):
        completed, _ = _earned_and_in_progress(item)
        amount = min(completed, remaining)
        allocations[index]["completed"] = amount
        remaining -= amount

    for index, item in enumerate(courses):
        _, in_progress = _earned_and_in_progress(item)
        amount = min(in_progress, remaining)
        allocations[index]["ip"] = amount
        remaining -= amount

    recognized = []
    overflow = []
    recognized_completed = 0.0
    recognized_ip = 0.0
    for item, allocation in zip(courses, allocations):
        completed, in_progress = _earned_and_in_progress(item)
        used_completed = allocation["completed"]
        used_ip = allocation["ip"]
        extra_completed = completed - used_completed
        extra_ip = in_progress - used_ip

        recognized_completed += used_completed
        recognized_ip += used_ip
        earned_total = completed + in_progress
        used_total = used_completed + used_ip

        if earned_total <= 1e-6:
            # Keep a failed/unresolved exact attempt visible beside the missing rule.
            recognized.append(item)
        elif used_total > 1e-6:
            if abs(used_total - earned_total) < 1e-6:
                recognized.append(item)
            else:
                recognized.append(
                    _allocation_copy(item, used_completed, used_ip, f"{label}採認 {used_total:g} 學分")
                )

        if extra_completed + extra_ip > 1e-6:
            overflow.append(
                _allocation_copy(
                    item,
                    extra_completed,
                    extra_ip,
                    f"{label}門檻超額，轉自由選修 {extra_completed + extra_ip:g} 學分",
                )
            )

    return recognized, overflow, recognized_completed, recognized_ip


def _iter_primary_allocation_courses(report):
    """Yield non-target allocated rows in a stable bucket order."""

    common = report.get("common", {})
    for course in common.get("compulsory_courses", []):
        yield "common_compulsory", course
    for category in sorted(common.get("categories", {}), key=str):
        for course in common.get("categories", {}).get(category, {}).get("courses", []):
            yield f"ge:{category}", course
    for course in common.get("common_elective_courses", []):
        yield "common_elective", course

    major = report.get("major", {})
    for key, bucket in (
        ("dept_compulsory_courses", "major_common_compulsory"),
        ("domain_compulsory_courses", "domain_compulsory"),
        ("domain_elective_courses", "domain_elective"),
        ("other_elective_courses", "other_elective"),
    ):
        for course in major.get(key, []):
            yield bucket, course


def _build_shared_reuse_allocations(report, allowance):
    """Keep the legacy helper inert; aggregate allowances are not bindings.

    Older integrations may still call this private compatibility helper.  It
    intentionally returns no rows and no effective credits.  New callers must
    use :func:`equivalency_audit.audit_equivalency_decisions` with an explicit
    source attempt and target requirement.
    """

    try:
        allowance_value = max(0.0, float(allowance or 0.0))
    except (TypeError, ValueError):
        allowance_value = 0.0
    return {
        "allowance": allowance_value,
        "completed": 0.0,
        "ip": 0.0,
        "total": 0.0,
        "rows": [],
        "unallocated_allowance": allowance_value,
        "approval_scope": "legacy_unbound",
        "allocation_type": "not_counted",
        "selection_basis": "legacy_compatibility_only",
        "course_identity_status": "not_bound",
        "official_course_identity_note": "舊版 aggregate 共同修課欄位未綁定來源與目標，不計入有效進度。",
    }


def _empty_shared_reuse():
    """Return the stable shape used when sharing is not applicable/evidenced."""

    return {
        "allowance": 0.0,
        "completed": 0.0,
        "ip": 0.0,
        "total": 0.0,
        "rows": [],
        "unallocated_allowance": 0.0,
        "approval_scope": _SHARED_REUSE_APPROVAL_SCOPE,
        "allocation_type": _SHARED_REUSE_ALLOCATION_TYPE,
        "selection_basis": _SHARED_REUSE_SELECTION_BASIS,
        "course_identity_status": _SHARED_REUSE_COURSE_IDENTITY_STATUS,
        "official_course_identity_note": _SHARED_REUSE_OFFICIAL_IDENTITY_NOTE,
    }


def _course_numeric_score(course):
    """Return the best numeric transcript score for deterministic tie-breaking."""

    scores = []
    for key in ("sem1_score", "sem2_score", "score"):
        value = str(course.get(key, "") or "").strip()
        try:
            scores.append(float(value))
        except (TypeError, ValueError):
            continue
    return max(scores, default=-1.0)


def _course_status_rank(course):
    if course.get("is_completed"):
        return 3
    if course.get("is_in_progress"):
        return 2
    if course.get("is_zero_credit"):
        return 1
    return 0


def _course_stable_key(course):
    """Stable order independent of transcript row order."""

    return (
        normalize_course_name(course.get("name", "") or ""),
        round(float(course.get("total_credit") or 0.0), 6),
        -_course_status_rank(course),
        -round(float(course.get("completed_credit") or 0.0), 6),
        -round(_course_numeric_score(course), 6),
        str(course.get("academic_year", "") or ""),
        str(course.get("semester", "") or ""),
        normalize_course_name(course.get("raw_name", "") or ""),
    )


def _attempt_identity(course):
    """Identity of one offering/term, excluding score quality."""

    try:
        total_credit = round(float(course.get("total_credit") or 0.0), 6)
    except (TypeError, ValueError):
        total_credit = 0.0
    return (
        normalize_course_name(course.get("name", "") or ""),
        total_credit,
        str(course.get("academic_year", "") or ""),
        str(course.get("semester", "") or ""),
        str(course.get("sem1_credit", "") or ""),
        str(course.get("sem2_credit", "") or ""),
    )


def _stable_attempt_id(course):
    """Stable human-readable ID for allocation/audit joins."""

    return "attempt:" + "|".join(str(value) for value in _attempt_identity(course))


def _stable_course_id(course):
    """Backward-compatible alias for the stable attempt identity."""

    return _attempt_identity(course)


def _record_quality(course):
    """Quality tuple used when the same title/credit appears repeatedly."""

    return (
        _course_status_rank(course),
        round(float(course.get("completed_credit") or 0.0), 6),
        round(_course_numeric_score(course), 6),
        str(course.get("academic_year", "") or ""),
        str(course.get("semester", "") or ""),
        normalize_course_name(course.get("raw_name", "") or ""),
    )


def _canonicalize_courses(courses):
    """Copy, sort, and collapse repeated title/credit transcript records.

    A transcript can contain the same passed class more than once after PDF
    layout reconstruction or a repeat attempt.  The evaluator must never
    award both records.  Different credit values remain distinct so a wrong
    credit attempt can still be shown for manual review.
    """

    grouped = {}
    input_count = 0
    for original in courses or []:
        if not isinstance(original, dict):
            continue
        input_count += 1
        copied = deepcopy(original)
        name = normalize_course_name(copied.get("name", "") or copied.get("raw_name", ""))
        copied["name"] = name
        # Exact parser duplicates from the same offering collapse, while a
        # repeated title/credit in another academic term remains an attempt.
        key = _attempt_identity(copied)
        grouped.setdefault(key, []).append(copied)

    selected = []
    duplicate_count = 0
    for records in grouped.values():
        chosen = max(records, key=_record_quality)
        chosen["attempt_id"] = _stable_attempt_id(chosen)
        chosen["_origin_id"] = chosen["attempt_id"]
        selected.append(chosen)
        duplicate_count += max(0, len(records) - 1)
    selected.sort(key=_course_stable_key)
    return selected, {"input_count": input_count, "canonical_count": len(selected), "deduplicated_count": duplicate_count}


# 體育課名稱關鍵字（0學分但須追蹤修讀狀態）
PE_KEYWORDS = [
    "體育",
    "桌球",
    "網球",
    "羽球",
    "籃球",
    "排球",
    "游泳",
    "武術",
    "跆拳道",
    "有氧",
    "高爾夫",
    "棒球",
    "壘球",
    "足球",
    "乒乓",
]


def _is_pe_course(c):
    for kw in PE_KEYWORDS:
        if kw in c["name"] or kw in c["raw_name"]:
            return True
    return False


ZERO_CREDIT_OVERRIDE_NAMES = [
    "普通數學",
    "普通數學(一)",
    "普通數學(二)",
]

# 某些名稱包含「環境」但實際上為系內選修，列在此處以避免被誤判為通識
MAJOR_ELECTIVE_OVERRIDE = ["全球環境變遷", "環境教育", "環境政策", "環境倫理"]


def _is_exempt_course(c):
    raw = c.get("raw_name", "") or ""
    return any(name in c["name"] or name in raw for name in ZERO_CREDIT_OVERRIDE_NAMES)


def _plan_requirements(plan, program_type="單主修", target_plan=None):
    """Adapt a policy plan to the legacy renderer's requirement keys."""

    system_total = float(plan.get("system_total", 85.0) or 0.0)
    requirements = {
        "total": float(plan.get("total_required", 128.0) or 0.0),
        "common_total": float(plan.get("university_common_required", 28.0) or 0.0),
        "common_compulsory": 10.0,
        "ge_categories_total": 16.0,
        "ge_per_category": 4.0,
        "ge_common_elective": 2.0,
        "major_total": system_total,
        "major_common_compulsory": float(plan.get("major_common_required", plan.get("program_common_required", 0.0)) or 0.0),
        "domain_compulsory": float(plan.get("track_required", 0.0) or 0.0),
        "domain_elective": float(plan.get("elective_required", 0.0) or 0.0),
        "major_other_elective": 0.0,
        "free_elective": float(plan.get("free_required", 15.0) or 0.0),
        "pe_semesters": 4,
        "target_total": 0.0,
    }
    if target_plan:
        requirements["target_total"] = float(target_plan.get("total_required", 40.0) or 0.0)
    elif program_type in {"雙主修", "輔系"}:
        requirements["target_total"] = 40.0 if program_type == "雙主修" else 20.0
    return requirements


def _empty_threshold_report(plan, requirements, config, target_plan=None, target_eligibility=None, warnings=None):
    """Create a readable plan report without fabricating course identities."""

    categories = {name: {"completed": 0.0, "ip": 0.0, "courses": []} for name in ("藝術與美感", "人文與文化思考", "公民素養與社會探索", "自然、生命與科技")}
    target_req = float(requirements.get("target_total", 0.0) or 0.0)
    return {
        "handbook_year": str(plan.get("cohort", config.get("admission_cohort", ""))),
        "program_type": config.get("program_type", "單主修"),
        "target_dept": config.get("target_dept", ""),
        "application": {
            "application_year": config.get("application_year"),
            "application_semester": config.get("application_semester"),
            "application_status": config.get("application_status"),
            "shared_evidence_state": config.get("shared_evidence_state"),
            "cohort_mismatch_confirmed": bool(config.get("cohort_mismatch_confirmed", False)),
            "interrupted": bool(config.get("interrupted")),
        },
        "rules_meta": {"version": str(plan.get("cohort", "")), "evidence_file": plan.get("source_file", "")},
        "document_warnings": list(warnings or []),
        "policy_warnings": list(warnings or []),
        "citations": list(plan.get("citations", [])) + list((target_plan or {}).get("citations", [])),
        "requirements": requirements,
        "primary_plan": plan,
        "target_plan": target_plan,
        "double_major_eligibility": target_eligibility,
        "detailed": False,
        "summary": {
            "total_completed": 0.0,
            "total_ip": 0.0,
            "total_with_ip": 0.0,
            "major_completed": 0.0,
            "major_ip": 0.0,
            "target_completed": 0.0,
            "target_ip": 0.0,
            "free_completed": 0.0,
            "free_ip": 0.0,
            "common_completed": 0.0,
            "common_ip": 0.0,
            "graduation_ready": False,
            "graduation_status": UNKNOWN,
        },
        "graduation_gates": {
            "total": UNKNOWN,
            "common_total": UNKNOWN,
            "major_total": UNKNOWN,
            "free": UNKNOWN,
            "physical_education": UNKNOWN,
            "target": UNKNOWN if target_req else "NOT_APPLICABLE",
            "manual_evidence": UNKNOWN,
        },
        "common": {
            "compulsory_completed": 0.0,
            "compulsory_ip": 0.0,
            "compulsory_missing": [],
            "compulsory_courses": [],
            "categories": categories,
            "category_overflow": {name: [] for name in categories},
            "category_completed": 0.0,
            "category_ip": 0.0,
            "common_elective_completed": 0.0,
            "common_elective_ip": 0.0,
            "common_elective_courses": [],
        },
        "major": {
            "dept_compulsory_completed": 0.0,
            "dept_compulsory_ip": 0.0,
            "dept_compulsory_missing": [],
            "dept_compulsory_courses": [],
            "domain_compulsory_completed": 0.0,
            "domain_compulsory_ip": 0.0,
            "domain_compulsory_missing": [],
            "domain_compulsory_courses": [],
            "domain_elective_completed": 0.0,
            "domain_elective_ip": 0.0,
            "domain_elective_courses": [],
            "other_elective_completed": 0.0,
            "other_elective_ip": 0.0,
            "other_elective_courses": [],
        },
        "target": {
            "basic_core_completed": 0.0,
            "basic_core_ip": 0.0,
            "basic_core_missing": [],
            "basic_core_courses": [],
            "compulsory_completed": 0.0,
            "compulsory_ip": 0.0,
            "compulsory_missing": [],
            "compulsory_courses": [],
            "elective_completed": 0.0,
            "elective_ip": 0.0,
            "elective_courses": [],
            "elective_missing": [],
            "total_completed": 0.0,
            "total_ip": 0.0,
            "effective_total_completed": 0.0,
            "effective_total_ip": 0.0,
            "shared_reuse_credits": 0.0,
            "equivalency_courses": [],
            "equivalency_completed": 0.0,
            "equivalency_shared_completed": 0.0,
            "equivalency_exclusive_completed": 0.0,
        },
        "pe": {"courses": [], "semesters_completed": 0, "semesters_required": requirements.get("pe_semesters", 4), "semesters_ip": 0},
        "free": {"completed": 0.0, "ip": 0.0, "courses": [], "science_college_cross_credits": 0.0, "science_college_cross_courses": []},
        "manual_gates": {},
        "audit": {"input_course_count": len(config.get("courses", []) or []), "canonical_course_count": 0, "deduplicated_count": 0},
        "shared_reuse": _empty_shared_reuse(),
    }


def _target_program_config(program, track):
    if program == "資科":
        return "資科系"
    if program == "物化":
        return "物化系物理組" if track == "電子物理" else "物化系化學組"
    return ""


def _apc_target_plan_for_engine(handbook_year, target_dept, program):
    """Load the cohort-scoped APC target rows used by exact allocation.

    The old ``apc_rules.basic_core`` table is retained for compatibility, but
    the 115 chemistry/physics target lists differ by track.  This helper keeps
    that distinction at the target boundary and gives every row a stable
    requirement ID for the equivalency audit.
    """

    if program not in {"雙主修", "輔系"} or "物化系" not in str(target_dept or ""):
        return None
    track = "物理組" if "物理" in str(target_dept) else "化學組"
    try:
        return get_apc_target_requirements(handbook_year, track, program)
    except (KeyError, TypeError, ValueError):
        return None


def _target_course_rules(target_plan):
    if not isinstance(target_plan, dict):
        return {}
    return {
        str(row.get("name")): float(row.get("credits", 0.0) or 0.0)
        for row in target_plan.get("requirements", [])
        if isinstance(row, dict) and row.get("kind", "course") == "course" and row.get("name")
    }


def _annotate_target_requirements(report, target_plan):
    """Attach stable IDs to exact target rows and missing rows."""

    if not isinstance(target_plan, dict):
        return
    by_name = {
        normalize_course_name(row.get("name")): row
        for row in target_plan.get("requirements", [])
        if isinstance(row, dict) and row.get("name")
    }
    target = report.get("target", {})
    for key in ("basic_core_courses", "compulsory_courses", "elective_courses"):
        for course in target.get(key, []):
            if not isinstance(course, dict):
                continue
            item = by_name.get(normalize_course_name(course.get("name") or course.get("raw_name")))
            if item:
                course["target_requirement_id"] = item.get("id", "")
                course["target_requirement_name"] = item.get("name", "")
    for key in ("basic_core_missing", "compulsory_missing", "elective_missing"):
        for missing in target.get(key, []):
            if not isinstance(missing, dict):
                continue
            item = by_name.get(normalize_course_name(missing.get("name")))
            if item:
                missing["target_requirement_id"] = item.get("id", "")
                missing["target_requirement_name"] = item.get("name", "")


def evaluate_cohort_plan(courses, config):
    """Evaluate a selected cohort/primary track with conservative fallbacks."""

    from policy_audit import assess_double_major_eligibility

    cohort = config.get("admission_cohort") or config.get("handbook_year") or "114"
    primary_value = config.get("primary_program") or config.get("program_name") or config.get("domain", "地生")
    program, track = normalize_primary_program(primary_value, cohort)
    track = config.get("primary_track") or config.get("track") or track
    plan = get_primary_requirements(cohort, primary_value, track)
    program_type = config.get("program_type", "單主修")
    parser_diagnostics = config.get("parser_diagnostics") or {}
    detected_cohort = parser_diagnostics.get("detected_admission_cohort") or config.get("detected_admission_cohort")
    cohort_match = assess_cohort_match(
        cohort,
        detected_cohort,
        confirmed=bool(config.get("cohort_mismatch_confirmed", False)),
    )

    target_plan = None
    target_eligibility = None
    target_program = config.get("target_program") or config.get("target_dept")
    if program_type == "雙主修":
        if not target_program:
            target_eligibility = assess_double_major_eligibility(program_type=program_type, admission_cohort=cohort)
        else:
            target_program, target_track = normalize_primary_program(target_program, cohort)
            target_plan = get_double_structure(cohort, target_program, target_track or config.get("target_track"))
            if target_program == "物化":
                target_plan["target_requirements"] = _apc_target_plan_for_engine(
                    cohort,
                    "物化系物理組" if target_track == "電子物理" else "物化系化學組",
                    program_type,
                )
            target_eligibility = assess_double_major_eligibility(
                program_type=program_type,
                admission_cohort=cohort,
                application_year=config.get("application_year"),
                application_semester=config.get("application_semester"),
                application_status=config.get("application_status"),
                secondary_credits=config.get("secondary_credits"),
                shared_credits=config.get("shared_credits"),
                shared_course_credits=config.get("shared_course_credits"),
                shared_reuse_credits=config.get("shared_reuse_credits"),
                shared_approved=config.get("shared_approved"),
                shared_evidence_state=config.get("shared_evidence_state"),
                department_approved=config.get("department_approved"),
                interrupted=bool(config.get("interrupted")),
                leave_history=config.get("leave_history"),
            )

    # Preserve the established detailed Earth evaluator where its exact
    # course tables are available and the target can be safely mapped.
    target_old = _target_program_config(*(normalize_primary_program(target_program, cohort) if target_program else ("", None))) if target_program else ""
    can_detail = program == "地生" and str(cohort) in {"112", "113", "114"} and (not target_program or target_old)
    if can_detail:
        legacy = dict(config)
        legacy.pop("primary_program", None)
        legacy.pop("primary_track", None)
        legacy.pop("admission_cohort", None)
        legacy["domain"] = track or "地球環境"
        legacy["handbook_year"] = str(cohort)
        legacy["program"] = program_type
        if target_old:
            legacy["target_dept"] = target_old
        if target_plan and target_plan.get("target_requirements"):
            legacy["target_requirements"] = target_plan["target_requirements"]
        legacy["equivalency_decisions"] = config.get("equivalency_decisions", [])
        legacy["equivalency_context"] = config.get("equivalency_context", {})
        report = evaluate_graduation(courses, legacy)
        report["primary_plan"] = plan
        report["target_plan"] = target_plan
        report["cohort_match"] = cohort_match
        report["evidence_states"] = plan.get("evidence_states", plan.get("evidence", {}))
        # The legacy evaluator has now classified the actual transcript.  Use
        # that target total when applying the independent double-major rule;
        # do not retain the pre-transcript UNKNOWN produced above.
        if target_old and program_type == "雙主修":
            bound_shared = float(
                (report.get("equivalency", {}) or {}).get("approved_shared_reuse_credits", 0.0) or 0.0
            )
            target_eligibility = assess_double_major_eligibility(
                program_type=program_type,
                admission_cohort=cohort,
                application_year=config.get("application_year"),
                application_semester=config.get("application_semester"),
                application_status=config.get("application_status"),
                secondary_credits=report.get("target", {}).get(
                    "effective_total_completed", report.get("summary", {}).get("target_completed", 0.0)
                ),
                shared_credits=bound_shared,
                shared_approved=True,
                shared_evidence_state="approved" if bound_shared > 1e-6 else "confirmed_zero",
                equivalency_bound=bound_shared > 1e-6,
                department_approved=config.get("department_approved"),
                interrupted=bool(config.get("interrupted")),
                leave_history=config.get("leave_history"),
            )
        report["double_major_eligibility"] = target_eligibility
        report["citations"] = list(plan.get("citations", [])) + list((target_plan or {}).get("citations", []))
        if cohort_match.get("status") == UNKNOWN:
            report["policy_warnings"] = list(
                dict.fromkeys(report.get("policy_warnings", []) + cohort_match.get("reasons", []))
            )
            report["summary"]["graduation_status"] = UNKNOWN
            report["summary"]["graduation_ready"] = False
        if target_eligibility and target_eligibility.get("status") != "SATISFIED":
            report["policy_warnings"] = list(dict.fromkeys(report.get("policy_warnings", []) + target_eligibility.get("reasons", [])))
            report["summary"]["graduation_status"] = UNKNOWN
            report["summary"]["graduation_ready"] = False
        return report

    requirements = _plan_requirements(plan, program_type, target_plan)
    warnings = list(plan.get("warnings", []))
    if target_plan:
        warnings.extend(target_plan.get("warnings", []))
    if target_eligibility and target_eligibility.get("status") != "SATISFIED":
        warnings.extend(target_eligibility.get("reasons", []))
    report = _empty_threshold_report(plan, requirements, {**config, "courses": courses}, target_plan, target_eligibility, warnings)
    report["cohort_match"] = cohort_match
    report["evidence_states"] = plan.get("evidence_states", plan.get("evidence", {}))
    if cohort_match.get("status") == UNKNOWN:
        report["policy_warnings"] = list(dict.fromkeys(report["policy_warnings"] + cohort_match.get("reasons", [])))
    if program == "資科":
        report["manual_gates"]["cs"] = assess_cs_manual_gate(
            config.get("cs_project_evidence"),
            config.get("cs_certification_a"),
            config.get("cs_certification_b"),
            config.get("cs_alternative_course"),
        )
        if report["manual_gates"]["cs"]["status"] != "COMPLETED":
            report["policy_warnings"].extend(report["manual_gates"]["cs"].get("warnings", []))
    # A threshold-only plan is useful without a transcript, but it cannot
    # produce a definitive graduation decision or course-level gaps.
    report["summary"]["graduation_status"] = UNKNOWN
    return report


def evaluate_graduation(courses, config):
    """
    Evaluate courses against one explicitly selected Science College handbook.

    Parameters:
        courses (list): List of parsed course dicts from pdf_parser.
        config (dict): {
            "domain": "地球環境" or "生命科學",
            "program": "單主修", "雙主修", or "輔系",
            "target_dept": "物化系化學組", "物化系物理組", or "資科系",
            "handbook_year": "112", "113", or "114"
        }
    """
    config = config or {}
    if any(key in config for key in ("primary_program", "admission_cohort", "primary_track")):
        return evaluate_cohort_plan(courses, config)

    domain = config.get("domain", "地球環境")
    program = config.get("program", "單主修")
    target_dept = config.get("target_dept", "物化系化學組")
    handbook_year = config.get("handbook_year")
    rule_sets = get_rule_sets(handbook_year)
    university_common = rule_sets["university_common"]
    earth_life_major = rule_sets["earth_life_major"]
    apc_rules = rule_sets["apc_rules"]
    cs_rules = rule_sets["cs_rules"]
    alias_sets = rule_sets.get("course_aliases", {})
    courses, canonical_meta = _canonicalize_courses(courses)
    rule_names_set = _collect_rule_names(rule_sets)
    major_compulsory_set = _collect_major_compulsory(earth_life_major)

    if domain not in earth_life_major.get("domains", {}):
        raise ValueError(f"不支援的主修專業領域：{domain}")
    if program not in {"單主修", "雙主修", "輔系"}:
        raise ValueError(f"不支援的修課身分：{program}")

    requirements = get_credit_requirements(program, target_dept, rule_sets["academic_year"])
    target_requirements = config.get("target_requirements")
    if not isinstance(target_requirements, dict):
        target_requirements = _apc_target_plan_for_engine(rule_sets["academic_year"], target_dept, program)

    report = {
        "handbook_year": rule_sets["academic_year"],
        "program_type": program,
        "target_dept": target_dept,
        "application": {
            "application_year": config.get("application_year"),
            "application_semester": config.get("application_semester"),
            "application_status": config.get("application_status"),
            "shared_evidence_state": config.get("shared_evidence_state"),
            "cohort_mismatch_confirmed": bool(config.get("cohort_mismatch_confirmed", False)),
            "interrupted": bool(config.get("interrupted")),
        },
        "rules_meta": get_rules_meta(rule_sets["academic_year"]),
        "document_warnings": rule_sets.get("document_warnings", []),
        "policy_warnings": [],
        "citations": [],
        "requirements": requirements,
        "target_requirements": target_requirements,
        "detailed": True,
        "summary": {
            "total_completed": 0.0,
            "total_ip": 0.0,
            "major_completed": 0.0,
            "major_ip": 0.0,
            "target_completed": 0.0,
            "target_ip": 0.0,
            "free_completed": 0.0,
            "free_ip": 0.0,
            "common_completed": 0.0,
            "common_ip": 0.0,
            "graduation_ready": False,
        },
        "common": {
            # 校共同必修（英文、國文 10學分）
            "compulsory_completed": 0.0,
            "compulsory_ip": 0.0,
            "compulsory_missing": [],
            "compulsory_courses": [],
            # 通識分類選修（四大領域 16學分）
            "categories": {
                k: {"completed": 0.0, "ip": 0.0, "courses": []}
                for k in university_common["category_domains"].keys()
            },
            "category_overflow": {k: [] for k in university_common["category_domains"].keys()},
            "category_completed": 0.0,
            "category_ip": 0.0,
            # 通識共同選修（2學分）
            "common_elective_completed": 0.0,
            "common_elective_ip": 0.0,
            "common_elective_courses": [],
        },
        "major": {
            "dept_compulsory_completed": 0.0,
            "dept_compulsory_ip": 0.0,
            "dept_compulsory_missing": [],
            "dept_compulsory_courses": [],
            "domain_compulsory_completed": 0.0,
            "domain_compulsory_ip": 0.0,
            "domain_compulsory_missing": [],
            "domain_compulsory_courses": [],
            "domain_elective_completed": 0.0,
            "domain_elective_ip": 0.0,
            "domain_elective_courses": [],
            "other_elective_completed": 0.0,
            "other_elective_ip": 0.0,
            "other_elective_courses": [],
        },
        "target": {
            "basic_core_completed": 0.0,
            "basic_core_ip": 0.0,
            "basic_core_missing": [],
            "basic_core_courses": [],
            "compulsory_completed": 0.0,
            "compulsory_ip": 0.0,
            "compulsory_missing": [],
            "compulsory_courses": [],
            "elective_completed": 0.0,
            "elective_ip": 0.0,
            "elective_courses": [],
            "elective_missing": [],
            "total_completed": 0.0,
            "total_ip": 0.0,
            "effective_total_completed": 0.0,
            "effective_total_ip": 0.0,
            "shared_reuse_credits": 0.0,
            "equivalency_courses": [],
            "equivalency_completed": 0.0,
            "equivalency_shared_completed": 0.0,
            "equivalency_exclusive_completed": 0.0,
        },
        "pe": {
            # 體育（每學期 0學分必修，共需修 4 學期）
            "courses": [],
            "semesters_completed": 0,
            "semesters_required": requirements["pe_semesters"],
            "semesters_ip": 0,
        },
        "free": {
            "completed": 0.0,
            "ip": 0.0,
            "courses": [],
            "science_college_cross_credits": 0.0,
            "science_college_cross_courses": [],
        },
        "audit": canonical_meta,
        "manual_gates": {},
        "shared_reuse": _empty_shared_reuse(),
    }

    consumed = set()

    for c in courses:
        if _is_exempt_course(c):
            c["total_credit"] = 0.0
            c["completed_credit"] = 0.0
            c["is_zero_credit"] = True
            c["is_in_progress"] = False

    def get_course_credits(c):
        return c["completed_credit"], c["total_credit"] - c["completed_credit"] if c["is_in_progress"] else 0.0

    # ── PHASE 0: 體育課先標記（0學分不計入總學分，但追蹤修課學期數）──────────
    for c in courses:
        if _is_pe_course(c):
            consumed.add(id(c))
            sem_count = 0
            ip_count = 0
            # 每個課程記錄它佔幾個學期
            if c["sem1_score"] and c["sem1_score"] not in ("--", ""):
                if c["sem1_score"] == "未":
                    ip_count += 1
                else:
                    try:
                        if float(c["sem1_score"]) >= 60:
                            sem_count += 1
                    except ValueError:
                        if c["sem1_score"] in ("P", "抵", "免"):
                            sem_count += 1
            if c["sem2_score"] and c["sem2_score"] not in ("--", ""):
                if c["sem2_score"] == "未":
                    ip_count += 1
                else:
                    try:
                        if float(c["sem2_score"]) >= 60:
                            sem_count += 1
                    except ValueError:
                        if c["sem2_score"] in ("P", "抵", "免"):
                            sem_count += 1
            report["pe"]["courses"].append(c)
            report["pe"]["semesters_completed"] += sem_count
            report["pe"]["semesters_ip"] += ip_count

    # ── PHASE 0.5: 地生系與專業領域必修（主修必修最高優先）────────
    for name, req_cred in earth_life_major["common_compulsory"].items():
        matched_c = find_and_consume_course(courses, name, consumed, req_cred)
        if matched_c:
            comp_c, ip_c = get_course_credits(matched_c)
            report["major"]["dept_compulsory_courses"].append(matched_c)
            report["major"]["dept_compulsory_completed"] += comp_c
            report["major"]["dept_compulsory_ip"] += ip_c
            if comp_c + 1e-6 < req_cred:
                report["major"]["dept_compulsory_missing"].append({"name": name, "credit": req_cred - comp_c})
        else:
            report["major"]["dept_compulsory_missing"].append({"name": name, "credit": req_cred})

    for group in earth_life_major.get("common_alternatives", []):
        required = float(group.get("required_credits", 0))
        matched_c = _find_best_alternative(courses, group.get("options", {}), consumed)
        if matched_c:
            comp_c, ip_c = get_course_credits(matched_c)
            report["major"]["dept_compulsory_courses"].append(matched_c)
            report["major"]["dept_compulsory_completed"] += min(comp_c, required)
            report["major"]["dept_compulsory_ip"] += min(ip_c, max(0.0, required - comp_c))
            if comp_c + 1e-6 < required:
                report["major"]["dept_compulsory_missing"].append(
                    {"name": group.get("label", "替代必修"), "credit": required - comp_c}
                )
        else:
            report["major"]["dept_compulsory_missing"].append(
                {"name": group.get("label", "替代必修"), "credit": required}
            )

    domain_rules = earth_life_major["domains"][domain]
    for name, req_cred in domain_rules.items():
        matched_c = find_and_consume_course(courses, name, consumed, req_cred)
        if matched_c:
            comp_c, ip_c = get_course_credits(matched_c)
            report["major"]["domain_compulsory_courses"].append(matched_c)
            report["major"]["domain_compulsory_completed"] += comp_c
            report["major"]["domain_compulsory_ip"] += ip_c
            if comp_c + 1e-6 < req_cred:
                report["major"]["domain_compulsory_missing"].append({"name": name, "credit": req_cred - comp_c})
        else:
            report["major"]["domain_compulsory_missing"].append({"name": name, "credit": req_cred})

    # ── PHASE 1: 輔系/雙主修必修（優先鎖定，防止被主修選修吃掉）──────────────
    if program in ["雙主修", "輔系"]:
        if "物化系" in target_dept:
            div = "化學組" if "化學組" in target_dept else "物理組"
            program_key = "double_major" if program == "雙主修" else "minor"
            program_rules = apc_rules[program_key]
            basic_core_rules = _target_course_rules(target_requirements) or apc_rules["basic_core"]

            for name, req_cred in basic_core_rules.items():
                matched_c = find_and_consume_course(courses, name, consumed, req_cred)
                if matched_c:
                    comp_c, ip_c = get_course_credits(matched_c)
                    report["target"]["basic_core_courses"].append(matched_c)
                    report["target"]["basic_core_completed"] += comp_c
                    report["target"]["basic_core_ip"] += ip_c
                    if comp_c + 1e-6 < req_cred:
                        report["target"]["basic_core_missing"].append({"name": name, "credit": req_cred - comp_c})
                else:
                    report["target"]["basic_core_missing"].append({"name": name, "credit": req_cred})

            other_req = float(
                (target_requirements or {}).get("other_required", program_rules.get("other_req", 0.0))
            )
            other_required_pool = dict(
                (target_requirements or {}).get(
                    "other_required_catalog",
                    dict(apc_rules.get("shared_other_required", {}))
                    | dict(apc_rules["divisions"][div]["compulsory"]),
                )
            )
            for name, req_cred in other_required_pool.items():
                matched_c = find_and_consume_course(courses, name, consumed, req_cred)
                if matched_c:
                    comp_c, ip_c = get_course_credits(matched_c)
                    report["target"]["compulsory_courses"].append(matched_c)
                    report["target"]["compulsory_completed"] += comp_c
                    report["target"]["compulsory_ip"] += ip_c

            (
                report["target"]["compulsory_courses"],
                target_overflow,
                report["target"]["compulsory_completed"],
                report["target"]["compulsory_ip"],
            ) = _cap_course_bucket(report["target"]["compulsory_courses"], other_req, f"{div}其餘必修")
            for overflow_course in target_overflow:
                overflow_completed, overflow_ip = _earned_and_in_progress(overflow_course)
                report["free"]["courses"].append(overflow_course)
                report["free"]["completed"] += overflow_completed
                report["free"]["ip"] += overflow_ip

            recognized_other = report["target"]["compulsory_completed"] + report["target"]["compulsory_ip"]
            if recognized_other + 1e-6 < other_req:
                report["target"]["compulsory_missing"].append(
                    {"name": f"{div}其餘必修課程", "credit": other_req - recognized_other}
                )

            report["target"]["total_completed"] = (
                report["target"]["basic_core_completed"]
                + report["target"]["compulsory_completed"]
            )
            report["target"]["total_ip"] = (
                report["target"]["basic_core_ip"] + report["target"]["compulsory_ip"]
            )

        elif "資科系" in target_dept:
            rules = cs_rules["double_major"] if program == "雙主修" else cs_rules["minor"]
            comp_rules = rules["compulsory"]

            for name, req_cred in comp_rules.items():
                matched_c = find_and_consume_course(courses, name, consumed, req_cred)
                if matched_c:
                    comp_c, ip_c = get_course_credits(matched_c)
                    report["target"]["compulsory_courses"].append(matched_c)
                    report["target"]["compulsory_completed"] += comp_c
                    report["target"]["compulsory_ip"] += ip_c
                    if comp_c + 1e-6 < req_cred:
                        report["target"]["compulsory_missing"].append({"name": name, "credit": req_cred - comp_c})
                else:
                    report["target"]["compulsory_missing"].append({"name": name, "credit": req_cred})

            for name, req_cred in cs_rules.get("department_courses", {}).items():
                matched_c = find_and_consume_course(
                    courses,
                    name,
                    consumed,
                    req_cred,
                    _explicit_aliases(alias_sets, "cs", name),
                )
                if matched_c:
                    comp_c, ip_c = get_course_credits(matched_c)
                    report["target"]["elective_courses"].append(matched_c)
                    report["target"]["elective_completed"] += comp_c
                    report["target"]["elective_ip"] += ip_c

            other_req = float(rules["other_req"])
            (
                report["target"]["elective_courses"],
                target_overflow,
                report["target"]["elective_completed"],
                report["target"]["elective_ip"],
            ) = _cap_course_bucket(report["target"]["elective_courses"], other_req, "資科系其他課程")
            for overflow_course in target_overflow:
                overflow_completed, overflow_ip = _earned_and_in_progress(overflow_course)
                report["free"]["courses"].append(overflow_course)
                report["free"]["completed"] += overflow_completed
                report["free"]["ip"] += overflow_ip

            recognized_other = report["target"]["elective_completed"] + report["target"]["elective_ip"]
            if recognized_other + 1e-6 < other_req:
                report["target"]["elective_missing"].append(
                    {"name": "資科系其他開設課程", "credit": other_req - recognized_other}
                )

            report["target"]["total_completed"] = (
                report["target"]["compulsory_completed"] + report["target"]["elective_completed"]
            )
            report["target"]["total_ip"] = report["target"]["compulsory_ip"] + report["target"]["elective_ip"]

    # ── PHASE 2: 校共同必修（英文、國文）─────────────────────────────────────
    for name, req_cred in university_common["compulsory"].items():
        matched_c = find_and_consume_course(
            courses,
            name,
            consumed,
            req_cred,
            _explicit_aliases(alias_sets, "university_common", name),
        )
        if matched_c:
            comp_c, ip_c = get_course_credits(matched_c)
            report["common"]["compulsory_courses"].append(matched_c)
            report["common"]["compulsory_completed"] += comp_c
            report["common"]["compulsory_ip"] += ip_c
            if comp_c + 1e-6 < req_cred:
                report["common"]["compulsory_missing"].append({"name": name, "credit": req_cred - comp_c})
        else:
            report["common"]["compulsory_missing"].append({"name": name, "credit": req_cred})

    # ── PHASE 3: 通識分類選修（匹配通識課程、標籤或關鍵字）──────────────────
    # 每類最低學分 (預設 4，若未在 rules 中提供則採此值)
    per_category_req = university_common.get("per_category_req", 4)

    for cat_name, keywords in university_common["category_domains"].items():
        for c in courses:
            c_idx = id(c)
            if c_idx not in consumed:
                raw_name = c.get("raw_name", "") or ""
                name = c.get("name", "") or ""
                # 使用 normalized 版本做匹配，避免全形／半形、額外空白或標點造成漏抓
                raw_norm = normalize_course_name(raw_name)
                name_norm = normalize_course_name(name)
                dbg(
                    f"PHASE3: checking course id={c_idx} name='{name_norm}' raw_norm='{raw_norm}' for category '{cat_name}'"
                )
                # 嚴格參考 rules_config.json：若此課已在任何系/雙主修/輔系規則中列出，則不應被歸為通識
                if _is_in_program_rules(name_norm, raw_norm, rule_names_set):
                    dbg(f"PHASE3: skipped (in program rules) id={c_idx} name='{name_norm}' raw_norm='{raw_norm}'")
                    continue

                is_match = False
                dbg(f"PHASE3: checking course id={c_idx} name='{name}' raw='{raw_name}' for category '{cat_name}'")

                # 優先處理成績單中以中括號或文字標註的通識分類，例如: [通選公民] 或 通選公民
                m = re.search(r"\[?通選\s*([^\]\s]+)\]?", raw_norm)
                if m:
                    label = m.group(1)
                    dbg(f"PHASE3: found bracket label='{label}' in raw_norm for course id={c_idx}")
                    # 若標註內容與類別名稱相符（包含或被包含），即視為該類別
                    cond1 = label in cat_name
                    cond2 = cat_name.find(label) != -1
                    cond3 = label in cat_name.replace("與", "")
                    dbg(f"PHASE3: compare label('{label}') vs cat('{cat_name}') -> {cond1},{cond2},{cond3}")
                    if cond1 or cond2 or cond3:
                        is_match = True
                # 無明確通識標記時不靠課名猜測，避免把系所專業課誤放進通識。
                if not is_match and ("通選" in raw_norm or "通識" in raw_norm):
                    for kw in keywords:
                        if kw in name_norm or kw in raw_norm:
                            is_match = True
                            break

                if is_match:
                    report["common"]["categories"][cat_name]["courses"].append(c)
                    consumed.add(c_idx)

    # ── PHASE 4: 通識共同選修（剩餘的通識課）─────────────────────────────────
    # 按照學分數大到小排序處理，優先把學分數大的課放入通識共同，滿了之後小學分的自然溢出
    sorted_courses_p4 = sorted(courses, key=lambda x: get_course_credits(x)[0] + get_course_credits(x)[1], reverse=True)
    for c in sorted_courses_p4:
        c_idx = id(c)
        if c_idx not in consumed:
            raw_name = c.get("raw_name", "") or ""
            name = c.get("name", "") or ""
            raw_norm = normalize_course_name(raw_name)
            name_norm = normalize_course_name(name)
            dbg(f"PHASE4: checking course id={c_idx} name='{name_norm}' raw_norm='{raw_norm}'")
            # 嚴格參考 rules_config.json：若此課已在任何系/雙主修/輔系規則中列出，則不應被歸為通識
            if _is_in_program_rules(name_norm, raw_norm, rule_names_set):
                dbg(f"PHASE4: skipped (in program rules) id={c_idx} name='{name_norm}' raw_norm='{raw_norm}'")
                continue
            # 若為系內選修 override 名稱，跳過通識判定，讓後續專業選修階段處理
            lower_combined = (name + " " + raw_name).lower()
            if any(kw.lower() in lower_combined for kw in MAJOR_ELECTIVE_OVERRIDE):
                continue

            # 如果成績單有中括號標註 [通選XXX]，優先把它指定到對應的分類
            m = re.search(r"\[?通選\s*([^\]\s]+)\]?", raw_norm)
            assigned = False
            if m:
                label = m.group(1)
                dbg(f"PHASE4: found bracket label='{label}' in raw_name for course id={c_idx}")
                for cat_name in report["common"]["categories"].keys():
                    cond1 = label in cat_name
                    cond2 = cat_name.find(label) != -1
                    cond3 = label in cat_name.replace("與", "")
                    dbg(f"PHASE4: compare label('{label}') vs cat('{cat_name}') -> {cond1},{cond2},{cond3}")
                    if cond1 or cond2 or cond3:
                        report["common"]["categories"][cat_name]["courses"].append(c)
                        consumed.add(c_idx)
                        assigned = True
                        break

            if assigned:
                continue
            if "通選" in raw_norm or "通識" in raw_norm or "共同選修" in raw_norm:
                report.setdefault("_common_elective_candidates", []).append(c)
                consumed.add(c_idx)

    # ── PHASE X: 通識分類／共同選修逐類精確封頂，超額保留至自由選修
    def add_free_course(item):
        comp_c, ip_c = get_course_credits(item)
        report["free"]["courses"].append(item)
        report["free"]["completed"] += comp_c
        report["free"]["ip"] += ip_c

    for cat_name, category in report["common"]["categories"].items():
        recognized, overflow_items, completed, ip = _cap_course_bucket(
            category["courses"], per_category_req, f"通識分類 {cat_name}"
        )
        category["courses"] = recognized
        category["completed"] = completed
        category["ip"] = ip
        report["common"]["category_overflow"][cat_name] = overflow_items
        report["common"]["category_completed"] += completed
        report["common"]["category_ip"] += ip
        for overflow_item in overflow_items:
            add_free_course(overflow_item)

    common_candidates = report.pop("_common_elective_candidates", [])
    recognized, overflow_items, completed, ip = _cap_course_bucket(
        common_candidates, requirements["ge_common_elective"], "通識共同選修"
    )
    report["common"]["common_elective_courses"] = recognized
    report["common"]["common_elective_completed"] = completed
    report["common"]["common_elective_ip"] = ip
    for overflow_item in overflow_items:
        add_free_course(overflow_item)

    # (原 PHASE 5, 6 已移至 PHASE 0.5)

    # ── PHASE 7: 專業領域選修（至少20學分）──────────────────────────────────
    domain_elective_rules = earth_life_major["domain_electives"][domain]
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            for rule_name, rule_credit in domain_elective_rules.items():
                if _course_matches_rule(c, rule_name, rule_credit):
                    comp_c, ip_c = get_course_credits(c)
                    report["major"]["domain_elective_courses"].append(c)
                    report["major"]["domain_elective_completed"] += comp_c
                    report["major"]["domain_elective_ip"] += ip_c
                    consumed.add(c_idx)
                    break

    # ── PHASE 8: 系共同選修（其他27學分）─────────────────────────────────────
    all_major_electives = dict(earth_life_major["domain_electives"].get("common_electives", {}))
    for dname, electives in earth_life_major["domain_electives"].items():
        if dname != domain and dname != "common_electives":
            all_major_electives.update(electives)

    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            for rule_name, rule_credit in all_major_electives.items():
                if _course_matches_rule(
                    c,
                    rule_name,
                    rule_credit,
                    _explicit_aliases(alias_sets, "earth_life_common_electives", rule_name),
                ):
                    comp_c, ip_c = get_course_credits(c)
                    report["major"]["other_elective_courses"].append(c)
                    report["major"]["other_elective_completed"] += comp_c
                    report["major"]["other_elective_ip"] += ip_c
                    consumed.add(c_idx)
                    break

    # 精確封頂專業選修；跨出第一個子門檻的部分仍可填入下一個系內
    # 選修池，但每一池都以切片方式封頂，避免出現超過目標學分的假進度。
    domain_recognized, overflow_to_other, domain_completed, domain_ip = _cap_course_bucket(
        report["major"]["domain_elective_courses"], requirements["domain_elective"], "專業選修"
    )
    report["major"]["domain_elective_courses"] = domain_recognized
    report["major"]["domain_elective_completed"] = domain_completed
    report["major"]["domain_elective_ip"] = domain_ip
    report["major"]["other_elective_courses"].extend(overflow_to_other)

    other_recognized, overflow_to_free, other_completed, other_ip = _cap_course_bucket(
        report["major"]["other_elective_courses"], requirements["major_other_elective"], "其他本系課程"
    )
    report["major"]["other_elective_courses"] = other_recognized
    report["major"]["other_elective_completed"] = other_completed
    report["major"]["other_elective_ip"] = other_ip
    for c in overflow_to_free:
        add_free_course(c)

    # ── PHASE 9: 自由選修（剩餘所有有學分的課）──────────────────────────────
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed and c["total_credit"] > 0:
            add_free_course(c)

            # 理學院院內跨系選修判定
            cross_keywords = ["物理", "化學", "資訊", "數學", "計算機", "離散數學", "微積分"]
            if any(kw in c["name"] for kw in cross_keywords):
                if (
                    normalize_course_name(c["name"]) not in major_compulsory_set
                    and normalize_course_name(c["name"]) not in _normalized_names(domain_elective_rules)
                ):
                    report["free"]["science_college_cross_courses"].append(c)
                    comp_c, _ = get_course_credits(c)
                    report["free"]["science_college_cross_credits"] += comp_c
            consumed.add(c_idx)

    # 3. 跨系各子門檻已於 PHASE 1 精確封頂；在此只重新匯總。
    report["target"]["total_completed"] = (
        report["target"]["compulsory_completed"]
        + report["target"].get("basic_core_completed", 0.0)
        + report["target"]["elective_completed"]
    )
    report["target"]["total_ip"] = (
        report["target"]["compulsory_ip"]
        + report["target"].get("basic_core_ip", 0.0)
        + report["target"]["elective_ip"]
    )
    _annotate_target_requirements(report, target_requirements)

    # ── PHASE 10: 匯總計算 ───────────────────────────────────────────────
    report["summary"]["common_completed"] = (
        report["common"]["compulsory_completed"]
        + report["common"]["category_completed"]
        + report["common"]["common_elective_completed"]
    )
    report["summary"]["common_ip"] = (
        report["common"]["compulsory_ip"] + report["common"]["category_ip"] + report["common"]["common_elective_ip"]
    )

    report["summary"]["major_completed"] = (
        report["major"]["dept_compulsory_completed"]
        + report["major"]["domain_compulsory_completed"]
        + report["major"]["domain_elective_completed"]
        + report["major"]["other_elective_completed"]
    )
    report["summary"]["major_ip"] = (
        report["major"]["dept_compulsory_ip"]
        + report["major"]["domain_compulsory_ip"]
        + report["major"]["domain_elective_ip"]
        + report["major"]["other_elective_ip"]
    )

    report["summary"]["target_completed"] = report["target"]["total_completed"]
    report["summary"]["target_ip"] = report["target"]["total_ip"]

    report["summary"]["free_completed"] = report["free"]["completed"]
    report["summary"]["free_ip"] = report["free"]["ip"]

    report["summary"]["total_completed"] = (
        report["summary"]["common_completed"]
        + report["summary"]["major_completed"]
        + report["summary"]["target_completed"]
        + report["summary"]["free_completed"]
    )
    report["summary"]["total_ip"] = (
        report["summary"]["common_ip"]
        + report["summary"]["major_ip"]
        + report["summary"]["target_ip"]
        + report["summary"]["free_ip"]
    )

    # 額外計算：將已取得 + 正在修習的學分一起顯示（以便學生查看含修讀中學分的總和）
    report["summary"]["total_with_ip"] = report["summary"]["total_completed"] + report["summary"]["total_ip"]

    # Credit conservation is an audit invariant: every completed or current
    # credit in the canonical transcript must appear in exactly one report
    # bucket (course attempts with zero earned credit do not contribute).
    source_earned = sum(sum(_earned_and_in_progress(course)) for course in courses)
    allocated_earned = report["summary"]["total_completed"] + report["summary"]["total_ip"]
    conservation_delta = allocated_earned - source_earned
    report["audit"]["source_earned_and_ip"] = source_earned
    report["audit"]["allocated_earned_and_ip"] = allocated_earned
    report["audit"]["shared_reuse_completed"] = report.get("shared_reuse", {}).get("completed", 0.0)
    report["audit"]["shared_reuse_ip"] = report.get("shared_reuse", {}).get("ip", 0.0)
    report["audit"]["shared_reuse_total"] = report.get("shared_reuse", {}).get("total", 0.0)
    report["audit"]["credit_conservation"] = abs(conservation_delta) <= 1e-6
    if not report["audit"]["credit_conservation"]:
        report["policy_warnings"].append(
            f"分類後學分未守恆（來源 {source_earned:g}、配置 {allocated_earned:g}）；請人工複核。"
        )

    # 畢業審查：每一個子門檻都必須通過，不能只用總學分作為捷徑。
    has_enough = report["summary"]["total_completed"] >= requirements["total"]
    has_common = report["summary"]["common_completed"] >= requirements["common_total"]
    has_ge_categories = all(
        category.get("completed", 0.0) >= requirements["ge_per_category"]
        for category in report["common"]["categories"].values()
    )
    has_ge_common_elective = report["common"]["common_elective_completed"] >= requirements["ge_common_elective"]
    has_major_common = report["major"]["dept_compulsory_completed"] >= requirements["major_common_compulsory"]
    has_domain_required = report["major"]["domain_compulsory_completed"] >= requirements["domain_compulsory"]
    has_domain_elective = report["major"]["domain_elective_completed"] >= requirements["domain_elective"]
    has_other_elective = report["major"]["other_elective_completed"] >= requirements["major_other_elective"]
    has_major = (
        report["summary"]["major_completed"] >= requirements["major_total"]
        and has_major_common
        and has_domain_required
        and has_domain_elective
        and has_other_elective
    )
    has_free = report["summary"]["free_completed"] >= requirements["free_elective"]
    has_pe = report["pe"]["semesters_completed"] >= requirements["pe_semesters"]

    no_missing = (
        len(report["common"]["compulsory_missing"]) == 0
        and len(report["major"]["dept_compulsory_missing"]) == 0
        and len(report["major"]["domain_compulsory_missing"]) == 0
    )

    # Shared-course reuse is a reporting-only allowance.  Keep the ordinary
    # target totals untouched so the source/allocated conservation invariant
    # remains meaningful.
    report["target"]["effective_total_completed"] = report["target"].get("total_completed", 0.0)
    report["target"]["effective_total_ip"] = report["target"].get("total_ip", 0.0)
    report["target"]["shared_reuse_credits"] = 0.0
    report["shared_reuse"] = _empty_shared_reuse()

    def target_gate_satisfied():
        if requirements["target_total"] <= 0:
            return True
        target_basic_req = 0.0
        target_compulsory_req = 0.0
        if "物化系" in target_dept:
            if target_requirements:
                target_basic_req = float(target_requirements.get("base_required", 0.0) or 0.0)
                target_compulsory_req = float(target_requirements.get("other_required", 0.0) or 0.0)
            else:
                target_basic_req = float(apc_rules.get("double_major" if program == "雙主修" else "minor", {}).get("basic_req", 0.0))
                target_compulsory_req = float(apc_rules.get("double_major" if program == "雙主修" else "minor", {}).get("other_req", 0.0))
        elif "資科系" in target_dept:
            target_compulsory_req = float(
                cs_rules.get("double_major" if program == "雙主修" else "minor", {}).get("compulsory_req", 0.0)
            )
        return (
            report["target"].get("effective_total_completed", report["target"].get("total_completed", 0.0))
            >= requirements["target_total"]
            and len(report["target"]["basic_core_missing"]) == 0
            and len(report["target"]["compulsory_missing"]) == 0
            and len(report["target"].get("elective_missing", [])) == 0
            and report["target"].get("basic_core_completed", 0.0) >= target_basic_req
            and report["target"].get("compulsory_completed", 0.0) + report["target"].get("elective_completed", 0.0) >= target_compulsory_req
        )

    # Course-level equivalency is a second pass over the exact transcript
    # allocations.  Suggestions remain UNKNOWN; only an approved source
    # attempt -> target requirement row can affect effective target progress.
    equivalency_audit = {
        "status": "NOT_APPLICABLE",
        "state": "NOT_APPLICABLE",
        "decisions": [],
        "approved_mappings": [],
        "candidates": [],
        "manual_gate": {"status": "NOT_APPLICABLE", "state": "NOT_APPLICABLE", "validation_codes": []},
        "warnings": [],
        "validation_codes": [],
        "legacy_unbound": False,
        "approved_shared_reuse_credits": 0.0,
        "approved_exclusive_credits": 0.0,
    }
    if target_requirements and "物化系" in target_dept:
        equivalency_context = dict(config.get("equivalency_context") or {})
        equivalency_context.update(
            {
                "admission_cohort": rule_sets["academic_year"],
                "target_program": "物化",
                "target_dept": target_dept,
                "target_track": target_requirements.get("track", ""),
                "program_type": program,
                # Preserve legacy inputs only for a compatibility warning;
                # audit_equivalency_decisions never treats them as bindings.
                "shared_credits": config.get("shared_credits"),
                "shared_course_credits": config.get("shared_course_credits"),
                "shared_reuse_credits": config.get("shared_reuse_credits"),
                "shared_reuse": config.get("shared_reuse"),
                "shared_approved": config.get("shared_approved"),
                "shared_evidence_state": config.get("shared_evidence_state"),
            }
        )
        equivalency_audit = audit_equivalency_decisions(
            courses,
            target_requirements,
            config.get("equivalency_decisions") or [],
            context=equivalency_context,
            report=report,
            include_candidates=True,
        )
        report = apply_equivalency_audit_to_report(report, equivalency_audit, mutate=True)

    target_satisfied = target_gate_satisfied()

    # Relevant policy contradictions / missing manual evidence are explicit
    # blockers for a definitive result.  Unrelated department warnings do not
    # contaminate an otherwise scoped Earth report.
    relevant_warnings = []
    for warning in report.get("document_warnings", []):
        text = str(warning)
        if "資科" in text and "資科" not in target_dept:
            continue
        if "物化" in text and "物化" not in target_dept:
            continue
        if any(term in text for term in ("矛盾", "衝突", "未附具體條件", "尚未完整")):
            relevant_warnings.append(text)
    report["policy_warnings"].extend(relevant_warnings)

    if "資科系" in target_dept:
        report["manual_gates"]["cs"] = assess_cs_manual_gate(
            config.get("cs_project_evidence"),
            config.get("cs_certification_a"),
            config.get("cs_certification_b"),
            config.get("cs_alternative_course"),
        )
        if report["manual_gates"]["cs"]["status"] != "COMPLETED":
            report["policy_warnings"].extend(report["manual_gates"]["cs"].get("warnings", []))

    if program == "雙主修":
        secondary_base = (
            config.get("secondary_credits")
            if config.get("secondary_credits") is not None
            else report["target"].get("effective_total_completed", report["summary"]["target_completed"])
        )
        bound_shared = float(equivalency_audit.get("approved_shared_reuse_credits", 0.0) or 0.0)
        # Legacy aggregate fields are deliberately not forwarded as an
        # allowance.  An explicit zero keeps the independent timing/40-credit
        # policy check useful while the equivalency gate reports any unresolved
        # source-to-target evidence.
        eligibility_kwargs = {
            "program_type": program,
            "admission_cohort": config.get("handbook_year"),
            "application_year": config.get("application_year"),
            "application_semester": config.get("application_semester"),
            "application_status": config.get("application_status"),
            "secondary_credits": secondary_base,
            "shared_credits": bound_shared,
            "shared_approved": True,
            "shared_evidence_state": "approved" if bound_shared > 1e-6 else "confirmed_zero",
            "department_approved": config.get("department_approved"),
            "interrupted": bool(config.get("interrupted")),
            "leave_history": config.get("leave_history"),
            "equivalency_bound": bound_shared > 1e-6,
        }
        eligibility = assess_double_major_eligibility(
            **eligibility_kwargs,
        )
        report["double_major_eligibility"] = eligibility
        if eligibility.get("status") != "SATISFIED":
            report["policy_warnings"].extend(eligibility.get("reasons", []))

    # Re-evaluate the target sub-bucket gate after any approved, separately
    # reported shared reuse has been applied.
    target_satisfied = target_gate_satisfied()

    report["policy_warnings"] = list(dict.fromkeys(str(item) for item in report["policy_warnings"] if item))
    parser_diagnostics = config.get("parser_diagnostics") or {}
    cohort_match = assess_cohort_match(
        report["handbook_year"],
        parser_diagnostics.get("detected_admission_cohort") or config.get("detected_admission_cohort"),
        confirmed=bool(config.get("cohort_mismatch_confirmed", False)),
    )
    report["cohort_match"] = cohort_match
    if cohort_match.get("status") == UNKNOWN:
        report["policy_warnings"] = list(
            dict.fromkeys(report["policy_warnings"] + cohort_match.get("reasons", []))
        )
    # Parser course-code/department omissions are non-fatal for the existing
    # Earth/Life title-based evaluator.  Only explicitly fatal diagnostics
    # block its definitive gates; threshold-only programs remain UNKNOWN via
    # their non-detailed path.
    if parser_diagnostics:
        parser_fatal = parser_diagnostics.get("fatal")
        if parser_fatal is None:
            parser_fatal = bool(parser_diagnostics.get("fatal_warnings"))
            if not parser_fatal and not (
                parser_diagnostics.get("course_code_missing")
                or parser_diagnostics.get("offering_department_missing")
            ):
                parser_fatal = parser_diagnostics.get("complete") is False
    else:
        parser_fatal = False
    unknown_blocker = bool(parser_fatal)
    unknown_blocker = unknown_blocker or cohort_match.get("status") == UNKNOWN
    unknown_blocker = unknown_blocker or bool(report["policy_warnings"])
    all_gates = has_enough and has_common and has_ge_categories and has_ge_common_elective and has_major and has_free and has_pe and no_missing and target_satisfied
    report["graduation_gates"] = {
        "total": has_enough,
        "common_total": has_common,
        "ge_categories": has_ge_categories,
        "ge_common_elective": has_ge_common_elective,
        "major_total": has_major,
        "major_common": has_major_common,
        "domain_required": has_domain_required,
        "domain_elective": has_domain_elective,
        "other_elective": has_other_elective,
        "free": has_free,
        "physical_education": has_pe,
        "required_courses": no_missing,
        "target": target_satisfied,
        "target_effective_total": report["target"].get("effective_total_completed", report["target"].get("total_completed", 0.0)) >= requirements["target_total"] if requirements["target_total"] else True,
        "credit_conservation": report["audit"]["credit_conservation"],
    }
    if unknown_blocker:
        graduation_status = UNKNOWN
    elif all_gates:
        graduation_status = GRADUATION_SATISFIED
    else:
        graduation_status = GRADUATION_NOT_SATISFIED
    report["summary"]["graduation_status"] = graduation_status
    report["summary"]["graduation_ready"] = graduation_status == GRADUATION_SATISFIED

    # Add the selected primary and double-major source references to exports.
    try:
        primary_plan = get_primary_requirements(report["handbook_year"], "地生", domain)
        report["citations"] = list(primary_plan.get("citations", []))
        report["evidence_states"] = primary_plan.get("evidence_states", primary_plan.get("evidence", {}))
        if target_dept:
            target_name = "資科" if "資科" in target_dept else "物化" if "物化" in target_dept else "地生"
            target_track = "電子物理" if "物理" in target_dept else "應用化學" if "化學" in target_dept else None
            report["citations"].extend(get_double_structure(report["handbook_year"], target_name, target_track).get("citations", []))
    except (ValueError, KeyError):
        report["citations"] = []

    return report


def find_and_consume_course(courses, rule_name, consumed_set, expected_credit=None, aliases=()):
    """Consume one exact scoped identity, preferring completed attempts.

    Substring matching, edit-distance matching and global aliases are forbidden.
    This is what keeps ``微積分`` separate from ``微積分(I)/(II)`` and keeps
    combined laboratory courses separate from their theory/lab components.
    """
    candidates = []
    for course in courses:
        c_idx = id(course)
        if c_idx in consumed_set:
            continue
        if _course_matches_rule(course, rule_name, expected_credit, aliases):
            rank = 2 if course.get("is_completed") else 1 if course.get("is_in_progress") else 0
            candidates.append((rank, course))
    if not candidates:
        return None
    _, selected = max(candidates, key=lambda item: (item[0], _record_quality(item[1]), tuple(reversed(_course_stable_key(item[1])))))
    consumed_set.add(id(selected))
    dbg(
        "find_and_consume: exact scoped match "
        f"rule='{normalize_course_name(rule_name)}' course='{normalize_course_name(selected.get('name', ''))}'"
    )
    return selected
