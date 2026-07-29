"""
Transcript PDF Parser using Coordinates-based Layout Reconstruct
"""

import os
import re

import fitz

from handbook_rules import normalize_course_name

MAX_PDF_BYTES = 20 * 1024 * 1024


def _open_transcript(source):
    """Open a path, uploaded file, or bytes object after basic PDF validation."""
    if isinstance(source, (str, os.PathLike)):
        path = os.fspath(source)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"找不到成績單 PDF：{path}")
        if os.path.getsize(path) > MAX_PDF_BYTES:
            raise ValueError("PDF 超過 20 MB，請先壓縮後再試。")
        with open(path, "rb") as handle:
            signature = handle.read(5)
        if signature != b"%PDF-":
            raise ValueError("檔案內容不是有效的 PDF。")
        return fitz.open(path)

    if hasattr(source, "getvalue"):
        data = source.getvalue()
    elif hasattr(source, "read"):
        data = source.read()
    else:
        data = source
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("成績單來源必須是 PDF 路徑或二進位內容。")
    if len(data) > MAX_PDF_BYTES:
        raise ValueError("PDF 超過 20 MB，請先壓縮後再試。")
    if not bytes(data).startswith(b"%PDF-"):
        raise ValueError("檔案內容不是有效的 PDF。")
    return fitz.open(stream=bytes(data), filetype="pdf")


