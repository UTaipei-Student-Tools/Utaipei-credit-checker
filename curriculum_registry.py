"""Versioned curriculum metadata and fail-closed rule resolution.

This module is deliberately small and data-oriented.  It is the boundary
between a student's selected identity (admission cohort, primary programme and
double-major target) and the older aggregate rule helpers.  In particular, a
target curriculum is never inferred from an admission cohort or an
application term.  A target version must be selected explicitly and be backed
by a scoped applicability assertion or an evidence reference.

The registry keeps two kinds of evidence separate:

* ``evidence_state`` describes what the official source says
  (``VERIFIED``, ``CONFLICTED`` or ``MISSING``).
* ``coverage_state`` describes how much of that source has been transcribed
  into course-level data (``COMPLETE``, ``PARTIAL`` or ``NONE``).

The returned dictionaries are copies, so report rendering and integrations
cannot mutate the process-wide registry.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

# Public states.  Keep these strings stable because reports and exports use
# them as audit values.
VERIFIED = "VERIFIED"
CONFLICTED = "CONFLICTED"
MISSING = "MISSING"
MANUAL_REVIEW = "MANUAL_REVIEW"

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
COVERAGE_NONE = "NONE"

RESOLVED = "RESOLVED"
NOT_APPLICABLE = "NOT_APPLICABLE"

_SUPPORTED_COHORTS = ("111", "112", "113", "114", "115")
_DOUBLE_MAJOR = "雙主修"

_ROOT = os.path.dirname(os.path.abspath(__file__))
_RULES_PATH = os.path.join(_ROOT, "rules_config.json")

_HANDBOOK_URLS = {
    "111": "https://curr.utaipei.edu.tw/app/index.php?Action=downloadfile&file=WVhSMFlXTm9MemN4TDNCMFlWODVNREkyTWw4eE56STBPREZmT0RBNU5qY3VjR1Jt&fname=0054YSGHRK10PPXXTSZSTSYW14PKJDKKQO343510LP25LKQPZWROYSA43454QOUSSSPOCDYTVSPKDHDH&cg=5",
    "112": "https://curr.utaipei.edu.tw/app/index.php?Action=downloadfile&file=WVhSMFlXTm9MelV5TDNCMFlWOHhNRFF3T1RKZk16YzNORGc0TVY4ek16ZzJOaTV3WkdZPQ==&fname=0054YSGHRK10PPXXTSZSTSYW14PKJDKKQO343510LP25LKQPZWROYSA43454QOUSSSPOCDYTVSPKDHDH&cg=5",
    "113": "https://curr.utaipei.edu.tw/app/index.php?Action=downloadfile&file=WVhSMFlXTm9MemcxTDNCMFlWOHhNell5TmpoZk16TXhNREE0TVY4ek9UY3lNUzV3WkdZPQ==&fname=0054YSGHRK10PPXXTSZSTSYW14PKJDKKQO343510LP25LKQPZWROYSA43454QOUSSSPOCDYTVSPKDHDH&cg=5",
    "114": "https://curr.utaipei.edu.tw/app/index.php?Action=downloadfile&file=WVhSMFlXTm9MemN5TDNCMFlWOHhNemN4TWpSZk5UQTVNalkzTWw4ek9UY3lNUzV3WkdZPQ==&fname=0054YSGHRK10PPXXTSZSTSYW14PKJDKKQO343510LP25LKQPZWROYSA43454QOUSSSPOCDYTVSPKDHDH&cg=5",
    "115": "https://curr.utaipei.edu.tw/app/index.php?Action=downloadfile&file=WVhSMFlXTm9Memt3TDNCMFlWOHhOelExTnpKZk1qTXlNak0yWHpjNE5qSXhMbkJrWmc9PQ==&fname=0054YSGHRK10PPXXTSZSTSYW14PKJDKKQO343510LP25LKQPZWROYSA43454QOUSSSPOCDYTVSPKDHDH&cg=5",
}
_DOUBLE_MAJOR_RULE_URL = "https://reg.utaipei.edu.tw/var/file/31/1031/img/926/316980591.pdf"

_PROGRAMS = {
    "地生": "earth",
    "地球環境": "earth",
    "地球環境暨生物資源學系": "earth",
    "生命科學": "earth",
    "生命科學系": "earth",
    "物化": "apc",
    "物理化學": "apc",
    "應用物理": "apc",
    "電子物理": "apc",
    "應用化學": "apc",
    "化學": "apc",
    "資科": "cs",
    "資訊科學": "cs",
    "資訊科學系": "cs",
    "數學": "math",
    "數學系": "math",
    "數據科學與數學": "math",
    "數據科學與數學系": "math",
}
_PROGRAM_DISPLAY = {"earth": "地生", "apc": "物化", "cs": "資科", "math": "數學"}
_TRACKS = {
    "earth_environment": {"地球環境", "地球環境系", "地球環境暨生物資源學系", "地生（地球環境）", "地生-地球環境"},
    "life_science": {"生命科學", "生命科學系", "地生（生命科學）", "地生-生命科學"},
    "physics": {"物理組", "電子物理", "電子物理組", "物化系物理組", "物化（電子物理）", "物化-電子物理"},
    "chemistry": {"化學組", "應用化學", "應用化學組", "物化系化學組", "物化（應用化學）", "物化-應用化學"},
}
_TRACK_DISPLAY = {
    "earth_environment": "地球環境",
    "life_science": "生命科學",
    "physics": "電子物理",
    "chemistry": "應用化學",
}
_PROGRAM_SLUGS = frozenset({"earth", "apc", "cs", "math"})
_TRACK_SLUGS = frozenset({"earth_environment", "life_science", "physics", "chemistry"})
_TRACK_PROGRAMS = {
    "earth_environment": "earth",
    "life_science": "earth",
    "physics": "apc",
    "chemistry": "apc",
}

# ``minor`` is a distinct target role.  It deliberately does not reuse the
# double-major catalogue or its shared-credit semantics.  These are the only
# five target programme scopes supported by the checked-in research matrix;
# no course is inferred from a neighbouring handbook year.
_MINOR_TARGET_ROLE = "minor_target"
_MINOR_RESEARCH_FILE = "research/minor_program_matrix_111_115.md"
_MINOR_PROGRAMS = ("earth", "apc", "cs", "math")
_MINOR_APC_TRACKS = ("physics", "chemistry")

_MINOR_SOURCE_PAGES: dict[tuple[str, str, str | None], tuple[Any, Any, str]] = {
    # ``(pdf page, printed page, matrix section)``
    **{
        (year, "apc", track): (
            {"111": 10, "112": 10, "113": 11, "114": "11–12", "115": 12}[year]
            if track == "physics"
            else {"111": 19, "112": 19, "113": 23, "114": 23, "115": 24}[year],
            {"111": 9, "112": 9, "113": 10, "114": "10–11", "115": 11}[year]
            if track == "physics"
            else {"111": 18, "112": 18, "113": 22, "114": 22, "115": 23}[year],
            f"5.1 APC {year} {track}",
        )
        for year in _SUPPORTED_COHORTS
        for track in _MINOR_APC_TRACKS
    },
    **{
        (year, "earth", None): (
            {"111": 39, "112": 39, "113": 45, "114": 47, "115": 55}[year],
            {"111": 38, "112": 38, "113": 44, "114": 46, "115": 54}[year],
            f"5.2 地生 {year}",
        )
        for year in _SUPPORTED_COHORTS
    },
    **{
        (year, "cs", None): (
            {"111": 121, "112": 116, "113": 111, "114": 116, "115": 127}[year],
            {"111": 120, "112": 115, "113": 110, "114": 115, "115": 126}[year],
            f"5.3 資科 {year}",
        )
        for year in _SUPPORTED_COHORTS
    },
    **{
        (year, "math", None): (
            {"111": "77–79", "112": "72–74", "113": "74–76", "114": "77–79", "115": "88–90"}[year],
            {"111": "76–78", "112": "71–73", "113": "73–75", "114": "76–78", "115": "87–89"}[year],
            f"5.4 數學／數據科學與數學 {year}",
        )
        for year in _SUPPORTED_COHORTS
    },
}

_MINOR_COURSE_KIND = "lecture"


def _table_cell_clause(name: str, credits: int | float) -> str:
    """Return only the transcribed course cell, never a synthesized sentence."""

    return f"{name} {credits:g} 學分"


def _minor_source(year: str, program: str, track: str | None) -> dict[str, Any]:
    pdf_page, printed_page, section = _MINOR_SOURCE_PAGES[(year, program, track)]
    course_pdf_page = pdf_page
    if program == "earth":
        course_pdf_page = {"111": 32, "112": 32, "113": 38, "114": 40, "115": 48}[year]
    elif program == "cs":
        course_pdf_page = {"111": 121, "112": 116, "113": 111, "114": 116, "115": 127}[year]
    elif program == "math":
        course_pdf_page = {"111": "77–79", "112": "72–74", "113": "74–76", "114": "77–79", "115": "88–90"}[year]
    elif program == "apc":
        course_pdf_page = pdf_page
    official_reference = f"handbook:{year}:pdf:{course_pdf_page}:table:{program}:{track or 'department'}"
    source = {
        "research_file": _MINOR_RESEARCH_FILE,
        "source_url": _HANDBOOK_URLS[year],
        "source_file": _source_file(year),
        "pdf_page": pdf_page,
        "printed_page": printed_page,
        "pages": f"PDF p.{pdf_page}（印刷 p.{printed_page}）",
        "section": section,
        # A research matrix is supporting provenance, never the official
        # row identity.  Course rows append ``:row:<slug>`` below.
        "source_reference": official_reference,
    }
    if program == "earth":
        course_pdf_page = {"111": 32, "112": 32, "113": 38, "114": 40, "115": 48}[year]
        course_printed_page = {"111": 31, "112": 31, "113": 37, "114": 39, "115": 47}[year]
        source.update(
            {
                "course_pdf_page": course_pdf_page,
                "course_printed_page": course_printed_page,
                "course_pages": f"PDF p.{course_pdf_page}（印刷 p.{course_printed_page}）",
                "course_table_location": f"{section}；共同必修逐課表",
                "source_reference": f"handbook:{year}:pdf:{course_pdf_page}:table:{program}:department",
            }
        )
    elif program == "cs":
        source.update(
            {
                "course_pdf_page": course_pdf_page,
                "course_printed_page": {"111": 120, "112": 115, "113": 110, "114": 115, "115": 126}[year],
                "course_pages": f"PDF p.{course_pdf_page}（印刷 p.{ {'111': 120, '112': 115, '113': 110, '114': 115, '115': 126}[year] }）",
                "course_table_location": f"{section}；輔系課程列項",
                "source_reference": f"handbook:{year}:pdf:{course_pdf_page}:table:{program}:department",
            }
        )
    elif program == "math":
        source.update(
            {
                "course_pdf_page": course_pdf_page,
                "course_printed_page": {"111": "76–78", "112": "71–73", "113": "73–75", "114": "76–78", "115": "87–89"}[year],
                "course_pages": f"PDF pp.{course_pdf_page}（印刷 pp.{ {'111': '76–78', '112': '71–73', '113': '73–75', '114': '76–78', '115': '87–89'}[year] }）",
                "course_table_location": f"{section}；輔系課程列項",
                "source_reference": f"handbook:{year}:pdf:{course_pdf_page}:table:{program}:department",
            }
        )
    elif program == "apc":
        source.update(
            {
                "course_pdf_page": pdf_page,
                "course_printed_page": printed_page,
                "course_pages": source["pages"],
                "course_table_location": f"{section}；輔系課程列項",
                "source_reference": f"handbook:{year}:pdf:{pdf_page}:table:{program}:{track or 'department'}",
            }
        )
    return source


def _minor_row(
    year: str,
    program: str,
    track: str | None,
    slug: str,
    name: str,
    credits: int | float,
    *,
    component: str = _MINOR_COURSE_KIND,
    eligible_names: tuple[str, ...] | None = None,
    eligible_options: tuple[tuple[str, int | float], ...] | None = None,
    requirement_type: str = "named_course",
    choice_group: str | None = None,
    choice_rule: str = "exact_course_or_approved_equivalency",
    accept_any: bool = False,
    waiver: bool = False,
    zero_credit: bool = False,
    evidence_state: str = VERIFIED,
    coverage_state: str = COMPLETE,
    original_clause: str = "",
    manual_reason: str = "",
) -> dict[str, Any]:
    source = _minor_source(year, program, track)
    row_pdf_page = source.get("course_pdf_page", source["pdf_page"])
    row_printed_page = source.get("course_printed_page", source["printed_page"])
    row_pages = source.get("course_pages", source["pages"])
    row_table_location = source.get("course_table_location", source["section"])
    row_id = f"minor.{year}.{program}.{track or 'department'}.{slug}"
    source_reference = f"{source['source_reference']}:row:{slug}"
    names = eligible_names if eligible_names is not None else (name,)
    automatic = evidence_state == VERIFIED and coverage_state == COMPLETE and not manual_reason
    result = {
        "id": row_id,
        "requirement_id": row_id,
        "name": name,
        "raw_title": name,
        "credits": float(credits),
        "bucket": "minor_required" if requirement_type != "course_pool" else "minor_elective",
        "kind": "MINOR_COURSE" if requirement_type != "credit_quota" else "MINOR_QUOTA",
        "requirement_type": requirement_type,
        "choice_group": choice_group,
        "choice_rule": choice_rule,
        "track": _TRACK_DISPLAY.get(track) if track else None,
        "eligible_course_names": tuple(names),
        "eligible_course_options": tuple(
            {"name": option_name, "credits": float(option_credits)}
            for option_name, option_credits in (eligible_options or ())
        ),
        "accept_any": accept_any,
        "waiver": waiver,
        "waiver_generates_credits": False,
        "component": component,
        "component_type": component,
        "component_label": "實驗" if component == "lab" else "講授" if component == "lecture" else component,
        "lecture_or_lab": component,
        "is_lab": component == "lab",
        "is_zero_credit": zero_credit,
        "allow_combined_lab_source": False,
        "evidence": evidence_state,
        "evidence_state": evidence_state,
        "coverage_state": coverage_state,
        "verification_status": evidence_state,
        "automation_sufficiency": "COMPLETE" if automatic else "PARTIAL",
        "automatic_decision": automatic,
        "manual_reason": manual_reason,
        "manual_review_reason": manual_reason,
        "program_slug": program,
        "track_slug": track or "department",
        "curriculum_version": year,
        "source_assertion_id": row_id,
        "assertion_id": row_id,
        "source_reference": source_reference,
        "source_url": source["source_url"],
        "source_file": source["source_file"],
        "research_file": source["research_file"],
        "pdf_page": row_pdf_page,
        "printed_page": row_printed_page,
        "page": row_pdf_page,
        "pages": row_pages,
        "table_location": row_table_location,
        "original_clause": original_clause,
        "original_text": original_clause,
        "source": {
            "file": source["source_file"],
            "source_file": source["source_file"],
            "url": source["source_url"],
            "source_url": source["source_url"],
            "pages": row_pages,
            "pdf_page": row_pdf_page,
            "printed_page": row_printed_page,
            "source_reference": source_reference,
            "original_clause": original_clause,
            "curriculum_version": year,
        },
        "provenance": {
            "assertion_id": row_id,
            "source_type": "official_handbook",
            "research_file": source["research_file"],
            "source_url": source["source_url"],
            "source_file": source["source_file"],
            "pdf_page": row_pdf_page,
            "printed_page": row_printed_page,
            "pages": row_pages,
            "source_reference": source_reference,
            "table_location": row_table_location,
            "original_clause": original_clause,
            "evidence_state": evidence_state,
            "verification_status": evidence_state,
            "automatic_decision": automatic,
            "manual_reason": manual_reason,
            "manual_review_reason": manual_reason,
        },
    }
    return result

# The APC chemistry double-major table is one of the few target tables that
# can be transcribed safely from the checked-in handbook page images.  Keep
# this list separate from ``rules_config.json``: that file is an older
# aggregate/primary-rule source and must not make a neighbouring cohort's
# rows appear in this target catalogue.
_APC_CHEMISTRY_DM_ROWS = {
    "111": (
        ("普通物理學(一)", 3.0, "lecture", "physics_1"),
        ("普通物理實驗(一)", 1.0, "lab", "physics_lab_1"),
        ("普通化學(一)", 3.0, "lecture", "chemistry_1"),
        ("普通化學實驗(一)", 1.0, "lab", "chemistry_lab_1"),
        ("普通物理學(二)", 3.0, "lecture", "physics_2"),
        ("普通物理實驗(二)", 1.0, "lab", "physics_lab_2"),
        ("普通化學(二)", 3.0, "lecture", "chemistry_2"),
        ("普通化學實驗(二)", 1.0, "lab", "chemistry_lab_2"),
    ),
    "112": (
        ("普通物理學(一)", 3.0, "lecture", "physics_1"),
        ("普通物理實驗(一)", 1.0, "lab", "physics_lab_1"),
        ("普通化學(一)", 3.0, "lecture", "chemistry_1"),
        ("普通化學實驗(一)", 1.0, "lab", "chemistry_lab_1"),
        ("普通物理學(二)", 3.0, "lecture", "physics_2"),
        ("普通物理實驗(二)", 1.0, "lab", "physics_lab_2"),
        ("普通化學(二)", 3.0, "lecture", "chemistry_2"),
        ("普通化學實驗(二)", 1.0, "lab", "chemistry_lab_2"),
    ),
    "113": (
        ("普通物理學(一)", 3.0, "lecture", "physics_1"),
        ("普通物理實驗(一)", 1.0, "lab", "physics_lab_1"),
        ("普通化學(一)", 3.0, "lecture", "chemistry_1"),
        ("普通化學實驗(一)", 1.0, "lab", "chemistry_lab_1"),
        ("普通物理學(二)", 3.0, "lecture", "physics_2"),
        ("普通物理實驗(二)", 1.0, "lab", "physics_lab_2"),
        ("普通化學(二)", 3.0, "lecture", "chemistry_2"),
        ("普通化學實驗(二)", 1.0, "lab", "chemistry_lab_2"),
    ),
    "114": (
        ("普通物理學(一)", 3.0, "lecture", "physics_1"),
        ("普通物理實驗(一)", 1.0, "lab", "physics_lab_1"),
        ("普通化學(一)", 3.0, "lecture", "chemistry_1"),
        ("普通化學實驗(一)", 1.0, "lab", "chemistry_lab_1"),
        ("普通物理學(二)", 3.0, "lecture", "physics_2"),
        ("普通物理實驗(二)", 1.0, "lab", "physics_lab_2"),
        ("普通化學(二)", 3.0, "lecture", "chemistry_2"),
        ("普通化學實驗(二)", 1.0, "lab", "chemistry_lab_2"),
    ),
    "115": (
        ("普通物理學(一)", 3.0, "lecture", "physics_1"),
        ("普通化學(一)", 3.0, "lecture", "chemistry_1"),
        ("普通化學實驗(一)", 1.0, "lab", "chemistry_lab_1"),
        ("微積分(一)", 3.0, "lecture", "calculus_1"),
        ("普通物理學(二)", 3.0, "lecture", "physics_2"),
        ("普通化學(二)", 3.0, "lecture", "chemistry_2"),
        ("普通化學實驗(二)", 1.0, "lab", "chemistry_lab_2"),
        ("微積分(二)", 3.0, "lecture", "calculus_2"),
    ),
}
_APC_PHYSICS_DM_ROWS = {
    "115": (
        ("普通物理學(一)", 3.0, "lecture", "physics_1"),
        ("普通化學(一)", 3.0, "lecture", "chemistry_1"),
        ("普通物理實驗(一)", 1.0, "lab", "physics_lab_1"),
        ("微積分(一)", 3.0, "lecture", "calculus_1"),
        ("普通物理學(二)", 3.0, "lecture", "physics_2"),
        ("普通化學(二)", 3.0, "lecture", "chemistry_2"),
        ("普通物理實驗(二)", 1.0, "lab", "physics_lab_2"),
        ("微積分(二)", 3.0, "lecture", "calculus_2"),
    ),
}
_APC_CHEMISTRY_DM_PAGE = {
    "111": {"pdf_page": 19, "printed_page": 18},
    "112": {"pdf_page": 19, "printed_page": 18},
    "113": {"pdf_page": 24, "printed_page": 23},
    "114": {"pdf_page": 24, "printed_page": 23},
    "115": {"pdf_page": 25, "printed_page": 24},
}
_APC_PHYSICS_DM_PAGE = {
    "111": {"pdf_page": 10, "printed_page": 9},
    "112": {"pdf_page": 10, "printed_page": 9},
    "113": {"pdf_page": 11, "printed_page": 10},
    "114": {"pdf_page": "11–12", "printed_page": "10–11"},
    "115": {"pdf_page": "12–13", "printed_page": "11–12"},
}
_SLUG_ALIASES = {
    "earth": "earth",
    "地生": "earth",
    "earth_environment": "earth_environment",
    "environment": "earth_environment",
    "地球環境": "earth_environment",
    "life_science": "life_science",
    "life": "life_science",
    "生命科學": "life_science",
    "apc": "apc",
    "物化": "apc",
    "physics": "physics",
    "電子物理": "physics",
    "chemistry": "chemistry",
    "應用化學": "chemistry",
    "cs": "cs",
    "資科": "cs",
    "math": "math",
    "數學": "math",
}


def _load_rules() -> dict[str, Any]:
    try:
        with open(_RULES_PATH, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


_RULES = _load_rules()


def _source_file(cohort: str) -> str:
    return "3-理學院.pdf" if cohort == "111" else f"3-理學院 ({cohort}).pdf"


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().replace("（", "(").replace("）", ")")


def _normalize_cohort(value: Any) -> str | None:
    text = _normalize_text(value).replace("學年度", "").replace("學年", "")
    match = re.search(r"(?<!\d)(11[1-5])(?!\d)", text)
    return match.group(1) if match else None


def _program_slug(value: Any) -> str | None:
    text = _normalize_text(value)
    if text in _PROGRAMS:
        return _PROGRAMS[text]
    compact = text.replace(" ", "").replace("　", "")
    if "地球環境" in compact or compact.startswith("地生") or "生命科學" in compact:
        return "earth"
    if "資科" in compact or "資訊科學" in compact:
        return "cs"
    if "數學" in compact:
        return "math"
    if "物化" in compact or "應用化學" in compact or "應用物理" in compact or "電子物理" in compact:
        return "apc"
    alias = _SLUG_ALIASES.get(compact.lower())
    # Track slugs are not programs.  Keeping this distinction here prevents
    # a later default from turning ``chemistry`` into APC physics (or an
    # Earth track into a different primary curriculum).
    return alias if alias in _PROGRAM_SLUGS else None


def _track_slug(value: Any, program: str | None = None) -> str | None:
    text = _normalize_text(value)
    compact = text.replace(" ", "").replace("　", "")
    canonical = compact.lower()
    if canonical in _TRACK_SLUGS:
        candidate = canonical
        if program is None or _TRACK_PROGRAMS[candidate] == program:
            return candidate
        return None
    for slug, aliases in _TRACKS.items():
        if compact in {item.replace(" ", "").replace("　", "") for item in aliases}:
            if program is None or _TRACK_PROGRAMS[slug] == program:
                return slug
            return None
    if "地球環境" in compact:
        candidate = "earth_environment"
        return candidate if program in (None, _TRACK_PROGRAMS[candidate]) else None
    if "生命科學" in compact:
        candidate = "life_science"
        return candidate if program in (None, _TRACK_PROGRAMS[candidate]) else None
    if "物理" in compact or "電子物理" in compact:
        candidate = "physics"
        return candidate if program in (None, _TRACK_PROGRAMS[candidate]) else None
    if "化學" in compact or "應用化學" in compact:
        candidate = "chemistry"
        return candidate if program in (None, _TRACK_PROGRAMS[candidate]) else None
    if program == "earth" and not compact:
        return "earth_environment"
    return None


def _canonical_id(kind: str, cohort: str, program: str, track: str | None = None) -> str:
    if kind == "primary":
        prefix = "primary"
    elif kind in {_MINOR_TARGET_ROLE, "minor", "minor_target"}:
        prefix = "minor"
    else:
        prefix = "target:double_major"
    parts = [prefix, cohort, program]
    if kind in {_MINOR_TARGET_ROLE, "minor", "minor_target"}:
        # Minor scopes are department-level for Earth/CS/Math and track-level
        # only for APC.  ``department`` is part of the stable public ID.
        parts.append(track or "department")
    elif track and ((program == "earth") or (program == "apc")):
        parts.append(track)
    return ":".join(parts)


def _citation(cohort: str, pages: str, label: str, *, url: str | None = None) -> dict[str, str]:
    return {
        "file": _source_file(cohort),
        "pages": pages,
        "label": label,
        "url": url or _HANDBOOK_URLS.get(cohort, ""),
    }


def _apc_target_rows(cohort: str, track: str) -> tuple[tuple[str, float, str, str], ...]:
    if track == "chemistry":
        return _APC_CHEMISTRY_DM_ROWS[cohort]
    if track == "physics":
        return _APC_PHYSICS_DM_ROWS[cohort]
    raise KeyError(f"unsupported APC target track: {track}")


def _apc_target_page(cohort: str, track: str) -> dict[str, Any]:
    pages = _APC_CHEMISTRY_DM_PAGE if track == "chemistry" else _APC_PHYSICS_DM_PAGE
    page = pages[cohort]
    return {
        **page,
        "pages": f"PDF p.{page['pdf_page']}（印刷 p.{page['printed_page']}）",
        "source_reference": f"handbook:{cohort}:pdf:{page['pdf_page']}",
    }


def _apc_chemistry_page(cohort: str) -> dict[str, Any]:
    return _apc_target_page(cohort, "chemistry")


def _apc_chemistry_row_assertion_id(cohort: str, slug: str) -> str:
    return f"apc.dm.{cohort}.chemistry.{slug}"


def _apc_target_catalog_assertions(cohort: str, track: str) -> list[dict[str, Any]]:
    """Return row-level assertions for a readable APC DM page.

    The footer's generic ``其餘必修`` amount is an official aggregate, but the
    page does not provide a complete named course pool in the local evidence.
    Keep that missing semantic as an assertion instead of treating a guessed
    primary catalogue as the target's course list.
    """

    page = _apc_target_page(cohort, track)
    track_label = "電子物理組" if track == "physics" else "應用化學組"
    label = f"{cohort} 學年度物化系{track_label}雙主修表"
    assertions: list[dict[str, Any]] = []
    for name, credits, _component, slug in _apc_target_rows(cohort, track):
        assertions.append(
            _assertion(
                f"apc.dm.{cohort}.{track}.{slug}",
                cohort,
                page["pages"],
                f"雙主修列項：{name}",
                credits,
                label=label,
            )
        )
    other_credits = 20 if cohort == "115" else 24
    other_claim = (
        "表尾必修課程應修畢（語義待確認）"
        if cohort in {"111", "112"} and track == "chemistry"
        else "表尾其餘必修課程應修畢"
    )
    other_evidence = CONFLICTED if cohort in {"111", "112"} and track == "chemistry" else VERIFIED
    assertions.append(
        _assertion(
            f"apc.dm.{cohort}.{track}.other_catalog",
            cohort,
            page["pages"],
            "其餘必修課程完整命名與選擇規則",
            "not_transcribed",
            evidence_state=MISSING,
            label=label,
        )
    )
    # Keep the aggregate amount available as an independent official claim;
    # this assertion is also used by the quota row provenance below.
    assertions.append(
        _assertion(
            f"apc.dm.{cohort}.other{other_credits}",
            cohort,
            page["pages"],
            other_claim,
            other_credits,
            evidence_state=other_evidence,
            label=label,
        )
    )
    return assertions


def _apc_chemistry_catalog_assertions(cohort: str) -> list[dict[str, Any]]:
    return _apc_target_catalog_assertions(cohort, "chemistry")


def _apc_target_catalog(cohort: str, track: str) -> list[dict[str, Any]]:
    """Build exact visible APC double-major rows for one cohort/track.

        This intentionally returns the eight named rows plus one generic footer
    quota.  The quota is not expanded with 115 primary/track courses because
    that would be a false claim about the target page's missing choice pool.
    """

    page = _apc_target_page(cohort, track)
    track_label = "電子物理組" if track == "physics" else "應用化學組"
    source = _citation(cohort, page["pages"], f"物化系{track_label}雙主修課程表")
    rows: list[dict[str, Any]] = []
    for name, credits, component, slug in _apc_target_rows(cohort, track):
        requirement_id = f"apc.dm.{cohort}.{track}.{slug}"
        source_reference = f"{page['source_reference']}:row:{slug}"
        original_clause = f"{track_label}雙主修列項：{name} {credits:g} 學分。"
        provenance = {
            "assertion_id": requirement_id,
            "source_type": "official_handbook",
            "source_file": source["file"],
            "source_url": source["url"],
            "research_file": "research/apc_cs_handbook_matrix_111_115.md",
            "pdf_page": page["pdf_page"],
            "printed_page": page["printed_page"],
            "source_reference": source_reference,
            "table_location": source["label"],
            "raw_title": name,
            "claim": original_clause,
            "original_clause": original_clause,
            "evidence_state": VERIFIED,
            "verification_status": VERIFIED,
            "coverage_state": PARTIAL,
            "automation_sufficiency": PARTIAL,
            "automatic_decision": False,
            "manual_reason": "雙主修其餘必修完整命名課程池與個案核准仍需人工確認。",
            "manual_review_reason": "雙主修其餘必修完整命名課程池與個案核准仍需人工確認。",
            "extraction_method": "handbook_text_and_visual_crosscheck",
        }
        rows.append(
            {
                "id": requirement_id,
                "requirement_id": requirement_id,
                "name": name,
                "raw_title": name,
                "credits": float(credits),
                "bucket": "base",
                "kind": "course",
                "requirement_type": "named_course",
                "choice_group": None,
                "choice_rule": "exact_course_or_approved_equivalency",
                "track": track,
                "track_slug": track,
                "track_name": track_label,
                "cohort": cohort,
                "curriculum_version": cohort,
                "component": component,
                "component_type": component,
                "component_label": "講授" if component == "lecture" else "實驗",
                "lecture_or_lab": component,
                "is_lab": component == "lab",
                "is_zero_credit": False,
                "allow_combined_lab_source": False,
                "evidence": VERIFIED,
                "evidence_state": VERIFIED,
                "assertion_id": requirement_id,
                "source_assertion_id": requirement_id,
                "source_reference": source_reference,
                "source_url": source["url"],
                "source_file": source["file"],
                "pdf_page": page["pdf_page"],
                "printed_page": page["printed_page"],
                "page": page["pdf_page"],
                "pages": page["pages"],
                "source": deepcopy(source),
                "provenance": provenance,
                "official_course_identity": f"{cohort}:apc:{track}:{slug}",
                "research_file": "research/apc_cs_handbook_matrix_111_115.md",
                "table_location": source["label"],
                "original_clause": original_clause,
                "original_text": original_clause,
                "verification_status": VERIFIED,
                "coverage_state": PARTIAL,
                "automation_sufficiency": PARTIAL,
                "automatic_decision": False,
                "manual_reason": "雙主修其餘必修完整命名課程池與個案核准仍需人工確認。",
                "manual_review_reason": "雙主修其餘必修完整命名課程池與個案核准仍需人工確認。",
            }
        )

    other_credits = 20.0 if cohort == "115" else 24.0
    quota_slug = "other_required"
    quota_requirement_id = f"apc.dm.{cohort}.{track}.{quota_slug}"
    quota_assertion_id = f"apc.dm.{cohort}.{track}.other{int(other_credits)}"
    quota_reference = f"{page['source_reference']}:footer:{quota_slug}"
    quota_is_conflicted = cohort in {"111", "112"} and track == "chemistry"
    quota_title = "必修課程（語義待確認）" if quota_is_conflicted else "其餘必修課程"
    quota_original_clause = f"{track_label}雙主修表尾：{quota_title} {int(other_credits)} 學分。"
    quota_evidence = CONFLICTED if quota_is_conflicted else VERIFIED
    quota_manual_reason = (
        "可見 16 學分與表尾必修 24 學分的語義衝突，不能自動解讀為其餘必修。"
        if quota_is_conflicted
        else "官方頁面未在本地證據中提供其餘必修的完整命名課程池。"
    )
    quota_provenance = {
        "assertion_id": quota_assertion_id,
        "source_type": "official_handbook",
        "source_file": source["file"],
        "source_url": source["url"],
        "research_file": "research/apc_cs_handbook_matrix_111_115.md",
        "pdf_page": page["pdf_page"],
        "printed_page": page["printed_page"],
        "source_reference": quota_reference,
        "table_location": source["label"],
        "raw_title": "其餘必修課程",
        "claim": quota_original_clause,
        "original_clause": quota_original_clause,
        "evidence_state": quota_evidence,
        "verification_status": quota_evidence,
        "coverage_state": PARTIAL,
        "automation_sufficiency": PARTIAL,
        "automatic_decision": False,
        "manual_reason": quota_manual_reason,
        "manual_review_reason": quota_manual_reason,
        "extraction_method": "handbook_text_and_visual_crosscheck",
        "named_course_pool": "not_transcribed",
    }
    rows.append(
        {
            "id": quota_requirement_id,
            "requirement_id": quota_requirement_id,
            "name": quota_title,
            "display_name": f"{track_label}{quota_title}",
            "raw_title": quota_title,
            "credits": other_credits,
            "bucket": "other_required",
            "kind": "quota",
            "requirement_type": "credit_quota",
            "choice_group": "other_required_pool",
            "choice_rule": "department_approved_named_course_pool",
            "track": track,
            "track_slug": track,
            "track_name": track_label,
            "cohort": cohort,
            "curriculum_version": cohort,
            "component": "quota",
            "component_type": "quota",
            "component_label": "其餘必修額度",
            "lecture_or_lab": "quota",
            "is_lab": False,
            "is_zero_credit": False,
            "allow_combined_lab_source": False,
            "evidence": quota_evidence,
            "evidence_state": quota_evidence,
            "assertion_id": quota_assertion_id,
            "source_assertion_id": quota_assertion_id,
            "source_reference": quota_reference,
            "source_url": source["url"],
            "source_file": source["file"],
            "pdf_page": page["pdf_page"],
            "printed_page": page["printed_page"],
            "page": page["pdf_page"],
            "pages": page["pages"],
            "source": deepcopy(source),
            "provenance": quota_provenance,
            "official_course_identity": f"{cohort}:apc:{track}:{quota_slug}",
            "catalog": [],
            "named_course_pool_state": PARTIAL,
            "research_file": "research/apc_cs_handbook_matrix_111_115.md",
            "table_location": source["label"],
            "original_clause": quota_original_clause,
            "original_text": quota_original_clause,
            "verification_status": quota_evidence,
            "coverage_state": PARTIAL,
            "automation_sufficiency": PARTIAL,
            "automatic_decision": False,
            "manual_reason": quota_manual_reason,
            "manual_review_reason": quota_manual_reason,
            "missing_semantics": [
                "官方頁面未在本地證據中提供可執行的其餘必修完整課名清單。",
                "其餘必修的選擇規則與系所核准條件仍需人工確認。",
            ],
        }
    )
    return rows


def _apc_chemistry_catalog(cohort: str) -> list[dict[str, Any]]:
    return _apc_target_catalog(cohort, "chemistry")


def _assertion(
    assertion_id: str,
    cohort: str,
    pages: str,
    claim: str,
    value: Any,
    *,
    evidence_state: str = VERIFIED,
    label: str = "學生手冊",
    url: str | None = None,
    pdf_page: str | None = None,
    printed_page: str | None = None,
    original_clause: str | None = None,
    source_reference: str | None = None,
    automatic_decision: bool | None = None,
    manual_reason: str | None = None,
    coverage_state: str | None = None,
    conflict_group: str | None = None,
) -> dict[str, Any]:
    source = _citation(cohort, pages, label, url=url)
    resolved_pdf_page = str(pdf_page or pages).strip()
    resolved_printed_page = str(printed_page or "未標示").strip()
    resolved_coverage = coverage_state or (COMPLETE if evidence_state == VERIFIED else PARTIAL)
    resolved_automatic = (
        automatic_decision
        if automatic_decision is not None
        else evidence_state == VERIFIED and resolved_coverage == COMPLETE
    )
    resolved_manual_reason = manual_reason or (
        "官方證據不足或衝突，需人工確認。" if not resolved_automatic else ""
    )
    resolved_original_clause = original_clause or claim
    resolved_reference = source_reference or f"handbook:{cohort}:pdf:{resolved_pdf_page}:assertion:{assertion_id}"
    source.update(
        {
            "curriculum_version": cohort,
            "pdf_page": resolved_pdf_page,
            "printed_page": resolved_printed_page,
            "source_reference": resolved_reference,
            "original_clause": resolved_original_clause,
            "verification_status": evidence_state,
            "coverage_state": resolved_coverage,
            "automation_sufficiency": "COMPLETE" if resolved_automatic else "PARTIAL" if evidence_state == VERIFIED else "NONE",
            "automatic_decision": resolved_automatic,
            "manual_reason": resolved_manual_reason,
        }
    )
    if conflict_group:
        source["conflict_group"] = conflict_group
    return {
        "id": assertion_id,
        "assertion_id": assertion_id,
        "claim": claim,
        "value": value,
        "evidence_state": evidence_state,
        "source": source,
        # Flat copies make the evidence easy to consume in CSV/JSON exports.
        "source_url": source["url"],
        "source_file": source["file"],
        "pages": pages,
        "page": pages,
        "pdf_page": resolved_pdf_page,
        "printed_page": resolved_printed_page,
        "table_location": label,
        "source_reference": resolved_reference,
        "original_clause": resolved_original_clause,
        "original_text": resolved_original_clause,
        "curriculum_version": cohort,
        "conflict_group": conflict_group,
        "verification_status": evidence_state,
        "coverage_state": resolved_coverage,
        "automation_sufficiency": "COMPLETE" if resolved_automatic else "PARTIAL" if evidence_state == VERIFIED else "NONE",
        "automatic_decision": resolved_automatic,
        "manual_reason": resolved_manual_reason,
        "manual_review_reason": resolved_manual_reason,
    }


def _base_thresholds(program: str, cohort: str, track: str | None) -> dict[str, Any]:
    """Return independently transcribed aggregate thresholds."""

    if program == "earth":
        domain_elective = 22 if cohort == "111" else 20
        return {
            "total": 128,
            "university_common": 28,
            "major_total": 85,
            "major_common": 24,
            "domain_required": 14,
            "domain_elective": domain_elective,
            "other_elective": 13 if cohort == "111" else 27,
            "free": 15,
        }
    if program == "apc":
        is_chemistry = track == "chemistry"
        if cohort == "115":
            return {"total": 128, "university_common": 28, "major_common": 18, "track_required": 42, "elective": 25, "free": 15}
        return {
            "total": 128,
            "university_common": 28,
            "major_common": 16,
            "track_required": 45 if is_chemistry else 44,
            "elective": 24 if is_chemistry else 25,
            "free": 15,
        }
    if program == "cs":
        return {
            "total": 128,
            "university_common": 28,
            "department_required": 31,
            "department_elective": 54,
            "free": 15,
            "common_split": {"compulsory": 10, "category": 16, "elective": 2},
        }
    if cohort in {"111", "112"}:
        return {"total": 128, "university_common": 28, "program_common": 36, "program_elective": 64, "free": 15}
    if cohort == "115":
        return {"total": 128, "university_common": 28, "program_common": 20, "domain_required": 7, "program_elective": 65, "free": 15}
    return {"total": 128, "university_common": 28, "program_common": 20, "domain_required": 7, "program_elective": 65, "free": 15}


def _double_thresholds(program: str, cohort: str, track: str | None) -> dict[str, Any]:
    """Return the separate 40-credit double-major aggregate schema.

    These values describe the target curriculum only.  They intentionally do
    not inherit the primary 128-credit graduation thresholds.  For the
    Math 111/112 and APC chemistry 111/112 conflicts, the visible bucket
    values are retained as evidence while the registry keeps the official
    total independently.
    """

    if program == "earth":
        base, other = 24, 16
    elif program == "cs":
        base, other = 15, 25
    elif program == "math":
        if cohort in {"111", "112"}:
            base, other = 21, 18
        else:
            base, other = 14, 26
    elif cohort == "115":
        base, other = 20, 20
    else:
        base, other = 16, 24
    return {
        "schema": "double_major_40",
        "total": 40,
        "total_required": 40,
        "base": base,
        "other": other,
        "base_required": base,
        "other_required": other,
    }


def _primary_conflict_assertions(program: str, cohort: str) -> list[dict[str, Any]]:
    if program == "math" and cohort == "114":
        return [
            _assertion("math.primary.114.common20", cohort, "PDF p.67", "系共同必修架構", 20, label="數學系課程架構"),
            _assertion("math.primary.114.detail36", cohort, "PDF p.70", "必修科目表總額", 36, label="數學系必修科目表"),
        ]
    if program == "cs" and cohort == "114":
        conflict_group = "cs.primary.114.common-course-split"
        manual_reason = "官方 114 手冊同一共同課程分配同時有兩個可加總為 28 的版本，不能自動選定其中一個。"
        return [
            _assertion(
                "cs.primary.114.split10-16-2",
                cohort,
                "PDF p.108",
                "共同課程分配",
                "10/16/2",
                label="資科系學分規劃表",
                pdf_page="108",
                printed_page="107",
                original_clause="共同課程分配：10／16／2。",
                automatic_decision=False,
                manual_reason=manual_reason,
                coverage_state=PARTIAL,
                conflict_group=conflict_group,
            ),
            _assertion(
                "cs.primary.114.split8-16-4",
                cohort,
                "PDF p.110",
                "共同課程分配",
                "8/16/4",
                label="資科系課程說明",
                pdf_page="110",
                printed_page="109",
                original_clause="共同課程分配：8／16／4。",
                automatic_decision=False,
                manual_reason=manual_reason,
                coverage_state=PARTIAL,
                conflict_group=conflict_group,
            ),
        ]
    if program == "cs" and cohort == "115":
        return [
            _assertion("cs.primary.115.diagram15", cohort, "PDF p.118", "學校共同課程下限", "at-least-15", label="資科系課程架構圖"),
            _assertion("cs.primary.115.table28", cohort, "PDF p.119", "校共同課程總額", 28, label="資科系學分規劃表"),
        ]
    return []


def _primary_assertions(program: str, cohort: str, track: str | None) -> list[dict[str, Any]]:
    pages = {
        "earth": {"111": "PDF p.26", "112": "PDF p.26", "113": "PDF p.31", "114": "PDF p.32", "115": "PDF p.40"},
        "apc": {"111": "PDF p.3", "112": "PDF p.3", "113": "PDF p.3", "114": "PDF p.3", "115": "PDF p.3"},
        "math": {"111": "PDF p.67", "112": "PDF p.62", "113": "PDF p.67", "114": "PDF p.67", "115": "PDF p.78"},
        "cs": {"111": "PDF p.113", "112": "PDF p.108", "113": "PDF p.103", "114": "PDF p.108", "115": "PDF p.119"},
    }
    assertions = [
        _assertion(
            f"{program}.primary.{cohort}.total",
            cohort,
            pages[program][cohort],
            "主修總畢業學分",
            128,
            label=f"{cohort} 學年度{_PROGRAM_DISPLAY[program]}主修門檻",
        )
    ]
    assertions.extend(_primary_conflict_assertions(program, cohort))
    return assertions


def _double_assertions(program: str, cohort: str, track: str | None) -> tuple[list[dict[str, Any]], str, str, str]:
    """Return assertions, evidence state, coverage and warning for a target."""

    if program == "math" and cohort in {"111", "112"}:
        pages = "PDF pp.80–82" if cohort == "111" else "PDF pp.75–77"
        assertions = [
            _assertion(f"math.dm.{cohort}.total40", cohort, pages, "雙主修總額", 40, label="數學系雙主修表"),
            _assertion(f"math.dm.{cohort}.required21", cohort, pages, "雙主修必修列項合計", 21, label="數學系雙主修表"),
            _assertion(f"math.dm.{cohort}.elective18", cohort, pages, "雙主修選修下限", 18, label="數學系雙主修表"),
        ]
        return assertions, CONFLICTED, PARTIAL, "總額40與必修21＋選修至少18的分項無法安全相加。"
    if program == "math" and cohort == "113":
        pages = "PDF pp.77–79"
        assertions = [
            _assertion("math.dm.113.header14", cohort, pages, "雙主修表頭必修", 14, label="數學系雙主修表"),
            _assertion("math.dm.113.visible21", cohort, pages, "雙主修可見必修列項合計", 21, label="數學系雙主修表"),
            _assertion("math.dm.113.elective26", cohort, pages, "雙主修選修下限", 26, label="數學系雙主修表"),
        ]
        return assertions, CONFLICTED, PARTIAL, "表頭必修14與可見必修列項21衝突；選修下限26亦不能替代表頭。"
    if program == "math" and cohort in {"114", "115"}:
        pages = "PDF pp.80–82" if cohort == "114" else "PDF pp.91–93"
        assertions = [
            _assertion(f"math.dm.{cohort}.total40", cohort, pages, "雙主修總額", 40, label="數學系雙主修表"),
            _assertion(f"math.dm.{cohort}.required14", cohort, pages, "雙主修必修", 14, label="數學系雙主修表"),
            _assertion(f"math.dm.{cohort}.elective26", cohort, pages, "雙主修選修下限", 26, label="數學系雙主修表"),
        ]
        return assertions, VERIFIED, PARTIAL, "aggregate 14＋至少26 可核對，但逐課目錄尚未完整建置，需人工複核。"
    if program == "apc" and track == "chemistry" and cohort in {"111", "112"}:
        pages = "PDF p.19"
        assertions = [
            _assertion(f"apc.dm.{cohort}.visible16", cohort, pages, "應用化學雙主修可見基礎列項", 16, label="物化系雙主修表"),
            _assertion(f"apc.dm.{cohort}.footer24", cohort, pages, "表尾必修課程應修", 24, label="物化系雙主修表"),
            _assertion(f"apc.dm.{cohort}.footer-semantics", cohort, pages, "表尾是否為其餘必修", "unknown", evidence_state=MISSING, label="物化系雙主修表"),
        ]
        row_assertions = _apc_target_catalog_assertions(cohort, track)
        existing_ids = {item["id"] for item in assertions}
        assertions.extend(item for item in row_assertions if item["id"] not in existing_ids)
        return assertions, CONFLICTED, PARTIAL, "可見16學分與表尾必修24的語義不明，不能擅自解讀為其餘必修。"
    if program == "cs" and cohort == "115":
        pages = "PDF p.127"
        assertions = [
            _assertion("cs.dm.115.aggregate15", cohort, pages, "雙主修必修 aggregate", 15, label="資科系雙主修表"),
            _assertion("cs.dm.115.aggregate25", cohort, pages, "雙主修其他課程 aggregate", 25, label="資科系雙主修表"),
            _assertion("cs.dm.115.visible-named", cohort, pages, "可見命名基礎課列項", "incomplete", evidence_state=MISSING, label="資科系雙主修表"),
        ]
        return assertions, VERIFIED, PARTIAL, "aggregate 15＋25 可核對，但命名基礎課程表不完整，需人工核對。"
    if program == "earth":
        pages = {"111": "PDF p.39", "112": "PDF p.39", "113": "PDF p.45", "114": "PDF p.47", "115": "PDF p.55"}[cohort]
        assertions = [
            _assertion(f"earth.dm.{cohort}.total40", cohort, pages, "地生雙主修總額", 40, label="地生系雙主修表"),
            _assertion(f"earth.dm.{cohort}.base24", cohort, pages, "共同必修", 24, label="地生系雙主修表"),
            _assertion(f"earth.dm.{cohort}.other16", cohort, pages, "專業選修", 16, label="地生系雙主修表"),
        ]
        return assertions, VERIFIED, PARTIAL, "雙主修頁只有 aggregate 結構，未提供可安全逐課配置的完整目錄。"
    if program == "apc":
        page_map = _APC_PHYSICS_DM_PAGE if track == "physics" else _APC_CHEMISTRY_DM_PAGE
        page = page_map[cohort]
        pages = f"PDF p.{page['pdf_page']}"
        track_label = "電子物理組" if track == "physics" else "應用化學組"
        if cohort == "115":
            base, other = 20, 20
        else:
            base, other = 16, 24
        assertions = [
            _assertion(f"apc.dm.{cohort}.base{base}", cohort, pages, "物化雙主修基礎列項", base, label=f"物化系{track_label}雙主修表"),
            _assertion(f"apc.dm.{cohort}.other{other}", cohort, pages, "物化雙主修其餘必修", other, label=f"物化系{track_label}雙主修表"),
        ]
        if track == "chemistry" or (track == "physics" and cohort == "115"):
            # Preserve the aggregate assertions above while exposing the
            # exact visible target rows and the missing named-pool semantic.
            # The returned evidence state stays VERIFIED because the official
            # claims are readable; coverage remains PARTIAL below.
            row_assertions = _apc_target_catalog_assertions(cohort, track)
            existing_ids = {item["id"] for item in assertions}
            assertions.extend(item for item in row_assertions if item["id"] not in existing_ids)
            track_label = "電子物理組" if track == "physics" else "應用化學組"
            warning = (
                f"可見八項（含微積分(一)、微積分(二)）與其餘必修20 aggregate 已核對；{track_label}官方其餘必修完整命名目錄與選擇規則尚未轉錄，"
                "coverage=PARTIAL，需人工複核。"
                if cohort == "115"
                else f"可見八項與其餘必修24 aggregate 已核對；{track_label}官方其餘必修完整命名目錄與選擇規則尚未轉錄，coverage=PARTIAL，需人工複核。"
            )
            return assertions, VERIFIED, PARTIAL, warning
        return assertions, VERIFIED, PARTIAL, "雙主修 aggregate 可核對，但逐課目錄尚未完整建置。"
    # CS 111–114 have readable aggregate rows, but only the older configured
    # rule table can be used for exact names.  Keep the evidence independent.
    pages = {"111": "PDF pp.121–122", "112": "PDF pp.116–117", "113": "PDF pp.111–112", "114": "PDF pp.116–117", "115": "PDF p.127"}[cohort]
    assertions = [
        _assertion(f"cs.dm.{cohort}.required15", cohort, pages, "資科雙主修必修", 15, label="資科系雙主修表"),
        _assertion(f"cs.dm.{cohort}.other25", cohort, pages, "資科雙主修其他課程", 25, label="資科系雙主修表"),
    ]
    return assertions, VERIFIED, PARTIAL, "aggregate 15＋25 可核對，但 required/other 與申請核准語義尚未完整建置。"


def _primary_evidence(cohort: str, program: str) -> dict[str, Any]:
    """Return the source contract for a primary handbook section.

    New 111/115 records carry section-level evidence in ``rules_config.json``;
    older records receive conservative legacy defaults.  A missing section
    never inherits a neighbouring cohort's citation or course rows.
    """

    handbook = _RULES.get("handbooks", {}).get(cohort, {})
    meta = handbook.get("_meta", {}) if isinstance(handbook, dict) else {}
    section_key = {
        "earth": "earth_life_major",
        "apc": "apc_rules",
        "math": "math_rules",
        "cs": "cs_rules",
    }[program]
    section = handbook.get(section_key, {}) if isinstance(handbook, dict) else {}
    evidence = section.get("evidence", {}) if isinstance(section, dict) else {}
    if not isinstance(evidence, dict):
        evidence = {}
    pages = meta.get("source_pages", {}).get(
        "earth_life" if program == "earth" else program,
        "官方學生手冊",
    )
    source_url = evidence.get("source_url") or meta.get("source_url") or _HANDBOOK_URLS.get(cohort, "")
    return {
        "curriculum_version": cohort,
        "research_file": evidence.get("research_file", "research/math_earth_handbook_matrix_111_115.md" if program in {"earth", "math"} else "research/apc_cs_handbook_matrix_111_115.md"),
        "source_reference": evidence.get("source_reference", f"handbook:{cohort}:primary:{program}"),
        "source_url": source_url,
        "source_file": meta.get("source_file", _source_file(cohort)),
        "pdf_page": evidence.get("pdf_page", pages),
        "printed_page": evidence.get("printed_page", "未標示"),
        "pages": pages,
        "table_location": evidence.get("table_location", f"{_PROGRAM_DISPLAY[program]} 主修課程表"),
        "evidence_state": evidence.get("evidence_state", meta.get("evidence_state", VERIFIED)),
        "coverage_state": evidence.get("coverage_state", meta.get("coverage_state", PARTIAL)),
        "automation_sufficiency": evidence.get("automation_sufficiency", meta.get("automation_sufficiency", PARTIAL)),
        "original_clause": evidence.get("original_clause", ""),
        "manual_reason": evidence.get("manual_review_reason", meta.get("manual_review_reason", "")),
    }


def _primary_course_row(
    cohort: str,
    program: str,
    track: str | None,
    name: str,
    credits: int | float,
    bucket: str,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one auditable primary course row from a source-backed map."""

    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", str(name)).strip("_").lower() or "course"
    track_slug = track or "department"
    row_id = f"{program}.primary.{cohort}.{track_slug}.{slug}"
    component = "lab" if "實驗" in str(name) else "lecture"
    source_reference = f"{source['source_reference']}:row:{slug}"
    original_clause = source.get("original_clause") or f"{name} {float(credits):g} 學分。"
    evidence_state = source.get("evidence_state", VERIFIED)
    row_automatic = evidence_state == VERIFIED and source.get("automation_sufficiency") == "COMPLETE"
    provenance = {
        "assertion_id": row_id,
        "source_type": "official_handbook",
        "research_file": source["research_file"],
        "source_url": source["source_url"],
        "source_file": source["source_file"],
        "pdf_page": source["pdf_page"],
        "printed_page": source["printed_page"],
        "pages": source["pages"],
        "table_location": source["table_location"],
        "source_reference": source_reference,
        "raw_title": name,
        "original_clause": original_clause,
        "evidence_state": evidence_state,
        "verification_status": evidence_state,
        "automation_sufficiency": source.get("automation_sufficiency", PARTIAL),
        "automatic_decision": row_automatic,
        "manual_reason": source.get("manual_reason", ""),
        "manual_review_reason": source.get("manual_reason", ""),
    }
    return {
        "id": row_id,
        "requirement_id": row_id,
        "name": name,
        "raw_title": name,
        "credits": float(credits),
        "bucket": bucket,
        "kind": "PRIMARY_COURSE",
        "requirement_type": "named_course",
        "choice_group": None,
        "choice_rule": "exact_course_or_approved_equivalency",
        "track": _TRACK_DISPLAY.get(track) if track else None,
        "track_slug": track_slug,
        "eligible_course_names": (name,),
        "eligible_course_options": ({"name": name, "credits": float(credits)},),
        "waiver": False,
        "waiver_generates_credits": False,
        "component": component,
        "component_type": component,
        "component_label": "實驗" if component == "lab" else "講授",
        "lecture_or_lab": component,
        "is_lab": component == "lab",
        "is_zero_credit": float(credits) == 0,
        "allow_combined_lab_source": False,
        "evidence": evidence_state,
        "evidence_state": evidence_state,
        "coverage_state": source.get("coverage_state", PARTIAL),
        "verification_status": evidence_state,
        "automation_sufficiency": source.get("automation_sufficiency", PARTIAL),
        "automatic_decision": row_automatic,
        "manual_reason": source.get("manual_reason", ""),
        "manual_review_reason": source.get("manual_reason", ""),
        "program_slug": program,
        "curriculum_version": cohort,
        "cohort": cohort,
        "source_assertion_id": row_id,
        "assertion_id": row_id,
        "source_reference": source_reference,
        "source_url": source["source_url"],
        "source_file": source["source_file"],
        "research_file": source["research_file"],
        "pdf_page": source["pdf_page"],
        "printed_page": source["printed_page"],
        "page": source["pdf_page"],
        "pages": source["pages"],
        "table_location": source["table_location"],
        "original_clause": original_clause,
        "original_text": original_clause,
        "provenance": provenance,
        "official_course_identity": f"{cohort}:{program}:{track_slug}:{slug}",
    }


