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

# The APC chemistry double-major table is one of the few target tables that
# can be transcribed safely from the checked-in handbook page images.  Keep
# this list separate from ``rules_config.json``: that file is an older
# aggregate/primary-rule source and must not make a neighbouring cohort's
# rows appear in this target catalogue.
_APC_CHEMISTRY_DM_ROWS = {
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
_APC_CHEMISTRY_DM_PAGE = {
    "113": {"pdf_page": 24, "printed_page": 23},
    "114": {"pdf_page": 24, "printed_page": 23},
    "115": {"pdf_page": 25, "printed_page": 24},
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
    prefix = "primary" if kind == "primary" else "target:double_major"
    parts = [prefix, cohort, program]
    if track and ((program == "earth") or (program == "apc")):
        parts.append(track)
    return ":".join(parts)


def _citation(cohort: str, pages: str, label: str, *, url: str | None = None) -> dict[str, str]:
    return {
        "file": _source_file(cohort),
        "pages": pages,
        "label": label,
        "url": url or _HANDBOOK_URLS.get(cohort, ""),
    }


def _apc_chemistry_page(cohort: str) -> dict[str, Any]:
    page = _APC_CHEMISTRY_DM_PAGE[cohort]
    return {
        **page,
        "pages": f"PDF p.{page['pdf_page']}（印刷 p.{page['printed_page']}）",
        "source_reference": f"handbook:{cohort}:pdf:{page['pdf_page']}",
    }


def _apc_chemistry_row_assertion_id(cohort: str, slug: str) -> str:
    return f"apc.dm.{cohort}.chemistry.{slug}"


def _apc_chemistry_catalog_assertions(cohort: str) -> list[dict[str, Any]]:
    """Return row-level assertions for the readable chemistry DM page.

    The footer's generic ``其餘必修`` amount is an official aggregate, but the
    page does not provide a complete named course pool in the local evidence.
    Keep that missing semantic as an assertion instead of treating a guessed
    primary catalogue as the target's course list.
    """

    page = _apc_chemistry_page(cohort)
    label = f"{cohort} 學年度物化系應用化學組雙主修表"
    assertions: list[dict[str, Any]] = []
    for name, credits, _component, slug in _APC_CHEMISTRY_DM_ROWS[cohort]:
        assertions.append(
            _assertion(
                _apc_chemistry_row_assertion_id(cohort, slug),
                cohort,
                page["pages"],
                f"雙主修列項：{name}",
                credits,
                label=label,
            )
        )
    other_credits = 20 if cohort == "115" else 24
    assertions.append(
        _assertion(
            f"apc.dm.{cohort}.chemistry.other_catalog",
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
            "表尾其餘必修課程應修畢",
            other_credits,
            label=label,
        )
    )
    return assertions


def _apc_chemistry_catalog(cohort: str) -> list[dict[str, Any]]:
    """Build exact visible APC chemistry double-major rows for one cohort.

    This intentionally returns the eight named rows plus one generic footer
    quota.  The quota is not expanded with 115 primary/track courses because
    that would be a false claim about the target page's missing choice pool.
    """

    page = _apc_chemistry_page(cohort)
    source = _citation(cohort, page["pages"], "物化系應用化學組雙主修課程表")
    rows: list[dict[str, Any]] = []
    for name, credits, component, slug in _APC_CHEMISTRY_DM_ROWS[cohort]:
        requirement_id = _apc_chemistry_row_assertion_id(cohort, slug)
        source_reference = f"{page['source_reference']}:row:{slug}"
        provenance = {
            "assertion_id": requirement_id,
            "source_type": "official_handbook",
            "source_file": source["file"],
            "source_url": source["url"],
            "pdf_page": page["pdf_page"],
            "printed_page": page["printed_page"],
            "source_reference": source_reference,
            "raw_title": name,
            "claim": f"雙主修列項：{name}，{credits:g} 學分",
            "evidence_state": VERIFIED,
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
                "track": "chemistry",
                "track_slug": "chemistry",
                "track_name": "應用化學",
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
                "official_course_identity": f"{cohort}:apc:chemistry:{slug}",
            }
        )

    other_credits = 20.0 if cohort == "115" else 24.0
    quota_slug = "other_required"
    quota_requirement_id = f"apc.dm.{cohort}.chemistry.{quota_slug}"
    quota_assertion_id = f"apc.dm.{cohort}.other{int(other_credits)}"
    quota_reference = f"{page['source_reference']}:footer:{quota_slug}"
    quota_provenance = {
        "assertion_id": quota_assertion_id,
        "source_type": "official_handbook",
        "source_file": source["file"],
        "source_url": source["url"],
        "pdf_page": page["pdf_page"],
        "printed_page": page["printed_page"],
        "source_reference": quota_reference,
        "raw_title": "其餘必修課程",
        "claim": f"表尾其餘必修課程應修畢 {int(other_credits)} 學分",
        "evidence_state": VERIFIED,
        "extraction_method": "handbook_text_and_visual_crosscheck",
        "named_course_pool": "not_transcribed",
    }
    rows.append(
        {
            "id": quota_requirement_id,
            "requirement_id": quota_requirement_id,
            "name": "其餘必修課程",
            "display_name": "應用化學組其餘必修課程",
            "raw_title": "其餘必修課程",
            "credits": other_credits,
            "bucket": "other_required",
            "kind": "quota",
            "requirement_type": "credit_quota",
            "choice_group": "other_required_pool",
            "choice_rule": "department_approved_named_course_pool",
            "track": "chemistry",
            "track_slug": "chemistry",
            "track_name": "應用化學",
            "cohort": cohort,
            "curriculum_version": cohort,
            "component": "quota",
            "component_type": "quota",
            "component_label": "其餘必修額度",
            "lecture_or_lab": "quota",
            "is_lab": False,
            "is_zero_credit": False,
            "allow_combined_lab_source": False,
            "evidence": VERIFIED,
            "evidence_state": VERIFIED,
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
            "official_course_identity": f"{cohort}:apc:chemistry:{quota_slug}",
            "catalog": [],
            "named_course_pool_state": PARTIAL,
            "missing_semantics": [
                "官方頁面未在本地證據中提供可執行的其餘必修完整課名清單。",
                "其餘必修的選擇規則與系所核准條件仍需人工確認。",
            ],
        }
    )
    return rows


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
) -> dict[str, Any]:
    source = _citation(cohort, pages, label, url=url)
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
        return [
            _assertion("cs.primary.114.split10-16-2", cohort, "PDF p.108", "共同課程分配", "10/16/2", label="資科系學分規劃表"),
            _assertion("cs.primary.114.split8-16-4", cohort, "PDF p.110", "共同課程分配", "8/16/4", label="資科系課程說明"),
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
        pages = {"111": "PDF p.19", "112": "PDF p.19", "113": "PDF p.24", "114": "PDF p.24", "115": "PDF p.25"}[cohort]
        if cohort == "115":
            base, other = 20, 20
        else:
            base, other = 16, 24
        assertions = [
            _assertion(f"apc.dm.{cohort}.base{base}", cohort, pages, "物化雙主修基礎列項", base, label="物化系雙主修表"),
            _assertion(f"apc.dm.{cohort}.other{other}", cohort, pages, "物化雙主修其餘必修", other, label="物化系雙主修表"),
        ]
        if track == "chemistry" and cohort in {"113", "114", "115"}:
            # Preserve the aggregate assertions above while exposing the
            # exact visible target rows and the missing named-pool semantic.
            # The returned evidence state stays VERIFIED because the official
            # claims are readable; coverage remains PARTIAL below.
            row_assertions = _apc_chemistry_catalog_assertions(cohort)
            existing_ids = {item["id"] for item in assertions}
            assertions.extend(item for item in row_assertions if item["id"] not in existing_ids)
            warning = (
                "可見八項與其餘必修24 aggregate 已核對；官方其餘必修完整命名目錄與選擇規則尚未轉錄，"
                "coverage=PARTIAL，需人工複核。"
                if cohort in {"113", "114"}
                else "可見八項（含微積分(一)、微積分(二)）與其餘必修20 aggregate 已核對；官方其餘必修完整命名目錄與選擇規則尚未轉錄，coverage=PARTIAL，需人工複核。"
            )
            return assertions, VERIFIED, PARTIAL, warning
        if cohort == "115":
            return assertions, VERIFIED, PARTIAL, "aggregate 20＋20 可核對，但化學／物理組雙主修逐課目錄尚未建置。"
        return assertions, VERIFIED, PARTIAL, "雙主修 aggregate 可核對，但逐課目錄尚未完整建置。"
    # CS 111–114 have readable aggregate rows, but only the older configured
    # rule table can be used for exact names.  Keep the evidence independent.
    pages = {"111": "PDF pp.121–122", "112": "PDF pp.116–117", "113": "PDF pp.111–112", "114": "PDF pp.116–117", "115": "PDF p.127"}[cohort]
    assertions = [
        _assertion(f"cs.dm.{cohort}.required15", cohort, pages, "資科雙主修必修", 15, label="資科系雙主修表"),
        _assertion(f"cs.dm.{cohort}.other25", cohort, pages, "資科雙主修其他課程", 25, label="資科系雙主修表"),
    ]
    return assertions, VERIFIED, PARTIAL, "aggregate 15＋25 可核對，但 required/other 與申請核准語義尚未完整建置。"


def _course_catalog(program: str, cohort: str, kind: str, track: str | None, coverage: str) -> list[dict[str, Any]]:
    """Build only catalogs that are genuinely present in the local data.

    A planning cohort is intentionally *not* filled from its neighbour.  The
    configured 112–114 tables are safe to expose as a compatibility catalog;
    their values are copied from the checked-in source configuration, not used
    to claim evidence for another cohort.
    """

    if coverage == COVERAGE_NONE:
        return []
    if kind == "double_major_target" and program == "apc" and track == "chemistry" and cohort in {"113", "114", "115"}:
        # This is an intentionally partial but exact transcription: eight
        # visible named rows plus the official footer quota.  Do not populate
        # the quota from a primary/legacy catalogue that the target page does
        # not identify as its complete choice pool.
        return _apc_chemistry_catalog(cohort)
    if kind == "double_major_target" and not (program == "cs" and cohort in {"112", "113", "114"}):
        return []
    handbook = _RULES.get("handbooks", {}).get(cohort, {})
    if not isinstance(handbook, dict):
        return []
    rows: list[dict[str, Any]] = []
    if program == "earth":
        major = handbook.get("earth_life_major", {})
        for section, data in (("common", major.get("common_compulsory", {})), ("domains", major.get("domains", {}))):
            if section == "common":
                data = data.get("courses", {}) if isinstance(data, dict) else {}
                for name, credits in data.items():
                    rows.append({"name": name, "credits": credits, "bucket": "common_compulsory"})
            elif isinstance(data, dict):
                for domain, domain_data in data.items():
                    for name, credits in (domain_data.get("compulsory", {}) if isinstance(domain_data, dict) else {}).items():
                        rows.append({"name": name, "credits": credits, "bucket": f"{domain}:compulsory"})
    elif program == "cs":
        cs = handbook.get("cs_rules", {})
        data = cs.get("department_courses", {}) if isinstance(cs, dict) else {}
        double_major = cs.get("double_major", {}) if isinstance(cs, dict) else {}
        required_names = set(double_major.get("compulsory", {})) if isinstance(double_major, dict) else set()
        for name, credits in data.items():
            bucket = "double_major_required" if kind == "double_major_target" and name in required_names else "department"
            rows.append({"name": name, "credits": credits, "bucket": bucket})
    if coverage == PARTIAL:
        return rows[: min(len(rows), 8)]
    return rows


def _build_curriculum(kind: str, cohort: str, program: str, track: str | None) -> dict[str, Any]:
    curriculum_id = _canonical_id(kind, cohort, program, track)
    is_primary = kind == "primary"
    if is_primary:
        assertions = _primary_assertions(program, cohort, track)
        conflict = bool(_primary_conflict_assertions(program, cohort))
        evidence_state = CONFLICTED if conflict else VERIFIED
        # The configured Earth and CS rows are only a partial compatibility
        # catalog: alternatives, track semantics and zero-credit/choice
        # handling are not represented in each executable row yet.
        if program == "earth" and cohort in {"112", "113", "114"}:
            coverage = PARTIAL
        elif program == "cs" and cohort in {"112", "113"}:
            coverage = PARTIAL
        elif program == "apc" and cohort in {"112", "113"}:
            coverage = PARTIAL
        else:
            coverage = PARTIAL if cohort not in {"111", "115"} else COVERAGE_NONE
        warning = "官方表格存在衝突，不能自動宣告主修門檻完整。" if conflict else ""
        if cohort in {"111", "115"}:
            warning = "此入學 cohort 僅有門檻相容資料，未以相鄰年度課程表補猜逐課清單。"
    else:
        assertions, evidence_state, coverage, warning = _double_assertions(program, cohort, track)
    thresholds = _base_thresholds(program, cohort, track) if is_primary else _double_thresholds(program, cohort, track)
    catalog = _course_catalog(program, cohort, kind, track, coverage)
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
    blockers: list[dict[str, Any]] = []
    if evidence_state == CONFLICTED:
        blockers.append({"code": CONFLICTED, "reason": warning or "官方來源 assertion 互相衝突。"})
    if coverage != COMPLETE:
        blockers.append({"code": MANUAL_REVIEW, "reason": f"課程目錄 coverage={coverage}，不足以安全逐課判定。"})
    return {
        "id": curriculum_id,
        "curriculum_id": curriculum_id,
        "kind": "primary" if is_primary else "double_major_target",
        "type": "primary" if is_primary else "target",
        "curriculum_kind": "primary" if is_primary else "double_major_target",
        "version": cohort,
        "curriculum_version": cohort,
        "admission_cohort": cohort if is_primary else None,
        "program": _PROGRAM_DISPLAY[program],
        "program_slug": program,
        "track": _TRACK_DISPLAY.get(track) if track else None,
        "track_slug": track,
        "program_type": "單主修" if is_primary else _DOUBLE_MAJOR,
        "thresholds": thresholds,
        "requirements": deepcopy(thresholds),
        "total_required": thresholds.get("total_required", thresholds.get("total")),
        "base_required": thresholds.get("base_required") if not is_primary else None,
        "other_required": thresholds.get("other_required") if not is_primary else None,
        "course_catalog": catalog,
        "source_assertions": assertions,
        "assertions": deepcopy(assertions),
        "citations": citations,
        "source_file": _source_file(cohort),
        "source_url": _HANDBOOK_URLS.get(cohort, ""),
        "evidence_state": evidence_state,
        "coverage_state": coverage,
        "aggregate_status": aggregate_status,
        "status": status,
        "pass_eligible": status == VERIFIED and coverage == COMPLETE and evidence_state == VERIFIED,
        "warnings": [warning] if warning else [],
        "blockers": blockers,
        "legacy_planning": cohort in {"111", "115"} and is_primary,
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
    return result


_REGISTRY = _build_registry()


def _normalize_kind(value: Any) -> str | None:
    text = _normalize_text(value).lower().replace("-", "_")
    if text in {"primary", "major", "home", "主修"}:
        return "primary"
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
    expected_track = _track_slug(track, expected_program) if track not in (None, "") else None
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
    if parsed_program == "earth" and parsed_track not in {"earth_environment", "life_science"}:
        if parsed_track is None:
            parsed_track = "earth_environment"
        else:
            return None
    if parsed_program == "apc" and parsed_track not in {"physics", "chemistry"}:
        return None
    if parsed_program in {"cs", "math"}:
        if parsed_track is not None:
            return None
        parsed_track = None
    expected_kind = _normalize_kind(kind) if kind is not None else None
    expected_cohort = _normalize_cohort(cohort) if cohort not in (None, "") else None
    expected_program = _program_slug(program) if program not in (None, "") else None
    expected_track = _track_slug(track, expected_program) if track not in (None, "") else None
    if kind is not None and (expected_kind is None or parsed_kind != expected_kind):
        return None
    if expected_cohort is not None and parsed_cohort != expected_cohort:
        return None
    if expected_program is not None and parsed_program != expected_program:
        return None
    if track not in (None, "") and (expected_track is None or parsed_track != expected_track):
        return None
    canonical = _canonical_id("primary" if parsed_kind == "primary" else "double_major_target", parsed_cohort, parsed_program, parsed_track)
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
    for curriculum_id, item in _REGISTRY.items():
        if kind and item["kind"] != kind and not (kind == "target" and item["kind"] == "double_major_target"):
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


def _assertion_curriculum_id(assertion: Any, *, cohort: str | None, program: str | None, track: str | None) -> str | None:
    if not isinstance(assertion, dict):
        return None
    value = _request_value(assertion, "curriculum_id", "target_curriculum_id", "id", "version")
    if value in (None, ""):
        return None
    # A target curriculum's version is independent from the student's
    # admission cohort.  The assertion is checked against the selected target
    # identity later, so do not constrain its version here.
    return _parse_id(value, kind="double_major_target", cohort=None, program=program, track=track)


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
        kind="double_major_target",
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
    record_track = _track_slug(record_track_value, record_program)
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
    "program_type",
    "program",
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
    program_type = str(_request_value(request, "program_type", "program") or "單主修").strip()
    is_double = program_type == _DOUBLE_MAJOR or str(program_type).lower() in {"double_major", "double", "dm"}
    target_program, target_track = _target_program_and_track(request)

    dimensions: dict[str, dict[str, Any]] = {}
    blockers: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not cohort:
        dimensions["admission_cohort"] = _dimension(MISSING, reason="缺少 admission_cohort；不能選擇原主修手冊。")
    else:
        dimensions["admission_cohort"] = _dimension(RESOLVED, value=cohort, reason="已由使用者明確提供入學 cohort。")
    if not primary_program:
        dimensions["primary_curriculum"] = _dimension(MISSING, reason="缺少原主修系所／組別。")
    elif not cohort:
        dimensions["primary_curriculum"] = _dimension(MISSING, value=None, reason="缺 admission_cohort，不能解析原主修版本。")
    else:
        primary_id = _canonical_id("primary", cohort, primary_program, primary_track)
        primary = _REGISTRY.get(primary_id)
        if primary is None:
            dimensions["primary_curriculum"] = _dimension(MISSING, reason=f"找不到原主修課表：{primary_id}。")
        else:
            primary_status = CONFLICTED if primary["evidence_state"] == CONFLICTED else RESOLVED
            dimensions["primary_curriculum"] = _dimension(
                primary_status,
                value=primary_id,
                curriculum=primary,
                reason="原主修課表由 admission_cohort 與主修系所解析。",
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
    elif is_double:
        dimensions["application_event"] = _dimension(MISSING, reason="雙主修缺少 application term／申請事件證據。")
    else:
        dimensions["application_event"] = _dimension(NOT_APPLICABLE, reason="單主修不需要雙主修申請事件。")

    target_curriculum: dict[str, Any] | None = None
    if not is_double:
        dimensions["target_program"] = _dimension(NOT_APPLICABLE, reason="目前不是雙主修規劃。")
        dimensions["target_curriculum_version"] = _dimension(NOT_APPLICABLE, reason="單主修不需要目標課表版本。")
    elif not target_program:
        dimensions["target_program"] = _dimension(MISSING, reason="缺少雙主修目標系所／組別。")
        dimensions["target_curriculum_version"] = _dimension(MISSING, reason="未能建立目標系所，故不能解析 target curriculum version。")
    else:
        target_id_value = _request_value(request, "target_curriculum_version", "target_curriculum_id", "target_version")
        assertion = _applicability_assertion(request)
        assertion_scoped = _is_scoped_assertion(assertion, request)
        assertion_id = _assertion_curriculum_id(assertion, cohort=cohort, program=target_program, track=target_track)
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
            dimensions["target_program"] = _dimension(MISSING, value=target_program, reason="物化雙主修必須明確指定化學組或物理組。")
            dimensions["target_curriculum_version"] = _dimension(MISSING, reason="缺少物化雙主修組別，不能解析目標課表版本。")
        else:
            dimensions["target_program"] = _dimension(RESOLVED, value=target_program, reason="目標系所／組別已由使用者提供。")
            # Target curriculum version is an independent dimension.  The
            # selected target may be from a different handbook version than
            # the student's admission cohort.
            selected_target_id = _parse_id(
                target_id_value,
                kind="double_major_target",
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
            )
            trusted_assertion_record = _resolve_evidence_record(
                evidence_resolver,
                assertion,
                request=request,
                selected_curriculum_id=selected_target_id,
                cohort=cohort,
                program=target_program,
                track=target_track,
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
                    reason="雙主修 target curriculum version 必須明確提供；不能由 admission_cohort 或 application term 推定。",
                )
            elif selected_target_id is None:
                dimensions["target_curriculum_version"] = _dimension(
                    MISSING,
                    value=target_id_value,
                    reason="指定的 target curriculum ID 必須是符合目標系所／組別的 double_major_target 版本。",
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
