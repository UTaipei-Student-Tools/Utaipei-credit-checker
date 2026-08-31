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
    """Build a review-gated compatibility table for 111/115.

    This enables the old parser/engine callers to continue operating while
    policy_audit supplies the verified threshold facts.  It is never treated
    as proof that a course identity is valid for the selected cohort.
    """

    base_year = "112" if selected == "111" else "114"
    if base_year not in _CFG.get("handbooks", {}):
        return {}
    handbook = deepcopy(_CFG["handbooks"][base_year])
    meta = handbook.setdefault("_meta", {})
    meta.update(
        {
            "version": selected,
            "academic_year": selected,
            "source_file": _EVIDENCE_SOURCE_NAMES[selected],
            "evidence_file": _EVIDENCE_SOURCE_NAMES[selected],
            "document_warnings": [
                f"{selected} 學年度目前採核對過的門檻規劃；逐課課號／課程表資料尚未完整建置，結果需人工複核。"
            ],
        }
    )
    handbook["academic_year"] = selected
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

    return {
        "academic_year": handbook["academic_year"],
        "university_common": university_common,
        "earth_life_major": earth_life_major,
        "apc_rules": deepcopy(handbook["apc_rules"]),
        "cs_rules": deepcopy(handbook["cs_rules"]),
        "course_aliases": deepcopy(handbook.get("course_aliases", {})),
        "document_warnings": deepcopy(handbook.get("_meta", {}).get("document_warnings", [])),
    }


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
