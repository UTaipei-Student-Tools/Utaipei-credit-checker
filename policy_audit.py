"""Cohort-aware policy planning and conservative eligibility helpers.

The detailed Earth/biology evaluator remains in :mod:`credit_engine`.  This
module owns the policy facts that are useful before a transcript is available
and deliberately does not invent course identities for programs whose source
course tables are not encoded in the application.
"""

from __future__ import annotations

import re
from typing import Any


SATISFIED = "SATISFIED"
UNSATISFIED = "UNSATISFIED"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"
ELIGIBILITY_STATES = (SATISFIED, UNSATISFIED, UNKNOWN, NOT_APPLICABLE)

# Graduation uses a readable unmet label; double-major eligibility retains the
# four policy states above.
GRADUATION_SATISFIED = SATISFIED
GRADUATION_NOT_SATISFIED = "NOT_SATISFIED"
GRADUATION_UNKNOWN = UNKNOWN
CS_GATE_COMPLETED = "COMPLETED"
CS_GATE_INCOMPLETE = "INCOMPLETE"
CS_GATE_UNKNOWN = UNKNOWN
MANUAL_EVIDENCE_COMPLETED = "completed"
MANUAL_EVIDENCE_INCOMPLETE = "incomplete"
MANUAL_EVIDENCE_UNKNOWN = "unknown"

# Keep policy confidence separate from a student's graduation status.  A
# threshold can be transcribed from an official handbook while the detailed
# course catalogue or an application decision is still unavailable.
EVIDENCE_VERIFIED = "VERIFIED"
EVIDENCE_INCOMPLETE = "INCOMPLETE"
EVIDENCE_CONFLICTED = "CONFLICTED"
EVIDENCE_MANUAL_REVIEW = "MANUAL_REVIEW"

# Shared-course evidence is intentionally separate from the numeric amount:
# an unanswered field must not be serialized as a confirmed zero.
SHARED_EVIDENCE_UNANSWERED = "UNANSWERED"
SHARED_EVIDENCE_CONFIRMED_ZERO = "CONFIRMED_ZERO"
SHARED_EVIDENCE_APPROVED = "APPROVED"
SHARED_EVIDENCE_UNAPPROVED = "UNAPPROVED"
SHARED_EVIDENCE_INVALID = "INVALID"

ADMISSION_COHORTS = ("111", "112", "113", "114", "115")
DOUBLE_MAJOR_MIN_CREDITS = 40.0
DOUBLE_MAJOR_RULE_URL = "https://reg.utaipei.edu.tw/var/file/31/1031/img/926/316980591.pdf"
CS_RULE_URL = "https://cs.utaipei.edu.tw/var/file/81/1081/img/1416/276427143.pdf"


def _citation(file_name: str, pages: str, label: str, url: str | None = None) -> dict[str, str]:
    item = {"file": file_name, "pages": pages, "label": label}
    if url:
        item["url"] = url
    return item


# These are the source-page facts supplied with the project brief.  Keeping
# them as structured data makes them available to both the UI and exports.
_PRIMARY_CITATIONS = {
    "111": [_citation("3-理學院.pdf", "PDF pp. 2-82", "111 學年度理學院學生手冊")],
    "112": [_citation("3-理學院 (112).pdf", "PDF pp. 2-82", "112 學年度理學院學生手冊")],
    "113": [_citation("3-理學院 (113).pdf", "PDF pp. 2-82", "113 學年度理學院學生手冊")],
    "114": [_citation("3-理學院 (114).pdf", "PDF pp. 2-82", "114 學年度理學院學生手冊")],
    "115": [_citation("3-理學院 (115).pdf", "PDF pp. 2-93", "115 學年度理學院學生手冊")],
}

# Undergraduate primary-course evidence is not one contiguous generic range:
# each department starts at a different page in the same college PDF.  These
# ranges are kept separate from the double-major page citations below so an
# audit always points at the selected program's evidence, including CS pages.
_PRIMARY_PAGE_RANGES = {
    "111": {"物化": "PDF pp.2-19", "地生": "PDF pp.25-39", "數學": "PDF pp.65-82", "資科": "PDF pp.111-122"},
    "112": {"物化": "PDF pp.2-19", "地生": "PDF pp.25-39", "數學": "PDF pp.60-77", "資科": "PDF pp.106-117"},
    "113": {"物化": "PDF pp.2-24", "地生": "PDF pp.30-45", "數學": "PDF pp.61-79", "資科": "PDF pp.102-112"},
    "114": {"物化": "PDF pp.2-24", "地生": "PDF pp.31-47", "數學": "PDF pp.65-82", "資科": "PDF pp.106-117"},
    "115": {"物化": "PDF pp.2-25", "地生": "PDF pp.39-55", "數學": "PDF pp.76-93", "資科": "PDF pp.117-127"},
}


