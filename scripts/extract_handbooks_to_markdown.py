"""
Script to extract course tables from official 111~115 Science College handbooks
and General Education Center curriculum into clean GFM Markdown catalogs.
"""

import os
import re
import fitz

HANDBOOK_DIR = "學生手冊"
OUTPUT_DIR = os.path.join("data", "handbooks")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HANDBOOK_FILES = {
    "111": "3-理學院.pdf",
    "112": "3-理學院 (112).pdf",
    "113": "3-理學院 (113).pdf",
    "114": "3-理學院 (114).pdf",
    "115": "3-理學院 (115).pdf",
}

# Department definitions supporting Math variations and aliases
DEPARTMENTS = [
    ("應用物理暨化學系", ["電子物理組", "應用化學組"]),
    ("地球環境暨生物資源學系", ["地球環境組", "生命科學組"]),
    ("資訊科學系", ["主修", "輔系", "雙主修"]),
    ("數據科學與數學系", ["數學與科學計算組", "數據科學組", "數學教育組", "數學與科學計算領域", "數據科學領域", "數學教育領域"]),
    ("數據科學與數學教育學系", ["數學與科學計算組", "數據科學組", "數學教育組"]),
    ("數學系", ["數學與科學計算組", "數據科學組", "數學教育組", "數學與科學計算領域", "數據科學領域", "數學教育領域"]),
]

# Authoritative 1-based page bounds for undergraduate programs from research matrices:
# (dept_name, track_name, start_page_1based, end_page_1based, out_filename)
UNDERGRADUATE_SECTIONS = {
    "111": [
        ("應用物理暨化學系", "電子物理組", 3, 14, "111學年度_理學院_應用物理暨化學系_電子物理組_課程手冊.md"),
        ("應用物理暨化學系", "應用化學組", 15, 24, "111學年度_理學院_應用物理暨化學系_應用化學組_課程手冊.md"),
        ("地球環境暨生物資源學系", "", 25, 39, "111學年度_理學院_地球環境暨生物資源學系_課程手冊.md"),
        ("數學系", "", 65, 82, "111學年度_理學院_數學系_課程手冊.md"),
        ("資訊科學系", "", 113, 122, "111學年度_理學院_資訊科學系_課程手冊.md"),
    ],
    "112": [
        ("應用物理暨化學系", "電子物理組", 3, 14, "112學年度_理學院_應用物理暨化學系_電子物理組_課程手冊.md"),
        ("應用物理暨化學系", "應用化學組", 15, 24, "112學年度_理學院_應用物理暨化學系_應用化學組_課程手冊.md"),
        ("地球環境暨生物資源學系", "", 25, 39, "112學年度_理學院_地球環境暨生物資源學系_課程手冊.md"),
        ("數學系", "", 60, 77, "112學年度_理學院_數學系_課程手冊.md"),
        ("資訊科學系", "", 108, 117, "112學年度_理學院_資訊科學系_課程手冊.md"),
    ],
    "113": [
        ("應用物理暨化學系", "電子物理組", 3, 18, "113學年度_理學院_應用物理暨化學系_電子物理組_課程手冊.md"),
        ("應用物理暨化學系", "應用化學組", 19, 29, "113學年度_理學院_應用物理暨化學系_應用化學組_課程手冊.md"),
        ("地球環境暨生物資源學系", "", 30, 45, "113學年度_理學院_地球環境暨生物資源學系_課程手冊.md"),
        ("數學系", "", 61, 79, "113學年度_理學院_數學系_課程手冊.md"),
        ("資訊科學系", "", 103, 112, "113學年度_理學院_資訊科學系_課程手冊.md"),
    ],
    "114": [
        ("應用物理暨化學系", "電子物理組", 3, 18, "114學年度_理學院_應用物理暨化學系_電子物理組_課程手冊.md"),
        ("應用物理暨化學系", "應用化學組", 19, 30, "114學年度_理學院_應用物理暨化學系_應用化學組_課程手冊.md"),
        ("地球環境暨生物資源學系", "", 31, 47, "114學年度_理學院_地球環境暨生物資源學系_課程手冊.md"),
        ("數學系", "", 65, 82, "114學年度_理學院_數學系_課程手冊.md"),
        ("資訊科學系", "", 108, 117, "114學年度_理學院_資訊科學系_課程手冊.md"),
    ],
    "115": [
        ("應用物理暨化學系", "電子物理組", 3, 19, "115學年度_理學院_應用物理暨化學系_電子物理組_課程手冊.md"),
        ("應用物理暨化學系", "應用化學組", 20, 38, "115學年度_理學院_應用物理暨化學系_應用化學組_課程手冊.md"),
        ("地球環境暨生物資源學系", "", 39, 55, "115學年度_理學院_地球環境暨生物資源學系_課程手冊.md"),
        ("數據科學與數學系", "", 76, 93, "115學年度_理學院_數據科學與數學系_課程手冊.md"),
        ("資訊科學系", "", 119, 127, "115學年度_理學院_資訊科學系_課程手冊.md"),
    ],
}


