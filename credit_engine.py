# -*- coding: utf-8 -*-
"""
Graduation Credit Evaluation Engine — v2
新增：體育追蹤、通識/校必修分離、自由選修正確溢流
"""

from handbook_rules import (
    normalize_course_name,
    UNIVERSITY_COMMON,
    EARTH_LIFE_MAJOR,
    APC_RULES,
    CS_RULES
)

import re
import logging

# 匹配除錯開關：出問題時可打開以取得匹配決策輸出
DEBUG_MATCHING = False

def dbg(msg):
    if DEBUG_MATCHING:
        try:
            print("[MATCH_DBG]", msg)
        except Exception:
            pass


def _collect_rule_names():
    """收集所有系、雙主修與輔系的課名（normalized），用於排除不該被當作通識的課程。"""
    names = set()
    try:
        # Earth/Life major
        for k in EARTH_LIFE_MAJOR.get("common_compulsory", {}).keys():
            names.add(normalize_course_name(k))
        for domain, rules in EARTH_LIFE_MAJOR.get("domains", {}).items():
            for k in rules.keys():
                names.add(normalize_course_name(k))
        for d, lst in EARTH_LIFE_MAJOR.get("domain_electives", {}).items():
            for it in lst:
                names.add(normalize_course_name(it))

        # APC rules
        for k in APC_RULES.get("basic_core", {}).keys():
            names.add(normalize_course_name(k))
        for div, data in APC_RULES.get("divisions", {}).items():
            for k in data.get("compulsory", {}).keys():
                names.add(normalize_course_name(k))

        # CS rules
        for prog in ["double_major", "minor"]:
            for k in CS_RULES.get(prog, {}).get("compulsory", {}).keys():
                names.add(normalize_course_name(k))
    except Exception:
        pass
    return names


_RULE_NAMES_SET = _collect_rule_names()


def _collect_major_names():
    """收集地生系（主修）的所有必選修課名，用於在雙輔系判定中排除本系課程。"""
    names = set()
    try:
        for k in EARTH_LIFE_MAJOR.get("common_compulsory", {}).keys():
            names.add(normalize_course_name(k))
        for domain, rules in EARTH_LIFE_MAJOR.get("domains", {}).items():
            for k in rules.keys():
                names.add(normalize_course_name(k))
        for d, lst in EARTH_LIFE_MAJOR.get("domain_electives", {}).items():
            for it in lst:
                names.add(normalize_course_name(it))
    except Exception:
        pass
    return names

_MAJOR_NAMES_SET = _collect_major_names()


def _collect_major_compulsory():
    """收集地生系（主修）的所有必修課名，用於在雙輔系判定中確保必修不被搶佔。"""
    names = set()
    try:
        for k in EARTH_LIFE_MAJOR.get("common_compulsory", {}).keys():
            names.add(normalize_course_name(k))
        for domain, rules in EARTH_LIFE_MAJOR.get("domains", {}).items():
            for k in rules.keys():
                names.add(normalize_course_name(k))
    except Exception:
        pass
    return names

_MAJOR_COMPULSORY_SET = _collect_major_compulsory()


def _is_in_program_rules(name_norm, raw_norm):
    """若課程名稱或原始名稱命中任何系/雙主修/輔系規則清單，回傳 True（表示應由系規則處理，而非通識）。"""
    # 精準或包含比對皆視為命中
    for r in _RULE_NAMES_SET:
        if not r:
            continue
        if r in name_norm or r in raw_norm or name_norm in r or raw_norm in r:
            return True
    return False

# 體育課名稱關鍵字（0學分但須追蹤修讀狀態）
PE_KEYWORDS = ["體育", "桌球", "網球", "羽球", "籃球", "排球", "游泳", "武術",
               "跆拳道", "有氧", "高爾夫", "棒球", "壘球", "足球", "乒乓"]

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
MAJOR_ELECTIVE_OVERRIDE = [
    "全球環境變遷",
    "環境教育",
    "環境政策",
    "環境倫理"
]


def _is_exempt_course(c):
    raw = c.get("raw_name", "") or ""
    return any(name in c["name"] or name in raw for name in ZERO_CREDIT_OVERRIDE_NAMES)