def _primary_citations(cohort: str, program: str, track: str | None = None) -> list[dict[str, str]]:
    label = f"{cohort} 學年度{program}"
    if track:
        label += f"（{track}）"
    return [_citation(_source_file(cohort), _PRIMARY_PAGE_RANGES[cohort][program], label)]


def _primary_evidence(cohort: str, program: str) -> dict[str, str]:
    """Describe which parts of a primary plan are actually evidenced."""

    # The legacy evaluator has exact Earth/Life tables only for these three
    # handbooks.  Other programs intentionally expose thresholds without
    # claiming that transcript rows can be classified course-by-course.
    course_catalog = EVIDENCE_VERIFIED if program == "地生" and cohort in {"112", "113", "114"} else EVIDENCE_INCOMPLETE
    return {
        "threshold": EVIDENCE_VERIFIED,
        "course_catalog": course_catalog,
        "eligibility": EVIDENCE_MANUAL_REVIEW,
    }


_DOUBLE_CITATION_PAGES = {
    "地生": {"111": "PDF p.39", "112": "PDF p.39", "113": "PDF p.45", "114": "PDF p.47", "115": "PDF p.55"},
    "資科": {
        "111": "PDF pp.121-122",
        "112": "PDF pp.116-117",
        "113": "PDF pp.111-112",
        "114": "PDF pp.116-117",
        "115": "PDF p.127",
    },
    "數學": {
        "111": "PDF pp.80-82",
        "112": "PDF pp.75-77",
        "113": "PDF pp.77-79",
        "114": "PDF pp.80-82",
        "115": "PDF pp.91-93",
    },
    "物化": {
        "111": "PDF pp.10,19",
        "112": "PDF pp.10,19",
        "113": "PDF pp.23-24",
        "114": "PDF pp.12,24",
        "115": "PDF pp.12-13,24-25",
    },
}


def _source_file(cohort: str) -> str:
    return "3-理學院.pdf" if cohort == "111" else f"3-理學院 ({cohort}).pdf"


def get_admission_cohort_options() -> list[str]:
    """Return selectable admission cohorts in chronological order."""

    return list(ADMISSION_COHORTS)


def normalize_cohort(value: Any) -> str:
    text = str(value or "").strip().replace("學年度", "")
    match = re.search(r"(?<!\d)(11[1-5])(?!\d)", text)
    if match and match.group(1) in ADMISSION_COHORTS:
        return match.group(1)
    raise ValueError(f"不支援的入學 cohort：{value}")


def assess_cohort_match(selected_cohort: Any, detected_cohort: Any = None, confirmed: bool = False) -> dict[str, Any]:
    """Gate a selected handbook against a transcript-detected cohort.

    A missing detected value is not a contradiction: old transcripts often do
    not expose the admission year in a parseable form.  A mismatch is
    intentionally UNKNOWN until the user records an explicit confirmation so
    a convenient UI selection cannot silently apply the wrong handbook.
    """

    selected = normalize_cohort(selected_cohort)
    detected_text = str(detected_cohort or "").strip()
    try:
        detected = normalize_cohort(detected_text) if detected_text else ""
    except ValueError:
        detected = ""
    if not detected:
        return {
            "status": NOT_APPLICABLE,
            "state": NOT_APPLICABLE,
            "selected_cohort": selected,
            "detected_cohort": "",
            "confirmed": bool(confirmed),
            "reasons": [],
        }
    if detected == selected:
        return {
            "status": SATISFIED,
            "state": SATISFIED,
            "selected_cohort": selected,
            "detected_cohort": detected,
            "confirmed": bool(confirmed),
            "reasons": ["成績單辨識到的入學 cohort 與選定手冊一致。"],
        }
    if confirmed:
        return {
            "status": SATISFIED,
            "state": SATISFIED,
            "selected_cohort": selected,
            "detected_cohort": detected,
            "confirmed": True,
            "reasons": ["成績單辨識到不同入學 cohort；已由使用者明確確認仍採用選定手冊。"],
        }
    return {
        "status": UNKNOWN,
        "state": UNKNOWN,
        "selected_cohort": selected,
        "detected_cohort": detected,
        "confirmed": False,
        "reasons": [f"成績單辨識到 {detected} 學年度，但目前選定 {selected} 學年度手冊；需明確確認適用版本。"],
    }