def cleanup_contaminated_files(handbook_dir=OUTPUT_DIR):
    """Remove legacy files contaminated with incorrect track names."""
    if not os.path.exists(handbook_dir):
        return
    for fname in os.listdir(handbook_dir):
        if "_應用化學組_" in fname and "應用物理暨化學系" not in fname:
            fpath = os.path.join(handbook_dir, fname)
            try:
                os.remove(fpath)
                print(f"Removed contaminated file: {fname}")
            except OSError as e:
                print(f"Error removing {fname}: {e}")


def extract_section_tables(doc, start_pno_1based, end_pno_1based):
    """Extract table rows cleanly bounded to specific page ranges."""
    all_courses = []
    # Convert 1-based inclusive range to 0-based
    for pno in range(start_pno_1based - 1, end_pno_1based):
        if pno >= len(doc):
            continue
        page = doc[pno]
        tabs = page.find_tables()
        for t in tabs.tables:
            extracted = t.extract()
            for row in extracted:
                cells = [str(c or "").strip().replace("\n", " ") for c in row]
                if not any(cells):
                    continue
                if any("Course Name" in c for c in cells):
                    continue
                chinese_text = " ".join(cells)
                if any(ch in chinese_text for ch in ["必", "選", "學分", "實習", "實驗"]) or len(cells) >= 5:
                    all_courses.append(cells)
    return all_courses


def extract_tables_from_pdf(pdf_path, year_label):
    if not os.path.exists(pdf_path):
        print(f"Warning: {pdf_path} not found.")
        return

    doc = fitz.open(pdf_path)
    print(f"Processing {year_label} ({pdf_path}), pages: {len(doc)}")

    sections = UNDERGRADUATE_SECTIONS.get(year_label, [])
    if not sections:
        # Dynamic fallback with explicit track reset per page
        current_dept = "理學院通用"
        pages_by_dept = {}
        for pno in range(len(doc)):
            current_track = ""  # RESET on every page transition
            text = doc[pno].get_text()
            first_lines = [l.strip() for l in text.split("\n")[:5] if l.strip()]
            header = " ".join(first_lines)

            for dept_name, tracks in DEPARTMENTS:
                if dept_name in header:
                    current_dept = dept_name
                    for trk in tracks:
                        if trk in header:
                            current_track = trk
                            break
                    break

            key = f"{current_dept}_{current_track}" if current_track else current_dept
            if key not in pages_by_dept:
                pages_by_dept[key] = []
            pages_by_dept[key].append(pno)

        for section_key, pnos in pages_by_dept.items():
            out_filename = f"{year_label}學年度_理學院_{section_key}_課程手冊.md"
            out_path = os.path.join(OUTPUT_DIR, out_filename)
            all_courses = []
            for pno in pnos:
                tabs = doc[pno].find_tables()
                for t in tabs.tables:
                    for row in t.extract():
                        cells = [str(c or "").strip().replace("\n", " ") for c in row]
                        if not any(cells) or any("Course Name" in c for c in cells):
                            continue
                        if any(ch in " ".join(cells) for ch in ["必", "選", "學分", "實習", "實驗"]) or len(cells) >= 5:
                            all_courses.append(cells)
            if all_courses:
                _write_markdown(out_path, year_label, section_key.replace("_", " - "), os.path.basename(pdf_path), all_courses)
        return

    # Use authoritative undergraduate sections
    for dept_name, track_name, start_p, end_p, out_filename in sections:
        out_path = os.path.join(OUTPUT_DIR, out_filename)
        all_courses = extract_section_tables(doc, start_p, end_p)
        section_display = f"{dept_name} - {track_name}" if track_name else dept_name
        if all_courses:
            _write_markdown(out_path, year_label, section_display, os.path.basename(pdf_path), all_courses)
            print(f"  -> Generated {out_filename} ({len(all_courses)} rows, pp. {start_p}-{end_p})")

            # For 115 Math, also provide backward-compatible alias
            if year_label == "115" and dept_name == "數據科學與數學系":
                alias_filename = "115學年度_理學院_數學系_課程手冊.md"
                alias_path = os.path.join(OUTPUT_DIR, alias_filename)
                _write_markdown(alias_path, year_label, "數學系 (數據科學與數學系)", os.path.basename(pdf_path), all_courses)
                print(f"  -> Generated alias {alias_filename} ({len(all_courses)} rows)")


