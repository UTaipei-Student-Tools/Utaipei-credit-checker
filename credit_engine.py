# -*- coding: utf-8 -*-
"""
Graduation Credit Evaluation Engine
"""

from handbook_rules import (
    normalize_course_name,
    UNIVERSITY_COMMON,
    EARTH_LIFE_MAJOR,
    APC_RULES,
    CS_RULES
)

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
    
    # Initialize results structures
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
            "compulsory_completed": 0.0,
            "compulsory_ip": 0.0,
            "compulsory_missing": [],
            "compulsory_courses": [],
            "categories": {
                "藝術與美感": {"completed": 0.0, "ip": 0.0, "courses": []},
                "人文與文化思考": {"completed": 0.0, "ip": 0.0, "courses": []},
                "公民素養與社會探索": {"completed": 0.0, "ip": 0.0, "courses": []},
                "自然、生命與科技": {"completed": 0.0, "ip": 0.0, "courses": []}
            },
            "category_completed": 0.0,
            "category_ip": 0.0,
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
        "free": {
            "completed": 0.0,
            "ip": 0.0,
            "courses": [],
            "science_college_cross_credits": 0.0,
            "science_college_cross_courses": []
        }
    }
    
    # Helper set to track consumed courses to avoid double counting
    consumed = set()
    
    # Helper function to check if course is completed or IP
    def get_course_credits(c):
        return c["completed_credit"], c["total_credit"] - c["completed_credit"] if c["is_in_progress"] else 0.0
        
    # --- PHASE 1: EVALUATE TARGET DEPARTMENT (DOUBLE MAJOR / MINOR) FIRST ---
    # Because double major/minor courses are specific and should not be consumed by major electives.
    if program in ["雙主修", "輔系"]:
        if "物化系" in target_dept:
            div = "化學組" if "化學組" in target_dept else "物理組"
            rules = APC_RULES["divisions"][div]
            basic_core_rules = APC_RULES["basic_core"]
            specialty_comp_rules = rules["compulsory"]
            
            # Match Basic Core (16 Credits)
            for name, req_cred in basic_core_rules.items():
                matched_c = find_and_consume_course(courses, name, consumed)
                if matched_c:
                    comp_c, ip_c = get_course_credits(matched_c)
                    report["target"]["basic_core_courses"].append(matched_c)
                    report["target"]["basic_core_completed"] += comp_c
                    report["target"]["basic_core_ip"] += ip_c
                else:
                    report["target"]["basic_core_missing"].append({"name": name, "credit": req_cred})
                    
            # Match Division specialty compulsory
            other_req = rules["double_major_other_req"] if program == "雙主修" else rules["minor_other_req"]
            
            for name, req_cred in specialty_comp_rules.items():
                matched_c = find_and_consume_course(courses, name, consumed)
                if matched_c:
                    comp_c, ip_c = get_course_credits(matched_c)
                    report["target"]["compulsory_courses"].append(matched_c)
                    report["target"]["compulsory_completed"] += comp_c
                    report["target"]["compulsory_ip"] += ip_c
                else:
                    # Only add as missing if it's double major and we need to list important compulsory ones,
                    # or we can list all possible specialty compulsory they haven't taken.
                    report["target"]["compulsory_missing"].append({"name": name, "credit": req_cred})
                    
            report["target"]["total_completed"] = report["target"]["basic_core_completed"] + report["target"]["compulsory_completed"]
            report["target"]["total_ip"] = report["target"]["basic_core_ip"] + report["target"]["compulsory_ip"]
            
        elif "資科系" in target_dept:
            rules = CS_RULES["double_major"] if program == "雙主修" else CS_RULES["minor"]
            comp_rules = rules["compulsory"]
            
            # Match CS Compulsory Core
            for name, req_cred in comp_rules.items():
                matched_c = find_and_consume_course(courses, name, consumed)
                if matched_c:
                    comp_c, ip_c = get_course_credits(matched_c)
                    report["target"]["compulsory_courses"].append(matched_c)
                    report["target"]["compulsory_completed"] += comp_c
                    report["target"]["compulsory_ip"] += ip_c
                else:
                    report["target"]["compulsory_missing"].append({"name": name, "credit": req_cred})
                    
            # Match CS electives (any other courses parsed with CS in name or that can be taken in CS)
            # In our scraper, CS courses might have "資訊" in name
            for c in courses:
                c_idx = id(c)
                if c_idx not in consumed:
                    if "資訊" in c["name"] or "程式設計" in c["name"] or "資料結構" in c["name"] or "演算法" in c["name"] or "計算機" in c["name"]:
                        # Check it doesn't match main major compulsory first
                        if c["name"] not in EARTH_LIFE_MAJOR["common_compulsory"]:
                            comp_c, ip_c = get_course_credits(c)
                            report["target"]["elective_courses"].append(c)
                            report["target"]["elective_completed"] += comp_c
                            report["target"]["elective_ip"] += ip_c
                            consumed.add(c_idx)
                            
            report["target"]["total_completed"] = report["target"]["compulsory_completed"] + report["target"]["elective_completed"]
            report["target"]["total_ip"] = report["target"]["compulsory_ip"] + report["target"]["elective_ip"]

    # --- PHASE 2: UNIVERSITY COMMON REQUIREMENTS ---
    # 2.1 Common Compulsory (英文, 國文)
    for name, req_cred in UNIVERSITY_COMMON["compulsory"].items():
        matched_c = find_and_consume_course(courses, name, consumed)
        if matched_c:
            comp_c, ip_c = get_course_credits(matched_c)
            report["common"]["compulsory_courses"].append(matched_c)
            report["common"]["compulsory_completed"] += comp_c
            report["common"]["compulsory_ip"] += ip_c
        else:
            report["common"]["compulsory_missing"].append({"name": name, "credit": req_cred})
            
    # 2.2 Category Electives (通識分類選修 - 16 credits, 4 domains)
    for cat_name, keywords in UNIVERSITY_COMMON["category_domains"].items():
        # Find courses in transcript that have these keywords or domain names
        for c in courses:
            c_idx = id(c)
            if c_idx not in consumed:
                # ONLY count as GE category elective if it has a clear GE marker in its raw name
                if not ("通選" in c["raw_name"] or "通選" in c["name"] or "通識" in c["raw_name"]):
                    continue
                    
                # Check if it has a GE marker in original raw name e.g., [通選藝術] or matches keywords
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
                    
    # 2.3 Common Elective (通識共同選修 - 2 credits)
    # Any leftover 通識 courses can flow into common electives
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            if "通選" in c["raw_name"] or "通識" in c["raw_name"]:
                comp_c, ip_c = get_course_credits(c)
                report["common"]["common_elective_courses"].append(c)
                report["common"]["common_elective_completed"] += comp_c
                report["common"]["common_elective_ip"] += ip_c
                consumed.add(c_idx)

    # --- PHASE 3: MAIN MAJOR (地生系專門課程 - 85 credits) ---
    # 3.1 Dept Common Compulsory (系共同必修 - 24 credits)
    for name, req_cred in EARTH_LIFE_MAJOR["common_compulsory"].items():
        matched_c = find_and_consume_course(courses, name, consumed)
        if matched_c:
            comp_c, ip_c = get_course_credits(matched_c)
            report["major"]["dept_compulsory_courses"].append(matched_c)
            report["major"]["dept_compulsory_completed"] += comp_c
            report["major"]["dept_compulsory_ip"] += ip_c
        else:
            report["major"]["dept_compulsory_missing"].append({"name": name, "credit": req_cred})
            
    # 3.2 Domain Compulsory (專業領域必修 - 14 credits)
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
            
    # 3.3 Domain Electives (專業領域選修 - at least 20 credits)
    # Match courses that belong to the chosen domain electives list
    domain_elective_keywords = EARTH_LIFE_MAJOR["domain_electives"][domain]
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            # Check if course name matches any in domain electives
            if c["name"] in domain_elective_keywords or any(kw in c["name"] for kw in domain_elective_keywords):
                comp_c, ip_c = get_course_credits(c)
                report["major"]["domain_elective_courses"].append(c)
                report["major"]["domain_elective_completed"] += comp_c
                report["major"]["domain_elective_ip"] += ip_c
                consumed.add(c_idx)
                
    # 3.4 Other Dept Specialty/Common Electives (其他本系專門選修 - 27 credits)
    # Match leftover courses that match domain electives of the OTHER domain, or Dept Common Electives
    other_domain = "生命科學" if domain == "地球環境" else "地球環境"
    other_domain_keywords = EARTH_LIFE_MAJOR["domain_electives"][other_domain]
    common_elective_keywords = EARTH_LIFE_MAJOR["domain_electives"]["common_electives"]
    
    all_major_electives = other_domain_keywords + common_elective_keywords
    
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            if c["name"] in all_major_electives or any(kw in c["name"] for kw in all_major_electives):
                comp_c, ip_c = get_course_credits(c)
                report["major"]["other_elective_courses"].append(c)
                report["major"]["other_elective_completed"] += comp_c
                report["major"]["other_elective_ip"] += ip_c
                consumed.add(c_idx)
                
    # --- PHASE 4: FREE ELECTIVES (自由選修 - 15 credits) ---
    # Any remaining courses taken by the student flow into Free Electives!
    # This automatically captures double major/minor courses, surplus department courses, and external courses.
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed:
            # Skip zero credit course headers or physical education if they are completed but aren't academic credits
            if c["total_credit"] > 0:
                comp_c, ip_c = get_course_credits(c)
                report["free"]["courses"].append(c)
                report["free"]["completed"] += comp_c
                report["free"]["ip"] += ip_c
                
                # Check if it satisfies "理學院院內跨系選修" rule
                # College of Science departments: 應用物理暨化學系 (物化系), 資訊科學系 (資科系), 數學系 (數學系), 體育系 (not really science college), etc.
                if "物理" in c["name"] or "化學" in c["name"] or "資訊" in c["name"] or "數學" in c["name"] or "計算機" in c["name"] or "離散數學" in c["name"] or "微積分" in c["name"]:
                    # Ensure it is not Earth/Life dept course
                    if c["name"] not in EARTH_LIFE_MAJOR["common_compulsory"] and c["name"] not in EARTH_LIFE_MAJOR["domain_electives"][domain]:
                        report["free"]["science_college_cross_courses"].append(c)
                        report["free"]["science_college_cross_credits"] += comp_c
                consumed.add(c_idx)

    # --- PHASE 5: SUMMARY CALCULATION ---
    report["summary"]["common_completed"] = report["common"]["compulsory_completed"] + report["common"]["category_completed"] + report["common"]["common_elective_completed"]
    report["summary"]["common_ip"] = report["common"]["compulsory_ip"] + report["common"]["category_ip"] + report["common"]["common_elective_ip"]
    
    report["summary"]["major_completed"] = report["major"]["dept_compulsory_completed"] + report["major"]["domain_compulsory_completed"] + report["major"]["domain_elective_completed"] + report["major"]["other_elective_completed"]
    report["summary"]["major_ip"] = report["major"]["dept_compulsory_ip"] + report["major"]["domain_compulsory_ip"] + report["major"]["domain_elective_ip"] + report["major"]["other_elective_ip"]
    
    report["summary"]["target_completed"] = report["target"]["total_completed"]
    report["summary"]["target_ip"] = report["target"]["total_ip"]
    
    report["summary"]["free_completed"] = report["free"]["completed"]
    report["summary"]["free_ip"] = report["free"]["ip"]
    
    report["summary"]["total_completed"] = report["summary"]["common_completed"] + report["summary"]["major_completed"] + report["summary"]["target_completed"] + report["summary"]["free_completed"]
    report["summary"]["total_ip"] = report["summary"]["common_ip"] + report["summary"]["major_ip"] + report["summary"]["target_ip"] + report["summary"]["free_ip"]
    
    # Assess if graduation ready (128 credits total, common 28, major 85, free 15, missing compulsory = 0)
    has_enough_credits = (report["summary"]["total_completed"] >= 128.0)
    has_common_credits = (report["summary"]["common_completed"] >= 28.0)
    has_major_credits = (report["summary"]["major_completed"] >= 85.0)
    has_free_credits = (report["summary"]["free_completed"] >= 15.0)
    
    no_missing_compulsory = (
        len(report["common"]["compulsory_missing"]) == 0 and 
        len(report["major"]["dept_compulsory_missing"]) == 0 and 
        len(report["major"]["domain_compulsory_missing"]) == 0
    )
    
    # Under double major/minor, target requirements must be satisfied as well
    target_satisfied = True
    if program == "雙主修":
        target_satisfied = (report["target"]["total_completed"] >= 40.0)
    elif program == "輔系":
        target_satisfied = (report["target"]["total_completed"] >= 20.0)
        
    report["summary"]["graduation_ready"] = has_enough_credits and has_common_credits and has_major_credits and has_free_credits and no_missing_compulsory and target_satisfied
    
    return report