check_cohort_match = assess_cohort_match


def get_primary_program_options(cohort: Any = "114") -> list[str]:
    """Display labels for the six supported primary tracks."""

    cohort_value = normalize_cohort(cohort)
    math_label = "數據科學與數學" if cohort_value == "115" else "數學"
    return ["地生（地球環境）", "地生（生命科學）", "物化（電子物理）", "物化（應用化學）", "資科", math_label]


def get_target_program_options(cohort: Any, primary_program: Any) -> list[str]:
    """Return cross-department targets, excluding every primary department track."""

    cohort_value = normalize_cohort(cohort)
    primary, _ = normalize_primary_program(primary_program, cohort_value)
    return [
        option
        for option in get_primary_program_options(cohort_value)
        if normalize_primary_program(option, cohort_value)[0] != primary
    ]


def normalize_primary_program(value: Any, cohort: Any = "114") -> tuple[str, str | None]:
    """Normalize a UI label to ``(program, track)``.

    Accepted values intentionally include the legacy Earth-domain labels so
    callers using the original evaluator do not need a migration shim.
    """

    text = str(value or "").strip()
    cohort_value = normalize_cohort(cohort)
    if text in {"地生", "地球環境", "地球環境暨生物資源學系", "地生（地球環境）", "地生-地球環境"}:
        return "地生", "地球環境"
    if text in {"生命科學", "地生（生命科學）", "地生-生命科學"}:
        return "地生", "生命科學"
    if text in {"物化", "物理化學", "電子物理", "物化（電子物理）", "物化-電子物理", "物化系物理組"}:
        return "物化", "電子物理"
    if text in {"應用化學", "化學", "物化（應用化學）", "物化-應用化學", "物化系化學組"}:
        return "物化", "應用化學"
    if text in {"資科", "資科系", "資訊科學", "資訊科學系"}:
        return "資科", None
    if text in {"數學", "數據科學與數學", "數學系"}:
        return "數學", None
    raise ValueError(f"不支援的主修系所／組別：{value}（{cohort_value}）")


def _earth_plan(cohort: str, track: str) -> dict[str, Any]:
    return {
        "program": "地生",
        "track": track,
        "verified": False,
        "evidence": _primary_evidence(cohort, "地生"),
        "evidence_states": _primary_evidence(cohort, "地生"),
        "status": SATISFIED,
        "system_total": 85.0,
        "university_common_required": 28.0,
        "major_common_required": 24.0,
        "track_required": 14.0,
        "elective_required": 47.0,
        "free_required": 15.0,
        "total_required": 128.0,
        "breakdown": [
            {"label": "系共同必修", "required": 24.0},
            {"label": "專業／領域必修", "required": 14.0},
            {"label": "專業選修與其他本系選修", "required": 47.0},
        ],
        "citations": _primary_citations(cohort, "地生", track),
        "warnings": [],
    }


def _apc_plan(cohort: str, track: str) -> dict[str, Any]:
    if cohort == "115":
        major_common, track_required, elective = 18.0, 42.0, 25.0
    elif track == "電子物理":
        major_common, track_required, elective = 16.0, 44.0, 25.0
    else:
        major_common, track_required, elective = 16.0, 45.0, 24.0
    return {
        "program": "物化",
        "track": track,
        "verified": False,
        "evidence": _primary_evidence(cohort, "物化"),
        "evidence_states": _primary_evidence(cohort, "物化"),
        "status": SATISFIED,
        "system_total": 85.0,
        "university_common_required": 28.0,
        "major_common_required": major_common,
        "track_required": track_required,
        "elective_required": elective,
        "free_required": 15.0,
        "total_required": 128.0,
        "breakdown": [
            {"label": "物化系共同／基礎必修", "required": major_common},
            {"label": "組別必修", "required": track_required},
            {"label": "系選修", "required": elective},
        ],
        "citations": _primary_citations(cohort, "物化", track),
        "warnings": [],
    }