def _write_markdown(out_path, year_label, section_title, pdf_name, courses):
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# {year_label}學年度 臺北市立大學理學院課程架構規範表\n\n")
        f.write(f"**系所／領域**：{section_title}  \n")
        f.write(f"**來源檔案**：`{pdf_name}`  \n")
        f.write(f"**收錄課表筆數**：{len(courses)} 筆  \n\n")
        f.write("| 序號 | 擷取欄位 1 | 擷取欄位 2 | 課程中文名稱 | 課程英文名稱 | 學分/學期 | 備註 |\n")
        f.write("|:---:|:---|:---|:---|:---|:---:|:---|\n")
        for idx, c in enumerate(courses, 1):
            row_cells = [c[i] if i < len(c) else "-" for i in range(6)]
            f.write(f"| {idx} | {' | '.join(row_cells)} |\n")


def extract_ge_handbook():
    ge_path = os.path.join(HANDBOOK_DIR, "通識教育中心課程手冊.pdf")
    if not os.path.exists(ge_path):
        print(f"Warning: {ge_path} not found.")
        return
    doc = fitz.open(ge_path)
    out_path = os.path.join(OUTPUT_DIR, "通識教育中心_全校通識課程架構表.md")
    print(f"Processing GE handbook ({ge_path}), pages: {len(doc)}")
    all_rows = []
    for pno in range(len(doc)):
        tabs = doc[pno].find_tables()
        for t in tabs.tables:
            for row in t.extract():
                cells = [str(c or "").strip().replace("\n", " ") for c in row]
                if any(cells) and len(cells) >= 3:
                    all_rows.append(cells)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# 臺北市立大學 通識教育中心課程架構與領域核心清單\n\n")
        f.write(f"**來源手冊**：`通識教育中心課程手冊.pdf`  \n")
        f.write(f"**總課表記錄**：{len(all_rows)} 筆  \n\n")
        f.write("| 序號 | 領域／類別 | 課程名稱 | 學分數 | 開課學期 | 備註說明 |\n")
        f.write("|:---:|:---|:---|:---:|:---:|:---|\n")
        for idx, r in enumerate(all_rows, 1):
            row_cells = [r[i] if i < len(r) else "-" for i in range(5)]
            f.write(f"| {idx} | {' | '.join(row_cells)} |\n")
    print(f"  -> Generated 通識教育中心_全校通識課程架構表.md ({len(all_rows)} rows)")


if __name__ == "__main__":
    cleanup_contaminated_files()
    for yr, fname in HANDBOOK_FILES.items():
        pdf_file = os.path.join(HANDBOOK_DIR, fname)
        extract_tables_from_pdf(pdf_file, yr)
    extract_ge_handbook()
    print("All handbook markdown catalogs successfully generated in data/handbooks/!")