def parse_transcript_pdf(pdf_path):
    doc = _open_transcript(pdf_path)
    if len(doc) == 0:
        raise ValueError("PDF file is empty")

    all_pages = [page for page in doc]
    full_text = "\n".join(page.get_text() for page in all_pages)

    # 1. Extract Student Information from the first page
    student_info = {"name": "", "student_id": "", "department": "", "admission_year": "", "print_date": ""}

    text_blocks = all_pages[0].get_text("blocks")
    for block in text_blocks:
        text = block[4].strip()
        if "姓名:" in text or "姓名：" in text:
            m = re.search(r"姓名：([^\s\n]+)", text)
            if m:
                student_info["name"] = m.group(1)
        if "學號:" in text or "學號：" in text:
            m = re.search(r"學號：([^\s\n]+)", text)
            if m:
                student_info["student_id"] = m.group(1)
        if "地球環境暨生物資源學系" in text:
            student_info["department"] = "地球環境暨生物資源學系"
        if "入學年月:" in text or "入學年月：" in text:
            m = re.search(r"入學年月：([^\s\n]+)", text)
            if m:
                student_info["admission_year"] = m.group(1)
        if "列印日期" in text:
            m = re.search(r"列印日期\(Date of Issue\)：([^\s\n]+)", text)
            if m:
                student_info["print_date"] = m.group(1)

    # Never substitute another student's data when the PDF layout changes.
    for key in ("name", "student_id", "department", "admission_year", "print_date"):
        if not student_info[key]:
            student_info[key] = "未辨識"

    def group_words_by_row(words, y_tol=4):
        rows = []
        for w in sorted(words, key=lambda w: (w[1], w[0])):
            x0, y0, x1, y1, text_w, block_no, line_no, word_no = w
            placed = False
            for row in rows:
                if abs(y0 - row["y"]) < y_tol:
                    row["words"].append(w)
                    placed = True
                    break
            if not placed:
                rows.append({"y": y0, "words": [w]})
        return rows

    def merge_continuation_rows(rows, col_x=295):
        merged_rows = []
        i = 0
        while i < len(rows):
            row = rows[i]

            # --- 1. 左側欄位合併邏輯 ---
            left_words = [w for w in row["words"] if w[0] < col_x]
            left_text = "".join([w[4] for w in sorted(left_words, key=lambda w: w[0])]).strip()
            left_has_type = any(w[4] in ("必", "選") for w in left_words)
            left_has_credit = any(re.match(r"^(?:\d+|--|P|抵|免|未)$", w[4]) for w in left_words if w[0] > 180)

            # 如果當前行左側沒有課程屬性標記(必/選)，且有文字內容，且不是學期標題等，嘗試與下一行合併
            if (
                left_text
                and not left_has_type
                and not left_has_credit
                and not any(
                    term in left_text
                    for term in [
                        "學年",
                        "累計學分",
                        "實得學分",
                        "附註",
                        "學分分數",
                        "科科科科",
                        "第一學期",
                        "第二學期",
                        "學分",
                        "分數",
                    ]
                )
                and i + 1 < len(rows)
            ):
                next_row = rows[i + 1]
                next_left_words = [w for w in next_row["words"] if w[0] < col_x]
                next_left_text = "".join([w[4] for w in sorted(next_left_words, key=lambda w: w[0])]).strip()

                # 條件1: 下一行以數字編號開頭（如"一)","二)"）
                # 條件2: 當前行以"("結尾（如課程名稱換行）
                # 條件3: 下一行有"必"或"選"標記（表示是課程屬性行）
                next_has_type = any(w[4] in ("必", "選") for w in next_left_words)
                if (
                    re.match(r"^[一二三四五六七八九十][\)\]]?$", next_left_text)
                    or left_text.endswith("(")
                    or (next_left_text and next_has_type)
                ):
                    # 合併：目前行加上下一行左側的文字
                    row["words"] = row["words"] + next_left_words
                    next_row["words"] = [w for w in next_row["words"] if w[0] >= col_x]

            # --- 2. 右側欄位合併邏輯 ---
            right_words = [w for w in row["words"] if w[0] >= col_x]
            right_text = "".join([w[4] for w in sorted(right_words, key=lambda w: w[0])]).strip()
            right_has_type = any(w[4] in ("必", "選") for w in right_words)
            right_has_credit = any(re.match(r"^(?:\d+|--|P|抵|免|未)$", w[4]) for w in right_words if w[0] > 470)

            # 如果當前行右側沒有課程屬性標記(必/選)，且有文字內容，且不是學期標題等，嘗試與下一行合併
            if (
                right_text
                and not right_has_type
                and not right_has_credit
                and not any(
                    term in right_text
                    for term in [
                        "學年",
                        "累計學分",
                        "實得學分",
                        "附註",
                        "學分分數",
                        "科科科科",
                        "第一學期",
                        "第二學期",
                        "學分",
                        "分數",
                    ]
                )
                and i + 1 < len(rows)
            ):
                next_row = rows[i + 1]
                next_right_words = [w for w in next_row["words"] if w[0] >= col_x]
                next_right_text = "".join([w[4] for w in sorted(next_right_words, key=lambda w: w[0])]).strip()

                # 條件與左欄同理，下一行有必選修屬性或名稱連續
                next_right_has_type = any(w[4] in ("必", "選") for w in next_right_words)
                if (
                    re.match(r"^[一二三四五六七八九十][\)\]]?$", next_right_text)
                    or right_text.endswith("(")
                    or (next_right_text and next_right_has_type)
                ):
                    # 合併：目前行加上下一行右側的文字
                    row["words"] = row["words"] + next_right_words
                    next_row["words"] = [w for w in next_row["words"] if w[0] < col_x]

            merged_rows.append(row)
            i += 1
        return merged_rows

    def extract_reported_totals_from_doc(doc):
        for page in doc:
            words = page.get_text("words")
            rows = group_words_by_row(words, y_tol=4)
            for idx, row in enumerate(rows):
                row_text = "".join([w[4] for w in sorted(row["words"], key=lambda w: w[0])])
                if "修習總學分數" in row_text:
                    if idx + 1 < len(rows):
                        next_row = sorted(rows[idx + 1]["words"], key=lambda w: w[0])
                        nums = []
                        for w in next_row:
                            try:
                                nums.append(float(w[4]))
                            except Exception:
                                pass
                        if nums:
                            return nums[0], nums[1] if len(nums) > 1 else None
        reported_total = None
        reported_ip = None
        m = re.search(r"修習學分(?:[:：\s]*)?(\d+(?:\.\d+)?)", full_text)
        if m:
            try:
                reported_total = float(m.group(1))
            except Exception:
                reported_total = None
        m2 = re.search(r"修習中(?:學分)?(?:[:：\s]*)?(\d+(?:\.\d+)?)", full_text)
        if m2:
            try:
                reported_ip = float(m2.group(1))
            except Exception:
                reported_ip = None
        return reported_total, reported_ip

    reported_total, _reported_ip = extract_reported_totals_from_doc(all_pages)

    def page_contains_course_rows(words):
        return any(w[4] in ("必", "選") for w in words)

    def parse_page_words(words, y_tol=3):
        rows = group_words_by_row(words, y_tol=y_tol)
        rows = merge_continuation_rows(rows)
        parsed = []
        year_tokens = []
        for word in words:
            match = re.search(r"(?<!\d)(1\d{2})(?!\d)", word[4])
            if match:
                year_tokens.append((word[0], match.group(1)))
        left_years = [value for x, value in year_tokens if x < 295]
        right_years = [value for x, value in year_tokens if x >= 295]
        left_year = left_years[0] if left_years else ""
        right_year = right_years[0] if right_years else left_year
        exclude_exact = {"科目名稱", "累計班排名/人數/百分比", "附", "註", "成績註記"}
        exclude_contains = [
            "修習學分",
            "實得學分",
            "操行成績",
            "累計學分",
            "學年",
            "實得總學分數",
            "實得學分及平均成績",
            "抵免課程",
            "抵免學分",
            "科科科科",
            "修習總學分數",
            "附註",
            "[抵]",
            "[免]",
            "[未]",
            "[P]",
            "[F]",
            "[停]",
        ]
        noise_patterns = [r"^\d+\.\d+\.\d+$", r"^\d+/\d+/\d+(?:\.\d+)?%?$", r"^\d+/\d+%$", r"^\d+\.?\d*\.\d+$"]

        def is_noise_text(text):
            cleaned = re.sub(r"\s+", "", text)
            if not cleaned:
                return True
            if re.fullmatch(r"[0-9./%]+(?:[選必])?", cleaned):
                return True
            if re.fullmatch(r"[選必][0-9./%]+", cleaned):
                return True
            if re.fullmatch(r"[0-9./%]+(?:[，,、][0-9./%]+)*", cleaned):
                return True
            if not re.search(r"[\u4e00-\u9fffA-Za-z]", cleaned) and re.search(r"[0-9]", cleaned):
                return True
            return False

        def is_valid_course_row(name, ctype, s1_cred, s1_score, s2_cred, s2_score, full_row_text):
            if not name:
                return False
            if is_noise_text(name):
                return False
            if len(name) < 2:
                return False
            if re.fullmatch(r"[0-9./%]+", name):
                return False
            if not any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in name):
                return False
            if ctype and ctype not in ("必", "選", "選修", "必修", "免", "抵"):
                if not any(tok in full_row_text for tok in ("必", "選", "修", "抵", "免")):
                    return False
            if not any([s1_cred, s1_score, s2_cred, s2_score]):
                return False
            if is_noise_text(full_row_text):
                return False
            return True

        for row in rows:
            row_words = sorted(row["words"], key=lambda w: w[0])
            full_row_text = "".join([w[4] for w in row_words]).strip()
            if not full_row_text:
                continue
            if full_row_text in exclude_exact:
                continue
            if any(re.match(pat, full_row_text) for pat in noise_patterns):
                continue
            if is_noise_text(full_row_text):
                continue
            left_part = [w for w in row_words if w[0] < 295]
            right_part = [w for w in row_words if w[0] >= 295]

            if left_part:
                name_words = [w for w in left_part if w[0] < 150]
                type_words = [w for w in left_part if 160 <= w[0] < 190]
                s1_cred_words = [w for w in left_part if 190 <= w[0] < 210]
                s1_score_words = [w for w in left_part if 210 <= w[0] < 240]
                s2_cred_words = [w for w in left_part if 240 <= w[0] < 270]
                s2_score_words = [w for w in left_part if 270 <= w[0] < 295]

                name = "".join([w[4] for w in name_words]).strip()
                ctype = "".join([w[4] for w in type_words]).strip()
                s1_cred = "".join([w[4] for w in s1_cred_words]).strip()
                s1_score = "".join([w[4] for w in s1_score_words]).strip()
                s2_cred = "".join([w[4] for w in s2_cred_words]).strip()
                s2_score = "".join([w[4] for w in s2_score_words]).strip()

                # 過濾掉註記行和全是數字/符號的行
                full_row_text = "".join([w[4] for w in row_words]).strip()
                is_page_number = re.match(r"^\d+\s*\d+/\d+\s*[\d.%]+$", full_row_text)

                if (
                    name
                    and not any(term in name for term in exclude_contains)
                    and not any(
                        k in name for k in ["姓名", "系所", "畢業年月", "列印日期", "學號", "[WEB參考用]", "(大學部)"]
                    )
                    and not is_page_number
                    and is_valid_course_row(name, ctype, s1_cred, s1_score, s2_cred, s2_score, full_row_text)
                ):
                    cd = build_course_dict(name, ctype, s1_cred, s1_score, s2_cred, s2_score, left_year)
                    if cd:
                        parsed.append(cd)

            if right_part:
                name_words = [w for w in right_part if w[0] < 440]
                type_words = [w for w in right_part if 440 <= w[0] < 470]
                s1_cred_words = [w for w in right_part if 470 <= w[0] < 490]
                s1_score_words = [w for w in right_part if 490 <= w[0] < 520]
                s2_cred_words = [w for w in right_part if 520 <= w[0] < 545]
                s2_score_words = [w for w in right_part if 545 <= w[0] < 580]

                name = "".join([w[4] for w in name_words]).strip()
                ctype = "".join([w[4] for w in type_words]).strip()
                s1_cred = "".join([w[4] for w in s1_cred_words]).strip()
                s1_score = "".join([w[4] for w in s1_score_words]).strip()
                s2_cred = "".join([w[4] for w in s2_cred_words]).strip()
                s2_score = "".join([w[4] for w in s2_score_words]).strip()

                # 過濾掉註記行和全是數字/符號的行
                full_row_text = "".join([w[4] for w in row_words]).strip()
                is_page_number = re.match(r"^\d+\s*\d+/\d+\s*[\d.%]+$", full_row_text)

                if (
                    name
                    and not any(term in name for term in exclude_contains)
                    and not any(
                        k in name for k in ["姓名", "系所", "畢業年月", "列印日期", "學號", "[WEB參考用]", "(大學部)"]
                    )
                    and not is_page_number
                    and is_valid_course_row(name, ctype, s1_cred, s1_score, s2_cred, s2_score, full_row_text)
                ):
                    cd = build_course_dict(name, ctype, s1_cred, s1_score, s2_cred, s2_score, right_year)
                    if cd:
                        parsed.append(cd)

        return parsed

    parsed_courses = []
    for page in all_pages:
        page_words = page.get_text("words")
        parsed_courses.extend(parse_page_words(page_words, y_tol=3))

    def totals_from_courses(course_list):
        total = sum((c.get("total_credit") or 0.0) for c in course_list)
        ip = sum((c.get("total_credit") or 0.0) for c in course_list if c.get("is_in_progress"))
        return total, ip

    parsed_total, _ = totals_from_courses(parsed_courses)

    if reported_total and parsed_total + 0.01 < reported_total:
        tried = False
        for ytol in (6, 9, 12, 18):
            alt = []
            for page in all_pages:
                alt.extend(parse_page_words(page.get_text("words"), y_tol=ytol))
            alt_total, _ = totals_from_courses(alt)
            if alt_total >= reported_total - 0.01:
                parsed_courses = alt
                parsed_total = alt_total
                tried = True
                break
        if not tried:
            best = parsed_courses
            best_total = parsed_total
            for ytol in (6, 9, 12, 18):
                alt = []
                for page in all_pages:
                    alt.extend(parse_page_words(page.get_text("words"), y_tol=ytol))
                alt_total, _ = totals_from_courses(alt)
                if alt_total > best_total:
                    best, best_total = alt, alt_total
            parsed_courses = best

    parsed_courses = split_two_semester_courses(parsed_courses)
    doc.close()
    if not parsed_courses:
        raise ValueError("未能從 PDF 辨識任何課程；請確認檔案為北市大歷年成績單。")
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
            return (
                False,
                False,
            )  # 0-credit physical training or guidance can be considered completed if score is numeric
        if not score or score == "--":
            # Blank/undefined score with credit likely indicates ongoing course enrollment
            return False, True if credit > 0 else (False, False)
        if score == "未":
            return False, True  # In Progress
        if score == "P" or score == "抵" or score == "免":
            return True, False  # Completed
        if score == "F" or score == "停" or score == "W":
            return False, False  # Failed/Withdraw
        try:
            val = float(score)
            return val >= 60, False  # Completed if >= 60
        except ValueError:
            return False, False

    is_c1_completed, is_c1_ip = eval_status(
        s1_score, c1 if c1 > 0 else 1.0
    )  # Treat 0-credit physical education/guidance as 1.0 for check
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
    is_zero_credit = total_credit == 0.0
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
        "is_zero_credit": is_zero_credit,
    }