def evaluate_graduation(courses, config):
    """
    Evaluates student course credits against 114 Science College Handbook rules.

    Parameters:
        courses (list): List of parsed course dicts from pdf_parser.
        config (dict): {
            "domain": "地球環境" or "生命科學",
            "program": "單主修", "雙主修", or "輔系",
            "target_dept": "物化系化學組", "物化系物理組", or "資科系"
        }
    """
    domain = config.get("domain", "地球環境")
    program = config.get("program", "單主修")
    target_dept = config.get("target_dept", "物化系化學組")

    report = {
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
            "graduation_ready": False
        },
        "common": {
            # 校共同必修（英文、國文 10學分）
            "compulsory_completed": 0.0,
            "compulsory_ip": 0.0,
            "compulsory_missing": [],
            "compulsory_courses": [],
            # 通識分類選修（四大領域 16學分）
            "categories": {k: {"completed": 0.0, "ip": 0.0, "courses": []} for k in UNIVERSITY_COMMON["category_domains"].keys()},
            "category_overflow": {k: [] for k in UNIVERSITY_COMMON["category_domains"].keys()},
            "category_completed": 0.0,
            "category_ip": 0.0,
            # 通識共同選修（2學分）
            "common_elective_completed": 0.0,
            "common_elective_ip": 0.0,
            "common_elective_courses": []
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
            "other_elective_courses": []
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
            "total_completed": 0.0,
            "total_ip": 0.0
        },
        "pe": {
            # 體育（每學期 0學分必修，共需修 4 學期）
            "courses": [],
            "semesters_completed": 0,
            "semesters_required": 4,
            "semesters_ip": 0
        },
        "free": {
            "completed": 0.0,
            "ip": 0.0,
            "courses": [],
            "science_college_cross_credits": 0.0,
            "science_college_cross_courses": []
        }
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

    # ── PHASE 0.5: 地生系與專業領域必修（主修必修最高優先，避免被雙主修吃掉）────────
    for name, req_cred in EARTH_LIFE_MAJOR["common_compulsory"].items():
        matched_c = find_and_consume_course(courses, name, consumed)
        if matched_c:
            comp_c, ip_c = get_course_credits(matched_c)
            report["major"]["dept_compulsory_courses"].append(matched_c)
            report["major"]["dept_compulsory_completed"] += comp_c
            report["major"]["dept_compulsory_ip"] += ip_c
        else:
            report["major"]["dept_compulsory_missing"].append({"name": name, "credit": req_cred})

    domain_rules = EARTH_LIFE_MAJOR["domains"][domain]
    for name, req_cred in domain_rules.items():
        matched_c = find_and_consume_course(courses, name, consumed)
        if matched_c:
            comp_c, ip_c = get_course_credits(matched_c)
            report["major"]["domain_compulsory_courses"].append(matched_c)
            report["major"]["domain_compulsory_completed"] += comp_c
            report["major"]["domain_compulsory_ip"] += ip_c
        else:
            report["major"]["domain_compulsory_missing"].append({"name": name, "credit": req_cred})

    # ── PHASE 1: 輔系/雙主修必修（優先鎖定，防止被主修選修吃掉）──────────────
    if program in ["雙主修", "輔系"]:
        if "物化系" in target_dept:
            div = "化學組" if "化學組" in target_dept else "物理組"
            rules = APC_RULES["divisions"][div]
            basic_core_rules = APC_RULES["basic_core"]
            specialty_comp_rules = rules["compulsory"]

            for name, req_cred in basic_core_rules.items():
                matched_c = find_and_consume_course(courses, name, consumed)
                if matched_c:
                    comp_c, ip_c = get_course_credits(matched_c)
                    report["target"]["basic_core_courses"].append(matched_c)
                    report["target"]["basic_core_completed"] += comp_c
                    report["target"]["basic_core_ip"] += ip_c
                else:
                    report["target"]["basic_core_missing"].append({"name": name, "credit": req_cred})

            other_req = rules["double_major_other_req"] if program == "雙主修" else rules["minor_other_req"]

            for name, req_cred in specialty_comp_rules.items():
                matched_c = find_and_consume_course(courses, name, consumed)
                if matched_c:
                    comp_c, ip_c = get_course_credits(matched_c)
                    report["target"]["compulsory_courses"].append(matched_c)
                    report["target"]["compulsory_completed"] += comp_c
                    report["target"]["compulsory_ip"] += ip_c
                else:
                    report["target"]["compulsory_missing"].append({"name": name, "credit": req_cred})

            apc_electives = set(normalize_course_name(name) for name in APC_RULES.get("electives", []))
            for c in courses:
                c_idx = id(c)
                if c_idx not in consumed:
                    c_norm = normalize_course_name(c["name"])
                    if (c_norm in apc_electives or "微積分" in c["name"]) and c_norm not in _MAJOR_COMPULSORY_SET:
                        comp_c, ip_c = get_course_credits(c)
                        report["target"]["elective_courses"].append(c)
                        report["target"]["elective_completed"] += comp_c
                        report["target"]["elective_ip"] += ip_c
                        consumed.add(c_idx)

            report["target"]["total_completed"] = report["target"]["basic_core_completed"] + report["target"]["compulsory_completed"] + report["target"]["elective_completed"]
            report["target"]["total_ip"] = report["target"]["basic_core_ip"] + report["target"]["compulsory_ip"] + report["target"]["elective_ip"]

        elif "資科系" in target_dept:
            rules = CS_RULES["double_major"] if program == "雙主修" else CS_RULES["minor"]
            comp_rules = rules["compulsory"]

            for name, req_cred in comp_rules.items():
                matched_c = find_and_consume_course(courses, name, consumed)
                if matched_c:
                    comp_c, ip_c = get_course_credits(matched_c)
                    report["target"]["compulsory_courses"].append(matched_c)
                    report["target"]["compulsory_completed"] += comp_c
                    report["target"]["compulsory_ip"] += ip_c
                else:
                    report["target"]["compulsory_missing"].append({"name": name, "credit": req_cred})

            cs_electives = set(normalize_course_name(name) for name in CS_RULES.get("electives", []))
            for c in courses:
                c_idx = id(c)
                if c_idx not in consumed:
                    c_norm = normalize_course_name(c["name"])
                    # 優先判定：如果是資科系輔系明定的選修（如微積分I、II），且非本系「必修」課，直接歸入輔系
                    if c_norm in cs_electives and c_norm not in _MAJOR_COMPULSORY_SET:
                        comp_c, ip_c = get_course_credits(c)
                        report["target"]["elective_courses"].append(c)
                        report["target"]["elective_completed"] += comp_c
                        report["target"]["elective_ip"] += ip_c
                        consumed.add(c_idx)
                    # 模糊判定：如果符合關鍵字匹配，且完全不是本系的課（不屬於 _MAJOR_NAMES_SET），歸入輔系
                    elif c_norm not in _MAJOR_NAMES_SET:
                        if "資訊" in c["name"] or "程式設計" in c["name"] or "資料結構" in c["name"] or "演算法" in c["name"] or "計算機" in c["name"]:
                            comp_c, ip_c = get_course_credits(c)
                            report["target"]["elective_courses"].append(c)
                            report["target"]["elective_completed"] += comp_c
                            report["target"]["elective_ip"] += ip_c
                            consumed.add(c_idx)

            report["target"]["total_completed"] = report["target"]["compulsory_completed"] + report["target"]["elective_completed"]
            report["target"]["total_ip"] = report["target"]["compulsory_ip"] + report["target"]["elective_ip"]

    # ── PHASE 2: 校共同必修（英文、國文）─────────────────────────────────────
    for name, req_cred in UNIVERSITY_COMMON["compulsory"].items():
        matched_c = find_and_consume_course(courses, name, consumed)
        if matched_c:
            comp_c, ip_c = get_course_credits(matched_c)
            report["common"]["compulsory_courses"].append(matched_c)
            report["common"]["compulsory_completed"] += comp_c
            report["common"]["compulsory_ip"] += ip_c
        else:
            report["common"]["compulsory_missing"].append({"name": name, "credit": req_cred})

    # ── PHASE 3: 通識分類選修（匹配通識課程、標籤或關鍵字）──────────────────
    # 每類最低學分 (預設 4，若未在 rules 中提供則採此值)
    per_category_req = UNIVERSITY_COMMON.get("per_category_req", 4)

    for cat_name, keywords in UNIVERSITY_COMMON["category_domains"].items():
        for c in courses:
            c_idx = id(c)
            if c_idx not in consumed:
                raw_name = c.get("raw_name", "") or ""
                name = c.get("name", "") or ""
                # 使用 normalized 版本做匹配，避免全形／半形、額外空白或標點造成漏抓
                raw_norm = normalize_course_name(raw_name)
                name_norm = normalize_course_name(name)
                dbg(f"PHASE3: checking course id={c_idx} name='{name_norm}' raw_norm='{raw_norm}' for category '{cat_name}'")
                # 嚴格參考 rules_config.json：若此課已在任何系/雙主修/輔系規則中列出，則不應被歸為通識
                if _is_in_program_rules(name_norm, raw_norm):
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
                # 若沒有中括號標註，回退到原本的關鍵字比對（課名或 raw_name 包含關鍵字）
                if not is_match:
                    for kw in keywords:
                        if kw in name_norm or kw in raw_norm:
                            is_match = True
                            break

                if is_match:
                    comp_c, ip_c = get_course_credits(c)
                    # 若此類別已達最低要求，將後續課程登記為 overflow（超額）以便檢視
                    if report["common"]["categories"][cat_name]["completed"] >= per_category_req:
                        report["common"]["category_overflow"][cat_name].append(c)
                    report["common"]["categories"][cat_name]["courses"].append(c)
                    report["common"]["categories"][cat_name]["completed"] += comp_c
                    report["common"]["categories"][cat_name]["ip"] += ip_c
                    report["common"]["category_completed"] += comp_c
                    report["common"]["category_ip"] += ip_c
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
            if _is_in_program_rules(name_norm, raw_norm):
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
                        comp_c, ip_c = get_course_credits(c)
                        # 若該分類已滿，視為 overflow
                        if report["common"]["categories"][cat_name]["completed"] >= per_category_req:
                            report["common"]["category_overflow"][cat_name].append(c)
                        report["common"]["categories"][cat_name]["courses"].append(c)
                        report["common"]["categories"][cat_name]["completed"] += comp_c
                        report["common"]["categories"][cat_name]["ip"] += ip_c
                        report["common"]["category_completed"] += comp_c
                        report["common"]["category_ip"] += ip_c
                        consumed.add(c_idx)
                        assigned = True
                        break

            if assigned:
                continue
            if "通選" in raw_norm or "通識" in raw_norm or "共同選修" in raw_norm or any(kw in name_norm or kw in raw_norm for kw in [
                "藝術", "美感", "人文", "文化", "社會", "公民", "自然", "生命", "科技", "環境", "歷史", "哲學", "科學", "資訊", "文藝"
            ]):
                comp_c, ip_c = get_course_credits(c)
                ge_common_req = UNIVERSITY_COMMON.get("ge_common_elective_req", 2)
                # 溢出處理：如果通識共同選修已滿，溢出到自由選修
                if report["common"]["common_elective_completed"] + report["common"]["common_elective_ip"] >= ge_common_req:
                    report["free"]["courses"].append(c)
                    report["free"]["completed"] += comp_c
                    report["free"]["ip"] += ip_c
                else:
                    report["common"]["common_elective_courses"].append(c)
                    report["common"]["common_elective_completed"] += comp_c
                    report["common"]["common_elective_ip"] += ip_c
                consumed.add(c_idx)

    # ── PHASE X: 將通識分類中的超額課程重新歸類為自由選修（避免被計入各分類總和）
    overflow = report["common"].get("category_overflow", {})
    for cat_name, items in overflow.items():
        for c in list(items):
            # use get_course_credits to compute comp/ip credits
            comp_c, ip_c = get_course_credits(c)
            # subtract from category totals (避免負值)
            cat = report["common"]["categories"].get(cat_name)
            if cat:
                cat["completed"] = max(0.0, cat.get("completed", 0.0) - comp_c)
                cat["ip"] = max(0.0, cat.get("ip", 0.0) - ip_c)
                # remove from courses list if present
                try:
                    cat["courses"] = [cc for cc in cat.get("courses", []) if id(cc) != id(c)]
                except Exception:
                    pass
            # subtract from aggregate category counters
            report["common"]["category_completed"] = max(0.0, report["common"].get("category_completed", 0.0) - comp_c)
            report["common"]["category_ip"] = max(0.0, report["common"].get("category_ip", 0.0) - ip_c)
            # add into free electives
            report["free"]["courses"].append(c)
            report["free"]["completed"] += comp_c
            report["free"]["ip"] += ip_c
    # 清空 overflow 結構（已轉移）以避免重複處理
    report["common"]["category_overflow"] = {k: [] for k in report["common"].get("category_overflow", {})}

    # (原 PHASE 5, 6 已移至 PHASE 0.5)

    # ── PHASE 7: 專業領域選修（至少20學分）──────────────────────────────────
    domain_elective_keywords = EARTH_LIFE_MAJOR["domain_electives"][domain]
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            if c["name"] in domain_elective_keywords or any(kw == c["name"] for kw in domain_elective_keywords):
                comp_c, ip_c = get_course_credits(c)
                report["major"]["domain_elective_courses"].append(c)
                report["major"]["domain_elective_completed"] += comp_c
                report["major"]["domain_elective_ip"] += ip_c
                consumed.add(c_idx)

    # ── PHASE 8: 系共同選修（其他27學分）─────────────────────────────────────
    all_major_electives = set(EARTH_LIFE_MAJOR["domain_electives"].get("common_electives", []))
    for dname, electives in EARTH_LIFE_MAJOR["domain_electives"].items():
        if dname != domain and dname != "common_electives":
            all_major_electives.update(electives)

    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            if c["name"] in all_major_electives or any(kw == c["name"] for kw in all_major_electives):
                comp_c, ip_c = get_course_credits(c)
                report["major"]["other_elective_courses"].append(c)
                report["major"]["other_elective_completed"] += comp_c
                report["major"]["other_elective_ip"] += ip_c
                consumed.add(c_idx)

    # ── PHASE 9: 自由選修（剩餘所有有學分的課）──────────────────────────────
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            if c["total_credit"] > 0:
                comp_c, ip_c = get_course_credits(c)
                report["free"]["courses"].append(c)
                report["free"]["completed"] += comp_c
                report["free"]["ip"] += ip_c

                # 理學院院內跨系選修判定
                cross_keywords = ["物理", "化學", "資訊", "數學", "計算機", "離散數學", "微積分"]
                if any(kw in c["name"] for kw in cross_keywords):
                    if c["name"] not in EARTH_LIFE_MAJOR["common_compulsory"] and \
                       c["name"] not in EARTH_LIFE_MAJOR["domain_electives"][domain]:
                        report["free"]["science_college_cross_courses"].append(c)
                        report["free"]["science_college_cross_credits"] += comp_c
                consumed.add(c_idx)

    # ── PHASE 9.5: 超額選修學分溢流至自由選修（避免主修/輔系超額學分未計入自由選修而影響畢業判定） ──────────────────────
    # 1. 專業選修超額 (超過 20 學分的部分) -> 溢流到 其他本系選修
    domain_req = 20.0
    accumulated = 0.0
    new_domain_courses = []
    overflow_to_other = []
    for c in report["major"]["domain_elective_courses"]:
        comp_c = c["completed_credit"]
        if accumulated >= domain_req:
            overflow_to_other.append(c)
        else:
            new_domain_courses.append(c)
            accumulated += comp_c
    report["major"]["domain_elective_courses"] = new_domain_courses
    report["major"]["domain_elective_completed"] = sum(c["completed_credit"] for c in new_domain_courses)
    report["major"]["domain_elective_ip"] = sum(c["total_credit"] - c["completed_credit"] if c["is_in_progress"] else 0.0 for c in new_domain_courses)

    # 將超出的專業選修併入其他本系選修
    for c in overflow_to_other:
        report["major"]["other_elective_courses"].append(c)
        comp_c, ip_c = get_course_credits(c)
        report["major"]["other_elective_completed"] += comp_c
        report["major"]["other_elective_ip"] += ip_c

    # 2. 其他本系選修超額 (超過 27 學分的部分) -> 溢流到 自由選修
    other_req = 27.0
    accumulated = 0.0
    new_other_courses = []
    overflow_to_free = []
    for c in report["major"]["other_elective_courses"]:
        comp_c = c["completed_credit"]
        if accumulated >= other_req:
            overflow_to_free.append(c)
        else:
            new_other_courses.append(c)
            accumulated += comp_c
    report["major"]["other_elective_courses"] = new_other_courses
    report["major"]["other_elective_completed"] = sum(c["completed_credit"] for c in new_other_courses)
    report["major"]["other_elective_ip"] = sum(c["total_credit"] - c["completed_credit"] if c["is_in_progress"] else 0.0 for c in new_other_courses)

    # 將超出的其他選修併入自由選修
    for c in overflow_to_free:
        report["free"]["courses"].append(c)
        comp_c, ip_c = get_course_credits(c)
        report["free"]["completed"] += comp_c
        report["free"]["ip"] += ip_c

    # 3. 雙主修/輔系選修超額 (輔系超過 20 或雙主修超過 40 學分的部分) -> 溢流到 自由選修
    target_req = 40.0 if program == "雙主修" else (20.0 if program == "輔系" else 0.0)
    if target_req > 0.0:
        comp_total = report["target"]["compulsory_completed"] + report["target"].get("basic_core_completed", 0.0)
        allowed_elective_req = max(0.0, target_req - comp_total)
        accumulated = 0.0
        new_target_electives = []
        overflow_target_to_free = []
        for c in report["target"]["elective_courses"]:
            comp_c = c["completed_credit"]
            if accumulated >= allowed_elective_req:
                overflow_target_to_free.append(c)
            else:
                new_target_electives.append(c)
                accumulated += comp_c

        report["target"]["elective_courses"] = new_target_electives
        report["target"]["elective_completed"] = sum(c["completed_credit"] for c in new_target_electives)
        report["target"]["elective_ip"] = sum(c["total_credit"] - c["completed_credit"] if c["is_in_progress"] else 0.0 for c in new_target_electives)

        for c in overflow_target_to_free:
            report["free"]["courses"].append(c)
            comp_c, ip_c = get_course_credits(c)
            report["free"]["completed"] += comp_c
            report["free"]["ip"] += ip_c
            
        report["target"]["total_completed"] = (
            report["target"]["compulsory_completed"] +
            report["target"].get("basic_core_completed", 0.0) +
            report["target"]["elective_completed"]
        )
        report["target"]["total_ip"] = (
            report["target"]["compulsory_ip"] +
            report["target"].get("basic_core_ip", 0.0) +
            report["target"]["elective_ip"]
        )

    # ── PHASE 10: 匯總計算 ───────────────────────────────────────────────
    report["summary"]["common_completed"] = (
        report["common"]["compulsory_completed"] +
        report["common"]["category_completed"] +
        report["common"]["common_elective_completed"]
    )
    report["summary"]["common_ip"] = (
        report["common"]["compulsory_ip"] +
        report["common"]["category_ip"] +
        report["common"]["common_elective_ip"]
    )

    report["summary"]["major_completed"] = (
        report["major"]["dept_compulsory_completed"] +
        report["major"]["domain_compulsory_completed"] +
        report["major"]["domain_elective_completed"] +
        report["major"]["other_elective_completed"]
    )
    report["summary"]["major_ip"] = (
        report["major"]["dept_compulsory_ip"] +
        report["major"]["domain_compulsory_ip"] +
        report["major"]["domain_elective_ip"] +
        report["major"]["other_elective_ip"]
    )

    report["summary"]["target_completed"] = report["target"]["total_completed"]
    report["summary"]["target_ip"] = report["target"]["total_ip"]

    report["summary"]["free_completed"] = report["free"]["completed"]
    report["summary"]["free_ip"] = report["free"]["ip"]

    report["summary"]["total_completed"] = (
        report["summary"]["common_completed"] +
        report["summary"]["major_completed"] +
        report["summary"]["target_completed"] +
        report["summary"]["free_completed"]
    )
    report["summary"]["total_ip"] = (
        report["summary"]["common_ip"] +
        report["summary"]["major_ip"] +
        report["summary"]["target_ip"] +
        report["summary"]["free_ip"]
    )

    # 額外計算：將已取得 + 正在修習的學分一起顯示（以便學生查看含修讀中學分的總和）
    report["summary"]["total_with_ip"] = report["summary"]["total_completed"] + report["summary"]["total_ip"]

    # 畢業審查
    has_enough = report["summary"]["total_completed"] >= 128.0
    has_common = report["summary"]["common_completed"] >= 28.0
    has_major  = report["summary"]["major_completed"] >= 85.0
    has_free   = report["summary"]["free_completed"] >= 15.0
    has_pe     = report["pe"]["semesters_completed"] >= 4

    no_missing = (
        len(report["common"]["compulsory_missing"]) == 0 and
        len(report["major"]["dept_compulsory_missing"]) == 0 and
        len(report["major"]["domain_compulsory_missing"]) == 0
    )

    target_satisfied = True
    if program == "雙主修":
        target_satisfied = report["target"]["total_completed"] >= 40.0
    elif program == "輔系":
        target_satisfied = report["target"]["total_completed"] >= 20.0

    report["summary"]["graduation_ready"] = (
        has_enough and has_common and has_major and has_free and
        has_pe and no_missing and target_satisfied
    )

    return report


