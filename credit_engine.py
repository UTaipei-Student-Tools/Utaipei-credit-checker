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

# 體育課名稱關鍵字（0學分但須追蹤修讀狀態）
PE_KEYWORDS = ["體育", "桌球", "網球", "羽球", "籃球", "排球", "游泳", "武術",
               "跆拳道", "有氧", "高爾夫", "棒球", "壘球", "足球", "乒乓"]

def _is_pe_course(c):
    for kw in PE_KEYWORDS:
        if kw in c["name"] or kw in c["raw_name"]:
            return True
    return False

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
            "categories": {
                "藝術與美感":        {"completed": 0.0, "ip": 0.0, "courses": []},
                "人文與文化思考":     {"completed": 0.0, "ip": 0.0, "courses": []},
                "公民素養與社會探索": {"completed": 0.0, "ip": 0.0, "courses": []},
                "自然、生命與科技":  {"completed": 0.0, "ip": 0.0, "courses": []}
            },
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

            report["target"]["total_completed"] = report["target"]["basic_core_completed"] + report["target"]["compulsory_completed"]
            report["target"]["total_ip"] = report["target"]["basic_core_ip"] + report["target"]["compulsory_ip"]

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

            for c in courses:
                c_idx = id(c)
                if c_idx not in consumed:
                    if "資訊" in c["name"] or "程式設計" in c["name"] or "資料結構" in c["name"] or "演算法" in c["name"] or "計算機" in c["name"]:
                        if c["name"] not in EARTH_LIFE_MAJOR["common_compulsory"]:
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

    # ── PHASE 3: 通識分類選修（只匹配有 [通選XXX] 標記的課程）──────────────────
    for cat_name, keywords in UNIVERSITY_COMMON["category_domains"].items():
        for c in courses:
            c_idx = id(c)
            if c_idx not in consumed:
                # 只有明確有 [通選] 標記的課才算通識
                is_ge = "通選" in c["raw_name"] or "通識" in c["raw_name"]
                if not is_ge:
                    continue

                is_match = False
                if f"通選{cat_name[:2]}" in c["raw_name"]:
                    is_match = True
                else:
                    for kw in keywords:
                        if kw in c["name"]:
                            is_match = True
                            break

                if is_match:
                    comp_c, ip_c = get_course_credits(c)
                    report["common"]["categories"][cat_name]["courses"].append(c)
                    report["common"]["categories"][cat_name]["completed"] += comp_c
                    report["common"]["categories"][cat_name]["ip"] += ip_c
                    report["common"]["category_completed"] += comp_c
                    report["common"]["category_ip"] += ip_c
                    consumed.add(c_idx)

    # ── PHASE 4: 通識共同選修（剩餘的通識課）─────────────────────────────────
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            if "通選" in c["raw_name"] or "通識" in c["raw_name"]:
                comp_c, ip_c = get_course_credits(c)
                report["common"]["common_elective_courses"].append(c)
                report["common"]["common_elective_completed"] += comp_c
                report["common"]["common_elective_ip"] += ip_c
                consumed.add(c_idx)

    # ── PHASE 5: 地生系共同必修（24學分）─────────────────────────────────────
    for name, req_cred in EARTH_LIFE_MAJOR["common_compulsory"].items():
        matched_c = find_and_consume_course(courses, name, consumed)
        if matched_c:
            comp_c, ip_c = get_course_credits(matched_c)
            report["major"]["dept_compulsory_courses"].append(matched_c)
            report["major"]["dept_compulsory_completed"] += comp_c
            report["major"]["dept_compulsory_ip"] += ip_c
        else:
            report["major"]["dept_compulsory_missing"].append({"name": name, "credit": req_cred})

    # ── PHASE 6: 專業領域必修（14學分）──────────────────────────────────────
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

    # ── PHASE 7: 專業領域選修（至少20學分）──────────────────────────────────
    domain_elective_keywords = [normalize_course_name(kw) for kw in EARTH_LIFE_MAJOR["domain_electives"][domain]]
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            if c["name"] in domain_elective_keywords:
                comp_c, ip_c = get_course_credits(c)
                report["major"]["domain_elective_courses"].append(c)
                report["major"]["domain_elective_completed"] += comp_c
                report["major"]["domain_elective_ip"] += ip_c
                consumed.add(c_idx)

    # ── PHASE 8: 系共同選修（其他27學分）─────────────────────────────────────
    other_domain = "生命科學" if domain == "地球環境" else "地球環境"
    other_domain_keywords = [normalize_course_name(kw) for kw in EARTH_LIFE_MAJOR["domain_electives"][other_domain]]
    common_elective_keywords = [normalize_course_name(kw) for kw in EARTH_LIFE_MAJOR["domain_electives"]["common_electives"]]
    all_major_electives = set(other_domain_keywords + common_elective_keywords)

    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            if c["name"] in all_major_electives:
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

    # 精確匹配
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed_set:
            if c["name"] == norm_rule_name:
                consumed_set.add(c_idx)
                return c

    # 包含匹配（較短的名稱包含在較長的名稱內，或反之）
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed_set:
            if (norm_rule_name in c["name"] or c["name"] in norm_rule_name) and len(norm_rule_name) >= 3:
                consumed_set.add(c_idx)
                return c

    # 模糊對應表
    fuzzy_mappings = {
        "英文(一)": ["英文(一)", "英文(I)"],
        "英文(二)": ["英文(二)", "英文(II)"],
        "英文(三)": ["英文(三)", "英文(III)", "英文三"],
        "國文(一)": ["國文(一)", "國文(I)", "國文一"],
        "國文(二)": ["國文(二)", "國文(II)", "國文二"],
        "普通物理學(一)": ["普通物理(含實驗)", "普通物理學(含實驗)"],
        "普通物理學(二)": ["普通物理(含實驗)", "普通物理學(含實驗)"],
        "普通化學(一)": ["普通化學(含實驗)", "普通化學(一)(含實驗)"],
        "普通化學(二)": ["普通化學(含實驗)", "普通化學(二)(含實驗)"],
    }

    for key, aliases in fuzzy_mappings.items():
        if norm_rule_name == normalize_course_name(key):
            for alias in aliases:
                norm_alias = normalize_course_name(alias)
                for c in courses:
                    c_idx = id(c)
                    if c_idx not in consumed_set:
                        if c["name"] == norm_alias or norm_alias in c["name"]:
                            consumed_set.add(c_idx)
                            return c

    return None
