# -*- coding: utf-8 -*-
"""
Graduation Handbook Rules — 動態載入版
Taipei City University (北市大) Science College (理學院)

【更新規則的方法】
============================
只需要修改同目錄下的 rules_config.json 即可！
不需要改動任何 Python 程式碼。

JSON 結構說明請參考 rules_config.json 內的 _comment 欄位。
修改完成後：
  - 本機：重啟 Streamlit (Ctrl+C 後再 streamlit run app.py)
  - Hugging Face：將更新後的 rules_config.json 推送至 Space 即自動生效

【安全性設計】
============================
1. JSON 讀取失敗時會自動 fallback 到程式碼內建的預設規則，確保系統不會崩潰。
2. 所有讀取操作均為唯讀，不會對任何外部系統寫入。
3. 版本號碼 (_meta.version) 方便追蹤每次規則更新的學年度。
"""

import re
import json
import os

# ─────────────────────────────────────────────
# 0. 讀取 JSON 設定檔（動態規則來源）
# ─────────────────────────────────────────────

def _load_config():
    """從 rules_config.json 讀取規則。讀取失敗時回傳 None，讓下方的 hardcoded 備援生效。"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules_config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        import warnings
        warnings.warn(f"[rules_config.json 解析失敗] {e}，已自動切換至程式碼內建的備援規則。")
        return None

_CFG = _load_config()

def get_rules_meta():
    """回傳目前載入的規則版本資訊，供 UI 顯示用。"""
    if _CFG and "_meta" in _CFG:
        return _CFG["_meta"]
    return {"version": "114(hardcoded)", "last_updated": "N/A", "description": "使用程式碼內建備援規則"}


# ─────────────────────────────────────────────
# 1. 課程名稱標準化（邏輯不會因 JSON 更新而改變）
# ─────────────────────────────────────────────

def normalize_course_name(name):
    if not name:
        return ""
    name = name.strip()
    # 全形括號 → 半形
    name = name.replace("（", "(").replace("）", ")")
    name = name.replace("：", ":")
    # 移除多餘空白／行斷造成的空格
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"\s*([()\[\]：:])\s*", r"\1", name)
    # Remove special marker annotations like [◇] [※] [◎] [§] [▲] [╳]
    name = re.sub(r"\[(?:◇|※|◎|§|▲|╳)\]", "", name)
    # Collapse spaces between Chinese characters caused by PDF line breaks
    name = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", name)
    # 注意：保留中括號內的通識標記（例如 [通選藝術與美感]），不要自動移除，
    # 因為成績單中常以中括號標註通識分類，保留可以讓使用者看到完整資訊。
    # 不再自動將羅馬數字 (I)/(II)/(III) 轉換或刪除，保留原樣以避免資訊遺失。
    # 統一語文課程的羅馬數字與中文寫法，對齊畢業門檻規則
    name = name.replace("英文(I)", "英文(一)").replace("英文(II)", "英文(二)").replace("英文(III)", "英文(三)")
    name = name.replace("國文(I)", "國文(一)").replace("國文(II)", "國文(二)")
    # 處理英文課程的子標題，例如 "英文(三):職場商旅" 統一歸類為 "英文(三)"
    name = re.sub(r"^(英文\([一二三]\))[:：\-].*", r"\1", name)
    # 移除括號內的單個字符或簡短標記（班級代號），但保留表示卷期的一二三四五，且排除 I, V, X 等單個羅馬數字
    name = re.sub(r"\((?![IvXiVx])[A-Za-z甲乙丙丁]\)$", "", name)
    if re.fullmatch(r"[\d./%]+", name):
        return ""
    if not re.search(r"[\u4e00-\u9fffA-Za-z]", name) and re.search(r"[0-9]", name):
        return ""
    return name.strip()


# ─────────────────────────────────────────────
# 2. 全校共同課程規則（UNIVERSITY_COMMON）
# ─────────────────────────────────────────────

def _build_university_common():
    if _CFG and "university_common" in _CFG:
        uc = _CFG["university_common"]
        return {
            "compulsory": {k: v for k, v in uc["compulsory"]["courses"].items()},
            "category_domains": {k: v for k, v in uc["ge_categories"]["categories"].items()},
            "per_category_req": uc.get("ge_categories", {}).get("per_category_req", 4)
        }
    # ── Hardcoded Fallback ──
    return {
        "compulsory": {
            "國文(一):閱讀與思辨": 2,
            "國文(二):語文表達": 2,
            "英文(一)": 2,
            "英文(二)": 2,
            "英文(三)": 2,
        },
        "category_domains": {
            "藝術與美感": ["藝術", "生活哲學與藝術", "美感", "音樂", "繪畫", "美學"],
            "人文與文化思考": ["人文", "日本旅行與日本文化", "建築史", "文化", "歷史", "文學", "哲學"],
            "公民素養與社會探索": ["公民", "臺北城市散步旅行", "政府運作與國會監督", "法學", "社會", "民主", "憲法"],
            "自然、生命與科技": ["自然", "生命科學與人生", "科技", "環境", "天文", "資訊應用", "科學"],
        },
        "per_category_req": 4
    }

UNIVERSITY_COMMON = _build_university_common()


# ─────────────────────────────────────────────
# 3. 地生系主修規則（EARTH_LIFE_MAJOR）
# ─────────────────────────────────────────────

def _build_earth_life_major():
    if _CFG and "earth_life_major" in _CFG:
        elm = _CFG["earth_life_major"]
        domains_raw = elm["domains"]
        domain_data = {}
        domain_electives = {}
        for dname, d in domains_raw.items():
            if isinstance(d, dict) and "compulsory" in d:
                domain_data[dname] = {k: v for k, v in d.get("compulsory", {}).items()}
                domain_electives[dname] = d.get("electives", [])
        domain_electives["common_electives"] = elm.get("common_electives", [])
        return {
            "common_compulsory": {k: v for k, v in elm["common_compulsory"]["courses"].items()},
            "domains": domain_data,
            "domain_electives": domain_electives
        }
    # ── Hardcoded Fallback ──
    return {
        "common_compulsory": {
            "普通生物學(上)": 3,
            "普通生物學(下)": 3,
            "普通生物學實驗": 1,
            "地球科學(上)": 3,
            "地球科學(下)": 3,
            "地球科學實驗": 1,
            "資料處理與分析": 3,
            "書報討論": 2,
            "基礎生態學": 3,
            "環境影響評估": 2,
        },
        "domains": {
            "地球環境": {
                "地質學": 3, "氣象學": 3, "地球環境變遷": 2,
                "衛星遙測學": 2, "海洋學": 2, "地球歷史": 2
            },
            "生命科學": {
                "生物化學": 3, "脊椎動物學": 3, "遺傳學(含實驗)": 3,
                "分子生物學(一)": 3, "分子生物學(二)": 2
            }
        },
        "domain_electives": {
            "地球環境": [
                "地形學", "地球物理通論", "環境地質學", "火山學", "水文地質學",
                "礦物與岩石學", "氣候學", "海洋地質概論", "野外地質學", "地震學",
                "天文學", "沈積學", "構造地質學", "工程地質", "地球化學導論",
                "地層學", "大氣動力學", "大氣化學", "地球科學文獻導讀",
                "台灣區域地質與調查", "第四紀環境變遷", "大臺北都會區之應用地質學"
            ],
            "生命科學": [
                "自然保育概論", "動物系統分類學", "生物化學實驗", "植物形態解剖學",
                "植物生理學", "無脊椎動物學", "海洋生物學", "昆蟲學",
                "植物系統分類學", "基因體學", "動物生理學", "動物行為學",
                "細胞生物學", "生物資訊學導論", "病毒學", "生物地理",
                "微生物資源與應用", "生物技術學", "環境生態與生物資源調查",
                "生態學特論", "演化生物學", "免疫學", "生技產業概論"
            ],
            "common_electives": [
                "Python程式設計與應用", "普通物理學(含實驗)", "普通物理(含實驗)",
                "環境科學", "統計學", "巨量資料探勘", "環境倫理學", "微積分", "微積分(I)",
                "有機化學", "微生物學", "環境規劃與管理", "科學文獻導讀", "生命科學發展史",
                "普通化學(含實驗)", "地理資訊系統", "生物多樣性",
                "生物統計學", "環境問題調查", "未來地球", "環境教育", "自然體驗",
                "環境化學", "數值分析", "保育生物學", "全球環境變遷", "未來生態學",
                "數值地形分析", "專題研究", "專業實習"
            ]
        }
    }

EARTH_LIFE_MAJOR = _build_earth_life_major()


# ─────────────────────────────────────────────
# 4. 物化系雙主修/輔系規則（APC_RULES）
# ─────────────────────────────────────────────

def _build_apc_rules():
    if _CFG and "apc_rules" in _CFG:
        apc = _CFG["apc_rules"]
        divisions = {}
        for div_name, div_data in apc["divisions"].items():
            divisions[div_name] = {
                "compulsory": {k: v for k, v in div_data["compulsory"].items()},
                "double_major_other_req": div_data["double_major_other_req"],
                "minor_other_req": div_data["minor_other_req"]
            }
        return {
            "basic_core": {k: v for k, v in apc["basic_core"]["courses"].items()},
            "divisions": divisions
        }
    # ── Hardcoded Fallback ──
    return {
        "basic_core": {
            "普通物理學(一)": 3, "普通物理實驗(一)": 1,
            "普通化學(一)": 3, "普通化學實驗(一)": 1,
            "普通物理學(二)": 3, "普通物理實驗(二)": 1,
            "普通化學(二)": 3, "普通化學實驗(二)": 1
        },
        "divisions": {
            "化學組": {
                "compulsory": {
                    "分析化學(一)": 3, "有機化學(一)": 3, "有機化學實驗(一)": 1,
                    "化學數學(一)": 3, "物理化學(一)": 3, "物理化學實驗(一)": 1,
                    "有機化學(二)": 3, "有機化學實驗(二)": 1, "物理化學(二)": 3,
                    "物理化學實驗(二)": 1, "材料科學": 3, "材料科學實驗(一)": 1,
                    "分析化學實驗": 1, "無機化學(一)": 3, "儀器分析(一)": 3,
                    "物理化學(三)": 3, "生物化學(一)": 3, "材料科學實驗(二)": 1,
                    "無機化學(二)": 3, "儀器分析實驗": 1, "生物化學實驗": 1,
                    "應用科學專題(一)": 1, "應用科學專題(二)": 1
                },
                "double_major_other_req": 24,
                "minor_other_req": 4
            },
            "物理組": {
                "compulsory": {
                    "物理數學(一)": 3, "電磁學(一)": 3, "電磁學實驗": 1,
                    "力學(一)": 3, "物理數學(二)": 3, "電磁學(二)": 3,
                    "光學": 3, "光學實驗": 1, "半導體物理": 3,
                    "光電子學": 3, "近代物理": 3, "近代物理實驗": 1,
                    "電子學(一)": 3, "電子學實驗(一)": 1, "電子學(二)": 3,
                    "電子學實驗(二)": 1, "固態物理(一)": 3, "固態物理(二)": 3,
                    "應用科學專題(一)": 1, "應用科學專題(二)": 1
                },
                "double_major_other_req": 24,
                "minor_other_req": 4
            }
        }
    }

APC_RULES = _build_apc_rules()


# ─────────────────────────────────────────────
# 5. 資科系雙主修/輔系規則（CS_RULES）
# ─────────────────────────────────────────────

def _build_cs_rules():
    fallback_electives = [
        "微積分", "微積分(I)", "微積分(II)", "微積分I", "微積分II", "微積分(一)", "微積分(二)", "微積分一", "微積分二",
        "線性代數", "離散數學", "工程數學", "機率與統計", "機率學", "機率",
        "影像處理", "影像處理概論", "電腦圖學",
        "Java程式設計", "Java程式語言", "Python程式設計與應用", "Python程式設計",
        "作業系統", "計算機組織", "計算機架構", "編譯器", "資料庫", "資料庫系統", "資料庫管理",
        "網頁程式設計", "網頁設計", "網路程式設計", "計算機網路", "軟體工程",
        "人工智慧", "機器學習", "深度學習", "資料科學"
    ]
    if _CFG and "cs_rules" in _CFG:
        cs = _CFG["cs_rules"]
        result = {}
        for prog_key in ["double_major", "minor"]:
            if prog_key in cs:
                result[prog_key] = {
                    "compulsory": {k: v for k, v in cs[prog_key]["compulsory"].items()},
                    "compulsory_req": cs[prog_key]["compulsory_req"],
                    "elective_req": cs[prog_key]["elective_req"],
                    "total_req": cs[prog_key]["total_req"]
                }
        result["electives"] = cs.get("electives", fallback_electives)
        return result
    # ── Hardcoded Fallback ──
    return {
        "double_major": {
            "compulsory": {"計算機概論": 3, "C程式設計": 3, "Java程式設計": 3, "資料結構": 3, "演算法": 3},
            "compulsory_req": 15, "elective_req": 25, "total_req": 40
        },
        "minor": {
            "compulsory": {"計算機概論": 3, "C程式設計": 3},
            "compulsory_req": 6, "elective_req": 14, "total_req": 20
        },
        "electives": fallback_electives
    }

CS_RULES = _build_cs_rules()
