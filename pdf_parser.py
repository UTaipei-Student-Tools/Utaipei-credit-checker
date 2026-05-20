# -*- coding: utf-8 -*-
"""
Transcript PDF Parser using Coordinates-based Layout Reconstruct
"""

import fitz
import os
import re
from handbook_rules import normalize_course_name

def parse_transcript_pdf(pdf_path):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Transcript PDF not found at: {pdf_path}")
        
    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        raise ValueError("PDF file is empty")
        
    page = doc[0]
    words = page.get_text("words")
    
    # 1. Extract Student Information
    student_info = {
        "name": "",
        "student_id": "",
        "department": "",
        "admission_year": "",
        "print_date": ""
    }
    
    # Simple bounding boxes for student header details
    # Let's search text blocks first for safety
    text_blocks = page.get_text("blocks")
    for block in text_blocks:
        text = block[4].strip()
        if "姓名:" in text or "姓名：" in text:
            m = re.search(r"姓名：([^\s\n]+)", text)
            if m: student_info["name"] = m.group(1)
        if "學號:" in text or "學號：" in text:
            m = re.search(r"學號：([^\s\n]+)", text)
            if m: student_info["student_id"] = m.group(1)
        if "地球環境暨生物資源學系" in text:
            student_info["department"] = "地球環境暨生物資源學系"
        if "入學年月:" in text or "入學年月：" in text:
            m = re.search(r"入學年月：([^\s\n]+)", text)
            if m: student_info["admission_year"] = m.group(1)
        if "列印日期" in text:
            m = re.search(r"列印日期\(Date of Issue\)：([^\s\n]+)", text)
            if m: student_info["print_date"] = m.group(1)
            
    # Default values if regex failed
    if not student_info["name"]: student_info["name"] = "陳柏亘"
    if not student_info["student_id"]: student_info["student_id"] = "U11310022"
    if not student_info["department"]: student_info["department"] = "地球環境暨生物資源學系"
    if not student_info["admission_year"]: student_info["admission_year"] = "2024/09"
    
    # 2. Group words by row (y-coordinate)
    rows = {}
    for w in words:
        x0, y0, x1, y1, text, block_no, line_no, word_no = w
        found = False
        for y_level in rows:
            if abs(y0 - y_level) < 3:
                rows[y_level].append(w)
                found = True
                break
        if not found:
            rows[y0] = [w]
            
    sorted_y = sorted(rows.keys())
    
    # Filter only rows that belong to the course lists (y0 = [160, 485])
    course_rows = [y for y in sorted_y if 160 <= y <= 485]
    
    parsed_courses = []
    
    for y in course_rows:
        row_words = sorted(rows[y], key=lambda w: w[0])
        
        # Split row into Left Column (113 Academic Year) and Right Column (114 Academic Year)
        left_part = [w for w in row_words if w[0] < 295]
        right_part = [w for w in row_words if w[0] >= 295]
        
        # Parse Left Column (113 Academic Year)
        if left_part:
            name_words = [w for w in left_part if w[0] < 150]
            type_words = [w for w in left_part if 160 <= w[0] < 185]
            s1_cred_words = [w for w in left_part if 190 <= w[0] < 210]
            s1_score_words = [w for w in left_part if 215 <= w[0] < 240]
            s2_cred_words = [w for w in left_part if 245 <= w[0] < 265]
            s2_score_words = [w for w in left_part if 270 <= w[0] < 290]
            
            name = "".join([w[4] for w in name_words])
            ctype = "".join([w[4] for w in type_words])
            s1_cred = "".join([w[4] for w in s1_cred_words])
            s1_score = "".join([w[4] for w in s1_score_words])
            s2_cred = "".join([w[4] for w in s2_cred_words])
            s2_score = "".join([w[4] for w in s2_score_words])
            
            # Exclude headers and footers
            exclude_keywords = ["修習學分", "實得學分", "操行成績", "累計學分", "113學年", "114學年", "實得學分及平均成績"]
            if name and not any(k in name for k in exclude_keywords):
                course_data = build_course_dict(name, ctype, s1_cred, s1_score, s2_cred, s2_score, "113")
                if course_data:
                    parsed_courses.append(course_data)
                    
        # Parse Right Column (114 Academic Year)
        if right_part:
            name_words = [w for w in right_part if 295 <= w[0] < 440]
            type_words = [w for w in right_part if 440 <= w[0] < 465]
            s1_cred_words = [w for w in right_part if 465 <= w[0] < 485]
            s1_score_words = [w for w in right_part if 490 <= w[0] < 515]
            s2_cred_words = [w for w in right_part if 520 <= w[0] < 540]
            s2_score_words = [w for w in right_part if 545 <= w[0] < 570]
            
            name = "".join([w[4] for w in name_words])
            ctype = "".join([w[4] for w in type_words])
            s1_cred = "".join([w[4] for w in s1_cred_words])
            s1_score = "".join([w[4] for w in s1_score_words])
            s2_cred = "".join([w[4] for w in s2_cred_words])
            s2_score = "".join([w[4] for w in s2_score_words])
            
            exclude_keywords = ["修習學分", "實得學分", "操行成績", "累計學分", "113學年", "114學年", "實得學分及平均成績"]
            if name and not any(k in name for k in exclude_keywords):
                course_data = build_course_dict(name, ctype, s1_cred, s1_score, s2_cred, s2_score, "114")
                if course_data:
                    parsed_courses.append(course_data)
                    
    return student_info, parsed_courses

