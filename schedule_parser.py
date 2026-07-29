"""
Parser for UTaipei Portal AG104 Course Schedule HTML.
"""

import re

from bs4 import BeautifulSoup

from handbook_rules import normalize_course_name


def parse_schedule_html(html_content, academic_year="115", semester="1"):
    """
    Parses the UTaipei portal AG104 HTML content and extracts courses.
    Returns a list of course dictionaries.
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    courses = []
    seen_names = set()

    def add_course(norm_name, raw_name, course_type, credit):
        if not norm_name or norm_name in seen_names:
            return
        seen_names.add(norm_name)
        is_second = str(semester) == "2"
        courses.append(
            {
                "name": norm_name,
                "raw_name": raw_name,
                "type": course_type,
                "academic_year": str(academic_year),
                "semester": str(semester),
                "sem1_credit": "" if is_second else str(credit),
                "sem1_score": "" if is_second else "未",
                "sem2_credit": str(credit) if is_second else "",
                "sem2_score": "未" if is_second else "",
                "total_credit": float(credit),
                "completed_credit": 0.0,
                "is_completed": False,
                "is_in_progress": True,
                "is_zero_credit": float(credit) == 0.0,
            }
        )

    # 1. Search for a table with course list.
    # Usually this table has rows with columns: 課號, 科目名稱, 學分, 必選修, etc.
    tables = soup.find_all("table")

    for table in tables:
        # Check if the table has headers like '科目名稱' or '課程名稱' and '學分'
        rows = table.find_all("tr")
        if not rows:
            continue

        header_row = None
        for r in rows[:3]:  # check first 3 rows
            cells = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
            if any("科目" in cell or "課程" in cell for cell in cells) and any("學分" in cell for cell in cells):
                header_row = cells
                break

        if header_row:
            name_idx = -1
            credit_idx = -1
            type_idx = -1

            for idx, cell in enumerate(header_row):
                if any(x in cell for x in ["科目名稱", "課程名稱", "科目", "課程"]):
                    name_idx = idx
                elif "學分" in cell:
                    credit_idx = idx
                elif any(x in cell for x in ["選別", "必選", "屬性", "必/選"]):
                    type_idx = idx

            if name_idx != -1:
                # Parse course rows
                for r in rows:
                    cells = r.find_all(["td"])
                    if len(cells) <= max(name_idx, credit_idx, type_idx):
                        continue
                    name_txt = cells[name_idx].get_text(strip=True)
                    if not name_txt or any(x in name_txt for x in ["名稱", "科目", "課程"]):
                        continue

                    # Filter out common noise
                    if re.match(r"^\d+$", name_txt) or len(name_txt) < 2:
                        continue

                    # Get credit
                    credit_val = 2.0
                    if credit_idx != -1:
                        try:
                            credit_txt = cells[credit_idx].get_text(strip=True)
                            m = re.search(r"\d+(?:\.\d+)?", credit_txt)
                            if m:
                                credit_val = float(m.group(0))
                        except Exception:
                            pass

                    # Get compulsory/elective type
                    type_val = "選"
                    if type_idx != -1:
                        type_txt = cells[type_idx].get_text(strip=True)
                        if "必" in type_txt:
                            type_val = "必"

                    norm_name = normalize_course_name(name_txt)
                    # Check if already added
                    add_course(norm_name, name_txt, type_val, credit_val)

    # 2. If no course list table found, parse the grid cells as fallback.
    if not courses:
        for table in tables:
            rows = table.find_all("tr")
            for r in rows:
                cells = r.find_all("td")
                for cell in cells:
                    # Clear nested tags that are noise
                    for tag in cell.find_all(["script", "style", "table"]):
                        tag.decompose()

                    text_parts = [t.strip() for t in cell.find_all(string=True) if t.strip()]
                    if not text_parts:
                        continue

                    # Usually, the first part is the course name
                    course_candidate = text_parts[0]

                    if len(course_candidate) < 2:
                        continue
                    if re.match(r"^\d+$", course_candidate):
                        continue
                    if any(x in course_candidate for x in ["星期", "時間", "節次", "第一節", "第二節", "第"]):
                        continue
                    if re.match(r"^[A-Z]\d+$", course_candidate):
                        continue

                    course_name = re.sub(r"^\d+[-_]?\d*\s*", "", course_candidate)
                    if not any(c.isalpha() or "\u4e00" <= c <= "\u9fff" for c in course_name):
                        continue

                    norm_name = normalize_course_name(course_name)
                    # The fallback layout does not expose credits reliably.
                    add_course(norm_name, course_name, "選", 2.0)

    return courses