def split_two_semester_courses(courses):
    split_targets = ["普通生物學", "地球科學"]
    new_courses = []

    def get_sem_status(score, cred_str):
        if not cred_str or cred_str == "--" or cred_str == "":
            return False, False, False
        try:
            c_val = float(cred_str)
        except ValueError:
            c_val = 0.0
        if c_val <= 0.0:
            return False, False, False

        if not score or score == "--":
            return True, False, True
        if score == "未":
            return True, False, True
        if score in ("P", "抵", "免"):
            return True, True, False
        if score in ("F", "停", "W"):
            return True, False, False
        try:
            val = float(score)
            return True, val >= 60.0, False
        except ValueError:
            return True, False, False

    for c in courses:
        if c.get("name") in split_targets:
            s1_active, s1_done, s1_ip = get_sem_status(c.get("sem1_score"), c.get("sem1_credit"))
            s2_active, s2_done, s2_ip = get_sem_status(c.get("sem2_score"), c.get("sem2_credit"))

            if s1_active or s2_active:
                if s1_active:
                    try:
                        cred = float(c["sem1_credit"])
                    except ValueError:
                        cred = 3.0
                    new_courses.append(
                        {
                            "name": f"{c['name']}(上)",
                            "raw_name": f"{c['raw_name']}(上)",
                            "type": c.get("type", "必"),
                            "academic_year": c.get("academic_year", ""),
                            "sem1_credit": c.get("sem1_credit", ""),
                            "sem1_score": c.get("sem1_score", ""),
                            "sem2_credit": "",
                            "sem2_score": "",
                            "total_credit": cred,
                            "completed_credit": cred if s1_done else 0.0,
                            "is_completed": s1_done,
                            "is_in_progress": s1_ip,
                            "is_zero_credit": False,
                        }
                    )
                if s2_active:
                    try:
                        cred = float(c["sem2_credit"])
                    except ValueError:
                        cred = 3.0
                    new_courses.append(
                        {
                            "name": f"{c['name']}(下)",
                            "raw_name": f"{c['raw_name']}(下)",
                            "type": c.get("type", "必"),
                            "academic_year": c.get("academic_year", ""),
                            "sem1_credit": "",
                            "sem1_score": "",
                            "sem2_credit": c.get("sem2_credit", ""),
                            "sem2_score": c.get("sem2_score", ""),
                            "total_credit": cred,
                            "completed_credit": cred if s2_done else 0.0,
                            "is_completed": s2_done,
                            "is_in_progress": s2_ip,
                            "is_zero_credit": False,
                        }
                    )
            else:
                half_credit = c["total_credit"] / 2.0
                new_courses.append(
                    {
                        "name": f"{c['name']}(上)",
                        "raw_name": f"{c['raw_name']}(上)",
                        "type": c.get("type", "必"),
                        "academic_year": c.get("academic_year", ""),
                        "sem1_credit": str(half_credit),
                        "sem1_score": "P" if c.get("is_completed") else ("未" if c.get("is_in_progress") else ""),
                        "sem2_credit": "",
                        "sem2_score": "",
                        "total_credit": half_credit,
                        "completed_credit": half_credit if c.get("is_completed") else 0.0,
                        "is_completed": c.get("is_completed", False),
                        "is_in_progress": c.get("is_in_progress", False),
                        "is_zero_credit": False,
                    }
                )
                new_courses.append(
                    {
                        "name": f"{c['name']}(下)",
                        "raw_name": f"{c['raw_name']}(下)",
                        "type": c.get("type", "必"),
                        "academic_year": c.get("academic_year", ""),
                        "sem1_credit": "",
                        "sem1_score": "",
                        "sem2_credit": str(half_credit),
                        "sem2_score": "P" if c.get("is_completed") else ("未" if c.get("is_in_progress") else ""),
                        "total_credit": half_credit,
                        "completed_credit": half_credit if c.get("is_completed") else 0.0,
                        "is_completed": c.get("is_completed", False),
                        "is_in_progress": c.get("is_in_progress", False),
                        "is_zero_credit": False,
                    }
                )
        else:
            new_courses.append(c)
    return new_courses