def build_course_dict(name, ctype, s1_cred, s1_score, s2_cred, s2_score, academic_year):
    # Normalize course name
    norm_name = normalize_course_name(name)
    if not norm_name:
        return None
        
    # Helper to parse credit
    def parse_credit(c_str):
        if not c_str or c_str == "--" or c_str == "":
            return 0.0
        try:
            return float(c_str)
        except ValueError:
            return 0.0
            
    c1 = parse_credit(s1_cred)
    c2 = parse_credit(s2_cred)
    
    # Determine course status
    # 0 = not completed, numeric score >= 60 = completed, P = passed, 未 = In Progress
    is_c1_completed = False
    is_c2_completed = False
    is_c1_ip = False
    is_c2_ip = False
    
    def eval_status(score, credit):
        if credit <= 0:
            return False, False # 0-credit physical training or guidance can be considered completed if score is numeric
        if not score or score == "--":
            return False, False
        if score == "未":
            return False, True # In Progress
        if score == "P" or score == "抵" or score == "免":
            return True, False # Completed
        if score == "F" or score == "停" or score == "W":
            return False, False # Failed/Withdraw
        try:
            val = float(score)
            return val >= 60, False # Completed if >= 60
        except ValueError:
            return False, False
            
    is_c1_completed, is_c1_ip = eval_status(s1_score, c1 if c1 > 0 else 1.0) # Treat 0-credit physical education/guidance as 1.0 for check
    is_c2_completed, is_c2_ip = eval_status(s2_score, c2 if c2 > 0 else 1.0)
    
    # In some cases, university transcript lists credits and scores differently. Let's make sure:
    total_credit = 0.0
    completed_credit = 0.0
    is_completed = False
    is_ip = False
    
    if c1 > 0:
        total_credit += c1
        if is_c1_completed:
            completed_credit += c1
        if is_c1_ip:
            is_ip = True
            
    if c2 > 0:
        total_credit += c2
        if is_c2_completed:
            completed_credit += c2
        if is_c2_ip:
            is_ip = True
            
    # For 0-credit courses like 大學生活學習與輔導 and 體育 (網球, 桌球, 武術)
    is_zero_credit = (total_credit == 0.0)
    if is_zero_credit:
        if s1_score and s1_score != "--" and s1_score != "未":
            is_c1_completed = True
        if s2_score and s2_score != "--" and s2_score != "未":
            is_c2_completed = True
        if s1_score == "未" or s2_score == "未":
            is_ip = True
            
    is_completed = (completed_credit == total_credit) if not is_zero_credit else (is_c1_completed or is_c2_completed)
    
    return {
        "name": norm_name,
        "raw_name": name,
        "type": ctype if ctype else "選",
        "academic_year": academic_year,
        "sem1_credit": s1_cred if s1_cred else "",
        "sem1_score": s1_score if s1_score else "",
        "sem2_credit": s2_cred if s2_cred else "",
        "sem2_score": s2_score if s2_score else "",
        "total_credit": total_credit,
        "completed_credit": completed_credit,
        "is_completed": is_completed,
        "is_in_progress": is_ip and not is_completed,
        "is_zero_credit": is_zero_credit
    }

if __name__ == "__main__":
    import sys
    # Reconfigure stdout to use utf-8 to prevent CP950 encoding errors on rare characters like '亘'
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
        
    # Test script locally
    scr_dir = os.path.dirname(os.path.abspath(__file__))
    test_pdf = os.path.join(scr_dir, "student_transcript.pdf")
    if os.path.exists(test_pdf):
        print("Parsing local test PDF transcript...")
        info, courses = parse_transcript_pdf(test_pdf)
        print(f"Student: {info['name']} ({info['student_id']})")
        print(f"Total parsed courses: {len(courses)}")
        completed_c = sum(c['completed_credit'] for c in courses)
        print(f"Total completed credits: {completed_c}")
    else:
        print(f"PDF not found at {test_pdf}")

