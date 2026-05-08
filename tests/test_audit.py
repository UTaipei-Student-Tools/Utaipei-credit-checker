from app.core.audit import audit_all
from app.models import AuditRequest, CourseRecord, CourseStatus


def test_earth_bio_and_double_major_requirements():
    courses = [
        CourseRecord(name="普通生物學", credits=6),
        CourseRecord(name="普通生物學實驗", credits=1),
        CourseRecord(name="地球科學實驗", credits=1),
        CourseRecord(name="地球科學", credits=6),
        CourseRecord(name="資料處理與分析", credits=3),
        CourseRecord(name="書報討論", credits=2),
        CourseRecord(name="基礎生態學", credits=3),
        CourseRecord(name="環境影響評估", credits=2),
        CourseRecord(name="地質學", credits=3),
        CourseRecord(name="氣象學", credits=3),
        CourseRecord(name="地球環境變遷", credits=2),
        CourseRecord(name="衛星遙測學", credits=2),
        CourseRecord(name="海洋學", credits=2),
        CourseRecord(name="地球歷史", credits=2),
        CourseRecord(name="地形學", credits=3),
        CourseRecord(name="環境地質學", credits=3),
        CourseRecord(name="火山學", credits=2),
        CourseRecord(name="水文地質學", credits=2),
        CourseRecord(name="構造地質學", credits=3),
        CourseRecord(name="工程地質", credits=3),
        CourseRecord(name="大氣動力學", credits=2),
        CourseRecord(name="Python 程式設計與應用", credits=3),
        CourseRecord(name="微積分", credits=3),
        CourseRecord(name="環境教育", credits=2),
        CourseRecord(name="全球環境變遷", credits=2),
        CourseRecord(name="有機化學", credits=3),
        CourseRecord(name="地理資訊系統", credits=3),
        CourseRecord(name="自然體驗", credits=2),
        CourseRecord(name="環境科學", credits=2),
        CourseRecord(name="微生物學", credits=2),
        CourseRecord(name="計算機概論", credits=3),
        CourseRecord(name="C 程式設計", credits=3),
        CourseRecord(name="Java 程式設計", credits=3),
        CourseRecord(name="資料結構", credits=3),
        CourseRecord(name="演算法", credits=3),
    ]
    results = audit_all(courses, AuditRequest(include_chem_double_major=False, include_cs_double_major=True))
    earth = results[0]
    cs = results[1]
    assert earth.requirements[1].missing_credits == 0
    assert earth.requirements[2].missing_credits == 0
    assert cs.requirements[0].missing_credits == 0


def test_invalid_and_in_progress_not_counted():
    courses = [
        CourseRecord(name="計算機概論", credits=3, grade="59"),
        CourseRecord(name="C 程式設計", credits=3, status=CourseStatus.IN_PROGRESS),
        CourseRecord(name="Java 程式設計", credits=3, notes="先修未過"),
    ]
    result = audit_all(courses, AuditRequest(include_chem_double_major=False, include_cs_double_major=True))[1]
    assert result.requirements[0].earned_credits == 0
    assert len(result.excluded) == 1
    assert len(result.in_progress) == 1
    assert len(result.needs_review) == 1

