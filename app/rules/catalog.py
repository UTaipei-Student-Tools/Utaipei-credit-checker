from __future__ import annotations

from dataclasses import dataclass, field

from app.core.normalize import course_key


@dataclass(frozen=True)
class NamedRequirement:
    key: str
    title: str
    required_credits: float
    course_names: tuple[str, ...] = ()
    pool_names: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def course_keys(self) -> set[str]:
        return {course_key(name) for name in self.course_names}

    @property
    def pool_keys(self) -> set[str]:
        return {course_key(name) for name in self.pool_names}


@dataclass(frozen=True)
class ProgramRule:
    key: str
    title: str
    total_required_credits: float
    requirements: tuple[NamedRequirement, ...]
    warnings: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


EARTH_COMMON_REQUIRED = (
    "普通生物學",
    "普通生物學實驗",
    "地球科學實驗",
    "地球科學",
    "資料處理與分析",
    "書報討論",
    "基礎生態學",
    "環境影響評估",
)

EARTH_ENV_REQUIRED = (
    "地質學",
    "氣象學",
    "地球環境變遷",
    "衛星遙測學",
    "海洋學",
    "地球歷史",
)

LIFE_SCI_REQUIRED = (
    "生物化學",
    "脊椎動物學",
    "遺傳學(含實驗)",
    "分子生物學(一)",
    "分子生物學(二)",
)

EARTH_ENV_ELECTIVES = (
    "地形學",
    "古生物學",
    "地球物理通論",
    "環境地質學",
    "火山學",
    "水文地質學",
    "礦物與岩石學",
    "氣候學",
    "海洋地質概論",
    "野外地質學",
    "地震學",
    "天文學",
    "沈積學",
    "構造地質學",
    "工程地質",
    "地球化學導論",
    "地層學",
    "大氣動力學",
    "大氣化學",
    "地球科學文獻導讀",
    "台灣區域地質與調查",
    "第四紀環境變遷",
    "大臺北都會區之應用地質學",
)

LIFE_SCI_ELECTIVES = (
    "自然保育概論",
    "動物系統分類學",
    "生物化學實驗",
    "植物形態解剖學",
    "植物生理學",
    "無脊椎動物學",
    "海洋生物學",
    "昆蟲學",
    "植物系統分類學",
    "基因體學",
    "動物生理學",
    "細胞生物學",
    "病毒學",
    "動物行為學",
    "生物資訊學導論",
    "生物地理",
    "微生物資源與應用",
    "生物技術學",
    "環境生態與生物資源調查",
    "生態學特論",
    "演化生物學",
    "免疫學",
    "生技產業概論",
)

EARTH_COMMON_ELECTIVES = (
    "Python程式設計與應用",
    "微積分",
    "普通物理學(含實驗)",
    "環境教育",
    "全球環境變遷",
    "普通化學(含實驗)",
    "有機化學",
    "地理資訊系統",
    "自然體驗",
    "環境科學",
    "微生物學",
    "生物多樣性",
    "環境化學",
    "未來生態學",
    "專題研究",
    "專業實習",
    "統計學",
    "環境規劃與管理",
    "生物統計學",
    "數值分析",
    "數值地形分析",
    "巨量資料探勘",
    "科學文獻導讀",
    "環境問題調查",
    "保育生物學",
    "環境倫理學",
    "生命科學發展史",
    "未來地球",
)

CHEM_DOUBLE_REQUIRED = (
    "普通物理學(一)",
    "普通物理實驗(一)",
    "普通化學(一)",
    "普通化學實驗(一)",
    "普通物理學(二)",
    "普通物理實驗(二)",
    "普通化學(二)",
    "普通化學實驗(二)",
)

CHEM_REMAINING_REQUIRED_POOL = (
    "分析化學(一)",
    "有機化學(一)",
    "有機化學實驗(一)",
    "化學數學(一)",
    "物理化學(一)",
    "物理化學實驗(一)",
    "有機化學(二)",
    "有機化學實驗(二)",
    "物理化學(二)",
    "物理化學實驗(二)",
    "材料科學",
    "材料科學實驗(一)",
    "分析化學實驗",
    "無機化學(一)",
    "儀器分析(一)",
    "物理化學(三)",
    "生物化學(一)",
    "材料科學實驗(二)",
    "無機化學(二)",
    "儀器分析實驗",
    "生物化學實驗",
)