def _cs_plan(cohort: str) -> dict[str, Any]:
    return {
        "program": "資科",
        "track": None,
        "verified": False,
        "evidence": _primary_evidence(cohort, "資科"),
        "evidence_states": _primary_evidence(cohort, "資科"),
        "status": SATISFIED,
        "system_total": 100.0,
        "university_common_required": 28.0,
        "required_courses_credits": 31.0,
        "elective_required": 54.0,
        "free_required": 15.0,
        "total_required": 128.0,
        "breakdown": [
            {"label": "資科系必修", "required": 31.0},
            {"label": "資科系選修", "required": 54.0},
            {"label": "自由選修", "required": 15.0},
        ],
        "citations": [*_primary_citations(cohort, "資科"), _citation(_source_file(cohort), _DOUBLE_CITATION_PAGES["資科"][cohort], "資科雙主修／跨系規範"), _citation("資科系規則", "PDF rule", "資科系畢業門檻", CS_RULE_URL)],
        "warnings": ["資科系課程身分與畢業專題／認證條件仍需系所或人工證明；本規劃不猜測課號。"],
    }


def _math_plan(cohort: str) -> dict[str, Any]:
    if cohort in {"111", "112"}:
        common, track, track_requirements = 36.0, None, {}
    elif cohort == "115":
        common, track, track_requirements = 20.0, 7.0, {"數學與科學計算": 7.0, "數據科學": 6.0}
    else:
        track_requirements = {"數學與科學計算": 7.0, "數據科學": 6.0, "數學教育": 3.0}
        common, track = 20.0, {"113": 7.0, "114": 6.0}[cohort]
    return {
        "program": "數學",
        "track": None,
        "verified": False,
        "evidence": _primary_evidence(cohort, "數學"),
        "evidence_states": _primary_evidence(cohort, "數學"),
        "status": SATISFIED,
        "system_total": 100.0,
        "university_common_required": 28.0,
        "program_common_required": common,
        "track_required": track,
        "track_requirements": track_requirements,
        "total_required": 128.0,
        "free_required": 15.0,
        "breakdown": [
            {"label": "數學系系統總額", "required": 100.0},
            {"label": "系共同必修", "required": common},
            *[{"label": f"{name}領域必修", "required": value} for name, value in track_requirements.items()],
        ],
        "citations": _primary_citations(cohort, "數學"),
        "warnings": ["數學系課程細項尚未具備可供本工具安全逐課分類的資料；僅顯示已核對總額規劃。"],
    }


def get_primary_requirements(cohort: Any, primary_program: Any, track: Any = None) -> dict[str, Any]:
    """Return verified threshold facts for a primary program.

    ``status`` describes the policy facts, not a student's transcript result.
    A caller must still apply transcript completeness and manual evidence
    gates before declaring graduation.
    """

    cohort_value = normalize_cohort(cohort)
    program, inferred_track = normalize_primary_program(primary_program, cohort_value)
    selected_track = str(track or inferred_track or "").strip() or inferred_track
    if program == "地生":
        plan = _earth_plan(cohort_value, selected_track or "地球環境")
    elif program == "物化":
        plan = _apc_plan(cohort_value, selected_track or "電子物理")
    elif program == "資科":
        plan = _cs_plan(cohort_value)
    else:
        plan = _math_plan(cohort_value)
    plan["cohort"] = cohort_value
    plan["primary_program"] = primary_program
    plan["source_file"] = _source_file(cohort_value)
    plan["system_required"] = plan.get("system_total")
    plan["total"] = plan.get("total_required")
    plan["common_total"] = plan.get("university_common_required", 28.0)
    if program in {"地生", "物化"}:
        plan["common_required"] = plan.get("major_common_required")
    elif program == "資科":
        plan["required"] = plan.get("required_courses_credits")
        plan["common_required"] = plan.get("required_courses_credits")
    else:
        plan["common_required"] = plan.get("program_common_required")
    plan["free"] = plan.get("free_required", 15.0)
    return plan


# Short aliases make the policy API discoverable to existing callers and
# hidden integrations without forcing them to know one canonical name.
get_cohort_plan = get_primary_requirements
get_primary_plan = get_primary_requirements


