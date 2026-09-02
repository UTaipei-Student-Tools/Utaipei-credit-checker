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
    text = unicodedata.normalize("NFKC", name or "").strip()
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("－", "-").replace("—", "-").replace("臺", "台")
    for roman, zh in sorted(_ROMAN_MAP.items(), key=lambda item: -len(item[0])):
        text = re.sub(rf"\({re.escape(roman)}\)", f"({zh})", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", "", text)
    return text


def course_key(name: str) -> str:
    return normalize_course_name(name).casefold()
