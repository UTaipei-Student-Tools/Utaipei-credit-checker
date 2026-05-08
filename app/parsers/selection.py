from __future__ import annotations

import re

from bs4 import BeautifulSoup

from app.models import CourseRecord, CourseStatus


def parse_selection_html(html: str) -> list[CourseRecord]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    courses: list[CourseRecord] = []

    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        joined = " ".join(cells)
        credit = next((float(value) for value in cells if re.fullmatch(r"\d+(?:\.\d)?", value)), None)
        if credit is None:
            continue
        name = _guess_course_name(cells)
        if not name:
            continue
        courses.append(
            CourseRecord(
                name=name,
                credits=credit,
                category=next((cell for cell in cells if "必修" in cell or "選修" in cell), None),
                notes=joined,
                status=CourseStatus.IN_PROGRESS,
                source="selection_html",
                raw={"cells": cells},
            )
        )

    if courses:
        return courses

    for line in text.splitlines():
        match = re.search(r"(?P<name>[\u4e00-\u9fffA-Za-z0-9()+（）ⅠⅡⅢIVX \-]{2,})\s+(?P<credits>\d+(?:\.\d)?)", line)
        if match:
            courses.append(
                CourseRecord(
                    name=match.group("name").strip(),
                    credits=float(match.group("credits")),
                    notes=line.strip(),
                    status=CourseStatus.IN_PROGRESS,
                    source="selection_html",
                )
            )
    return courses


def _guess_course_name(cells: list[str]) -> str | None:
    skip = {"選課代號", "學分數", "必選修", "科目", "班級"}
    for cell in cells:
        if cell in skip:
            continue
        if re.fullmatch(r"\d+(?:\.\d)?", cell):
            continue
        if len(cell) >= 2 and re.search(r"[\u4e00-\u9fffA-Za-z]", cell):
            if "老師" in cell or "教室" in cell:
                continue
            return cell
    return None
