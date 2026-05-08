from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from app.models import CourseRecord, CourseStatus


INVALID_MARKERS = ("先修未過", "擋修", "不得採計", "不採計", "退選", "停修")


def _status_from_text(text: str) -> CourseStatus:
    if any(marker in text for marker in ("先修未過", "擋修", "不得採計", "不採計")):
        return CourseStatus.NEEDS_REVIEW
    if any(marker in text for marker in ("退選", "停修")):
        return CourseStatus.INVALID
    return CourseStatus.PASSED


def _parse_line(line: str, semester: str | None) -> CourseRecord | None:
    compact = re.sub(r"\s+", " ", line).strip()
    if not compact:
        return None
    if re.search(r"(學分|科目|成績|平均|排名)", compact):
        return None

    match = re.match(
        r"(?P<name>[\u4e00-\u9fffA-Za-z0-9()+（）ⅠⅡⅢIVX \-]+?)\s+"
        r"(?P<credits>\d+(?:\.\d)?)\s+"
        r"(?P<grade>\d{1,3}|抵免|通過|P|不及格|退選|停修)",
        compact,
    )
    if not match:
        return None
    name = match.group("name").strip()
    if len(name) <= 1:
        return None
    notes = compact[match.end() :].strip() or None
    text = compact
    return CourseRecord(
        name=name,
        credits=float(match.group("credits")),
        semester=semester,
        grade=match.group("grade"),
        notes=notes,
        status=_status_from_text(text),
        source="transcript_pdf",
        raw={"line": line},
    )


def parse_transcript_text(text: str) -> list[CourseRecord]:
    courses: list[CourseRecord] = []
    semester: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        semester_match = re.search(r"(\d{2,3})\s*學年度\s*第?\s*([一二1-2])\s*學期", line)
        if semester_match:
            semester = line
        course = _parse_line(line, semester)
        if course:
            courses.append(course)
    return courses


def parse_transcript_pdf(path: str | Path) -> list[CourseRecord]:
    chunks: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return parse_transcript_text("\n".join(chunks))