def load_courses_from_csv(csv_path):
    """Load courses from an exported CSV file used as fallback when PDF parsing misses entries.

    Returns: student_info (dict), courses (list)
    """
    import csv

    student_info = {
        "name": "",
        "student_id": "",
        "department": "",
        "admission_year": "",
        "print_date": "",
    }
    courses = []
    if not os.path.exists(csv_path):
        return student_info, courses

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = r.get("科目名稱") or r.get("name") or ""
            raw_name = name
            ctype = r.get("科目屬性") or r.get("type") or ""
            ay = r.get("修課學年") or r.get("academic_year") or ""
            cred_str = r.get("學分數") or r.get("credit") or "0"
            done = str(r.get("是否完成") or r.get("is_completed") or "").strip().lower() in ("true", "1", "yes")
            ip = str(r.get("修讀中") or r.get("is_in_progress") or "").strip().lower() in ("true", "1", "yes")
            try:
                credit = float(cred_str)
            except Exception:
                import re

                m = re.search(r"\d+(?:\.\d+)?", cred_str or "")
                credit = float(m.group(0)) if m else 0.0

            completed_credit = credit if done else 0.0

            course = {
                "name": normalize_course_name(name),
                "raw_name": raw_name,
                "type": ctype if ctype else "選",
                "academic_year": ay,
                "sem1_credit": "",
                "sem1_score": "",
                "sem2_credit": str(credit) if credit else "",
                "sem2_score": "P" if done else ("未" if ip else ""),
                "total_credit": credit,
                "completed_credit": completed_credit,
                "is_completed": bool(done),
                "is_in_progress": bool(ip) and not done,
                "is_zero_credit": credit == 0.0,
            }
            courses.append(course)

    courses = split_two_semester_courses(courses)
    return student_info, courses
