"""Versioned Science College handbook rules.

The data lives in ``rules_config.json``.  Matching code deliberately keeps
course identity separate by handbook year and department scope; a similar
name is never treated as an equivalence by itself.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import warnings
from copy import deepcopy

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules_config.json")
ADMISSION_COHORTS = ["111", "112", "113", "114", "115"]

# The detailed course tables in the checked-in JSON currently cover 112--114.
# 111 and 115 are still valid selectable admission cohorts: their verified
# threshold plans are supplied by policy_audit, while detailed course
# matching falls back to the nearest known table and remains review-gated.
_PLANNING_COHORTS = {"111", "115"}
_LEGACY_SOURCE_NAMES = {
    "112": "3-理學院 (112).pdf",
    "113": "3-理學院 (113).pdf",
    "114": "3-理學院 (114).pdf",
}
_EVIDENCE_SOURCE_NAMES = {
    "111": "3-理學院.pdf",
    "112": "3-理學院 (112).pdf",
    "113": "3-理學院 (113).pdf",
    "114": "3-理學院 (114).pdf",
    "115": "3-理學院 (115).pdf",
}


# APC double-major target requirements are represented independently from the
# legacy aggregate ``basic_core``/``other_req`` values.  The IDs are generated
# from the selected admission cohort and target track, so a decision recorded
# for one handbook can never silently be applied to another handbook.
_APC_SPLIT_BASE = (
    ("普通物理學(一)", 3.0, "physics_1"),
    ("普通物理實驗(一)", 1.0, "physics_lab_1"),
    ("普通化學(一)", 3.0, "chemistry_1"),
    ("普通化學實驗(一)", 1.0, "chemistry_lab_1"),
    ("普通物理學(二)", 3.0, "physics_2"),
    ("普通物理實驗(二)", 1.0, "physics_lab_2"),
    ("普通化學(二)", 3.0, "chemistry_2"),
    ("普通化學實驗(二)", 1.0, "chemistry_lab_2"),
)

_APC_115_BASE = {
    "物理組": (
        ("普通物理學(一)", 3.0, "physics_1"),
        ("普通化學(一)", 3.0, "chemistry_1"),
        ("普通物理實驗(一)", 1.0, "physics_lab_1"),
        ("微積分(一)", 3.0, "calculus_1"),
        ("普通物理學(二)", 3.0, "physics_2"),
        ("普通化學(二)", 3.0, "chemistry_2"),
        ("普通物理實驗(二)", 1.0, "physics_lab_2"),
        ("微積分(二)", 3.0, "calculus_2"),
    ),
    "化學組": (
        ("普通物理學(一)", 3.0, "physics_1"),
        ("普通化學(一)", 3.0, "chemistry_1"),
        ("普通化學實驗(一)", 1.0, "chemistry_lab_1"),
        ("微積分(一)", 3.0, "calculus_1"),
        ("普通物理學(二)", 3.0, "physics_2"),
        ("普通化學(二)", 3.0, "chemistry_2"),
        ("普通化學實驗(二)", 1.0, "chemistry_lab_2"),
        ("微積分(二)", 3.0, "calculus_2"),
    ),
}

# These are the 115 handbook's track-specific "other required" catalogues.
# They are intentionally catalogues, not aliases: a source course still needs
# an exact title/credit match or an auditable department-approved decision.
_APC_115_OTHER_CATALOGS = {
    "物理組": {
        "應用科學專題(一)": 1,
        "應用科學專題(二)": 1,
        "物理數學(一)": 3,
        "電磁學(一)": 3,
        "電磁學實驗": 1,
        "力學(一)": 2,
        "電子學(一)": 3,
        "電子學(二)": 3,
        "電子學實驗(一)": 1,
        "物理數學(二)": 3,
        "電磁學(二)": 3,
        "光學": 3,
        "光學實驗": 1,
        "半導體物理": 3,
        "光電子學": 3,
        "近代物理": 3,
        "近代物理實驗": 1,
        "電子學實驗(二)": 1,
        "固態物理(一)": 3,
        "固態物理(二)": 3,
    },
    "化學組": {
        "應用科學專題(一)": 1,
        "應用科學專題(二)": 1,
        "普通化學實驗(一)": 1,
        "普通化學實驗(二)": 1,
        "分析化學(一)": 3,
        "有機化學 (一)": 3,
        "有機化學實驗 (一)": 1,
        "化學數學(一)": 2,
        "物理化學 (一)": 3,
        "物理化學實驗 (一)": 1,
        "有機化學 (二)": 3,
        "有機化學實驗 (二)": 1,
        "物理化學 (二)": 3,
        "物理化學實驗 (二)": 1,
        "材料科學": 3,
        "無機化學(一)": 3,
        "儀器分析(一)": 3,
        "物理化學(三)": 3,
        "生物化學": 3,
        "無機化學(二)": 3,
        "儀器分析實驗": 1,
    },
}


def _load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            config = json.load(handle)
        if not isinstance(config, dict) or not isinstance(config.get("handbooks"), dict):
            raise ValueError("規則檔必須包含 handbooks 物件。")
        if not config["handbooks"]:
            raise ValueError("規則檔至少要包含一個學生手冊版本。")
        return config
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        warnings.warn(f"[學生手冊規則載入失敗] {exc}")
        return {"_meta": {"default_academic_year": "114"}, "shared": {}, "handbooks": {}}


_CFG = _load_config()


def _deep_merge(base, overlay):
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def get_available_handbook_years(include_planning=False):
    """Return detailed handbook years, newest first.

    The default preserves the original API (detailed course tables only).
    ``include_planning=True`` exposes all selectable admission cohorts,
    including years whose verified threshold plan is intentionally
    review-gated rather than a guessed course catalogue.
    """

    configured = sorted((str(year) for year in _CFG.get("handbooks", {})), key=int, reverse=True)
    if include_planning:
        return sorted(set(configured).union(ADMISSION_COHORTS), key=int, reverse=True)
    return configured


def get_available_admission_cohorts():
    """Return all supported admission cohorts in chronological order."""

    return list(ADMISSION_COHORTS)


get_admission_cohort_options = get_available_admission_cohorts
get_supported_cohorts = get_available_admission_cohorts


def get_default_handbook_year():
    configured = str(_CFG.get("_meta", {}).get("default_academic_year", "114"))
    years = get_available_handbook_years()
    if configured in years:
        return configured
    return years[0] if years else configured


def normalize_handbook_year(year=None):
    selected = str(year or get_default_handbook_year()).strip()
    selected = selected.replace("學年度", "").strip()
    if selected not in get_available_handbook_years(include_planning=True):
        raise ValueError(f"不支援的學生手冊年度：{selected}")
    return selected


def _make_planning_handbook(selected):
    """Build a threshold-only compatibility record for 111/115.

    The old implementation copied the nearest configured handbook, which
    silently applied 112 rules to 111 and 114 rules to 115.  Keep the legacy
    shape so callers can still read aggregate thresholds, but deliberately
    leave every course catalogue empty.  The registry and evaluator therefore
    expose ``coverage_state=NONE``/``PARTIAL`` and cannot produce a PASS until
    the cohort-specific source tables are transcribed.
    """

    if selected not in _PLANNING_COHORTS:
        return {}
    if selected == "111":
        domain_elective = 22
        other_elective = 13
    else:
        domain_elective = 20
        other_elective = 27
    handbook = {
        "_meta": {
            "version": selected,
            "academic_year": selected,
            "college": "理學院",
            "source_file": _EVIDENCE_SOURCE_NAMES[selected],
            "evidence_file": _EVIDENCE_SOURCE_NAMES[selected],
            "total_graduation_credits": 128,
            "coverage_state": "NONE",
            "course_catalog_coverage": "NONE",
            "document_warnings": [
                f"{selected} 學年度僅建立官方 aggregate 門檻；未以相鄰年度課程表填入逐課清單，結果需人工複核。"
            ],
        },
        "earth_life_major": {
            "total_req": 85,
            "common_compulsory": {"total_req": 24, "courses": {}},
            "common_alternatives": [],
            "domains": {
                "domain_req": 14,
                "domain_elective_req": domain_elective,
                "other_elective_req": other_elective,
                "地球環境": {"compulsory": {}, "electives": {}},
                "生命科學": {"compulsory": {}, "electives": {}},
            },
            "common_electives": {},
        },
        "apc_rules": {
            "basic_core": {},
            "shared_other_required": {},
            "divisions": {"物理組": {"compulsory": {}}, "化學組": {"compulsory": {}}},
            "minor": {"basic_req": 16, "other_req": 4, "total_req": 20},
            "double_major": {"basic_req": 16, "other_req": 24, "total_req": 40},
        },
        "cs_rules": {
            "department_courses": {},
            "minor": {"compulsory": {}, "compulsory_req": 6, "other_req": 14, "total_req": 20},
            "double_major": {"compulsory": {}, "compulsory_req": 15, "other_req": 25, "total_req": 40},
        },
        "academic_year": selected,
    }
    if selected == "115":
        handbook["apc_rules"] = {
            **handbook["apc_rules"],
            "minor": {"basic_req": 20, "other_req": 0, "total_req": 20},
            "double_major": {"basic_req": 20, "other_req": 20, "total_req": 40},
        }
    return handbook


def get_handbook_config(year=None):
    selected = normalize_handbook_year(year)
    shared = _CFG.get("shared", {})
    version = _CFG.get("handbooks", {}).get(selected) or _make_planning_handbook(selected)
    if not version:
        raise ValueError(f"找不到 {selected} 學年度學生手冊規則。")
    merged = _deep_merge(shared, version)
    merged["academic_year"] = selected
    return merged


def get_rules_meta(year=None):
    selected = normalize_handbook_year(year)
    handbook = get_handbook_config(selected)
    meta = deepcopy(handbook.get("_meta", {}))
    meta.setdefault("version", selected)
    meta.setdefault("academic_year", selected)
    meta.setdefault("last_updated", _CFG.get("_meta", {}).get("last_updated", "N/A"))
    meta["evidence_file"] = _EVIDENCE_SOURCE_NAMES.get(selected, meta.get("source_file", "未標示"))
    # Keep source_file stable for legacy callers while exposing the actual
    # local PDF filename used for new citations.
    if selected in _LEGACY_SOURCE_NAMES:
        meta["source_file"] = _LEGACY_SOURCE_NAMES[selected]
    meta["available_years"] = get_available_handbook_years()
    meta["available_cohorts"] = get_available_admission_cohorts()
    return meta


def get_primary_requirements(cohort, primary_program, track=None):
    """Lazy wrapper for the cohort-aware policy plan API."""

    from policy_audit import get_primary_requirements as _get_primary_requirements

    return _get_primary_requirements(cohort, primary_program, track)


def get_double_major_structure(cohort, target_program, track=None):
    """Lazy wrapper for verified double-major structure facts."""

    from policy_audit import get_double_structure

    return get_double_structure(cohort, target_program, track)


get_cohort_requirements = get_primary_requirements
get_primary_plan = get_primary_requirements


def get_rule_sets(year=None):
    """Build the engine-facing rule dictionaries for one handbook year."""
    handbook = get_handbook_config(year)
    common = handbook["university_common"]
    earth = handbook["earth_life_major"]
    domains = earth["domains"]

    university_common = {
        "compulsory": deepcopy(common["compulsory"]["courses"]),
        "category_domains": deepcopy(common["ge_categories"]["categories"]),
        "per_category_req": float(common["ge_categories"].get("per_category_req", 4)),
    }
    earth_life_major = {
        "common_compulsory": deepcopy(earth["common_compulsory"]["courses"]),
        "common_alternatives": deepcopy(earth.get("common_alternatives", [])),
        "domains": {
            name: deepcopy(data["compulsory"])
            for name, data in domains.items()
            if isinstance(data, dict) and "compulsory" in data
        },
        "domain_electives": {
            name: deepcopy(data.get("electives", {}))
            for name, data in domains.items()
            if isinstance(data, dict) and "compulsory" in data
        },
    }
    earth_life_major["domain_electives"]["common_electives"] = deepcopy(earth.get("common_electives", {}))

    apc_target_requirements = {}
    for target_track in ("物理組", "化學組"):
        for target_type in ("雙主修", "輔系"):
            apc_target_requirements[f"{target_track}:{target_type}"] = get_apc_target_requirements(
                handbook["academic_year"], target_track, target_type
            )
    return {
        "academic_year": handbook["academic_year"],
        "university_common": university_common,
        "earth_life_major": earth_life_major,
        "apc_rules": deepcopy(handbook["apc_rules"]),
        "cs_rules": deepcopy(handbook["cs_rules"]),
        "course_aliases": deepcopy(handbook.get("course_aliases", {})),
        "document_warnings": deepcopy(handbook.get("_meta", {}).get("document_warnings", [])),
        "apc_target_requirements": apc_target_requirements,
    }


def _apc_target_slug(value):
    """Return a stable, ASCII-like component for an APC target ID."""

    mapping = {
        "物理組": "physics",
        "電子物理": "physics",
        "化學組": "chemistry",
        "應用化學": "chemistry",
        "普通物理學(一)": "physics_1",
        "普通物理學(二)": "physics_2",
        "普通物理實驗(一)": "physics_lab_1",
        "普通物理實驗(二)": "physics_lab_2",
        "普通化學(一)": "chemistry_1",
        "普通化學(二)": "chemistry_2",
        "普通化學實驗(一)": "chemistry_lab_1",
        "普通化學實驗(二)": "chemistry_lab_2",
        "微積分(一)": "calculus_1",
        "微積分(二)": "calculus_2",
        "其餘必修課程": "other_required",
    }
    if value in mapping:
        return mapping[value]
    text = re.sub(r"[^0-9A-Za-z]+", "_", str(value or "").strip()).strip("_").lower()
    return text or "requirement"


def apc_target_requirement_id(cohort, track, requirement_name, program_type="雙主修"):
    """Build the stable ID used by the source-attempt binding workflow."""

    selected = normalize_handbook_year(cohort)
    track_slug = _apc_target_slug(track)
    program_slug = "dm" if program_type == "雙主修" else "minor" if program_type == "輔系" else _apc_target_slug(program_type)
    requirement_slug = _apc_target_slug(requirement_name)
    return f"apc.{program_slug}.{selected}.{track_slug}.{requirement_slug}"


def get_apc_target_requirements(cohort, track="化學組", program_type="雙主修"):
    """Return auditable APC target rows for one cohort and track.

    The legacy engine's aggregate quota fields remain available for backward
    compatibility.  This API is the source of truth for new course-level
    decisions: every course row and the remaining named/generic quota have a
    cohort-scoped ID, while the catalogue stays exact-title/exact-credit.
    """

    selected = normalize_handbook_year(cohort)
    track_text = str(track or "化學組").strip()
    if track_text in {"電子物理", "物理", "物理組", "物化系物理組"}:
        selected_track = "物理組"
    elif track_text in {"應用化學", "化學", "化學組", "物化系化學組"}:
        selected_track = "化學組"
    else:
        raise ValueError(f"不支援的物化系組別：{track}")
    if program_type not in {"雙主修", "輔系"}:
        raise ValueError(f"不支援的物化系修讀身分：{program_type}")

    handbook = get_handbook_config(selected)
    apc = handbook.get("apc_rules", {})
    program_key = "double_major" if program_type == "雙主修" else "minor"
    program_rules = apc.get(program_key, {})
    if selected == "115":
        base_rows = _APC_115_BASE[selected_track]
        catalogue = _APC_115_OTHER_CATALOGS[selected_track]
        # The 115 handbook says the named base list is 20 credits for both
        # minor/double-major tables; only the double-major table adds the
        # remaining 20-credit other-required quota.
        other_required = 20.0 if program_type == "雙主修" else 0.0
        evidence = "VERIFIED" if selected_track == "化學組" else "MANUAL_REVIEW"
        warnings = [] if evidence == "VERIFIED" else ["115 電子物理組目標逐課清單仍需系所人工核對。"]
    else:
        base_rows = _APC_SPLIT_BASE
        catalogue = dict(apc.get("shared_other_required", {}))
        catalogue.update(apc.get("divisions", {}).get(selected_track, {}).get("compulsory", {}))
        other_required = float(program_rules.get("other_req", 0.0) or 0.0)
        evidence = "VERIFIED"
        warnings = []

    requirements = []
    for name, credits, slug in base_rows:
        requirements.append(
            {
                "id": apc_target_requirement_id(selected, selected_track, name, program_type),
                "requirement_id": apc_target_requirement_id(selected, selected_track, name, program_type),
                "name": name,
                "credits": float(credits),
                "bucket": "base",
                "kind": "course",
                "evidence": evidence,
                "allow_combined_lab_source": False,
            }
        )
    quota_name = f"{selected_track}其餘必修課程"
    quota_id = apc_target_requirement_id(selected, selected_track, "其餘必修課程", program_type)
    requirements.append(
        {
            "id": quota_id,
            "requirement_id": quota_id,
            "name": quota_name,
            "credits": float(other_required),
            "bucket": "other_required",
            "kind": "quota",
            "evidence": evidence,
            "catalog": [
                {"name": str(name), "credits": float(credits)} for name, credits in catalogue.items()
            ],
        }
    )
    return {
        "cohort": selected,
        "program": "物化",
        "track": selected_track,
        "program_type": program_type,
        "total_required": float(program_rules.get("total_req", 40.0 if program_type == "雙主修" else 20.0)),
        "base_required": sum(row["credits"] for row in requirements if row["bucket"] == "base"),
        "other_required": float(other_required),
        "requirements": requirements,
        "course_requirements": {
            row["name"]: row["credits"] for row in requirements if row["kind"] == "course"
        },
        "other_required_catalog": catalogue,
        "evidence": evidence,
        "warnings": warnings,
    }


get_target_requirements = get_apc_target_requirements
get_apc_requirement_catalog = get_apc_target_requirements


def get_credit_requirements(program="單主修", target_dept="", handbook_year=None):
    handbook = get_handbook_config(handbook_year)
    meta = handbook.get("_meta", {})
    common = handbook["university_common"]
    ge = common["ge_categories"]
    major = handbook["earth_life_major"]
    domains = major["domains"]
    requirements = {
        "total": float(meta.get("total_graduation_credits", 128)),
        "common_total": float(common.get("total_req", 28)),
        "common_compulsory": float(common["compulsory"].get("total_req", 10)),
        "ge_categories_total": float(ge.get("total_req", 16)),
        "ge_per_category": float(ge.get("per_category_req", 4)),
        "ge_common_elective": float(common.get("ge_common_elective_req", 2)),
        "major_total": float(major.get("total_req", 85)),
        "major_common_compulsory": float(major["common_compulsory"].get("total_req", 24)),
        "domain_compulsory": float(domains.get("domain_req", 14)),
        "domain_elective": float(domains.get("domain_elective_req", 20)),
        "major_other_elective": float(domains.get("other_elective_req", 27)),
        "free_elective": float(handbook["free_elective"].get("total_req", 15)),
        "pe_semesters": int(handbook["physical_education"].get("semesters_required", 4)),
        "target_total": 0.0,
    }
    if program in {"雙主修", "輔系"}:
        program_key = "double_major" if program == "雙主修" else "minor"
        target_rules = handbook["cs_rules"] if "資科系" in target_dept else handbook["apc_rules"]
        requirements["target_total"] = float(target_rules[program_key]["total_req"])
    return requirements


def normalize_course_name(name):
    """Normalize typography only; never erase semantic course identity.

    NFKC safely aligns full-width punctuation and Unicode Roman glyphs.  The
    sequence suffix, words such as ``實驗``/``含實驗``, and course subtitles
    are otherwise preserved.  In particular, ``微積分`` remains distinct from
    ``微積分(I)`` and ``微積分(II)``.
    """
    if not name:
        return ""
    value = unicodedata.normalize("NFKC", str(name)).strip()
    value = value.replace("：", ":")
    value = re.sub(r"\[(?:◇|※|◎|§|▲|╳)\]", "", value)
    value = re.sub(r"\s+", "", value)
    value = value.replace("英文(I)", "英文(一)").replace("英文(II)", "英文(二)").replace("英文(III)", "英文(三)")
    value = value.replace("國文(I)", "國文(一)").replace("國文(II)", "國文(二)")
    value = re.sub(r"^(英文\([一二三]\))[:-].*", r"\1", value)
    value = re.sub(r"\((?![IVXivx])[A-Za-z甲乙丙丁]\)$", "", value)
    if re.fullmatch(r"[\d./%]+", value):
        return ""
    if not re.search(r"[\u4e00-\u9fffA-Za-z]", value) and re.search(r"\d", value):
        return ""
    return value


def get_aliases(rule_name, handbook_year=None, scope="university_common"):
    """Return aliases explicitly declared inside one department scope."""
    rule_sets = get_rule_sets(handbook_year)
    aliases = rule_sets.get("course_aliases", {}).get(scope, {}).get(rule_name, [])
    return [rule_name, *aliases]


def validate_rule_collisions(year=None):
    """Check duplicate aliases inside a single scope; cross-scope names stay separate."""
    selected = normalize_handbook_year(year)
    aliases = get_rule_sets(selected).get("course_aliases", {})
    collisions = []
    for scope, mapping in aliases.items():
        owner = {}
        for official, values in mapping.items():
            for alias in [official, *values]:
                key = normalize_course_name(alias)
                previous = owner.get(key)
                if previous and previous != official:
                    collisions.append({"scope": scope, "alias": alias, "courses": [previous, official]})
                owner[key] = official
    return collisions