def get_double_structure(cohort: Any, target_program: Any, track: Any = None) -> dict[str, Any]:
    cohort_value = normalize_cohort(cohort)
    program, inferred_track = normalize_primary_program(target_program, cohort_value)
    selected_track = str(track or inferred_track or "").strip() or inferred_track
    citation = _citation(_source_file(cohort_value), _DOUBLE_CITATION_PAGES[program][cohort_value], "雙主修課程結構")
    if program == "地生":
        base, other, status = 24.0, 16.0, SATISFIED
    elif program == "資科":
        base, other, status = 15.0, 25.0, SATISFIED
    elif program == "數學":
        if cohort_value in {"111", "112"}:
            base, other, status = 21.0, 18.0, UNKNOWN
        else:
            base, other, status = 14.0, 26.0, SATISFIED
    else:
        if cohort_value == "115":
            base, other, status = 20.0, 20.0, SATISFIED
        else:
            base, other, status = 16.0, 24.0, SATISFIED
    warnings = []
    if status == UNKNOWN:
        warnings.append("手冊同時寫明雙主修40學分，但分項21＋18學分不相加為40；須由系所確認。")
    evidence_states = {
        "threshold": EVIDENCE_CONFLICTED if status == UNKNOWN else EVIDENCE_VERIFIED,
        "course_catalog": EVIDENCE_INCOMPLETE,
        "eligibility": EVIDENCE_MANUAL_REVIEW,
    }
    citations = [citation, _citation(DOUBLE_MAJOR_RULE_URL, "official rule", "校級雙主修申請與40學分規定", DOUBLE_MAJOR_RULE_URL)]
    if program == "資科":
        citations.append(_citation(CS_RULE_URL, "official rule", "資科系專題／認證門檻", CS_RULE_URL))
    return {
        "cohort": cohort_value,
        "program": program,
        "track": selected_track,
        "base_required": base,
        "other_required": other,
        "total_required": 40.0,
        "status": status,
        "evidence": evidence_states,
        "evidence_states": evidence_states,
        "warnings": warnings,
        "citations": citations,
    }


def _manual_state(value: Any) -> str:
    if value is True:
        return CS_GATE_COMPLETED
    if value is False:
        return CS_GATE_INCOMPLETE
    text = str(value or "").strip().lower()
    if text in {"completed", "complete", "已完成", "完成", "通過", "true", "yes", "1"}:
        return CS_GATE_COMPLETED
    if text in {"incomplete", "未完成", "不完整", "未通過", "false", "no", "0"}:
        return CS_GATE_INCOMPLETE
    return CS_GATE_UNKNOWN


def assess_cs_manual_gate(
    project_evidence: Any = None,
    certification_a: Any = None,
    certification_b: Any = None,
    alternative_course: Any = None,
) -> dict[str, Any]:
    """Assess the CS project plus A>=1/B>=2 (or approved alternative) gate."""

    project_state = _manual_state(project_evidence)
    alternative_state = _manual_state(alternative_course)
    try:
        a_count = int(certification_a) if certification_a not in (None, "") else None
    except (TypeError, ValueError):
        a_count = None
    try:
        b_count = int(certification_b) if certification_b not in (None, "") else None
    except (TypeError, ValueError):
        b_count = None
    if a_count is None or b_count is None:
        cert_state = CS_GATE_UNKNOWN
    elif a_count >= 1 or b_count >= 2:
        cert_state = CS_GATE_COMPLETED
    else:
        cert_state = CS_GATE_INCOMPLETE
    alternative_satisfies = alternative_state == CS_GATE_COMPLETED
    cert_satisfies = cert_state == CS_GATE_COMPLETED or alternative_satisfies
    if project_state == CS_GATE_INCOMPLETE or (not cert_satisfies and cert_state == CS_GATE_INCOMPLETE and alternative_state != CS_GATE_UNKNOWN):
        state = CS_GATE_INCOMPLETE
    elif project_state == CS_GATE_COMPLETED and cert_satisfies:
        state = CS_GATE_COMPLETED
    else:
        state = CS_GATE_UNKNOWN
    return {
        "status": state,
        "state": state,
        "normalized_status": state.lower(),
        "project": project_state,
        "certification": cert_state,
        "alternative_course": alternative_state,
        "certification_a": a_count,
        "certification_b": b_count,
        "requirements": {"project": "completed", "certification": "A>=1 or B>=2 or approved alternative course"},
        "warnings": [] if state == CS_GATE_COMPLETED else ["資科系專題與認證門檻仍需人工或系所證明。"],
        "citations": [_citation(CS_RULE_URL, "official rule", "資科系專題／認證門檻", CS_RULE_URL)],
    }