def _cs_target_quota_catalog(cohort: str) -> list[dict[str, Any]]:
    """Expose only the official CS double-major aggregates as generic rows."""

    pages = {
        "111": ("121", "120"),
        "112": ("116", "115"),
        "113": ("111", "110"),
        "114": ("116", "115"),
        "115": ("127", "126"),
    }
    pdf_page, printed_page = pages[cohort]
    label = f"{cohort} 學年度資科系雙主修 aggregate 表"
    source = _citation(cohort, f"PDF p.{pdf_page}（印刷 p.{printed_page}）", label)
    rows: list[dict[str, Any]] = []
    for slug, name, credits, clause in (
        ("required15", "資科雙主修命名必修 aggregate", 15.0, "資科雙主修必修 15 學分。"),
        ("other25", "資科雙主修其他課程 aggregate", 25.0, "資科雙主修其他課程 25 學分。"),
    ):
        requirement_id = f"cs.dm.{cohort}.{slug}"
        source_reference = f"handbook:{cohort}:pdf:{pdf_page}:row:{slug}"
        manual_reason = "官方只核對到 aggregate 額度，命名課程池與個案核准仍需人工確認。"
        row_source = {
            **deepcopy(source),
            "curriculum_version": cohort,
            "pdf_page": pdf_page,
            "printed_page": printed_page,
            "source_reference": source_reference,
            "original_clause": clause,
            "verification_status": VERIFIED,
            "coverage_state": PARTIAL,
            "automation_sufficiency": PARTIAL,
            "automatic_decision": False,
            "manual_reason": manual_reason,
        }
        provenance = {
            "assertion_id": requirement_id,
            "source_type": "official_handbook",
            "research_file": "research/apc_cs_handbook_matrix_111_115.md",
            "source_url": source["url"],
            "source_file": source["file"],
            "pdf_page": pdf_page,
            "printed_page": printed_page,
            "pages": source["pages"],
            "source_reference": source_reference,
            "table_location": label,
            "original_clause": clause,
            "evidence_state": VERIFIED,
            "verification_status": VERIFIED,
            "coverage_state": PARTIAL,
            "automation_sufficiency": PARTIAL,
            "automatic_decision": False,
            "manual_reason": manual_reason,
            "manual_review_reason": manual_reason,
        }
        rows.append(
            {
                "id": requirement_id,
                "requirement_id": requirement_id,
                "name": name,
                "display_name": name,
                "raw_title": name,
                "credits": credits,
                "bucket": "required" if slug == "required15" else "other_required",
                "kind": "quota",
                "requirement_type": "credit_quota",
                "choice_group": "cs_double_major_aggregate",
                "choice_rule": "official_aggregate_only",
                "track": None,
                "track_slug": "department",
                "cohort": cohort,
                "curriculum_version": cohort,
                "component": "quota",
                "component_type": "quota",
                "component_label": "aggregate 額度",
                "lecture_or_lab": "quota",
                "is_lab": False,
                "is_zero_credit": False,
                "allow_combined_lab_source": False,
                "eligible_course_names": (),
                "eligible_course_options": (),
                "accept_any": False,
                "waiver": False,
                "waiver_generates_credits": False,
                "evidence": VERIFIED,
                "evidence_state": VERIFIED,
                "verification_status": VERIFIED,
                "coverage_state": PARTIAL,
                "automation_sufficiency": PARTIAL,
                "automatic_decision": False,
                "manual_reason": manual_reason,
                "manual_review_reason": manual_reason,
                "assertion_id": requirement_id,
                "source_assertion_id": requirement_id,
                "source_reference": source_reference,
                "source_url": source["url"],
                "source_file": source["file"],
                "research_file": "research/apc_cs_handbook_matrix_111_115.md",
                "pdf_page": pdf_page,
                "printed_page": printed_page,
                "page": pdf_page,
                "pages": source["pages"],
                "table_location": label,
                "original_clause": clause,
                "original_text": clause,
                "source": row_source,
                "provenance": provenance,
                "official_course_identity": f"{cohort}:cs:double_major:{slug}",
                "catalog": [],
                "named_course_pool_state": PARTIAL,
            }
        )
    return rows


