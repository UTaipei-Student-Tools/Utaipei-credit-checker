from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from app.models import CourseRecord, CourseStatus, DataQuality, ParsedCourses, ParseDiagnostic

INVALID_MARKERS = ("先修未過", "擋修", "不得採計", "不採計")
WITHDRAWAL_MARKERS = ("退選", "停修", "W")
GRADE_PATTERN = (
    r"(?:\d{1,3}(?:\.\d+)?|[A-F](?:[+-])?|P|NP|PASS|FAIL|S|U|"
    r"抵免|通過|不通過|及格|不及格|退選|停修|W)"
)
COURSE_LINE_RE = re.compile(
    rf"^(?P<name>.+?)\s+(?P<credits>\d+(?:\.\d+)?)\s+"
    rf"(?P<grade>{GRADE_PATTERN})(?:\s+(?P<notes>.*))?$",
    flags=re.IGNORECASE,
)
SEMESTER_RE = re.compile(r"(\d{2,3})\s*學年度\s*第?\s*([一二1-2])\s*學期")
HEADER_KEYWORDS = ("學分", "科目", "成績", "平均", "排名", "學年度", "姓名", "學號")


def _status_from_text(text: str, grade: str) -> CourseStatus:
    if any(marker in text for marker in INVALID_MARKERS):
        return CourseStatus.NEEDS_REVIEW
    if any(marker in text for marker in ("退選", "停修")) or grade.strip().upper() == "W":
        return CourseStatus.INVALID
    return CourseStatus.PASSED


def _clean_course_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip(" -|｜")
    # Some exports prepend a course code. Remove it only when a readable name remains.
    parts = cleaned.split(" ", 1)
    if (
        len(parts) == 2
        and re.fullmatch(r"[A-Za-z0-9_-]{4,16}", parts[0])
        and (re.search(r"\d", parts[0]) or parts[0].isupper())
    ):
        if re.search(r"[\u4e00-\u9fffA-Za-z]", parts[1]):
            cleaned = parts[1]
    return cleaned


def _parse_line(line: str, semester: str | None) -> CourseRecord | None:
    compact = re.sub(r"\s+", " ", line).strip()
    if not compact:
        return None
    match = COURSE_LINE_RE.match(compact)
    if not match:
        return None
    name = _clean_course_name(match.group("name"))
    if len(name) <= 1 or not re.search(r"[\u4e00-\u9fffA-Za-z]", name):
        return None
    if any(marker in name for marker in ("總學分", "實得學分", "修習學分", "學期平均", "排名")):
        return None
    credits = float(match.group("credits"))
    if not 0 <= credits <= 12:
        return None
    grade = match.group("grade")
    notes = (match.group("notes") or "").strip() or None
    return CourseRecord(
        name=name,
        credits=credits,
        semester=semester,
        grade=grade,
        notes=notes,
        status=_status_from_text(compact, grade),
        source="transcript_pdf",
        raw={"line": line},
    )


def _looks_like_course_line(line: str) -> bool:
    compact = re.sub(r"\s+", " ", line).strip()
    if not compact or any(keyword in compact for keyword in HEADER_KEYWORDS):
        return False
    return bool(re.search(rf"\s\d+(?:\.\d+)?\s+{GRADE_PATTERN}(?:\s|$)", compact, flags=re.IGNORECASE))


def parse_transcript_text_with_diagnostics(text: str) -> ParsedCourses:
    courses: list[CourseRecord] = []
    semester: str | None = None
    candidates = 0
    unparsed: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        semester_match = SEMESTER_RE.search(line)
        if semester_match:
            semester = f"{semester_match.group(1)}-{semester_match.group(2)}"
            continue
        course = _parse_line(line, semester)
        if course:
            candidates += 1
            courses.append(course)
        elif _looks_like_course_line(line):
            candidates += 1
            if len(unparsed) < 10:
                unparsed.append(line[:300])

    unparsed_count = max(candidates - len(courses), 0)
    messages: list[str] = []
    if not courses:
        quality = DataQuality.FAILED
        messages.append("未能從成績單解析出任何課程；已停止正式學分審核。")
    elif unparsed_count:
        quality = DataQuality.PARTIAL
        messages.append(f"有 {unparsed_count} 筆疑似課程列無法解析，結果需人工核對。")
    else:
        quality = DataQuality.COMPLETE

    return ParsedCourses(
        courses=courses,
        diagnostic=ParseDiagnostic(
            source="transcript_pdf",
            quality=quality,
            total_candidates=candidates,
            parsed_count=len(courses),
            unparsed_count=unparsed_count,
            messages=messages,
            unparsed_samples=unparsed,
        ),
    )


def parse_transcript_text(text: str) -> list[CourseRecord]:
    return parse_transcript_text_with_diagnostics(text).courses


def parse_transcript_pdf_with_diagnostics(path: str | Path) -> ParsedCourses:
    chunks: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        if not pdf.pages:
            return ParsedCourses(
                courses=[],
                diagnostic=ParseDiagnostic(
                    source="transcript_pdf",
                    quality=DataQuality.FAILED,
                    messages=["PDF 沒有可讀頁面。"],
                ),
            )
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return parse_transcript_text_with_diagnostics("\n".join(chunks))


def parse_transcript_pdf(path: str | Path) -> list[CourseRecord]:
    return parse_transcript_pdf_with_diagnostics(path).courses
