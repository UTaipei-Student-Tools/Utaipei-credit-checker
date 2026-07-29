"""Parser and merge helpers for the UTaipei AG104 course schedule."""

import re

from bs4 import BeautifulSoup

from handbook_rules import normalize_course_name

COURSE_NAME_HEADERS = ("科目名稱", "課程名稱", "科目", "課程")
COURSE_TYPE_HEADERS = ("選別", "必選修", "必選", "屬性", "必/選")
COURSE_LINK_HINTS = ("ag064", "course", "crs", "syllabus")
NOISE_PREFIXES = (
    "列印日期",
    "列印時間",
    "列印：",
    "查詢日期",
    "查詢時間",
    "查詢條件",
    "資料日期",
    "產生日期",
    "學年度",
    "學期",
    "學生姓名",
    "姓名",
    "學號",
    "系所",
    "班級",
    "課表列印",
    "回上一頁",
    "頁次",
    "合計",
    "總計",
)
NOISE_EXACT = {
    "課表",
    "班級課表",
    "個人課表",
    "開課課表",
    "科目名稱",
    "課程名稱",
    "科目",
    "課程",
    "學分",
    "選別",
    "必選修",
    "授課教師",
    "教師",
    "教室",
    "節次",
    "時間",
}


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_noise_course_name(value):
    """Return True for headers, page metadata, dates, codes and other non-course text."""
    name = _clean_text(value)
    compact = re.sub(r"\s+", "", name)
    if not name or len(name) < 2 or len(name) > 80:
        return True
    if compact in NOISE_EXACT or any(compact.startswith(prefix) for prefix in NOISE_PREFIXES):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?", compact) or re.fullmatch(r"[A-Z]{1,4}\d+(?:\.\d+)?", compact):
        return True
    if re.search(r"\d{3,4}[/-]\d{1,2}[/-]\d{1,2}(?:\D+\d{1,2}:\d{2})?", compact):
        return True
    if compact.startswith(("星期", "第1節", "第一節", "第二節", "第三節", "第四節", "第五節")):
        return True
    if "http://" in name.lower() or "https://" in name.lower():
        return True
    return not any(char.isalpha() or "\u4e00" <= char <= "\u9fff" for char in name)


def _parse_credit(value, *, allow_plain_number=False):
    """Parse a plausible course credit value; never invent a default credit."""
    text = _clean_text(value)
    patterns = (
        r"(?:學分|credits?)\s*[:：]?\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*(?:學分|credits?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            credit = float(match.group(1))
            return credit if 0.0 <= credit <= 10.0 else None
    if allow_plain_number:
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", text)
        if match:
            credit = float(match.group(1))
            return credit if 0.0 <= credit <= 10.0 else None
    return None


def _schedule_course(raw_name, course_type, credit, academic_year, semester):
    norm_name = normalize_course_name(_clean_text(raw_name))
    if _is_noise_course_name(norm_name) or credit is None:
        return None
    is_second = str(semester) == "2"
    return {
        "name": norm_name,
        "raw_name": _clean_text(raw_name),
        "type": "必" if "必" in str(course_type or "") else "選",
        "academic_year": str(academic_year),
        "semester": str(semester),
        "sem1_credit": "" if is_second else str(float(credit)),
        "sem1_score": "" if is_second else "未",
        "sem2_credit": str(float(credit)) if is_second else "",
        "sem2_score": "未" if is_second else "",
        "total_credit": float(credit),
        "completed_credit": 0.0,
        "is_completed": False,
        "is_in_progress": True,
        "is_zero_credit": float(credit) == 0.0,
        "source": "schedule",
        "source_label": f"{academic_year}-{semester} 課表",
    }


def parse_schedule_html(html_content, academic_year="115", semester="1"):
    """Extract real course rows from an AG104 response as in-progress courses."""
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    courses = []
    seen_names = set()

    def add_course(raw_name, course_type, credit):
        course = _schedule_course(raw_name, course_type, credit, academic_year, semester)
        if not course or course["name"] in seen_names:
            return
        seen_names.add(course["name"])
        courses.append(course)

    tables = soup.find_all("table")

    # Prefer list tables with explicit course-name and credit columns.
    for table in tables:
        rows = table.find_all("tr")
        header_cells = None
        header_index = -1
        for index, row in enumerate(rows[:6]):
            cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
            has_name = any(any(header in cell for header in COURSE_NAME_HEADERS) for cell in cells)
            has_credit = any("學分" in cell or "credit" in cell.lower() for cell in cells)
            if has_name and has_credit:
                header_cells = cells
                header_index = index
                break
        if not header_cells:
            continue

        name_index = next(
            (i for i, cell in enumerate(header_cells) if any(header in cell for header in COURSE_NAME_HEADERS)), -1
        )
        credit_index = next(
            (i for i, cell in enumerate(header_cells) if "學分" in cell or "credit" in cell.lower()), -1
        )
        type_index = next(
            (i for i, cell in enumerate(header_cells) if any(header in cell for header in COURSE_TYPE_HEADERS)), -1
        )
        if name_index < 0 or credit_index < 0:
            continue

        for row in rows[header_index + 1 :]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(name_index, credit_index):
                continue
            name_text = _clean_text(cells[name_index].get_text(" ", strip=True))
            if _is_noise_course_name(name_text):
                continue
            credit = _parse_credit(cells[credit_index].get_text(" ", strip=True), allow_plain_number=True)
            if credit is None:
                continue
            course_type = cells[type_index].get_text(" ", strip=True) if 0 <= type_index < len(cells) else "選"
            add_course(name_text, course_type, credit)

    # Some timetable grids expose courses as syllabus/course-detail links rather than list rows.
    # Only accept such links when an explicit credit value is present in the same cell/row.
    if not courses:
        for table in tables:
            for cell in table.find_all("td"):
                if cell.find("table"):
                    continue
                full_text = _clean_text(cell.get_text(" ", strip=True))
                credit = _parse_credit(full_text)
                if credit is None:
                    for attr in ("data-credit", "data-credits", "credit"):
                        credit = _parse_credit(cell.get(attr), allow_plain_number=True)
                        if credit is not None:
                            break
                if credit is None:
                    continue

                for link in cell.find_all("a"):
                    href = str(link.get("href") or "").lower()
                    onclick = str(link.get("onclick") or "").lower()
                    if not any(hint in href or hint in onclick for hint in COURSE_LINK_HINTS):
                        continue
                    name_text = _clean_text(link.get_text(" ", strip=True) or link.get("title"))
                    if _is_noise_course_name(name_text):
                        continue
                    add_course(name_text, "必" if "必" in full_text else "選", credit)
                    break

    return courses


def merge_schedule_courses(transcript_courses, schedule_courses):
    """Merge published schedule courses without double-counting completed/in-progress courses."""
    merged = list(transcript_courses or [])
    existing_names = {
        normalize_course_name(course.get("name", ""))
        for course in merged
        if course.get("is_completed") or course.get("is_in_progress")
    }
    added = []
    for schedule_course in schedule_courses or []:
        name = normalize_course_name(schedule_course.get("name", ""))
        if not name or name in existing_names or _is_noise_course_name(name):
            continue
        course = dict(schedule_course)
        course["name"] = name
        course["source"] = "schedule"
        course["is_completed"] = False
        course["is_in_progress"] = True
        course["completed_credit"] = 0.0
        merged.append(course)
        added.append(course)
        existing_names.add(name)
    return merged, added