def _course_catalog(program: str, cohort: str, kind: str, track: str | None, coverage: str) -> list[dict[str, Any]]:
    """Build source-scoped catalogs without silently borrowing another year."""

    if coverage == COVERAGE_NONE:
        return []
    if kind == "double_major_target" and program == "apc" and (
        track == "chemistry" or (track == "physics" and cohort == "115")
    ):
        # This is an intentionally partial but exact transcription: eight
        # visible named rows plus the official footer quota.  Do not populate
        # the quota from a primary/legacy catalogue that the target page does
        # not identify as its complete choice pool.
        return _apc_target_catalog(cohort, track)
    if kind == "double_major_target" and program == "cs":
        # The checked-in evidence proves only the CS target aggregates
        # (15 named-core credits + 25 other credits).  The department course
        # catalogue is a candidate list, not proof that each row is required
        # by the selected target handbook.  Keep only generic quota rows;
        # these have no eligible course names and remain review-gated.
        return _cs_target_quota_catalog(cohort)
    if kind == "double_major_target":
        return []
    handbook = _RULES.get("handbooks", {}).get(cohort, {})
    if not isinstance(handbook, dict):
        return []
    source = _primary_evidence(cohort, program)
    rows: list[dict[str, Any]] = []
    if program == "earth":
        major = handbook.get("earth_life_major", {})
        for section, data in (("common", major.get("common_compulsory", {})), ("domains", major.get("domains", {}))):
            if section == "common":
                data = data.get("courses", {}) if isinstance(data, dict) else {}
                for name, credits in data.items():
                    rows.append(_primary_course_row(cohort, program, track, name, credits, "common_compulsory", source))
            elif isinstance(data, dict):
                for domain, domain_data in data.items():
                    for name, credits in (domain_data.get("compulsory", {}) if isinstance(domain_data, dict) else {}).items():
                        rows.append(_primary_course_row(cohort, program, track, name, credits, f"{domain}:compulsory", source))
            if section == "common":
                for alternative in major.get("common_alternatives", []):
                    options = alternative.get("options", {}) if isinstance(alternative, dict) else {}
                    for name, credits in options.items():
                        rows.append(_primary_course_row(cohort, program, track, name, credits, "common_alternative", source))
    elif program == "apc":
        apc = handbook.get("apc_rules", {})
        seen: set[str] = set()
        for name, credits in apc.get("basic_core", {}).items():
            seen.add(name)
            rows.append(_primary_course_row(cohort, program, track, name, credits, "apc_common", source))
        for name, credits in apc.get("shared_other_required", {}).items():
            if name not in seen:
                seen.add(name)
                rows.append(_primary_course_row(cohort, program, track, name, credits, "apc_common", source))
        division = apc.get("divisions", {}).get(
            "物理組" if track == "physics" else "化學組" if track == "chemistry" else "",
            {},
        )
        for name, credits in division.get("compulsory", {}).items() if isinstance(division, dict) else ():
            if name not in seen:
                rows.append(_primary_course_row(cohort, program, track, name, credits, "apc_track_compulsory", source))
    elif program == "cs":
        cs = handbook.get("cs_rules", {})
        data = cs.get("department_courses", {}) if isinstance(cs, dict) else {}
        double_major = cs.get("double_major", {}) if isinstance(cs, dict) else {}
        required_names = set(double_major.get("compulsory", {})) if isinstance(double_major, dict) else set()
        for name, credits in data.items():
            bucket = "double_major_required" if kind == "double_major_target" and name in required_names else "department"
            rows.append(_primary_course_row(cohort, program, track, name, credits, bucket, source))
    elif program == "math":
        math_rules = handbook.get("math_rules", {})
        seen: set[str] = set()
        for name, credits in math_rules.get("common_compulsory", {}).items():
            seen.add(name)
            rows.append(_primary_course_row(cohort, program, track, name, credits, "math_common_compulsory", source))
        for domain, domain_data in math_rules.get("domains", {}).items():
            required = domain_data.get("required", {}) if isinstance(domain_data, dict) else {}
            for name, credits in required.items():
                if name not in seen:
                    seen.add(name)
                    rows.append(_primary_course_row(cohort, program, track, name, credits, f"{domain}:required", source))
    if coverage == PARTIAL:
        return rows[: min(len(rows), 8)]
    return rows