check_cs_manual_gate = assess_cs_manual_gate


def _relative_application_year(application_year: Any, admission_cohort: Any) -> int | None:
    """Convert an application academic year to a study-year offset.

    The UI supplies an actual ROC academic year.  Integrations may still send
    the legacy relative year (1--9), and older records sometimes use a
    Gregorian academic year; accept all three forms without treating ROC 112
    as the literal study year 112.
    """

    if application_year is None or str(application_year).strip() == "":
        return None
    text = str(application_year).strip().replace("學年度", "").replace("學年", "")
    matches = re.findall(r"(?<!\d)\d{1,4}(?!\d)", text)
    if not matches:
        return None
    value = int(matches[0])
    try:
        cohort = int(normalize_cohort(admission_cohort))
    except (ValueError, TypeError):
        cohort = None

    # A one-digit value is the pre-existing relative-year format.
    if 1 <= value <= 9:
        return value

    # Academic years may be written as ROC 3-digit years or Gregorian years.
    if 100 <= value <= 999:
        roc_year = value
    elif 1900 <= value <= 2200:
        roc_year = value - 1911
    else:
        return None
    if cohort is None:
        return None
    return roc_year - cohort + 1


def _semester_number(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    if text in {"1", "一", "第一學期", "上"} or "第一" in text:
        return 1
    if text in {"2", "二", "第二學期", "下"} or "第二" in text:
        return 2
    return None


def _shared_evidence_state(shared_credits: Any, shared_approved: bool | None, explicit_state: Any = None) -> str:
    """Normalize shared-course evidence without collapsing missing into zero."""

    if explicit_state not in (None, ""):
        text = str(explicit_state).strip().lower()
        aliases = {
            "unanswered": SHARED_EVIDENCE_UNANSWERED,
            "unknown": SHARED_EVIDENCE_UNANSWERED,
            "未填寫": SHARED_EVIDENCE_UNANSWERED,
            "不確定": SHARED_EVIDENCE_UNANSWERED,
            "confirmed_zero": SHARED_EVIDENCE_CONFIRMED_ZERO,
            "zero": SHARED_EVIDENCE_CONFIRMED_ZERO,
            "已確認0": SHARED_EVIDENCE_CONFIRMED_ZERO,
            "已確認無共修": SHARED_EVIDENCE_CONFIRMED_ZERO,
            "approved": SHARED_EVIDENCE_APPROVED,
            "已核准": SHARED_EVIDENCE_APPROVED,
            "unapproved": SHARED_EVIDENCE_UNAPPROVED,
            "未核准": SHARED_EVIDENCE_UNAPPROVED,
        }
        return aliases.get(text, SHARED_EVIDENCE_INVALID)
    if shared_credits is None or str(shared_credits).strip() == "":
        return SHARED_EVIDENCE_UNANSWERED
    try:
        amount = float(shared_credits)
    except (TypeError, ValueError):
        return SHARED_EVIDENCE_INVALID
    if abs(amount) <= 1e-6:
        # A caller that supplied a numeric zero has answered the question;
        # the UI uses ``None`` for its unanswered option.
        return SHARED_EVIDENCE_CONFIRMED_ZERO
    return SHARED_EVIDENCE_APPROVED if shared_approved is True else SHARED_EVIDENCE_UNAPPROVED


def assess_double_major_eligibility(
    *,
    program_type: str = "雙主修",
    admission_cohort: Any = None,
    application_year: Any = None,
    application_semester: Any = None,
    application_status: Any = None,
    secondary_credits: Any = None,
    shared_credits: Any = None,
    shared_approved: bool | None = None,
    shared_evidence_state: Any = None,
    department_approved: bool | None = None,
    interrupted: bool = False,
    leave_history: Any = None,
    final_normal_year: int = 4,
) -> dict[str, Any]:
    """Assess the general double-major rule using four-state outcomes.

    Missing evidence is intentionally ``UNKNOWN``.  Application timing is
    derived only from the explicitly supplied application year and semester;
    admission cohort is never treated as an application date.
    """

    if program_type != "雙主修":
        return {
            "status": NOT_APPLICABLE,
            "state": NOT_APPLICABLE,
            "reasons": ["目前不是雙主修身分。"],
            "interrupted": bool(interrupted),
            "warnings": [],
            "citations": [_citation(DOUBLE_MAJOR_RULE_URL, "official rule", "校級雙主修規定", DOUBLE_MAJOR_RULE_URL)],
        }

    reasons: list[str] = []
    warnings: list[str] = []
    unknown = False
    unsatisfied = False

    relative_year = _relative_application_year(application_year, admission_cohort)
    semester = _semester_number(application_semester)
    if interrupted or leave_history:
        unknown = True
        reasons.append("有休學／中斷紀錄，無法安全推導正常修業年級。")
    elif relative_year is None or semester is None:
        unknown = True
        reasons.append("缺少可核對的申請學年或學期。")
    elif relative_year < 2 or relative_year > int(final_normal_year) or (
        relative_year == int(final_normal_year) and semester != 1
    ):
        unsatisfied = True
        reasons.append("申請時點不在大二起至正常修業最後一年第一學期的範圍內。")
    else:
        reasons.append("申請時點符合大二起至正常修業最後一年第一學期的校級範圍。")

    status_text = str(application_status or "").strip()
    if status_text in {"", "不確定"}:
        unknown = True
        reasons.append("申請狀態未能確認。")
    elif status_text in {"未申請", "未通過"}:
        unsatisfied = True
        reasons.append(f"申請狀態為「{status_text}」。")
    elif status_text == "申請中":
        unknown = True
        reasons.append("申請尚在審查中，不能視為已核准。")
    elif status_text == "已核准":
        reasons.append("申請狀態為已核准。")
    else:
        unknown = True
        reasons.append(f"無法辨識申請狀態：{status_text}。")

    try:
        secondary = None if secondary_credits is None or str(secondary_credits).strip() == "" else float(secondary_credits)
    except (TypeError, ValueError):
        secondary = None
    if secondary is None:
        unknown = True
        reasons.append("缺少可核對的雙主修已修學分。")
    elif secondary + 1e-6 < DOUBLE_MAJOR_MIN_CREDITS:
        unsatisfied = True
        reasons.append(f"雙主修已修學分為 {secondary:g}，未達至少40學分。")
    else:
        reasons.append(f"雙主修已修學分為 {secondary:g}，達至少40學分。")

    try:
        shared = None if shared_credits is None or str(shared_credits).strip() == "" else float(shared_credits)
    except (TypeError, ValueError):
        shared = None
    shared_state = _shared_evidence_state(shared_credits, shared_approved, shared_evidence_state)
    if shared is None and shared_state == SHARED_EVIDENCE_CONFIRMED_ZERO:
        # Explicit zero evidence is sufficient even when integrations omit a
        # redundant numeric field; unanswered remains a distinct state.
        shared = 0.0
    shared_reuse_allowance = 0.0
    if shared_state == SHARED_EVIDENCE_UNANSWERED:
        unknown = True
        reasons.append("尚未回答共同修課學分；不能視為已確認0學分。")
    elif shared_state == SHARED_EVIDENCE_INVALID:
        unsatisfied = True
        reasons.append("共同修課學分／證據格式無法辨識。")
    elif shared is None:
        unknown = True
        reasons.append("缺少可核對的共同修課學分。")
    elif shared < -1e-6:
        unsatisfied = True
        reasons.append("共同修課學分不可為負數。")
    elif shared > 6.0 + 1e-6:
        unsatisfied = True
        reasons.append("共同修課超過6學分上限。")
    elif shared_state == SHARED_EVIDENCE_UNAPPROVED:
        unknown = True
        reasons.append("共同修課須有系所核准；目前未提供核准證據。")
    elif shared_state == SHARED_EVIDENCE_APPROVED:
        if shared_approved is False and shared_evidence_state not in {"approved", "已核准"}:
            unknown = True
            reasons.append("共同修課證據彼此矛盾，需人工確認。")
        else:
            shared_reuse_allowance = max(0.0, shared)
            reasons.append("共同修課在6學分內且已有核准證據；共享額度將另列稽核。")
    elif shared_state == SHARED_EVIDENCE_CONFIRMED_ZERO:
        reasons.append("已確認沒有共同修課學分。")

    if department_approved is False:
        unsatisfied = True
        reasons.append("缺少或取得系所不核准的證據。")
    elif department_approved is None:
        warnings.append("系所可訂更嚴格規定；校級規則不能取代系所最終認定。")

    state = UNSATISFIED if unsatisfied else UNKNOWN if unknown else SATISFIED
    return {
        "status": state,
        "state": state,
        "reasons": reasons,
        "warnings": warnings,
        "application_year": application_year,
        "application_semester": application_semester,
        "application_status": status_text or "不確定",
        "interrupted": bool(interrupted),
        "secondary_credits": secondary,
        "shared_credits": shared,
        "shared_credit_state": shared_state,
        "shared_reuse_allowance": shared_reuse_allowance,
        "shared_evidence": {
            "state": shared_state,
            "raw_credits": shared,
            "approved": shared_approved is True or shared_state == SHARED_EVIDENCE_CONFIRMED_ZERO,
            "reuse_allowance": shared_reuse_allowance,
        },
        "citations": [_citation(DOUBLE_MAJOR_RULE_URL, "official rule", "校級雙主修申請與40學分規定", DOUBLE_MAJOR_RULE_URL)],
        "requirements": {
            "minimum_secondary_credits": DOUBLE_MAJOR_MIN_CREDITS,
            "application_window": "大二起至正常修業最後一年第一學期",
            "shared_credit_limit": 6.0,
        },
    }


check_double_major_eligibility = assess_double_major_eligibility
evaluate_double_major_eligibility = assess_double_major_eligibility
get_double_major_eligibility = assess_double_major_eligibility


def build_policy_audit(config: dict[str, Any] | None = None, report: dict[str, Any] | None = None, student_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Combine selected policy, transcript result, and conservative warnings."""

    config = config or {}
    cohort = config.get("admission_cohort") or config.get("handbook_year") or "114"
    program_value = config.get("primary_program") or config.get("program_name") or config.get("domain") or "地生"
    track = config.get("track")
    plan = get_primary_requirements(cohort, program_value, track)
    program_type = config.get("program_type") or (report or {}).get("program_type", "單主修")
    double = assess_double_major_eligibility(
        program_type=program_type,
        admission_cohort=cohort,
        application_year=config.get("application_year"),
        application_semester=config.get("application_semester"),
        application_status=config.get("application_status"),
        secondary_credits=config.get("secondary_credits", (report or {}).get("summary", {}).get("target_completed") if report else None),
        shared_credits=config.get("shared_credits"),
        shared_approved=config.get("shared_approved"),
        shared_evidence_state=config.get("shared_evidence_state"),
        department_approved=config.get("department_approved"),
        interrupted=bool(config.get("interrupted")),
        leave_history=config.get("leave_history"),
    )
    warnings = list(plan.get("warnings", [])) + list(double.get("warnings", []))
    if report:
        warnings.extend(report.get("policy_warnings", []))
        warnings.extend(report.get("document_warnings", []))
    parser_diagnostics = (student_info or {}).get("parse_diagnostics", {})
    if parser_diagnostics and parser_diagnostics.get("complete") is False:
        warnings.extend(parser_diagnostics.get("warnings", []))
    return {
        "cohort": normalize_cohort(cohort),
        "primary_program": program_value,
        "track": track or plan.get("track"),
        "program_type": program_type,
        "application": {
            "application_year": config.get("application_year"),
            "application_semester": config.get("application_semester"),
            "application_status": config.get("application_status"),
            "shared_evidence_state": config.get("shared_evidence_state"),
            "cohort_mismatch_confirmed": bool(config.get("cohort_mismatch_confirmed", False)),
            "interrupted": bool(config.get("interrupted")),
        },
        "program_plan": plan,
        "evidence_states": plan.get("evidence_states", plan.get("evidence", {})),
        "cohort_match": (report or {}).get(
            "cohort_match",
            assess_cohort_match(
                cohort,
                (student_info or {}).get("admission_cohort") or (student_info or {}).get("detected_admission_cohort"),
                confirmed=bool(config.get("cohort_mismatch_confirmed", False)),
            ),
        ),
        "double_major": double,
        "requirements": (report or {}).get("requirements", plan),
        "gate_results": (report or {}).get("graduation_gates", {}),
        "manual_gates": (report or {}).get("manual_gates", {}),
        "shared_reuse": (report or {}).get("shared_reuse", {}),
        "credit_audit": (report or {}).get("audit", {}),
        "warnings": list(dict.fromkeys(str(item) for item in warnings if item)),
        "citations": list(plan.get("citations", [])) + list(double.get("citations", [])),
        "status": (report or {}).get("summary", {}).get("graduation_status", UNKNOWN) if report else UNKNOWN,
    }
