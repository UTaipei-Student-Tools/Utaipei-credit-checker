"""Parser and merge helpers for the UTaipei AG104 course schedule.

The portal returns HTML with a surprisingly broad range of meanings: an
empty, but valid, course list; a login page rendered with HTTP 200; and pages
whose markup changed enough that a parser cannot safely identify the result.
The status-bearing API below keeps those cases distinct while
``parse_schedule_html`` remains compatible with the original list-returning
API.
"""

import re
from dataclasses import dataclass

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

VALID_EMPTY = "VALID_EMPTY"
VALID_WITH_ROWS = "VALID_WITH_ROWS"
INVALID_PAGE = "INVALID_PAGE"
AG104_UNVERIFIABLE_RESPONSE = "AG104_UNVERIFIABLE_RESPONSE"
MAINTENANCE_MARKERS = (
    "維護中",
    "暫停服務",
    "系統忙碌",
    "系統維護",
    "maintenance",
    "service unavailable",
    "temporarily unavailable",
    "system busy",
    "under maintenance",
)
LOGIN_FORM_IDS = {"login", "loginform", "login_form", "login-form"}
LOGIN_CONTEXT_MARKERS = ("登入", "sign in", "log in", "login page", "login form", "login portal")


@dataclass(frozen=True)
class ScheduleParseResult:
    """A safe, immutable interpretation of an AG104 response."""

    status: str
    courses: tuple = ()
    reason: str = ""

    def __post_init__(self):
        object.__setattr__(self, "courses", tuple(self.courses or ()))


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_maintenance_page(html_content):
    """Return true for known maintenance/interstitial page language."""

    if not html_content:
        return False
    soup = BeautifulSoup(str(html_content), "html.parser")
    text = _clean_text(soup.get_text(" ", strip=True)).lower()
    return any(marker.lower() in text for marker in MAINTENANCE_MARKERS)


def _has_login_context(text):
    normalized = _clean_text(text).lower()
    # ``Last login`` and labels such as ``帳號設定`` are common on an
    # authenticated account page.  They must not be treated as a login
    # interstitial merely because they contain the substring ``login`` or
    # ``帳號``.  Chinese ``登入`` remains an explicit portal-login signal;
    # English signals are restricted to phrases that describe a login UI.
    if "登入" in normalized:
        return True
    return any(marker in normalized for marker in LOGIN_CONTEXT_MARKERS[1:])


def is_login_page(html_content):
    """Identify a login page without mistaking authenticated hidden controls."""

    if not html_content:
        return False
    soup = BeautifulSoup(str(html_content), "html.parser")
    visible_text = _clean_text(soup.get_text(" ", strip=True))
    for form in soup.find_all("form"):
        action = str(form.get("action") or "").lower()
        form_id = str(form.get("id") or "").lower()
        if "login_check" in action or form_id in LOGIN_FORM_IDS or form_id.startswith("login"):
            return True
        has_password_input = any(
            str(control.get("type") or "").lower() == "password" for control in form.find_all("input")
        )
        form_text = _clean_text(form.get_text(" ", strip=True))
        if has_password_input and (_has_login_context(form_text) or _has_login_context(visible_text)):
            return True
    # Text alone is deliberately insufficient.  Authenticated pages often
    # contain labels such as 帳號設定, 密碼最後更新 or Last login; without a
    # recognized login form/password control those words cannot establish that
    # the response is a login interstitial.
    return False


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


def _parse_schedule_courses(html_content, academic_year="115", semester="1"):
    """Extract real course rows from a recognized AG104 response."""
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


def _looks_like_login_page(soup, html_content):
    """Identify a portal login response without trusting its HTTP status."""

    return is_login_page(html_content)


def _looks_like_schedule_page(soup):
    """Return whether the document has an identifiable AG104 result shell."""

    text = _clean_text(soup.get_text(" ", strip=True)).lower()
    # Generic open-course catalogues commonly contain 「開課／選課」 plus the
    # same 科目名稱／學分 headers.  Those pages are not proof of the student's
    # enrolled timetable, so only an explicit timetable label or AG104 marker
    # can establish schedule identity.
    has_schedule_semantics = any(marker in text for marker in ("課表", "課程表"))
    has_ag104_marker = _has_ag104_marker(soup)

    # A result must carry either an explicit AG104 marker or clear schedule
    # language.  This prevents a generic course catalogue with the same two
    # headers (科目名稱／學分) from being accepted as a verified timetable.
    if not (has_schedule_semantics or has_ag104_marker):
        return False

    for table in soup.find_all("table"):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in table.find_all(["td", "th"])[:24]]
        has_name = any(any(header in cell for header in COURSE_NAME_HEADERS) for cell in cells)
        has_credit = any("學分" in cell or "credit" in cell.lower() for cell in cells)
        if has_name and has_credit:
            return True
        if has_credit and any(
            any(hint in str(link.get("href") or "").lower() for hint in COURSE_LINK_HINTS)
            or any(hint in str(link.get("onclick") or "").lower() for hint in COURSE_LINK_HINTS)
            for link in table.find_all("a")
        ):
            return True
    # A form-only AG104 shell is not enough to prove that the requested term
    # was rendered.  In particular, the real portal can return a one-row,
    # three-cell layout shell (1列3格) before its result table; that response
    # must remain UNKNOWN/invalid instead of becoming VALID_EMPTY.
    return False


