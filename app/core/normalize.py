from __future__ import annotations

import re
import unicodedata


_ROMAN_MAP = {
    "Ⅰ": "一",
    "Ⅱ": "二",
    "Ⅲ": "三",
    "Ⅳ": "四",
    "I": "一",
    "II": "二",
    "III": "三",
    "IV": "四",
}


def normalize_course_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", name or "")
    text = text.strip()
    text = text.replace("（", "(").replace("）", ")")
    for roman, zh in sorted(_ROMAN_MAP.items(), key=lambda item: -len(item[0])):
        text = re.sub(rf"\({roman}\)", f"({zh})", text)
    text = re.sub(r"\s+", "", text)
    text = text.replace("程式設計 ", "程式設計")
    return text


def course_key(name: str) -> str:
    return normalize_course_name(name).lower()

