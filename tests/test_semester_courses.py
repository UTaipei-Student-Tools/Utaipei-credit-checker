from semester_courses import meeting_slots, class_grades, find_courses, load_catalog


def test_slots_keep_week_parity_and_expand_only_exact_periods():
    assert meeting_slots("(單週)教師 (三)11-14(博愛G402)") == {("三", i) for i in range(11, 15)}
    assert meeting_slots("教師 (二)1-2(教室未定)\n教師 (五)8-9(舞蹈教室(一))") == {("二", 1), ("二", 2), ("五", 8), ("五", 9)}
    assert not meeting_slots("時間未定")


def test_grade_comes_from_class_not_course_name():
    assert class_grades({"class_name": "中語系二A", "mixed_classes": "資科系三,英語系四"}) == {2, 3, 4}
    assert class_grades({"class_name": "通識課程(博愛)"}) == set()
    assert class_grades({"class_name": "數據數學系一(30+)"}) == {1}


def test_live_export_filters_and_no_private_or_action_fields():
    rows = load_catalog()["courses"]
    assert len(rows) == 1910
    matches = find_courses(rows, "三", 1)
    assert matches
    assert all(("三", 1) in meeting_slots(r["teaching_raw"]) for r in matches)
    assert not find_courses(rows, "三", 99)
    for row in rows:
        assert not ({"syllabus_request", "remarks_actions", "password", "token", "enrollment_raw"} & row.keys())
    scoped = find_courses(rows, "一", department="資訊科學系", grade="2")
    assert all("資訊科學系" in r["departments"] and 2 in class_grades(r) for r in scoped)


def _search_fixture():
    import streamlit as st
    from semester_courses import render_course_search
    render_course_search(st)


def test_common_electives_use_official_current_term_and_ignore_grade_department():
    rows = load_catalog()["courses"]
    common = find_courses(rows, "五", 3, "地生系", "3", category="共同選修")
    assert any(r["course_name_zh"] == "Python資料視覺化" for r in common)
    assert all(r["official_category"] == "共同選修" for r in common)
    general = find_courses(rows, "五", 3, category="通識")
    assert {r["course_code"] for r in common} <= {r["course_code"] for r in general}
    assert not find_courses([{**common[0], "official_category": ""}], "五", 3, category="共同選修")


def test_search_renders_without_a_transcript_and_handles_empty_result():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_function(_search_fixture).run()
    assert not app.exception
    assert app.dataframe
    app.selectbox(key="course_search_grade").select("8").run()
    assert not app.exception
    assert any("沒有課程" in i.value for i in app.info)
    app.selectbox(key="course_search_day").select("五")
    app.selectbox(key="course_search_category").select("共同選修").run()
    assert not app.exception
    assert app.selectbox(key="course_search_grade").disabled
    assert app.selectbox(key="course_search_department").disabled
    assert app.dataframe
