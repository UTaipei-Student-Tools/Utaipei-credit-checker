"""
Graduation Credit Evaluation Engine — v2
新增：體育追蹤、通識/校必修分離、自由選修正確溢流
"""

import re

from handbook_rules import get_credit_requirements, get_rule_sets, get_rules_meta, normalize_course_name

# 匹配除錯開關：出問題時可打開以取得匹配決策輸出
DEBUG_MATCHING = False


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
    _, _, selected = max(candidates, key=lambda item: item[0])
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
    allocated["_origin_id"] = course.get("_origin_id", id(course))
    allocated["total_credit"] = completed + in_progress
    allocated["completed_credit"] = completed
    allocated["is_completed"] = completed > 0
    allocated["is_in_progress"] = in_progress > 0
    allocated["allocation_note"] = note
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
    rule_names_set = _collect_rule_names(rule_sets)
    major_compulsory_set = _collect_major_compulsory(earth_life_major)

    if domain not in earth_life_major.get("domains", {}):
        raise ValueError(f"不支援的主修專業領域：{domain}")
    if program not in {"單主修", "雙主修", "輔系"}:
        raise ValueError(f"不支援的修課身分：{program}")

    requirements = get_credit_requirements(program, target_dept, rule_sets["academic_year"])

    report = {
        "handbook_year": rule_sets["academic_year"],
        "rules_meta": get_rules_meta(rule_sets["academic_year"]),
        "document_warnings": rule_sets.get("document_warnings", []),
        "requirements": requirements,
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
            basic_core_rules = apc_rules["basic_core"]

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

            other_req = float(program_rules["other_req"])
            other_required_pool = dict(apc_rules.get("shared_other_required", {}))
            other_required_pool.update(apc_rules["divisions"][div]["compulsory"])
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
            if "通選" in raw_norm or "通識" in raw_norm or "共同選修" in raw_norm:
                comp_c, ip_c = get_course_credits(c)
                ge_common_req = requirements["ge_common_elective"]
                # 溢出處理：如果通識共同選修已滿，溢出到自由選修
                if (
                    report["common"]["common_elective_completed"] + report["common"]["common_elective_ip"]
                    >= ge_common_req
                ):
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
                if _course_matches_rule(c, rule_name, rule_credit):
                    comp_c, ip_c = get_course_credits(c)
                    report["major"]["other_elective_courses"].append(c)
                    report["major"]["other_elective_completed"] += comp_c
                    report["major"]["other_elective_ip"] += ip_c
                    consumed.add(c_idx)
                    break

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
                    if (
                        normalize_course_name(c["name"]) not in major_compulsory_set
                        and normalize_course_name(c["name"]) not in _normalized_names(domain_elective_rules)
                    ):
                        report["free"]["science_college_cross_courses"].append(c)
                        report["free"]["science_college_cross_credits"] += comp_c
                consumed.add(c_idx)

    # ── PHASE 9.5: 超額選修學分溢流至自由選修（避免主修/輔系超額學分未計入自由選修而影響畢業判定） ──────────────────────
    # 1. 專業選修超額 (超過 20 學分的部分) -> 溢流到 其他本系選修
    domain_req = requirements["domain_elective"]
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
    report["major"]["domain_elective_ip"] = sum(
        c["total_credit"] - c["completed_credit"] if c["is_in_progress"] else 0.0 for c in new_domain_courses
    )

    # 將超出的專業選修併入其他本系選修
    for c in overflow_to_other:
        report["major"]["other_elective_courses"].append(c)
        comp_c, ip_c = get_course_credits(c)
        report["major"]["other_elective_completed"] += comp_c
        report["major"]["other_elective_ip"] += ip_c

    # 2. 其他本系選修超額 (超過 27 學分的部分) -> 溢流到 自由選修
    other_req = requirements["major_other_elective"]
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
    report["major"]["other_elective_ip"] = sum(
        c["total_credit"] - c["completed_credit"] if c["is_in_progress"] else 0.0 for c in new_other_courses
    )

    # 將超出的其他選修併入自由選修
    for c in overflow_to_free:
        report["free"]["courses"].append(c)
        comp_c, ip_c = get_course_credits(c)
        report["free"]["completed"] += comp_c
        report["free"]["ip"] += ip_c

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

    # 畢業審查
    has_enough = report["summary"]["total_completed"] >= requirements["total"]
    has_common = report["summary"]["common_completed"] >= requirements["common_total"]
    has_major = report["summary"]["major_completed"] >= requirements["major_total"]
    has_free = report["summary"]["free_completed"] >= requirements["free_elective"]
    has_pe = report["pe"]["semesters_completed"] >= requirements["pe_semesters"]

    no_missing = (
        len(report["common"]["compulsory_missing"]) == 0
        and len(report["major"]["dept_compulsory_missing"]) == 0
        and len(report["major"]["domain_compulsory_missing"]) == 0
    )

    target_satisfied = True
    if requirements["target_total"] > 0:
        target_satisfied = (
            report["target"]["total_completed"] >= requirements["target_total"]
            and len(report["target"]["basic_core_missing"]) == 0
            and len(report["target"]["compulsory_missing"]) == 0
            and len(report["target"].get("elective_missing", [])) == 0
        )

    report["summary"]["graduation_ready"] = (
        has_enough and has_common and has_major and has_free and has_pe and no_missing and target_satisfied
    )

    return report


def find_and_consume_course(courses, rule_name, consumed_set, expected_credit=None, aliases=()):
    """Consume one exact scoped identity, preferring completed attempts.

    Substring matching, edit-distance matching and global aliases are forbidden.
    This is what keeps ``微積分`` separate from ``微積分(I)/(II)`` and keeps
    combined laboratory courses separate from their theory/lab components.
    """
    candidates = []
    for position, course in enumerate(courses):
        c_idx = id(course)
        if c_idx in consumed_set:
            continue
        if _course_matches_rule(course, rule_name, expected_credit, aliases):
            rank = 2 if course.get("is_completed") else 1 if course.get("is_in_progress") else 0
            candidates.append((rank, -position, course))
    if not candidates:
        return None
    _, _, selected = max(candidates, key=lambda item: (item[0], item[1]))
    consumed_set.add(id(selected))
    dbg(
        "find_and_consume: exact scoped match "
        f"rule='{normalize_course_name(rule_name)}' course='{normalize_course_name(selected.get('name', ''))}'"
    )
    return selected