def _has_ag104_marker(soup):
    """Return whether markup carries an explicit AG104 identity marker."""

    return any(
        "ag104" in str(form.get("action") or "").lower()
        or "ag104" in str(form.get("id") or "").lower()
        or "ag104" in str(form.get("name") or "").lower()
        for form in soup.find_all("form")
    ) or "ag104" in str(soup).lower()


def is_unverifiable_ag104_response(html_content, *, trusted_ag104=False):
    """Identify the known AG104 one-row/three-cell response shell.

    This is deliberately narrower than ``INVALID_PAGE``.  It only applies to
    exactly one table containing exactly one three-cell row, without a
    verifiable schedule header/result.  Normal parser callers must provide an
    explicit AG104 marker; the scraper may set ``trusted_ag104`` only after it
    has pinned the request to the official AG104 route.  Such a shell means
    the query reached the portal, but the returned markup cannot prove either
    courses or a legitimate empty timetable.
    """

    if not html_content or not isinstance(html_content, str):
        return False
    soup = BeautifulSoup(html_content, "html.parser")
    if is_login_page(html_content) or is_maintenance_page(html_content):
        return False
    if _looks_like_schedule_page(soup):
        return False
    if not trusted_ag104 and not _has_ag104_marker(soup):
        return False
    # A second-stage query form also uses a three-cell layout table, but its
    # advertised ``yms`` selector proves that the query has not yet returned
    # a result.  Keep that flow eligible for the normal second POST.
    if any(
        str(select.get("name") or "").strip().lower() == "yms"
        for select in soup.find_all("select")
    ):
        return False
    tables = soup.find_all("table")
    if len(tables) != 1:
        return False
    rows = tables[0].find_all("tr")
    if len(rows) != 1:
        return False
    cells = rows[0].find_all(["td", "th"], recursive=False)
    return len(cells) == 3


def parse_schedule_result(html_content, academic_year="115", semester="1"):
    """Parse AG104 HTML and explicitly distinguish valid empty from invalid.

    ``INVALID_PAGE`` is fail-closed: callers must not replace previously
    confirmed schedule data when this status is returned.
    """

    if not html_content or not isinstance(html_content, str):
        return ScheduleParseResult(INVALID_PAGE, reason="課表頁面內容不足")
    soup = BeautifulSoup(html_content, "html.parser")
    if _looks_like_login_page(soup, html_content):
        return ScheduleParseResult(INVALID_PAGE, reason="收到登入頁")
    if is_maintenance_page(html_content):
        return ScheduleParseResult(INVALID_PAGE, reason="收到維護頁")
    if is_unverifiable_ag104_response(html_content):
        return ScheduleParseResult(INVALID_PAGE, reason=AG104_UNVERIFIABLE_RESPONSE)
    if not _looks_like_schedule_page(soup):
        return ScheduleParseResult(INVALID_PAGE, reason="無法辨識課表頁面")
    courses = _parse_schedule_courses(html_content, academic_year=academic_year, semester=semester)
    if courses:
        return ScheduleParseResult(VALID_WITH_ROWS, courses=tuple(courses))
    return ScheduleParseResult(VALID_EMPTY)


def parse_schedule_html(html_content, academic_year="115", semester="1"):
    """Backward-compatible list API; invalid pages safely return an empty list."""

    result = parse_schedule_result(html_content, academic_year=academic_year, semester=semester)
    if result.status != INVALID_PAGE:
        return list(result.courses)

    # The historical list API is also used by callers that pass an isolated
    # table fragment rather than a portal document.  Keep that narrow fragment
    # compatibility path, while full HTML documents still require the strict
    # AG104/schedule identity above and therefore fail closed.
    soup = BeautifulSoup(str(html_content or ""), "html.parser")
    if not soup.find("html") and not soup.find("body") and not soup.find("form"):
        return _parse_schedule_courses(html_content, academic_year=academic_year, semester=semester)
    return []


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