def find_and_consume_course(courses, rule_name, consumed_set):
    """
    Finds a course matching the rule name that is not consumed yet.
    Supports flexible matching e.g., chemical mathematical (一) vs (I).
    """
    norm_rule_name = normalize_course_name(rule_name)
    
    for c in courses:
        c_idx = id(c)
        if c_idx not in consumed_set:
            if c["name"] == norm_rule_name or norm_rule_name in c["name"] or c["name"] in norm_rule_name:
                consumed_set.add(c_idx)
                return c
                
    # Also support fuzzy name mappings
    fuzzy_mappings = {
        "英文(一)": "英文(一)",
        "英文(二)": "英文(二)",
        "英文(三)": "英文(三)：職場商旅",
        "國文(一)": "國文(一)：閱讀與思辨",
        "國文(二)": "國文(二)：語文表達",
        "普通物理學(一)": "普通物理(含實驗)",
        "普通化學(一)": "普通化學(含實驗)",
    }
    
    for key, val in fuzzy_mappings.items():
        if norm_rule_name == normalize_course_name(key) or norm_rule_name == normalize_course_name(val):
            for c in courses:
                c_idx = id(c)
                if c_idx not in consumed_set:
                    norm_c_name = normalize_course_name(c["name"])
                    if norm_c_name == normalize_course_name(key) or norm_c_name == normalize_course_name(val):
                        consumed_set.add(c_idx)
                        return c
                        
    return None
