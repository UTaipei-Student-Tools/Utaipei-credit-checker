# -*- coding: utf-8 -*-
"""
Graduation Handbook Rules Database (114 Academic Year)
Taipei City University (北市大) Science College (理學院)
"""

import re

# Course Name Normalizer to ensure robust matching
def normalize_course_name(name):
    if not name:
        return ""
    # Trim whitespace
    name = name.strip()
    # Convert full-width brackets/parentheses to half-width
    name = name.replace("（", "(").replace("）", ")")
    name = name.replace("：", ":")
    # Convert common Roman numerals / Chinese numerals representation
    # e.g., (I) -> (一), (II) -> (二), (III) -> (三)
    name = name.replace("(I)", "(一)").replace("(II)", "(二)").replace("(III)", "(三)")
    # Remove course prefixes like [通選公民] or [通選人文]
    name = re.sub(r"^\[通選[^\]]+\]", "", name)
    return name.strip()

# 1. UNIVERSITY COMMON REQUIREMENTS (校共同課程 - 28 Credits)
UNIVERSITY_COMMON = {
    # Common Compulsory (共同必修 - 10 Credits)
    "compulsory": {
        "國文(一):閱讀與思辨": 2,
        "國文(二):語文表達": 2,
        "英文(一)": 2,
        "英文(II)": 2,  # Matches 英文(II)
        "英文(三):職場商旅": 2,  # Matches 英文(III)：職場商旅
    },
    # General Education Categories (通識分類選修 - 16 Credits)
    "category_domains": {
        "藝術與美感": ["藝術", "生活哲學與藝術", "美感", "音樂", "繪畫", "美學"],
        "人文與文化思考": ["人文", "日本旅行與日本文化", "建築史", "文化", "歷史", "文學", "哲學"],
        "公民素養與社會探索": ["公民", "臺北城市散步旅行", "政府運作與國會監督", "法學", "社會", "民主", "憲法"],
        "自然、生命與科技": ["自然", "生命科學與人生", "科技", "環境", "天文", "資訊應用", "科學"],
    }
}

# 2. EARTH AND LIFE SCIENCES MAJOR (地生系專門課程 - 85 Credits)
EARTH_LIFE_MAJOR = {
    # Dept Common Compulsory (系共同必修 - 24 Credits)
    "common_compulsory": {
        "普通生物學": 6,          # 1st Sem (3) + 2nd Sem (3)
        "普通生物學實驗": 1,
        "地球科學": 6,          # 1st Sem (3) + 2nd Sem (3)
        "地球科學實驗": 1,
        "資料處理與分析": 3,
        "書報討論": 2,           # Normally 4th year
        "基礎生態學": 3,         # Normally 3rd year
        "環境影響評估": 2,       # Normally 3rd year
    },
    
    # Domains (專業領域必修 - 14 Credits, select 1 domain)
    "domains": {
        "地球環境": {
            "地質學": 3,
            "氣象學": 3,
            "地球環境變遷": 2,
            "衛星遙測學": 2,
            "海洋學": 2,
            "地球歷史": 2
        },
        "生命科學": {
            "生物化學": 3,
            "脊椎動物學": 3,
            "遺傳學(含實驗)": 3,
            "分子生物學(一)": 3,
            "分子生物學(二)": 2
        }
    },
    
    # Electives database for matching domain electives (at least 20 credits in domain, rest 27 in other系專選)
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
        # Dept Common Electives (系共同選修)
        "common_electives": [
            "Python程式設計與應用", "普通物理學(含實驗)", "普通物理(含實驗)",
            "環境科學", "統計學", "巨量資料探勘", "環境倫理學", "微積分", "微積分(I)",
            "有機化學", "微生物學", "環境規劃與管理", "科學文獻導讀", "生命科學發展史",
            "普通化學(含實驗)", "普通化學(含實驗)", "地理資訊系統", "生物多樣性", 
            "生物統計學", "環境問題調查", "未來地球", "環境教育", "自然體驗", 
            "環境化學", "數值分析", "保育生物學", "全球環境變遷", "未來生態學", 
            "數值地形分析", "專題研究", "專業實習", "溫室氣體國際標準法規與實務"
        ]
    }
}

# 3. APPLIED PHYSICS & CHEMISTRY (物化系)
# Both Double Major & Minor require Basic Core (16 credits) + Specialty Compulsory
APC_RULES = {
    # Basic Core (16 Credits)
    "basic_core": {
        "普通物理學(一)": 3,
        "普通物理實驗(一)": 1,
        "普通化學(一)": 3,
        "普通化學實驗(一)": 1,
        "普通物理學(二)": 3,
        "普通物理實驗(二)": 1,
        "普通化學(二)": 3,
        "普通化學實驗(二)": 1
    },
    
    # Division Specialty Compulsory Lists
    "divisions": {
        "化學組": {
            # Compulsory list (total 41 credits in table)
            "compulsory": {
                "分析化學(一)": 3,
                "有機化學(一)": 3,
                "有機化學實驗(一)": 1,
                "化學數學(一)": 3,
                "物理化學(一)": 3,
                "物理化學實驗(一)": 1,
                "有機化學(二)": 3,
                "有機化學實驗(二)": 1,
                "物理化學(二)": 3,
                "物理化學實驗(二)": 1,
                "材料科學": 3,
                "材料科學實驗(一)": 1,
                "分析化學實驗": 1,
                "無機化學(一)": 3,
                "儀器分析(一)": 3,
                "物理化學(三)": 3,
                "生物化學(一)": 3,
                "材料科學實驗(二)": 1,
                "無機化學(二)": 3,
                "儀器分析實驗": 1,
                "生物化學實驗": 1,
                "應用科學專題(一)": 1,
                "應用科學專題(二)": 1
            },
            "double_major_other_req": 24, # "其餘必修課程應修畢24學分"
            "minor_other_req": 4           # "其餘必修課程應修畢4學分"
        },
        "物理組": {
            # Compulsory list (total 44 credits in table)
            "compulsory": {
                "物理數學(一)": 3,
                "電磁學(一)": 3,
                "電磁學實驗": 1,
                "力學(一)": 3,
                "物理數學(二)": 3,
                "電磁學(二)": 3,
                "光學": 3,
                "光學實驗": 1,
                "半導體物理": 3,
                "光電子學": 3,
                "近代物理": 3,
                "近代物理實驗": 1,
                "電子學(一)": 3,
                "電子學實驗(一)": 1,
                "電子學(二)": 3,
                "電子學實驗(二)": 1,
                "固態物理(一)": 3,
                "固態物理(二)": 3,
                "應用科學專題(一)": 1,
                "應用科學專題(二)": 1
            },
            "double_major_other_req": 24,
            "minor_other_req": 4
        }
    }
}

# 4. COMPUTER SCIENCE (資科系)
CS_RULES = {
    "double_major": {
        "compulsory": {
            "計算機概論": 3,
            "C程式設計": 3,
            "Java程式設計": 3,
            "資料結構": 3,
            "演算法": 3
        },
        "compulsory_req": 15,
        "elective_req": 25,
        "total_req": 40
    },
    "minor": {
        "compulsory": {
            "計算機概論": 3,
            "C程式設計": 3
        },
        "compulsory_req": 6,
        "elective_req": 14,
        "total_req": 20
    }
}
