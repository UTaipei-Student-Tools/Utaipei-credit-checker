from streamlit.testing.v1 import AppTest


def _entrance_fixture():
    import streamlit as st
    from welcome import render_entrance

    st.session_state.setdefault("transcript_pdf_bytes", b"private-test-data")
    if render_entrance():
        st.text("工作區已開啟")


def test_enter_and_return_preserve_student_data():
    app = AppTest.from_function(_entrance_fixture).run()
    assert not app.exception
    app.button(key="enter_workspace").click().run()
    assert not app.exception
    assert app.text[0].value == "工作區已開啟"
    app.button(key="return_cover").click().run()
    assert not app.exception
    assert app.session_state["transcript_pdf_bytes"] == b"private-test-data"
    assert app.button(key="enter_workspace")


def test_help_opens_without_entering_or_losing_data():
    app = AppTest.from_function(_entrance_fixture).run()
    app.button(key="cover_help").click().run()
    assert not app.exception
    assert any("從成績單到學分進度" in item.value for item in app.markdown)
    assert app.session_state["transcript_pdf_bytes"] == b"private-test-data"


def test_cover_styles_stay_separate_from_glass_and_safe_for_html_sanitizer():
    from welcome import _stylesheet

    css = _stylesheet()
    assert "__BACKGROUND__" not in css
    # DOMPurify can remove the complete style element for HTML-like CSS syntax.
    assert "<" not in css
    assert ".st-key-dimension_actions .stButton > button" in css
    glass = css.split("/* Glass button", 1)[1]
    assert "dimension_actions" not in glass


def test_actual_application_can_enter_return_and_keep_applied_settings():
    from pathlib import Path

    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    assert not app.exception
    app.button(key="enter_workspace").click().run()
    assert not app.exception
    year = app.session_state["primary_handbook_year"]
    app.button(key="return_cover").click().run()
    assert not app.exception
    app.button(key="enter_workspace").click().run()
    assert not app.exception
    assert app.session_state["primary_handbook_year"] == year