def _minor_catalog(cohort: str, program: str, track: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the exact minor rows transcribed in the research matrix.

    The matrix intentionally does not provide official course codes.  Rows
    therefore expose names/components as candidate evidence only; the
    service can formalize a route only after a confirmed transcript identity
    or an explicit equivalency record is supplied.
    """

    rows: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {
        "manual_review_reasons": [],
        "conflicted_course_names": (),
        "zero_credit_gate": False,
    }
    if program == "apc":
        base_rows = (
            ("普通物理學(一)", 3, "lecture", "ordinary_physics_1"),
            ("普通物理實驗(一)", 1, "lab", "ordinary_physics_lab_1"),
            ("普通化學(一)", 3, "lecture", "ordinary_chemistry_1"),
            ("普通化學實驗(一)", 1, "lab", "ordinary_chemistry_lab_1"),
            ("普通物理學(二)", 3, "lecture", "ordinary_physics_2"),
            ("普通物理實驗(二)", 1, "lab", "ordinary_physics_lab_2"),
            ("普通化學(二)", 3, "lecture", "ordinary_chemistry_2"),
            ("普通化學實驗(二)", 1, "lab", "ordinary_chemistry_lab_2"),
        )
        if cohort in {"111", "112", "113", "114"}:
            # Both tracks share the eight named rows in the source page.  The
            # additional four credits are deliberately an unnamed quota.
            for name, credits, component, slug in base_rows:
                rows.append(
                    _minor_row(
                        cohort,
                        program,
                        track,
                        slug,
                        name,
                        credits,
                        component=component,
                        # The named eight rows are transcribed, but the
                        # separate unnamed four-credit quota keeps the
                        # overall 111–114 decision manual.
                        coverage_state=COMPLETE,
                        original_clause=_table_cell_clause(name, credits),
                    )
                )
            rows.append(
                _minor_row(
                    cohort,
                    program,
                    track,
                    "unnamed_required_4",
                    "未具名必修課程（需目標系書面確認）",
                    4,
                    requirement_type="credit_quota",
                    eligible_names=(),
                    coverage_state=PARTIAL,
                    evidence_state=VERIFIED,
                    original_clause="其餘／必修課程應修畢 4 學分（課名未具名）",
                    manual_reason="官方輔系頁只列 4 學分額度，沒有可執行的課名與選擇規則。",
                )
            )
            metadata["manual_review_reasons"].append("APC 111–114 額外 4 學分未具名，整體不得自動完成。")
            return rows, metadata

        # The 115 page is track-specific: the experiment component is not
        # interchangeable with the other component.
        lab_name = "普通物理實驗" if track == "physics" else "普通化學實驗"
        lab_component = "physics" if track == "physics" else "chemistry"
        rows = [
            _minor_row(cohort, program, track, "ordinary_physics_1", "普通物理學(一)", 3, original_clause=_table_cell_clause("普通物理學(一)", 3)),
            _minor_row(cohort, program, track, "ordinary_chemistry_1", "普通化學(一)", 3, original_clause=_table_cell_clause("普通化學(一)", 3)),
            _minor_row(cohort, program, track, "experiment_1", f"{lab_name}(一)", 1, component="lab", original_clause=_table_cell_clause(f"{lab_name}(一)", 1)),
            _minor_row(cohort, program, track, "calculus_1", "微積分(一)", 3, original_clause=_table_cell_clause("微積分(一)", 3)),
            _minor_row(cohort, program, track, "ordinary_physics_2", "普通物理學(二)", 3, original_clause=_table_cell_clause("普通物理學(二)", 3)),
            _minor_row(cohort, program, track, "ordinary_chemistry_2", "普通化學(二)", 3, original_clause=_table_cell_clause("普通化學(二)", 3)),
            _minor_row(cohort, program, track, "experiment_2", f"{lab_name}(二)", 1, component="lab", original_clause=_table_cell_clause(f"{lab_name}(二)", 1)),
            _minor_row(cohort, program, track, "calculus_2", "微積分(二)", 3, original_clause=_table_cell_clause("微積分(二)", 3)),
        ]
        metadata["track_experiment"] = lab_component
        return rows, metadata

    if program == "earth":
        common = (
            ("普通生物學(一)", 3, "biology_1"),
            ("普通生物學(二)", 3, "biology_2"),
            ("普通生物學實驗", 1, "biology_lab"),
            ("地球科學實驗", 1, "earth_science_lab"),
            ("地球科學(一)", 3, "earth_science_1"),
            ("地球科學(二)", 3, "earth_science_2"),
            ("資料處理與分析", 3, "data_processing"),
            ("基礎生態學", 3, "basic_ecology"),
            ("環境影響評估", 2, "environmental_impact"),
        )
        for name, credits, slug in common:
            rows.append(
                _minor_row(
                    cohort,
                    program,
                    None,
                    slug,
                    name,
                    credits,
                    original_clause=_table_cell_clause(name, credits),
                    # The named common rows are individually transcribed and
                    # verified.  The curriculum can still be PARTIAL because
                    # the zero-credit applicability gate and year-specific
                    # choice quota need a separate manual decision.
                    coverage_state=COMPLETE,
                )
            )
        if cohort in {"111", "112"}:
            rows.extend(
                (
                    _minor_row(
                        cohort,
                        program,
                        None,
                        "project_1_choice",
                        "專題研究／專業實習(一)",
                        1,
                        eligible_names=("專題研究(一)", "專業實習(一)"),
                        requirement_type="choice",
                        choice_group="earth_project_1",
                        choice_rule="二選一",
                        original_clause="專題研究(一)／專業實習(一) 二選一，1 學分",
                        coverage_state=COMPLETE,
                    ),
                    _minor_row(
                        cohort,
                        program,
                        None,
                        "project_2_choice",
                        "專題研究／專業實習(二)",
                        1,
                        eligible_names=("專題研究(二)", "專業實習(二)"),
                        requirement_type="choice",
                        choice_group="earth_project_2",
                        choice_rule="二選一",
                        original_clause="專題研究(二)／專業實習(二) 二選一，1 學分",
                        coverage_state=COMPLETE,
                    ),
                )
            )
        elif cohort == "113":
            rows.append(
                _minor_row(
                    cohort,
                    program,
                    None,
                    "project_choice",
                    "專題研究／專業實習",
                    2,
                    eligible_names=("專題研究", "專業實習"),
                    requirement_type="choice",
                    choice_group="earth_project",
                    choice_rule="二選一",
                    original_clause="專題研究／專業實習 二選一，2 學分",
                    coverage_state=COMPLETE,
                )
            )
        else:
            rows.append(
                _minor_row(
                    cohort,
                    program,
                    None,
                    "seminar",
                    "書報討論",
                    2,
                    original_clause="書報討論 2 學分",
                    coverage_state=COMPLETE,
                )
            )
        zero_names = ("大學生活學習與輔導",) if cohort == "115" else ("大學生活學習與輔導", "服務學習學年課")
        for index, name in enumerate(zero_names, start=1):
            rows.append(
                _minor_row(
                    cohort,
                    program,
                    None,
                    f"zero_credit_{index}",
                    name,
                    0,
                    zero_credit=True,
                    original_clause=f"{name} 0 學分",
                    coverage_state=PARTIAL,
                    manual_reason="0 學分課程是否屬輔系非學分完成 gate，官方輔系頁未說明。",
                )
            )
        metadata["zero_credit_gate"] = True
        metadata["manual_review_reasons"].append("共同必修中的 0 學分項目是否適用輔系，需人工確認。")
        return rows, metadata

    if program == "cs":
        rows = [
            _minor_row(cohort, program, None, "intro", "計算機概論", 3, original_clause=_table_cell_clause("計算機概論", 3), coverage_state=COMPLETE),
        ]
        if cohort == "115":
            # The 115 secondary page verifies the aggregate 6+14 structure,
            # but the locally checked image does not safely identify the
            # second named 3-credit course.  Keep the missing claim explicit;
            # do not copy the older C-programming title into this cohort.
            rows.append(
                _minor_row(
                    cohort,
                    program,
                    None,
                    "missing_named_core",
                    "資科系輔系第二項命名必修（官方列項未完整辨識）",
                    3,
                    requirement_type="missing_named_course",
                    coverage_state=PARTIAL,
                    evidence_state=MISSING,
                    original_clause="輔系必修 aggregate 6 學分；第二個命名列項未能辨識",
                    manual_reason="不得以 C 程式設計或其他年度名稱補猜 115 輔系第二項必修，需回看官方頁面或系所核准。",
                )
            )
            metadata["manual_review_reasons"].append("115 資科輔系第二項命名必修未能由官方頁面影像安全辨識。")
        else:
            rows.append(
                _minor_row(cohort, program, None, "c_programming", "C 程式設計", 3, original_clause=_table_cell_clause("C 程式設計", 3), coverage_state=COMPLETE)
            )
        rows.append(
            _minor_row(
                cohort,
                program,
                None,
                "other_cs_offerings_14",
                "本系其他開設課程（需開課單位證據）",
                14,
                requirement_type="credit_quota",
                eligible_names=(),
                coverage_state=PARTIAL,
                original_clause="本系其他開設課程至少 14 學分",
                manual_reason="其他 14 學分須有資訊科學系開課單位及個案核准證據，不能只靠課名或全域 mapping。",
            ),
        )
        metadata["manual_review_reasons"].append("資科其他 14 學分需要開課單位與必要替代核准證據。")
        return rows, metadata

    # Math / Data Science and Mathematics.  Keep each year independent.
    # The research matrix gives a complete, independently scoped named list
    # for every 111–115 minor table.  Keep each year exact: never manufacture
    # a course by taking a union with a neighbouring handbook version.
    math_elective_options_by_year: dict[str, tuple[tuple[str, int], ...]] = {
        "111": (
            ("線性代數(一)", 3), ("線性代數(二)", 3), ("基礎數學", 3),
            ("數學軟體應用與實作(A)", 3), ("計算機概論", 3), ("基礎統計學", 3), ("數論", 3),
            ("C語言程式設計", 3), ("數學軟體應用與實作(B)", 3), ("數學軟體應用與實作(C)", 3),
            ("統計套裝軟體之應用", 3), ("數學導論", 4), ("數學教育概論", 3),
            ("數學遊戲教學設計與實務", 3), ("高等微積分(一)", 4), ("高等微積分(二)", 4),
            ("代數學(一)", 3), ("代數學(二)", 3), ("機率論", 3), ("統計學", 3), ("幾何學", 3),
            ("微分方程(一)", 3), ("高等線性代數", 3), ("微分方程(二)", 3), ("數值分析(一)", 3),
            ("離散數學", 3), ("數學課程研究", 3), ("兒童數學概念發展", 3), ("資訊科技融入數學教學", 3),
            ("視覺化資料分析", 3), ("資料探勘", 3), ("統計程式語言", 3), ("財務數學", 3),
            ("迴歸分析", 3), ("時間序列", 3), ("應用統計方法(一)", 3), ("數理統計(一)", 3),
            ("數理統計(二)", 3), ("實變數函數論", 3), ("複變數函數論", 3), ("拓樸學", 3),
            ("數學教學與評量", 3), ("數學教育專題", 3),
        ),
        "112": (
            ("線性代數(一)", 3), ("線性代數(二)", 3), ("基礎數學", 3),
            ("數學軟體應用與實作(A)", 3), ("計算機概論", 3), ("基礎統計學", 3), ("數論", 3),
            ("C語言程式設計", 3), ("數學軟體應用與實作(B)", 3), ("數學軟體應用與實作(C)", 3),
            ("統計套裝軟體之應用", 3), ("數學導論", 4), ("數學教育概論", 3),
            ("數學遊戲教學設計與實務", 3), ("高等微積分(一)", 4), ("高等微積分(二)", 4),
            ("代數學(一)", 3), ("代數學(二)", 3), ("機率論", 3), ("統計學", 3), ("幾何學", 3),
            ("微分方程(一)", 3), ("高等線性代數", 3), ("微分方程(二)", 3), ("數值分析(一)", 3),
            ("離散數學", 3), ("數學課程研究", 3), ("兒童數學概念發展", 3), ("資訊科技融入數學教學", 3),
            ("視覺化資料分析", 3), ("資料探勘", 3), ("統計程式語言", 3), ("財務數學", 3),
            ("迴歸分析", 3), ("時間序列", 3), ("應用統計方法(一)", 3), ("數理統計(一)", 3),
            ("數理統計(二)", 3), ("實變數函數論", 3), ("複變數函數論", 3), ("拓樸學", 3),
            ("數學教學與評量", 3), ("數學教育專題", 3),
        ),
        "113": (
            ("線性代數(一)", 3), ("線性代數(二)", 3), ("集合與邏輯", 3), ("資訊科學與科學計算", 3),
            ("統計與生活", 3), ("數論", 3), ("C語言程式設計", 3), ("Matlab程式設計", 3),
            ("Python程式設計", 3), ("統計套裝軟體之應用", 3), ("數學導論", 3), ("數學教育概論", 3),
            ("數學遊戲教學設計與實務", 3), ("高等微積分(一)", 4), ("高等微積分(二)", 4),
            ("代數學(一)", 3), ("代數學(二)", 3), ("機率論", 3), ("統計學(一)", 3),
            ("統計學", 3), ("統計學(二)", 3), ("幾何學", 3), ("微分方程(一)", 3),
            ("高等線性代數", 3), ("微分方程(二)", 3), ("數值分析(一)", 3), ("離散數學", 3),
            ("數學課程研究", 3), ("兒童數學概念發展", 3), ("數學概念發展", 3), ("資訊科技融入數學教學", 3),
            ("視覺化資料分析", 3), ("資料探勘", 3), ("統計程式語言", 3), ("程式設計與資料庫", 3),
            ("財務數學", 3), ("迴歸分析", 3), ("時間序列", 3), ("應用統計方法(一)", 3),
            ("數理統計(一)", 3), ("數理統計(二)", 3), ("貝氏統計", 3), ("實變數函數論", 3),
            ("複變數函數論", 3), ("拓樸學", 3), ("數學教學與評量", 3), ("數學教學與評量研究", 3),
            ("數學教育專題", 3),
        ),
        "114": (
            ("線性代數(一)", 3), ("線性代數(二)", 3), ("集合與邏輯", 3), ("資訊科學與科學計算", 3),
            ("統計與生活", 3), ("數論", 3), ("Python程式設計", 3), ("Matlab程式設計", 3),
            ("統計套裝軟體之應用", 3), ("數學導論", 3), ("數學教育概論", 3),
            ("數學遊戲教學設計與實務", 3), ("高等微積分(一)", 4), ("高等微積分(二)", 4),
            ("代數學(一)", 3), ("代數學(二)", 3), ("統計學(一)", 3), ("統計學(二)", 3),
            ("微分方程", 3), ("高等線性代數", 3), ("數值分析", 3), ("離散數學", 3),
            ("數學課程研究", 3), ("數學概念發展", 3), ("資訊科技融入數學教學", 3),
            ("視覺化資料分析", 3), ("資料探勘", 3), ("統計程式語言", 3), ("財務數學", 3),
            ("迴歸分析", 3), ("時間序列", 3), ("應用統計", 3), ("貝氏數據分析導論", 3),
            ("實變數函數論", 3), ("複變數函數論", 3), ("數學教學與評量研究", 3), ("數學教育專題研究", 3),
        ),
        "115": (
            ("線性代數(一)", 3), ("線性代數(二)", 3), ("集合與邏輯", 3), ("統計與生活", 3),
            ("資訊科學與科學計算", 3), ("數論", 3), ("Python程式設計", 3), ("Matlab程式設計", 3),
            ("統計套裝軟體之應用", 3), ("數學導論", 3), ("數學教育概論", 3),
            ("數學遊戲數位設計與實務", 3), ("高等微積分(一)", 4), ("高等微積分(二)", 4),
            ("代數學(一)", 3), ("代數學(二)", 3), ("統計學(一)", 3), ("統計學(二)", 3),
            ("微分方程", 3), ("高等線性代數", 3), ("數值分析", 3), ("離散數學", 3),
            ("數學課程研究", 3), ("數學概念發展", 3), ("資訊科技融入數學教學", 3),
            ("視覺化資料分析", 3), ("資料探勘", 3), ("統計程式語言", 3), ("財務數學", 3),
            ("迴歸分析", 3), ("時間序列", 3), ("應用統計", 3), ("貝氏數據分析導論", 3),
            ("實變數函數論", 3), ("複變數函數論", 3), ("數學教學與評量研究", 3), ("數學教育專題研究", 3),
        ),
    }
    elective_options = math_elective_options_by_year[cohort]
    software = tuple(name for name, _credits in elective_options if name in {
        "數學軟體應用與實作(A)", "數學軟體應用與實作(B)", "數學軟體應用與實作(C)",
        "Matlab程式設計", "Python程式設計",
    })
    elective_names = tuple(name for name, _credits in elective_options)
    pool_coverage = COMPLETE
    pool_reason = ""
    rows = [
        _minor_row(
            cohort,
            program,
            None,
            "calculus_1",
            "微積分(一)",
            4,
            waiver=True,
            original_clause="微積分(一) 4 學分",
            coverage_state=COMPLETE,
        ),
        _minor_row(
            cohort,
            program,
            None,
            "calculus_2",
            "微積分(二)",
            4,
            waiver=True,
            original_clause="微積分(二) 4 學分",
            coverage_state=COMPLETE,
        ),
        _minor_row(
            cohort,
            program,
            None,
            "software_one_of",
            "數學軟體課程（擇一）",
            3,
            eligible_names=software,
            eligible_options=tuple(option for option in elective_options if option[0] in software),
            requirement_type="choice",
            choice_group="math_software",
            choice_rule="擇一，最多 3 學分",
            original_clause=f"數學軟體課程 {'／'.join(software)} 僅擇一採計 3 學分",
            coverage_state=COMPLETE,
        ),
        _minor_row(
            cohort,
            program,
            None,
            "other_electives_9",
            "其他表列選修（不含軟體擇一）",
            9,
            eligible_names=tuple(name for name in elective_names if name not in software),
            eligible_options=tuple(option for option in elective_options if option[0] not in software),
            requirement_type="course_pool",
            choice_group="math_electives",
            choice_rule="本系表列選修補足至少 12 學分",
            original_clause="表列選修至少 12 學分；軟體課程群僅擇一 3 學分",
            coverage_state=pool_coverage,
            manual_reason=pool_reason,
        ),
    ]
    if cohort == "113":
        metadata["conflicted_course_names"] = ("數學導論",)
        rows.append(
            _minor_row(
                cohort,
                program,
                None,
                "math_intro_conflict_candidate",
                "數學導論",
                0,
                eligible_names=("數學導論",),
                eligible_options=(("數學導論", 4), ("數學導論", 3)),
                requirement_type="conflict_candidate",
                choice_rule="4↔3 刪改衝突；僅作候選，不直接產生學分",
                evidence_state=CONFLICTED,
                coverage_state=COMPLETE,
                original_clause="數學導論 4 與 3 同時保留",
                manual_reason="官方 113 手冊的數學導論 4→3 刪改衝突，不能自動選擇學分。",
            )
        )
        metadata["manual_review_reasons"].append("官方 113 手冊保留數學導論 4 與 3 的刪改衝突；使用該列時必須人工確認。")
    return rows, metadata


def _minor_assertions(cohort: str, program: str, track: str | None, metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = _minor_source(cohort, program, track)
    label = f"{cohort} 學年度{_PROGRAM_DISPLAY[program]}輔系規則"
    if program == "apc":
        total = 20
        claim = "輔系指定課程總計 20 學分"
        assertions = [_assertion(f"minor.{cohort}.apc.total20", cohort, source["pages"], claim, total, label=label, url=source["source_url"])]
        if cohort in {"111", "112", "113", "114"}:
            assertions.append(_assertion(f"minor.{cohort}.apc.unnamed4", cohort, source["pages"], "另有未具名必修課程 4 學分", 4, evidence_state=VERIFIED, label=label, url=source["source_url"]))
        return _enrich_minor_assertions(assertions, source, label, metadata)
    if program == "earth":
        assertions = [_assertion(f"minor.{cohort}.earth.total24", cohort, source["pages"], "輔系為共同必修 24 學分", 24, label=label, url=source["source_url"])]
        assertions.append(_assertion(f"minor.{cohort}.earth.zero_gate", cohort, source["pages"], "共同必修 0 學分項目是否為輔系 gate", "unknown", evidence_state=MANUAL_REVIEW, label=label, url=source["source_url"]))
        return _enrich_minor_assertions(assertions, source, label, metadata)
    if program == "cs":
        claim = (
            "資科輔系 aggregate 6 + 其他本系開設課程 14 = 20；命名基礎列項未完整辨識"
            if cohort == "115"
            else "計算機概論 3 + C 程式設計 3 + 其他本系開設課程 14 = 20"
        )
        assertions = [_assertion(f"minor.{cohort}.cs.total20", cohort, source["pages"], claim, 20, label=label, url=source["source_url"])]
        if cohort == "115":
            assertions.append(
                _assertion(
                    "minor.115.cs.missing_named_core",
                    cohort,
                    source["pages"],
                    "輔系第二個命名基礎課程",
                    "not_transcribed",
                    evidence_state=MISSING,
                    label=label,
                    url=source["source_url"],
                )
            )
        return _enrich_minor_assertions(assertions, source, label, metadata)
    assertions = [_assertion(f"minor.{cohort}.math.total20", cohort, source["pages"], "微積分 8 + 表列選修至少 12 = 20", 20, label=label, url=source["source_url"])]
    if cohort == "113":
        assertions.append(_assertion(f"minor.{cohort}.math.conflict", cohort, source["pages"], "數學導論學分刪改衝突 4 與 3", "4↔3", evidence_state=CONFLICTED, label=label, url=source["source_url"]))
    return _enrich_minor_assertions(assertions, source, label, metadata)


def _enrich_minor_assertions(assertions: list[dict[str, Any]], source: Mapping[str, Any], label: str, metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    curriculum_version = _normalize_cohort(source.get("section")) or ""
    for item in assertions:
        assertion_id = item.get("assertion_id") or item.get("id") or "assertion"
        official_reference = f"{source['source_reference']}:assertion:{assertion_id}"
        item_source = item.get("source")
        if isinstance(item_source, dict):
            item_source.update(
                {
                    "curriculum_version": curriculum_version,
                    "source_reference": official_reference,
                }
            )
        item.update(
            {
                "research_file": source["research_file"],
                "source_reference": official_reference,
                "source_url": source["source_url"],
                "source_file": source["source_file"],
                "pdf_page": source["pdf_page"],
                "printed_page": source["printed_page"],
                "table_location": source["section"],
                "original_clause": item.get("original_clause") or item.get("claim", ""),
                "original_text": item.get("original_clause") or item.get("claim", ""),
                "curriculum_version": curriculum_version,
                "coverage_state": "PARTIAL" if metadata.get("manual_review_reasons") else "COMPLETE",
                "verification_status": item.get("evidence_state", VERIFIED),
                "automatic_decision": item.get("evidence_state", VERIFIED) == VERIFIED and not metadata.get("manual_review_reasons"),
                "manual_reason": "; ".join(str(value) for value in metadata.get("manual_review_reasons", ()) if value),
                "manual_review_reason": "; ".join(str(value) for value in metadata.get("manual_review_reasons", ()) if value),
            }
        )
    return assertions


def _build_curriculum(kind: str, cohort: str, program: str, track: str | None) -> dict[str, Any]:
    curriculum_id = _canonical_id(kind, cohort, program, track)
    is_primary = kind == "primary"
    is_minor = kind in {_MINOR_TARGET_ROLE, "minor", "minor_target"}
    if is_primary:
        assertions = _primary_assertions(program, cohort, track)
        conflict = bool(_primary_conflict_assertions(program, cohort))
        evidence_state = CONFLICTED if conflict else VERIFIED
        # Every configured primary section is intentionally PARTIAL until the
        # global allocator models all choices, zero-credit gates and teacher
        # certification branches.  A partial source-backed catalog is useful
        # for explanation, but it is never PASS-eligible.
        coverage = PARTIAL
        source_meta = _primary_evidence(cohort, program)
        warning = "官方表格存在衝突，不能自動宣告主修門檻完整。" if conflict else source_meta.get("manual_reason", "")
    elif is_minor:
        catalog, minor_metadata = _minor_catalog(cohort, program, track)
        assertions = _minor_assertions(cohort, program, track, minor_metadata)
        row_conflict = any(
            isinstance(row, dict) and row.get("evidence_state") == CONFLICTED
            for row in catalog
        )
        assertion_conflict = any(
            isinstance(item, dict) and item.get("evidence_state") == CONFLICTED
            for item in assertions
        )
        evidence_state = CONFLICTED if row_conflict or assertion_conflict else VERIFIED
        # The 20-credit math structure is transcribed for each named year;
        # The 113 value conflict is retained at both row and curriculum
        # level: unrelated named rows remain inspectable, but the scope is
        # never PASS-eligible while an official course value is ambiguous.
        # Earth/CS and APC 111–114 retain PARTIAL at the curriculum level
        # because their source has dynamic or unnamed portions.
        coverage = COMPLETE if program == "math" or (program == "apc" and cohort == "115") else PARTIAL
        warning = "; ".join(str(item) for item in minor_metadata.get("manual_review_reasons", ()) if item)
    else:
        assertions, evidence_state, coverage, warning = _double_assertions(program, cohort, track)
    if is_primary:
        thresholds = _base_thresholds(program, cohort, track)
        catalog = _course_catalog(program, cohort, kind, track, coverage)
        extra_metadata: dict[str, Any] = {}
    elif is_minor:
        # Keep the aggregate rules separate from the individual rows.  The
        # extra metadata is intentionally descriptive and is consumed by the
        # service gate, never by a renderer-side recalculation.
        thresholds = {"total": 20 if program in {"apc", "cs", "math"} else 24}
        if program == "apc" and cohort in {"111", "112", "113", "114"}:
            thresholds.update({"fixed_base_credits": 16, "unnamed_required_credits": 4})
        if program == "earth":
            thresholds.update({"credit_total": 24, "zero_credit_gate": True})
        if program == "cs":
            thresholds.update({"mandatory_credits": 6, "other_course_credits": 14})
        if program == "math":
            thresholds.update({"calculus_credits": 8, "elective_credits": 12})
        extra_metadata = minor_metadata
    else:
        thresholds = _double_thresholds(program, cohort, track)
        catalog = _course_catalog(program, cohort, kind, track, coverage)
        extra_metadata = {}
    citations = []
    for item in assertions:
        source = item.get("source") or {}
        if source and source not in citations:
            citations.append(deepcopy(source))
    if not citations:
        citations = [_citation(cohort, "官方學生手冊", f"{cohort} {_PROGRAM_DISPLAY[program]}")]
    # The aggregate can be trusted independently from a named catalog.  This
    # matters for CS 115: the 15+25 statement is VERIFIED while named rows are
    # only PARTIAL.
    aggregate_status = VERIFIED if evidence_state in {VERIFIED, CONFLICTED} else evidence_state
    status = evidence_state if evidence_state == CONFLICTED else VERIFIED if coverage == COMPLETE else MANUAL_REVIEW
    record_source = next(
        (item for item in assertions if isinstance(item, dict)),
        {},
    )
    record_automatic = status == VERIFIED and coverage == COMPLETE and evidence_state == VERIFIED
    record_manual_reason = warning or ("課程目錄或官方語義尚未完整，需人工確認。" if not record_automatic else "")
    blockers: list[dict[str, Any]] = []
    if evidence_state == CONFLICTED:
        blockers.append({"code": CONFLICTED, "reason": warning or "官方來源 assertion 互相衝突。"})
    if coverage != COMPLETE:
        blockers.append({"code": MANUAL_REVIEW, "reason": f"課程目錄 coverage={coverage}，不足以安全逐課判定。"})
    return {
        "id": curriculum_id,
        "curriculum_id": curriculum_id,
        "kind": "primary" if is_primary else _MINOR_TARGET_ROLE if is_minor else "double_major_target",
        "type": "primary" if is_primary else "target",
        "curriculum_kind": "primary" if is_primary else _MINOR_TARGET_ROLE if is_minor else "double_major_target",
        "version": cohort,
        "curriculum_version": cohort,
        "admission_cohort": cohort if is_primary else None,
        "program": _PROGRAM_DISPLAY[program],
        "program_slug": program,
        "track": _TRACK_DISPLAY.get(track) if track else None,
        "track_slug": track or ("department" if is_minor else None),
        "program_type": "單主修" if is_primary else "輔系" if is_minor else _DOUBLE_MAJOR,
        "thresholds": thresholds,
        "requirements": deepcopy(thresholds),
        "total_required": thresholds.get("total_required", thresholds.get("total")),
        "base_required": thresholds.get("base_required") if not is_primary and not is_minor else None,
        "other_required": thresholds.get("other_required") if not is_primary and not is_minor else None,
        "course_catalog": catalog,
        "source_assertions": assertions,
        "assertions": deepcopy(assertions),
        "citations": citations,
        "source_file": _source_file(cohort),
        "source_url": _HANDBOOK_URLS.get(cohort, ""),
        "source_reference": record_source.get("source_reference", f"handbook:{cohort}:curriculum:{curriculum_id}"),
        "pdf_page": record_source.get("pdf_page", "未標示"),
        "printed_page": record_source.get("printed_page", "未標示"),
        "table_location": record_source.get("table_location", f"{cohort} {_PROGRAM_DISPLAY[program]} 課程表"),
        "original_clause": record_source.get("original_clause", ""),
        "verification_status": evidence_state,
        "automation_sufficiency": "COMPLETE" if record_automatic else "PARTIAL" if evidence_state == VERIFIED else "NONE",
        "automatic_decision": record_automatic,
        "manual_reason": record_manual_reason,
        "manual_review_reason": record_manual_reason,
        "research_file": record_source.get("research_file", ""),
        "evidence_state": evidence_state,
        "coverage_state": coverage,
        "aggregate_status": aggregate_status,
        "status": status,
        # ``pass_eligible`` describes the integrity of this curriculum
        # catalogue itself.  It is not the student's minor qualification;
        # that separate gate still requires scoped target evidence and the
        # official approval/registration chain in ``graduation_service``.
        "pass_eligible": status == VERIFIED and coverage == COMPLETE and evidence_state == VERIFIED,
        "warnings": [warning] if warning else [],
        "blockers": blockers,
        "legacy_planning": cohort in {"111", "115"} and is_primary and cohort not in _RULES.get("handbooks", {}),
        "handbook_metadata": deepcopy(_RULES.get("handbooks", {}).get(cohort, {}).get("_meta", {})),
        **extra_metadata,
    }


def _build_registry() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for cohort in _SUPPORTED_COHORTS:
        for program in ("earth", "apc", "cs", "math"):
            tracks = ["earth_environment", "life_science"] if program == "earth" else ["physics", "chemistry"] if program == "apc" else [None]
            for track in tracks:
                primary = _build_curriculum("primary", cohort, program, track)
                target = _build_curriculum("double_major_target", cohort, program, track)
                result[primary["curriculum_id"]] = primary
                result[target["curriculum_id"]] = target
                # Minor targets are department-level for Earth/CS/Math and
                # track-level for APC.  Keep all 25 year scopes independent.
                minor_track = track if program == "apc" else None
                minor = _build_curriculum(_MINOR_TARGET_ROLE, cohort, program, minor_track)
                result[minor["curriculum_id"]] = minor
    return result


_REGISTRY = _build_registry()


def _normalize_kind(value: Any) -> str | None:
    text = _normalize_text(value).lower().replace("-", "_")
    if text in {"primary", "major", "home", "主修"}:
        return "primary"
    if text in {"minor", "minor_target", "secondary_minor", "輔系"}:
        return _MINOR_TARGET_ROLE
    if text in {"target", "double_major", "double_major_target", "doublemajor", "double", "雙主修", "dm"}:
        return "double_major_target"
    return None


def _record_matches(
    curriculum_id: str,
    *,
    kind: str | None = None,
    cohort: Any = None,
    program: Any = None,
    track: Any = None,
) -> bool:
    record = _REGISTRY.get(curriculum_id)
    if record is None:
        return False
    expected_kind = _normalize_kind(kind) if kind is not None else None
    expected_cohort = _normalize_cohort(cohort) if cohort not in (None, "") else None
    expected_program = _program_slug(program) if program not in (None, "") else None
    expected_track = (
        "department"
        if expected_kind == _MINOR_TARGET_ROLE and _normalize_text(track).lower() in {"department", "系級", "系所"}
        else _track_slug(track, expected_program) if track not in (None, "") else None
    )
    if kind is not None and expected_kind is None:
        return False
    if track not in (None, "") and expected_track is None:
        return False
    return all(
        (
            expected_kind is None or record.get("kind") == expected_kind,
            expected_cohort is None or record.get("version") == expected_cohort,
            expected_program is None or record.get("program_slug") == expected_program,
            expected_track is None or record.get("track_slug") == expected_track,
        )
    )


def _parse_id(value: Any, *, kind: str | None = None, cohort: Any = None, program: Any = None, track: Any = None) -> str | None:
    """Parse canonical, dotted, slash-delimited and Chinese-friendly IDs."""

    if isinstance(value, dict):
        for key in ("curriculum_id", "target_curriculum_id", "id", "version"):
            if value.get(key):
                parsed = _parse_id(value[key], kind=kind, cohort=cohort, program=program, track=track)
                if parsed:
                    return parsed
        return None
    text = _normalize_text(value)
    if not text:
        return None
    if text in _REGISTRY:
        return text if _record_matches(text, kind=kind, cohort=cohort, program=program, track=track) else None
    parts = [part for part in re.split(r"[.:/|]+", text) if part]
    parsed_kind = _normalize_kind(kind) if kind is not None else None
    parsed_cohort = _normalize_cohort(cohort)
    parsed_program = _program_slug(program)
    parsed_track = _track_slug(track, parsed_program)
    for part in parts:
        low = part.lower().replace("-", "_")
        if low in {"primary", "major", "home", "主修"}:
            parsed_kind = "primary"
        elif low in {"minor", "minor_target", "secondary_minor", "輔系"}:
            parsed_kind = _MINOR_TARGET_ROLE
        elif low in {"target", "double_major", "double_major_target", "doublemajor", "double", "雙主修", "dm"}:
            parsed_kind = "double_major_target"
        elif _normalize_cohort(part):
            parsed_cohort = _normalize_cohort(part)
        elif low in _SLUG_ALIASES:
            mapped = _SLUG_ALIASES[low]
            if mapped in _PROGRAM_SLUGS:
                parsed_program = mapped
            elif mapped in _TRACK_SLUGS:
                parsed_track = mapped
        elif part in _PROGRAMS or _program_slug(part):
            mapped = _program_slug(part)
            if mapped in _PROGRAM_SLUGS:
                parsed_program = mapped
        elif _track_slug(part, parsed_program):
            parsed_track = _track_slug(part, parsed_program)
    if parsed_kind is None:
        parsed_kind = "primary"
    if parsed_cohort not in _SUPPORTED_COHORTS or parsed_program not in _PROGRAM_SLUGS:
        return None
    if parsed_kind == _MINOR_TARGET_ROLE:
        if parsed_program == "apc" and parsed_track not in {"physics", "chemistry"}:
            return None
        if parsed_program in {"earth", "cs", "math"}:
            if parsed_track in (None, "department"):
                parsed_track = "department"
            else:
                return None
    elif parsed_program == "earth" and parsed_track not in {"earth_environment", "life_science"}:
        if parsed_track is None:
            parsed_track = "earth_environment"
        else:
            return None
    if parsed_kind != _MINOR_TARGET_ROLE and parsed_program == "apc" and parsed_track not in {"physics", "chemistry"}:
        return None
    if parsed_kind != _MINOR_TARGET_ROLE and parsed_program in {"cs", "math"}:
        if parsed_track is not None:
            return None
        parsed_track = None
    expected_kind = _normalize_kind(kind) if kind is not None else None
    expected_cohort = _normalize_cohort(cohort) if cohort not in (None, "") else None
    expected_program = _program_slug(program) if program not in (None, "") else None
    expected_track = (
        "department"
        if _normalize_kind(kind) == _MINOR_TARGET_ROLE and _normalize_text(track).lower() in {"department", "系級", "系所"}
        else _track_slug(track, expected_program) if track not in (None, "") else None
    )
    if kind is not None and (expected_kind is None or parsed_kind != expected_kind):
        return None
    if expected_cohort is not None and parsed_cohort != expected_cohort:
        return None
    if expected_program is not None and parsed_program != expected_program:
        return None
    if track not in (None, "") and (expected_track is None or parsed_track != expected_track):
        return None
    canonical = _canonical_id(parsed_kind, parsed_cohort, parsed_program, parsed_track)
    return canonical if _record_matches(canonical, kind=kind, cohort=cohort, program=program, track=track) else None


def get_curriculum(curriculum_id: Any) -> dict[str, Any]:
    """Return one immutable-by-copy, versioned curriculum record.

    ``curriculum_id`` accepts the canonical IDs emitted by this module (for
    example ``primary:114:apc:chemistry`` and
    ``target:double_major:114:apc:chemistry``), dotted/slash aliases, and
    Chinese programme labels when a cohort is supplied by the caller through a
    mapping.  Unknown IDs fail explicitly rather than falling back to a
    neighbouring handbook.
    """

    if isinstance(curriculum_id, dict):
        parsed = _parse_id(curriculum_id)
    else:
        parsed = _parse_id(curriculum_id)
    if not parsed:
        raise KeyError(f"找不到版本化課程表：{curriculum_id}")
    return deepcopy(_REGISTRY[parsed])


def list_curriculum_ids(*, kind: str | None = None, cohort: Any = None) -> list[str]:
    """List registry IDs for discovery UIs and integration tests."""

    selected_cohort = _normalize_cohort(cohort) if cohort is not None else None
    ids = []
    normalized_kind = _normalize_kind(kind) if kind not in (None, "", "target") else None
    for curriculum_id, item in _REGISTRY.items():
        if kind == "target":
            matches_kind = item["kind"] == "double_major_target"
        elif normalized_kind is not None:
            matches_kind = item["kind"] == normalized_kind
        else:
            matches_kind = True
        if not matches_kind:
            continue
        if selected_cohort and item["version"] != selected_cohort:
            continue
        ids.append(curriculum_id)
    return sorted(ids)


def _request_value(request: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = request.get(key)
        if value not in (None, ""):
            return value
    return None


def _target_program_and_track(request: dict[str, Any]) -> tuple[str | None, str | None]:
    raw_program = _request_value(request, "target_program", "target_dept", "secondary_program", "double_major_target")
    raw_track = _request_value(request, "target_track", "secondary_track")
    program = _program_slug(raw_program)
    track = _track_slug(raw_track, program)
    if track is None:
        inferred_track = _track_slug(raw_program)
        if inferred_track:
            inferred_program = _TRACK_PROGRAMS[inferred_track]
            if program is None:
                program = inferred_program
            if program == inferred_program:
                track = inferred_track
    if program == "earth" and track is None and raw_track in (None, ""):
        track = "earth_environment"
    return program, track


def _secondary_kind(request: Mapping[str, Any]) -> str:
    """Normalize the additive secondary programme role.

    ``program_type`` remains a compatibility input for existing callers, but
    the explicit ``secondary_kind`` field wins whenever it is provided.
    """

    value = _request_value(dict(request), "secondary_kind", "secondary_program_type", "program_type")
    text = _normalize_text(value).lower().replace("-", "_").replace(" ", "")
    if text in {"minor", "minor_target", "secondary_minor", "輔系"}:
        return _MINOR_TARGET_ROLE
    if text in {"double", "double_major", "double_major_target", "doublemajor", "雙主修", "dm"}:
        return "double_major_target"
    return "none"


def _evidence_reference(request: dict[str, Any]) -> str:
    value = _request_value(
        request,
        "target_version_evidence_reference",
        "target_curriculum_evidence_reference",
        "version_evidence_reference",
        "target_version_evidence",
    )
    if isinstance(value, dict):
        value = _request_value(
            value,
            "record_id",
            "evidence_record_id",
            "reference_id",
            "reference",
            "url",
            "id",
            "evidence_reference",
        )
    return str(value or "").strip()


def _applicability_assertion(request: dict[str, Any]) -> Any:
    return _request_value(
        request,
        "scoped_applicability_assertion",
        "target_applicability_assertion",
        "version_applicability_assertion",
        "applicability_assertion",
    )


def _assertion_curriculum_id(
    assertion: Any,
    *,
    cohort: str | None,
    program: str | None,
    track: str | None,
    target_kind: str = "double_major_target",
) -> str | None:
    if not isinstance(assertion, dict):
        return None
    value = _request_value(assertion, "curriculum_id", "target_curriculum_id", "id", "version")
    if value in (None, ""):
        return None
    # A target curriculum's version is independent from the student's
    # admission cohort.  The assertion is checked against the selected target
    # identity later, so do not constrain its version here.
    return _parse_id(value, kind=target_kind, cohort=None, program=program, track=track)


def _trusted_record_id(value: Any) -> str:
    if isinstance(value, dict):
        value = _request_value(value, "record_id", "evidence_record_id", "reference_id", "id")
    return str(value or "").strip()


def _application_event(value: Any, *, year: Any = None, semester: Any = None) -> tuple[str, ...] | None:
    term = _normalize_text(value)
    if term:
        return ("term", term)
    normalized_year = _normalize_text(year)
    normalized_semester = _normalize_text(semester)
    if normalized_year and normalized_semester:
        return ("year_semester", normalized_year, normalized_semester)
    return None


def _record_application_event(record: dict[str, Any]) -> tuple[str, ...] | None:
    return _application_event(
        _request_value(record, "application_term", "application_cohort"),
        year=_request_value(record, "application_year"),
        semester=_request_value(record, "application_semester", "application_term_semester"),
    )


def _request_application_event(request: dict[str, Any]) -> tuple[str, ...] | None:
    return _application_event(
        _request_value(request, "application_term", "application_cohort"),
        year=_request_value(request, "application_year"),
        semester=_request_value(request, "application_semester", "application_term_semester"),
    )


def _same_application_event(request_event: tuple[str, ...] | None, record_event: tuple[str, ...] | None) -> bool:
    if request_event is None or record_event is None:
        return False
    if request_event == record_event:
        return True
    if request_event[0] == "term" and record_event[0] == "year_semester":
        return request_event[1] == f"{record_event[1]}-{record_event[2]}"
    if request_event[0] == "year_semester" and record_event[0] == "term":
        return record_event[1] == f"{request_event[1]}-{request_event[2]}"
    return False


def _record_source_reference(record: dict[str, Any]) -> str:
    value = _request_value(
        record,
        "evidence_reference",
        "source_reference",
        "evidence_url",
        "source_url",
    )
    if value in (None, ""):
        source = record.get("source")
        if isinstance(source, dict):
            value = _request_value(source, "reference", "url", "id")
        elif source not in (None, ""):
            value = source
    return _normalize_text(value)


def _resolve_evidence_record(
    evidence_resolver: Any,
    reference: Any,
    *,
    request: dict[str, Any],
    selected_curriculum_id: str | None,
    cohort: str | None,
    program: str | None,
    track: str | None,
    target_kind: str = "double_major_target",
) -> dict[str, Any] | None:
    """Resolve and validate one server-owned applicability record.

    ``evidence_resolver`` is deliberately injected at the public boundary;
    request/config data can contain only its opaque record ID.  The returned
    record is used for validation only and is never copied into the request
    snapshot.
    """

    if not callable(evidence_resolver):
        return None
    record_id = _trusted_record_id(reference)
    if not record_id:
        return None
    try:
        record = evidence_resolver(record_id)
    except Exception:
        return None
    if not isinstance(record, dict):
        return None
    returned_record_id = _trusted_record_id(record.get("record_id"))
    if returned_record_id and returned_record_id != record_id:
        return None
    if record.get("evidence_state") != VERIFIED:
        return None
    record_curriculum_id = _parse_id(
        _request_value(record, "curriculum_id", "target_curriculum_id"),
        kind=target_kind,
        cohort=None,
        program=program,
        track=track,
    )
    if not record_curriculum_id or (selected_curriculum_id and record_curriculum_id != selected_curriculum_id):
        return None
    record_cohort = _normalize_cohort(_request_value(record, "admission_cohort", "cohort"))
    if not cohort or not record_cohort or record_cohort != cohort:
        return None
    record_program = _program_slug(_request_value(record, "target_program", "target_dept", "program"))
    if not program or not record_program or record_program != program:
        return None
    record_track_value = _request_value(record, "target_track", "track")
    record_track = (
        "department"
        if target_kind == _MINOR_TARGET_ROLE and _normalize_text(record_track_value).lower() in {"department", "系級", "系所", ""}
        else _track_slug(record_track_value, record_program)
    )
    if track:
        if not record_track or record_track != track:
            return None
    elif record_track_value not in (None, ""):
        # CS and Math have no target track.  Reject a record that tries to
        # smuggle another programme's track into their applicability scope.
        return None
    request_event = _request_application_event(request)
    record_event = _record_application_event(record)
    if not _same_application_event(request_event, record_event):
        return None
    if _normalize_text(record.get("authority")) == "":
        return None
    if not _record_source_reference(record):
        return None
    return deepcopy(record)


_REQUEST_SNAPSHOT_KEYS = {
    "admission_cohort",
    "handbook_year",
    "cohort",
    "primary_program",
    "primary_dept",
    "primary_track",
    "program_name",
    "domain",
    "primary_curriculum_id",
    "primary_curriculum_version",
    "primary_version",
    "program_type",
    "program",
    "secondary_kind",
    "secondary_program_type",
    "target_program",
    "target_dept",
    "secondary_program",
    "target_track",
    "secondary_track",
    "target_curriculum_version",
    "target_curriculum_id",
    "target_version",
    "target_version_evidence_reference",
    "target_curriculum_evidence_reference",
    "version_evidence_reference",
    "target_version_evidence",
    "scoped_applicability_assertion",
    "target_applicability_assertion",
    "version_applicability_assertion",
    "applicability_assertion",
    "application_term",
    "application_cohort",
    "application_year",
    "application_semester",
    "application_term_semester",
}

_EVIDENCE_REQUEST_KEYS = {
    "target_version_evidence_reference",
    "target_curriculum_evidence_reference",
    "version_evidence_reference",
    "target_version_evidence",
    "scoped_applicability_assertion",
    "target_applicability_assertion",
    "version_applicability_assertion",
    "applicability_assertion",
}


def _request_snapshot(request: dict[str, Any]) -> dict[str, Any]:
    """Keep an audit-safe request without injected services or user records."""

    snapshot: dict[str, Any] = {}
    for key in _REQUEST_SNAPSHOT_KEYS:
        value = request.get(key)
        if value in (None, ""):
            continue
        if key in _EVIDENCE_REQUEST_KEYS:
            if isinstance(value, dict):
                opaque_id = _trusted_record_id(value)
                if opaque_id:
                    snapshot[key] = opaque_id
            else:
                snapshot[key] = _normalize_text(value)
            continue
        if isinstance(value, (str, int, float, bool)):
            snapshot[key] = value
        elif key in {"target_curriculum_version", "target_curriculum_id", "target_version"}:
            opaque_id = _trusted_record_id(value)
            if opaque_id:
                snapshot[key] = opaque_id
    return snapshot


def _is_scoped_assertion(assertion: Any, request: dict[str, Any]) -> bool:
    if not isinstance(assertion, dict):
        return False
    scope_keys = {
        "scope",
        "student_id",
        "admission_cohort",
        "application_term",
        "application_year",
        "target_program",
        "target_dept",
        "target_track",
        "effective_term",
        "approval_id",
    }
    if not any(assertion.get(key) not in (None, "") for key in scope_keys):
        return False
    # If the assertion carries the same dimensions, reject an obvious
    # cross-program/cross-cohort citation instead of treating it as scoped.
    req_cohort = _normalize_cohort(_request_value(request, "admission_cohort", "handbook_year"))
    assertion_cohort = _normalize_cohort(assertion.get("admission_cohort"))
    if req_cohort and assertion_cohort and req_cohort != assertion_cohort:
        return False
    req_program, req_track = _target_program_and_track(request)
    assertion_program = _program_slug(_request_value(assertion, "target_program", "target_dept", "program"))
    assertion_track = _track_slug(_request_value(assertion, "target_track", "track"), assertion_program)
    if req_program and assertion_program and req_program != assertion_program:
        return False
    if req_track and assertion_track and req_track != assertion_track:
        return False
    return True


def _dimension(
    status: str,
    *,
    value: Any = None,
    curriculum: dict[str, Any] | None = None,
    reason: str = "",
    evidence_reference: str = "",
    evidence_state: str | None = None,
    coverage_state: str | None = None,
) -> dict[str, Any]:
    item = {
        "status": status,
        "state": status,
        "value": value,
        "reason": reason,
        "evidence_reference": evidence_reference,
        "evidence_state": evidence_state or (curriculum or {}).get("evidence_state"),
        "coverage_state": coverage_state or (curriculum or {}).get("coverage_state"),
        "curriculum_id": (curriculum or {}).get("curriculum_id"),
    }
    if curriculum is not None:
        item["curriculum"] = deepcopy(curriculum)
    return item


def resolve_rule_context(request: Any, *, evidence_resolver: Any = None) -> dict[str, Any]:
    """Resolve primary/target rule dimensions without guessing versions.

    The target dimension is intentionally stricter than the primary one.  A
    plain ``target_curriculum_version`` is only a user selection and therefore
    produces ``MANUAL_REVIEW``.  It becomes ``RESOLVED`` only when an opaque
    evidence record ID can be resolved by the injected server-owned resolver
    and its concrete applicability fields match this request.  Even then a
    conflicted or partially covered curriculum leaves a blocker in the overall
    resolution.
    """

    request = dict(request) if isinstance(request, dict) else {}
    cohort = _normalize_cohort(_request_value(request, "admission_cohort", "handbook_year", "cohort"))
    primary_id_value = _request_value(
        request,
        "primary_curriculum_id",
        "primary_curriculum_version",
        "primary_version",
    )
    primary_id_provided = primary_id_value not in (None, "")
    explicit_primary_id = _parse_id(primary_id_value, kind="primary") if primary_id_provided else None
    explicit_primary = _REGISTRY.get(explicit_primary_id) if explicit_primary_id else None
    primary_raw = _request_value(request, "primary_program", "primary_dept", "domain", "program_name")
    primary_program = _program_slug(primary_raw)
    primary_track = _track_slug(_request_value(request, "primary_track", "track"), primary_program)
    if primary_track is None:
        inferred_track = _track_slug(primary_raw)
        if inferred_track:
            inferred_program = _TRACK_PROGRAMS[inferred_track]
            if primary_program is None:
                primary_program = inferred_program
            if primary_program == inferred_program:
                primary_track = inferred_track
    if primary_program == "earth" and primary_track is None and _request_value(request, "primary_track", "track") in (None, ""):
        primary_track = "earth_environment"
    primary_identity_mismatch = False
    if explicit_primary is not None:
        explicit_program = _program_slug(explicit_primary.get("program_slug"))
        explicit_track = _track_slug(explicit_primary.get("track_slug"), explicit_program)
        raw_primary_track = _request_value(request, "primary_track", "track")
        if primary_program is None:
            primary_program = explicit_program
            if raw_primary_track in (None, ""):
                primary_track = explicit_track
        elif primary_program != explicit_program:
            primary_identity_mismatch = True
        if raw_primary_track not in (None, ""):
            requested_track = _track_slug(raw_primary_track, primary_program or explicit_program)
            if requested_track is None or requested_track != explicit_track:
                primary_identity_mismatch = True
    secondary_kind = _secondary_kind(request)
    is_double = secondary_kind == "double_major_target"
    is_minor = secondary_kind == _MINOR_TARGET_ROLE
    target_program, target_track = _target_program_and_track(request)
    if is_minor and target_program in {"earth", "cs", "math"}:
        # These minor scopes are department-level.  Never inherit a primary
        # track (or infer one from a friendly label) for them.
        target_track = None

    dimensions: dict[str, dict[str, Any]] = {}
    blockers: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not cohort:
        dimensions["admission_cohort"] = _dimension(MISSING, reason="缺少 admission_cohort；不能選擇原主修手冊。")
    else:
        dimensions["admission_cohort"] = _dimension(RESOLVED, value=cohort, reason="已由使用者明確提供入學 cohort。")
    if primary_id_provided and explicit_primary is None:
        dimensions["primary_curriculum"] = _dimension(
            MISSING,
            value=primary_id_value,
            reason="指定的 primary curriculum ID 不是 registry 中可驗證的原主修課表，不能靜默改用 admission_cohort。",
        )
    elif not primary_program:
        dimensions["primary_curriculum"] = _dimension(MISSING, reason="缺少原主修系所／組別。")
    elif not cohort:
        dimensions["primary_curriculum"] = _dimension(
            MISSING,
            value=explicit_primary_id if explicit_primary else None,
            curriculum=explicit_primary,
            reason="缺 admission_cohort，不能確認原主修課表是否與入學 cohort 相符。",
        )
    else:
        primary_id = explicit_primary_id or _canonical_id("primary", cohort, primary_program, primary_track)
        primary = _REGISTRY.get(primary_id)
        if primary is None:
            dimensions["primary_curriculum"] = _dimension(MISSING, reason=f"找不到原主修課表：{primary_id}。")
        else:
            version_mismatch = bool(explicit_primary and primary.get("version") != cohort)
            if primary_identity_mismatch:
                primary_status = MANUAL_REVIEW
                primary_reason = "explicit primary curriculum ID 與請求中的主修系所／組別不一致，需人工確認。"
            elif version_mismatch:
                primary_status = MANUAL_REVIEW
                primary_reason = "explicit primary curriculum handbook 年度與 admission cohort 不同，需人工確認；不得自動套用 admission cohort。"
            else:
                primary_status = CONFLICTED if primary["evidence_state"] == CONFLICTED else RESOLVED
                primary_reason = "原主修課表由明確選定的 primary curriculum ID 驗證，且與 admission cohort／主修身分一致。" if explicit_primary else "原主修課表由 admission_cohort 與主修系所解析。"
            dimensions["primary_curriculum"] = _dimension(
                primary_status,
                value=primary_id,
                curriculum=primary,
                reason=primary_reason,
            )

    application_term = _request_value(request, "application_term", "application_cohort")
    application_year = _request_value(request, "application_year")
    application_semester = _request_value(request, "application_semester", "application_term_semester")
    if application_term not in (None, "") or application_year not in (None, "") or application_semester not in (None, ""):
        dimensions["application_event"] = _dimension(
            RESOLVED,
            value=application_term or {"year": application_year, "semester": application_semester},
            reason="已保留使用者提供的申請事件；它不會單獨推定目標課表版本。",
        )
    elif is_double or is_minor:
        dimensions["application_event"] = _dimension(
            MISSING,
            reason="雙主修／輔系缺少 application term／申請事件證據。",
        )
    else:
        dimensions["application_event"] = _dimension(NOT_APPLICABLE, reason="單主修不需要雙主修申請事件。")

    target_curriculum: dict[str, Any] | None = None
    target_kind = _MINOR_TARGET_ROLE if is_minor else "double_major_target"
    target_label = "輔系" if is_minor else "雙主修"
    if not (is_double or is_minor):
        dimensions["target_program"] = _dimension(NOT_APPLICABLE, reason="目前沒有雙主修或輔系規劃。")
        dimensions["target_curriculum_version"] = _dimension(NOT_APPLICABLE, reason="單主修不需要目標課表版本。")
    elif not target_program:
        dimensions["target_program"] = _dimension(MISSING, reason=f"缺少{target_label}目標系所／組別。")
        dimensions["target_curriculum_version"] = _dimension(MISSING, reason="未能建立目標系所，故不能解析 target curriculum version。")
    else:
        target_id_value = _request_value(request, "target_curriculum_version", "target_curriculum_id", "target_version")
        assertion = _applicability_assertion(request)
        assertion_scoped = _is_scoped_assertion(assertion, request)
        assertion_id = _assertion_curriculum_id(
            assertion,
            cohort=cohort,
            program=target_program,
            track=target_track,
            target_kind=target_kind,
        )
        evidence_value = _request_value(
            request,
            "target_version_evidence_reference",
            "target_curriculum_evidence_reference",
            "version_evidence_reference",
            "target_version_evidence",
        )
        evidence_reference = _evidence_reference(request)
        if not cohort:
            dimensions["target_program"] = _dimension(RESOLVED, value=target_program, reason="目標系所已提供，但缺 admission_cohort。")
            dimensions["target_curriculum_version"] = _dimension(MISSING, reason="只有 application term 或其他事件時，不能解析目標課表版本。")
        elif target_program == "apc" and target_track is None:
            dimensions["target_program"] = _dimension(MISSING, value=target_program, reason=f"物化{target_label}必須明確指定化學組或物理組。")
            dimensions["target_curriculum_version"] = _dimension(MISSING, reason=f"缺少物化{target_label}組別，不能解析目標課表版本。")
        else:
            dimensions["target_program"] = _dimension(RESOLVED, value=target_program, reason="目標系所／組別已由使用者提供。")
            # Target curriculum version is an independent dimension.  The
            # selected target may be from a different handbook version than
            # the student's admission cohort.
            selected_target_id = _parse_id(
                target_id_value,
                kind=target_kind,
                cohort=None,
                program=target_program,
                track=target_track,
            )
            selected_id_provided = target_id_value not in (None, "")
            assertion_id_provided = assertion_id is not None or (
                isinstance(assertion, dict)
                and _request_value(assertion, "curriculum_id", "target_curriculum_id", "id", "version") not in (None, "")
            )
            assertion_mismatch = bool(assertion_id_provided and assertion_id is None)
            if selected_target_id and assertion_id and selected_target_id != assertion_id:
                assertion_mismatch = True
            if isinstance(assertion, dict) and assertion is not None and not assertion_scoped:
                assertion_mismatch = assertion_mismatch or any(
                    assertion.get(key) not in (None, "")
                    for key in (
                        "scope",
                        "student_id",
                        "admission_cohort",
                        "application_term",
                        "application_year",
                        "target_program",
                        "target_dept",
                        "target_track",
                        "effective_term",
                        "approval_id",
                    )
                )
            # A string assertion is only meaningful as a trusted record ID.
            # If both evidence references are supplied, validate both rather
            # than silently letting one hide a mismatching other reference.
            trusted_evidence_record = _resolve_evidence_record(
                evidence_resolver,
                evidence_value,
                request=request,
                selected_curriculum_id=selected_target_id,
                cohort=cohort,
                program=target_program,
                track=target_track,
                target_kind=target_kind,
            )
            trusted_assertion_record = _resolve_evidence_record(
                evidence_resolver,
                assertion,
                request=request,
                selected_curriculum_id=selected_target_id,
                cohort=cohort,
                program=target_program,
                track=target_track,
                target_kind=target_kind,
            )
            if assertion not in (None, "") and not isinstance(assertion, dict) and trusted_assertion_record is None:
                assertion_mismatch = True
            if (
                trusted_evidence_record is not None
                and trusted_assertion_record is not None
                and _request_value(trusted_evidence_record, "curriculum_id", "target_curriculum_id")
                != _request_value(trusted_assertion_record, "curriculum_id", "target_curriculum_id")
            ):
                assertion_mismatch = True
            # Keep a selected ID visible for diagnostics, but never infer a
            # target version from an applicability assertion alone.
            if not selected_id_provided:
                dimensions["target_curriculum_version"] = _dimension(
                    MISSING,
                    reason=f"TARGET_SCOPE_INCOMPLETE：{target_label} target curriculum version 必須明確提供；不能由 admission_cohort 或 application term 推定。",
                )
            elif selected_target_id is None:
                dimensions["target_curriculum_version"] = _dimension(
                    MISSING,
                    value=target_id_value,
                    reason=f"指定的 target curriculum ID 必須是符合目標系所／組別的 {target_kind} 版本。",
                )
            elif assertion_mismatch:
                dimensions["target_curriculum_version"] = _dimension(
                    MANUAL_REVIEW,
                    value=selected_target_id,
                    reason="selected target curriculum ID 與 applicability assertion 不一致或 assertion 未通過 scope 驗證。",
                )
            else:
                target_curriculum = _REGISTRY.get(selected_target_id)
                trusted_record = trusted_evidence_record or trusted_assertion_record
                if target_curriculum is None:
                    dimensions["target_curriculum_version"] = _dimension(MISSING, value=selected_target_id, reason="指定的目標課表版本不在 registry。")
                elif trusted_record is None and not (assertion_scoped or evidence_reference):
                    dimensions["target_curriculum_version"] = _dimension(
                        MANUAL_REVIEW,
                        value=selected_target_id,
                        curriculum=target_curriculum,
                        reason="目前只有 user-selected version，缺 scoped applicability assertion 或 version evidence reference。",
                    )
                elif trusted_record is None:
                    dimensions["target_curriculum_version"] = _dimension(
                        MANUAL_REVIEW,
                        value=selected_target_id,
                        curriculum=target_curriculum,
                        evidence_reference=evidence_reference,
                        reason="提供的 evidence reference／scoped assertion 未由 server-owned evidence resolver 驗證，不能自動解析。",
                    )
                elif target_curriculum["evidence_state"] == CONFLICTED:
                    dimensions["target_curriculum_version"] = _dimension(
                        CONFLICTED,
                        value=selected_target_id,
                        curriculum=target_curriculum,
                        evidence_reference=evidence_reference,
                        reason="指定版本的官方 assertions 互相衝突，不能自動選邊。",
                    )
                else:
                    dimensions["target_curriculum_version"] = _dimension(
                        RESOLVED,
                        value=selected_target_id,
                        curriculum=target_curriculum,
                        evidence_reference=evidence_reference,
                        reason="目標版本由 server-owned evidence resolver 的適用範圍記錄解析。",
                    )
                    if target_curriculum["coverage_state"] != COMPLETE:
                        warnings.append(
                            f"目標課表 {selected_target_id} 的 course catalog coverage={target_curriculum['coverage_state']}；逐課結果仍需人工複核。"
                        )

    # Keep blocker details structured and also expose compact aliases for
    # clients that only need the first/unique code.
    for name, dimension in dimensions.items():
        status = dimension.get("status")
        if status in {MISSING, MANUAL_REVIEW, CONFLICTED}:
            blockers.append(
                {
                    "code": status,
                    "dimension": name,
                    "reason": dimension.get("reason", ""),
                    "curriculum_id": dimension.get("curriculum_id"),
                }
            )
    primary_curriculum_record = dimensions.get("primary_curriculum", {}).get("curriculum")
    if (
        isinstance(primary_curriculum_record, dict)
        and primary_curriculum_record.get("coverage_state") != COMPLETE
    ):
        blockers.append(
            {
                "code": MANUAL_REVIEW,
                "dimension": "primary_curriculum_coverage",
                "reason": "原主修課表 course catalog 未達 COMPLETE，不得產生逐課 PASS。",
                "curriculum_id": primary_curriculum_record.get("curriculum_id"),
            }
        )
    if target_curriculum is not None and target_curriculum.get("coverage_state") != COMPLETE:
        blockers.append(
            {
                "code": MANUAL_REVIEW,
                "dimension": "target_curriculum_coverage",
                "reason": "目標課表 course catalog 未達 COMPLETE，不得產生逐課 PASS。",
                "curriculum_id": target_curriculum.get("curriculum_id"),
            }
        )
    unique_codes: list[str] = []
    for blocker in blockers:
        if blocker["code"] not in unique_codes:
            unique_codes.append(blocker["code"])
    if CONFLICTED in unique_codes:
        status = CONFLICTED
    elif MISSING in unique_codes:
        status = MISSING
    elif MANUAL_REVIEW in unique_codes:
        status = MANUAL_REVIEW
    else:
        status = RESOLVED
    primary = dimensions.get("primary_curriculum", {})
    target = dimensions.get("target_curriculum_version", {})
    can_pass = (
        status == RESOLVED
        and primary.get("status") == RESOLVED
        and target.get("status") in {RESOLVED, NOT_APPLICABLE}
        and (not primary.get("coverage_state") or primary.get("coverage_state") == COMPLETE)
        and (not target.get("coverage_state") or target.get("coverage_state") == COMPLETE)
    )
    return {
        "status": status,
        "state": status,
        "resolved": can_pass,
        "can_pass": can_pass,
        "blocker": unique_codes[0] if unique_codes else None,
        "blockers": blockers,
        "blocker_codes": unique_codes,
        "warnings": warnings,
        "request": _request_snapshot(request),
        "secondary_kind": secondary_kind,
        "target_role": target_kind if is_double or is_minor else "none",
        "dimensions": dimensions,
        "primary_curriculum": deepcopy(primary.get("curriculum")) if primary.get("curriculum") else None,
        "target_curriculum": deepcopy(target.get("curriculum")) if target.get("curriculum") else None,
        "primary_curriculum_id": primary.get("curriculum_id"),
        "target_curriculum_id": target.get("curriculum_id"),
        "admission_cohort": cohort,
        "application_term": application_term,
        "target_program": _PROGRAM_DISPLAY.get(target_program) if target_program else None,
        "target_track": _TRACK_DISPLAY.get(target_track) if target_track else None,
    }


__all__ = [
    "COMPLETE",
    "CONFLICTED",
    "COVERAGE_NONE",
    "MANUAL_REVIEW",
    "MISSING",
    "NOT_APPLICABLE",
    "PARTIAL",
    "RESOLVED",
    "VERIFIED",
    "get_curriculum",
    "list_curriculum_ids",
    "resolve_rule_context",
]