CS_DOUBLE_REQUIRED = (
    "計算機概論",
    "C 程式設計",
    "Java 程式設計",
    "資料結構",
    "演算法",
)

CS_OTHER_POOL = (
    "離散數學",
    "數位電子學",
    "線性代數",
    "數位系統設計",
    "作業系統",
    "資訊專題(I)",
    "資訊專題(II)",
    "微積分(I)",
    "程式設計技巧",
    "機率",
    "計算機網路",
    "數位電路實驗",
    "系統程式",
    "組合語言",
    "計算機結構",
    "自動機與形式語言",
    "資料庫系統",
    "人工智慧概論",
    "Matlab程式設計",
    "數位學習概論",
    "微積分(II)",
    "Java軟體實務",
    "資料科學",
    "工程數學",
    "計算機圖學",
    "手機程式設計",
    "電腦動畫",
    "動態網頁設計",
    "C++程式設計",
    "資訊安全",
    "網路程式設計",
    "機器學習概論",
)


def earth_bio_major_rule(domain: str = "earth_environment") -> ProgramRule:
    domain_required = EARTH_ENV_REQUIRED if domain == "earth_environment" else LIFE_SCI_REQUIRED
    domain_electives = EARTH_ENV_ELECTIVES if domain == "earth_environment" else LIFE_SCI_ELECTIVES
    return ProgramRule(
        key="earth_bio_major",
        title="地生系非師培主修",
        total_required_credits=128,
        requirements=(
            NamedRequirement("school_common", "校共同課程", 28),
            NamedRequirement("earth_common_required", "地生系共同必修", 24, EARTH_COMMON_REQUIRED),
            NamedRequirement("earth_domain_required", "地生系專業領域必修", 14, domain_required),
            NamedRequirement(
                "earth_domain_elective",
                "地生系專業領域選修",
                20,
                pool_names=domain_electives,
            ),
            NamedRequirement(
                "earth_department_elective",
                "地生系其他本系課程",
                27,
                pool_names=EARTH_COMMON_ELECTIVES + domain_electives,
            ),
            NamedRequirement(
                "free_elective",
                "自由選修",
                15,
                warnings=("自由選修不含通識，且至少 3 學分需為理學院院內課程。",),
            ),
        ),
        warnings=("專業領域預設為地球環境；可在請求中切換為生命科學。",),
    )


CHEM_DOUBLE_MAJOR = ProgramRule(
    key="chem_double_major",
    title="物化系應用化學組雙主修",
    total_required_credits=40,
    requirements=(
        NamedRequirement("chem_double_common", "物化系雙主修基礎必修", 16, CHEM_DOUBLE_REQUIRED),
        NamedRequirement(
            "chem_double_remaining",
            "物化系雙主修其餘必修",
            24,
            pool_names=CHEM_REMAINING_REQUIRED_POOL,
            warnings=("若基礎必修已於原主修修過，需經本系同意後改修其他課補足。",),
        ),
    ),
)

CS_DOUBLE_MAJOR = ProgramRule(
    key="cs_double_major",
    title="資訊科學系雙主修",
    total_required_credits=40,
    requirements=(
        NamedRequirement("cs_double_required", "資訊系雙主修必修", 15, CS_DOUBLE_REQUIRED),
        NamedRequirement(
            "cs_double_other",
            "資訊系其他開設課程",
            25,
            pool_names=CS_OTHER_POOL,
            warnings=("若雙主修必修已於原主修修過，需經本系同意後改修本系其他課補足。",),
        ),
    ),
)

CS_MINOR = ProgramRule(
    key="cs_minor",
    title="資訊科學系輔系",
    total_required_credits=20,
    requirements=(
        NamedRequirement("cs_minor_required", "資訊系輔系必修", 6, ("計算機概論", "C 程式設計")),
        NamedRequirement(
            "cs_minor_other",
            "資訊系其他開設課程",
            14,
            pool_names=CS_OTHER_POOL + CS_DOUBLE_REQUIRED,
            warnings=("若輔系必修已於所屬學系修過，需經本系同意後改修本系其他課補足。",),
        ),
    ),
)
