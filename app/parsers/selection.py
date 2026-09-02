from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup

from app.models import CourseRecord, CourseStatus, DataQuality, ParsedCourses, ParseDiagnostic

NAME_HEADERS = {"科目", "科目名稱", "課程", "課程名稱", "中文科目名稱"}
CREDIT_HEADERS = {"學分", "學分數", "學分數/時數", "學分/時數"}
CATEGORY_HEADERS = {"必選修", "修別", "課程類別", "類別"}
DEPARTMENT_HEADERS = {"開課系所", "開課單位", "系所"}
SEMESTER_HEADERS = {"學期", "學年度學期"}


def _header_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"[\s：:()（）]", "", text).strip()


def _find_index(headers: list[str], aliases: set[str]) -> int | None:
    normalized_aliases = {_header_key(alias) for alias in aliases}
    for index, header in enumerate(headers):
        if _header_key(header) in normalized_aliases:
            return index
    return None


def _safe_cell(cells: list[str], index: int | None) -> str | None:
    if index is None or index >= len(cells):
        return None
    value = cells[index].strip()
    return value or None


def _parse_credit(value: str) -> float | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:[/／]\s*\d+(?:\.\d+)?)?\s*", value)
    if not match:
        return None
    credits = float(match.group(1))
    return credits if 0 <= credits <= 12 else None


def parse_selection_html_with_diagnostics(html: str) -> ParsedCourses:
    soup = BeautifulSoup(html, "html.parser")
    courses: list[CourseRecord] = []
    candidates = 0
    unparsed: list[str] = []
    recognized_tables = 0

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header_position: int | None = None
        header_cells: list[str] = []
        name_index: int | None = None
        credit_index: int | None = None
        category_index: int | None = None
        department_index: int | None = None
        semester_index: int | None = None

        for position, row in enumerate(rows):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if not cells:
                continue
            candidate_name_index = _find_index(cells, NAME_HEADERS)
            candidate_credit_index = _find_index(cells, CREDIT_HEADERS)
            if candidate_name_index is not None and candidate_credit_index is not None:
                header_position = position
                header_cells = cells
                name_index = candidate_name_index
                credit_index = candidate_credit_index
                category_index = _find_index(cells, CATEGORY_HEADERS)
                department_index = _find_index(cells, DEPARTMENT_HEADERS)
                semester_index = _find_index(cells, SEMESTER_HEADERS)
                recognized_tables += 1
                break

        if header_position is None or name_index is None or credit_index is None:
            continue

        for row in rows[header_position + 1 :]:
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            if not cells or cells == header_cells:
                continue
            if max(name_index, credit_index) >= len(cells):
                continue
            name = cells[name_index].strip()
            credit_text = cells[credit_index].strip()
            if not name and not credit_text:
                continue
            candidates += 1
            credits = _parse_credit(credit_text)
            if credits is None:
                if len(unparsed) < 10:
                    unparsed.append(" | ".join(cells)[:300])
                continue
            if not name or not re.search(r"[\u4e00-\u9fffA-Za-z]", name):
                if len(unparsed) < 10:
                    unparsed.append(" | ".join(cells)[:300])
                continue
            courses.append(
                CourseRecord(
                    name=name,
                    credits=credits,
                    semester=_safe_cell(cells, semester_index),
                    category=_safe_cell(cells, category_index),
                    department=_safe_cell(cells, department_index),
                    notes=" | ".join(cells),
                    status=CourseStatus.IN_PROGRESS,
                    source="selection_html",
                    raw={"cells": cells},
                )
            )

    unparsed_count = max(candidates - len(courses), 0)
    messages: list[str] = []
    if recognized_tables == 0:
        quality = DataQuality.FAILED
        messages.append("找不到同時包含課程名稱與學分欄位的選課表格。")
    elif unparsed_count:
        quality = DataQuality.PARTIAL
        messages.append(f"有 {unparsed_count} 筆選課資料無法解析。")
    else:
        quality = DataQuality.COMPLETE

    return ParsedCourses(
        courses=courses,
        diagnostic=ParseDiagnostic(
            source="selection_html",
            quality=quality,
            total_candidates=candidates,
            parsed_count=len(courses),
            unparsed_count=unparsed_count,
            messages=messages,
            unparsed_samples=unparsed,
        ),
    )


def parse_selection_html(html: str) -> list[CourseRecord]:
    return parse_selection_html_with_diagnostics(html).courses
