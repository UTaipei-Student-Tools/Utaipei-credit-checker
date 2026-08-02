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


def get_available_handbook_years():
    """Return handbook academic years, newest first."""
    return sorted((str(year) for year in _CFG.get("handbooks", {})), key=int, reverse=True)


def get_default_handbook_year():
    configured = str(_CFG.get("_meta", {}).get("default_academic_year", "114"))
    years = get_available_handbook_years()
    if configured in years:
        return configured
    return years[0] if years else configured


def normalize_handbook_year(year=None):
    selected = str(year or get_default_handbook_year()).strip()
    selected = selected.replace("學年度", "").strip()
    if selected not in get_available_handbook_years():
        raise ValueError(f"不支援的學生手冊年度：{selected}")
    return selected


def get_handbook_config(year=None):
    selected = normalize_handbook_year(year)
    shared = _CFG.get("shared", {})
    version = _CFG["handbooks"][selected]
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
    meta["available_years"] = get_available_handbook_years()
    return meta


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
