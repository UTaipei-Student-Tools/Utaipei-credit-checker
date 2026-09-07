"""Time-first, read-only lookup of the supplied semester course snapshot."""
import json
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

CATALOG = Path(__file__).parent / "data" / "semester_courses_115_1.json"
DAYS = tuple("一二三四五六日")


def meeting_slots(text):
    slots = set()
    for day, start, end in re.findall(r"[（(]([一二三四五六日天])[）)]\s*(\d+)(?:\s*[-~～]\s*(\d+))?", text):
        first, last = int(start), int(end or start)
        if 0 <= first <= last <= 20:
            slots.update(("日" if day == "天" else day, period) for period in range(first, last + 1))
    return slots


def class_grades(row):
    # Only explicit class-name suffixes; never infer student eligibility.
    names = [row.get("class_name", ""), *row.get("mixed_classes", "").split(",")]
    grades = set()
    for name in names:
        match = re.search(r"([一二三四五六七八1-8])(?:[ABＣCＤD])?(?:\(30\+\))?$", name.strip())
        if match:
            value = match[1]
            grades.add(int(value) if value.isdigit() else "一二三四五六七八".index(value) + 1)
    return grades


@lru_cache(maxsize=1)
def load_catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def find_courses(rows, day, period=None, department="全部", grade="全部"):
    results = []
    for row in rows:
        slots = meeting_slots(row["teaching_raw"])
        if day == "未定時段":
            if slots:
                continue
        elif not any(d == day and (period is None or p == period) for d, p in slots):
            continue
        if department != "全部" and department not in row["departments"]:
            continue
        if grade != "全部" and int(grade) not in class_grades(row):
            continue
        results.append(row)
    return sorted(results, key=lambda row: (min(meeting_slots(row["teaching_raw"]), default=("", 0)), row["course_code"]))


def render_course_search(ui):
    try:
        catalog = load_catalog()
    except (OSError, ValueError):
        ui.warning("課程資料暫時無法讀取，請稍後再試。")
        return
    rows = catalog["courses"]
    query = catalog["query"]
    captured = datetime.fromisoformat(catalog["captured_at"]).astimezone(timezone(timedelta(hours=8)))
    ui.caption(f"{query['academic_year']}-{query['semester']} · {query['campus']}校區 · 資料擷取於 {captured:%Y/%m/%d}。非即時名額，也不代表個人選課資格。")
    day = ui.selectbox("先選星期", (*DAYS, "未定時段"), format_func=lambda d: "星期" + d if d in DAYS else d, key="course_search_day")
    periods = sorted({p for row in rows for d, p in meeting_slots(row["teaching_raw"]) if d == day})
    period = ui.selectbox("再選節次", [None, *periods], format_func=lambda p: "整天" if p is None else f"第 {p} 節", key="course_search_period", disabled=day == "未定時段")
    department = ui.selectbox("科系／開課單位（可不選）", ["全部", *sorted({d for row in rows for d in row["departments"]})], key="course_search_department")
    grade = ui.selectbox("年級（可不選）", ["全部", *map(str, range(1, 9))], key="course_search_grade")
    ui.caption("年級依開課班級與合班班級篩選；共同課程未註明年級時，請選「全部」。單雙週與完整上課資訊保留在表格內。")
    matches = find_courses(rows, day, period, department, grade)
    if not matches:
        ui.info("這個條件沒有課程。可改選其他節次，或將科系、年級改為全部。")
        return
    ui.write(f"找到 {len(matches)} 筆課程")
    ui.dataframe([{"選課代碼": r["course_code"], "課程": r["course_name_zh"],
                   "教師／完整時段／教室": r["teaching_raw"], "開課班級": r["class_name"],
                   "必選修": r["required_elective"], "學分": r["credits"],
                   "合班班級": r["mixed_classes"], "備註": r["remarks"]} for r in matches],
                 hide_index=True, use_container_width=True)