def find_and_consume_course(courses, rule_name, consumed_set):
    """精確名稱優先，模糊對應次之，防止過度匹配。"""
    norm_rule_name = normalize_course_name(rule_name)

    # 精確匹配（使用 normalized name）
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed_set:
            c_name_norm = normalize_course_name(c.get("name", "") or "")
            if c_name_norm == norm_rule_name:
                consumed_set.add(c_idx)
                dbg(f"find_and_consume: exact match id={c_idx} rule='{norm_rule_name}' course='{c_name_norm}'")
                return c

    # 包含匹配（較短的名稱包含在較長的名稱內，或反之），使用 normalized 比對
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed_set:
            c_name_norm = normalize_course_name(c.get("name", "") or "")
            if len(norm_rule_name) >= 3 and (norm_rule_name in c_name_norm):
                consumed_set.add(c_idx)
                dbg(f"find_and_consume: contains match id={c_idx} rule='{norm_rule_name}' course='{c_name_norm}'")
                return c

    # 模糊對應表
    fuzzy_mappings = {
        "英文(一)": ["英文(一)"],
        "英文(二)": ["英文(二)"],
        "國文(一):閱讀與思辨": ["國文(一):閱讀與思辨", "國文(一)", "國文一"],
        "國文(二):語文表達": ["國文(二):語文表達", "國文(二)", "國文二"],
        "普通物理學(一)": ["普通物理(含實驗)", "普通物理學(含實驗)"],
        "普通物理學(二)": ["普通物理(含實驗)", "普通物理學(含實驗)"],
        "普通化學(一)": ["普通化學(含實驗)", "普通化學(一)(含實驗)"],
        "普通化學(二)": ["普通化學(含實驗)", "普通化學(二)(含實驗)"],
        "生物化學(一)": ["生物化學(一)", "生物化學"],
    }

    for key, aliases in fuzzy_mappings.items():
        if norm_rule_name == normalize_course_name(key):
            for alias in aliases:
                norm_alias = normalize_course_name(alias)
                for c in courses:
                    c_idx = id(c)
                    if c_idx not in consumed_set:
                        c_name_norm = normalize_course_name(c.get("name", "") or "")
                        if c_name_norm == norm_alias or norm_alias in c_name_norm:
                            consumed_set.add(c_idx)
                            dbg(f"find_and_consume: fuzzy alias match id={c_idx} rule='{norm_rule_name}' alias='{norm_alias}' course='{c_name_norm}'")
                            return c

    # 額外寬鬆匹配：若規則名稱包含冒號（如 "國文(一):閱讀與思辨"），嘗試只用冒號前段比對
    if ":" in norm_rule_name:
        head = norm_rule_name.split(":", 1)[0]
        for c in courses:
            c_idx = id(c)
            if c_idx not in consumed_set:
                c_name_norm = normalize_course_name(c.get("name", "") or "")
                if c_name_norm == head or head in c_name_norm or c_name_norm in head:
                    consumed_set.add(c_idx)
                    dbg(f"find_and_consume: colon-head match id={c_idx} rule_head='{head}' course='{c_name_norm}'")
                    return c

    # 最後嘗試使用 raw_name 的包含比對，避免因標點或空白差異漏抓常見課名
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed_set:
            raw = (c.get("raw_name") or "")
            raw_norm = normalize_course_name(raw)
            if raw_norm:
                if ":" in norm_rule_name:
                    head = norm_rule_name.split(":", 1)[0]
                    if head in raw_norm or norm_rule_name in raw_norm:
                        consumed_set.add(c_idx)
                        dbg(f"find_and_consume: raw_name match id={c_idx} rule='{norm_rule_name}' raw_norm='{raw_norm}'")
                        return c
                else:
                    if norm_rule_name in raw_norm or raw_norm in norm_rule_name:
                        consumed_set.add(c_idx)
                        dbg(f"find_and_consume: raw_name contains match id={c_idx} rule='{norm_rule_name}' raw_norm='{raw_norm}'")
                        return c

    return None
