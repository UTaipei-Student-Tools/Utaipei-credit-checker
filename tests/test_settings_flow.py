"""Behavior contracts for the main-page academic settings flow."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import app
import sidebar


def _fresh_app() -> None:
    import app as app_module

    app_module.main()


def test_state_keeps_admission_and_primary_handbook_independent(monkeypatch):
    state = {
        "handbook_year": "114",
        "primary_handbook_year": "114",
        "admission_cohort": "111",
        "primary_curriculum_id": "primary:114:cs",
        "program_type": "單主修",
        "target_curriculum_id": None,
        "transcript_pdf_bytes": None,
        "transcript_pdf_path": None,
    }
    monkeypatch.setattr(sidebar, "st", SimpleNamespace(session_state=state))

    result = sidebar._build_state({"version": "114"})

    assert result["admission_cohort"] == "111"
    assert result["primary_handbook_year"] == "114"
    assert result["handbook_year"] == "114"
    assert result["primary_curriculum_id"] == "primary:114:cs"


def test_minor_settings_are_explicitly_wired_to_request():
    assert sidebar._target_registry_kind("輔系") == "minor"
    request = app._build_evaluation_request(
        {
            "admission_cohort": "111",
            "primary_handbook_year": "114",
            "primary_curriculum_id": "primary:114:cs",
            "program_type": "輔系",
            "secondary_kind": "minor",
            "target_curriculum_year": "115",
            "target_curriculum_id": "minor:115:apc:chemistry",
            "target_program": "物化",
            "target_track": "化學組",
            "application_year": "114",
            "application_semester": "2",
            "application_self_report": "已申請",
            "school_approval_self_report": "自述已核准",
            "formal_qualification_status": "不確定",
            "formal_award_status": "未提供官方證據",
        }
    )

    assert request.admission_cohort == "111"
    assert request.primary_curriculum_id == "primary:114:cs"
    assert request.secondary_kind == "minor"
    assert request.target_curriculum_year == "115"
    assert request.target_curriculum_id == "minor:115:apc:chemistry"
    assert request.formal_qualification_status == "不確定"
    assert request.formal_award_status == "未提供官方證據"


def test_main_settings_are_ordered_and_have_one_apply_boundary():
    tested = AppTest.from_function(_fresh_app, default_timeout=30).run()
    assert not tested.exception

    labels = [widget.label for widget in tested.selectbox]
    required = [
        "入學年度",
        "主修適用學生手冊",
        "主修系所／組別",
        "規劃類型",
    ]
    positions = [labels.index(label) for label in required]
    assert positions == sorted(positions)
    assert "輔系／雙主修目標課表年度" not in labels
    assert "輔系／雙主修目標系所／組別" not in labels
    assert any(button.label == "套用設定" for button in tested.button)


def test_math_domain_requires_explicit_choice_and_commits_canonical_id():
    tested = AppTest.from_function(_fresh_app, default_timeout=30).run()
    _selectbox(tested, "主修系所／組別").set_value("數學").run()
    domain = _selectbox(tested, "主修專業領域")
    assert domain.options == ["請選擇主修專業領域", "數據科學", "數學教育", "數學與科學計算"]
    assert _button(tested, "套用設定").disabled
    domain.set_value("primary:114:math:data_science").run()
    assert not _button(tested, "套用設定").disabled
    _button(tested, "套用設定").click().run()
    assert not tested.exception
    assert tested.session_state["primary_curriculum_id"] == "primary:114:math:data_science"
    assert tested.session_state["primary_track"] == "data_science"

    # A new handbook cannot inherit the old canonical ID or a removed domain.
    _selectbox(tested, "主修適用學生手冊").set_value("115").run()
    assert _selectbox(tested, "主修專業領域").value is None
    assert "數學教育" not in _selectbox(tested, "主修專業領域").options
    assert _button(tested, "套用設定").disabled
    assert tested.session_state["primary_curriculum_id"] == "primary:114:math:data_science"


def test_settings_and_data_controls_are_separate_main_page_expanders():
    tested = AppTest.from_function(_fresh_app, default_timeout=30).run()

    expander_labels = [expander.label for expander in tested.expander]
    assert any(label.startswith("開始設定") or label.startswith("審查設定") for label in expander_labels)
    assert "成績資料與校務系統（點開載入）" in expander_labels


def _selectbox(tested, label):
    return next(widget for widget in tested.selectbox if widget.label == label)


def _button(tested, label):
    return next(widget for widget in tested.button if widget.label == label)


def test_secondary_settings_progress_without_intermediate_apply():
    tested = AppTest.from_function(_fresh_app, default_timeout=30).run()
    assert not tested.exception
    canonical_before = tested.session_state["program_type"]

    _selectbox(tested, "規劃類型").set_value("雙主修").run()

    assert not tested.exception
    assert tested.session_state["program_type"] == canonical_before
    assert tested.session_state["_settings_draft"]["program_type"] == "雙主修"
    target_year = _selectbox(tested, "輔系／雙主修目標課表年度")
    assert not target_year.disabled
    assert any(str(option).startswith("115") for option in target_year.options)

    target_year.set_value("115").run()

    assert not tested.exception
    assert tested.session_state["program_type"] == canonical_before
    assert tested.session_state["_settings_draft"]["target_curriculum_year"] == "115"
    target = _selectbox(tested, "輔系／雙主修目標系所／組別")
    assert not target.disabled
    assert target.options


def test_apply_commits_one_coherent_draft_and_only_then_changes_canonical_state():
    tested = AppTest.from_function(_fresh_app, default_timeout=30).run()
    canonical_before = tested.session_state["program_type"]

    _selectbox(tested, "規劃類型").set_value("輔系").run()
    _selectbox(tested, "輔系／雙主修目標課表年度").set_value("115").run()
    target_widget = _selectbox(tested, "輔系／雙主修目標系所／組別")
    target_widget.set_value(target_widget.options[-1]).run()
    selected_target = _selectbox(tested, "輔系／雙主修目標系所／組別").value

    assert tested.session_state["program_type"] == canonical_before
    assert tested.session_state["target_curriculum_id"] is None
    assert tested.session_state["_settings_draft"]["target_curriculum_id"] == selected_target
    _button(tested, "套用設定").click().run()

    assert not tested.exception
    assert tested.session_state["program_type"] == "輔系"
    assert tested.session_state["secondary_kind"] == "minor"
    assert tested.session_state["target_curriculum_year"] == "115"
    assert tested.session_state["target_curriculum_id"] == selected_target
    assert tested.session_state["_settings_draft"]["target_curriculum_id"] == selected_target


def test_new_target_self_reports_survive_final_apply_while_old_evidence_is_dropped():
    tested = AppTest.from_function(_fresh_app, default_timeout=30).run()

    _selectbox(tested, "規劃類型").set_value("雙主修").run()
    _selectbox(tested, "輔系／雙主修目標課表年度").set_value("115").run()
    target_widget = _selectbox(tested, "輔系／雙主修目標系所／組別")
    target_widget.set_value(target_widget.options[-1]).run()
    selected = {
        "申請年度（使用者自述）": "114",
        "申請學期（使用者自述）": "2",
        "申請狀態（使用者自述，不是官方核准）": "已申請",
        "系所／學校核准狀態（使用者自述，不是官方證據）": "自述已核准",
        "正式取得資格（使用者自述，非校方紀錄）": "自述已取得",
        "正式授予（使用者自述，非校方紀錄）": "自述已授予",
        "共同修課（使用者自述；未提供官方綁定）": "confirmed_zero",
    }
    for label, value in selected.items():
        _selectbox(tested, label).set_value(value).run()

    _button(tested, "套用設定").click().run()

    assert not tested.exception
    for key, value in (
        ("application_year", "114"),
        ("application_semester", "2"),
        ("application_status", "已申請"),
        ("school_approval_status", "自述已核准"),
        ("formal_qualification_status", "自述已取得"),
        ("formal_award_status", "自述已授予"),
        ("shared_evidence_state", "confirmed_zero"),
    ):
        assert tested.session_state[key] == value
    assert tested.session_state["shared_credits"] == 0.0
    assert "target_curriculum_evidence_id" not in tested.session_state or tested.session_state["target_curriculum_evidence_id"] is None


def test_cs_settings_are_retained_after_apply_recreates_widget_context():
    tested = AppTest.from_function(_fresh_app, default_timeout=30).run()

    _selectbox(tested, "主修系所／組別").set_value("資科").run()
    _selectbox(tested, "專題狀態").set_value("completed").run()
    next(widget for widget in tested.number_input if widget.label == "認證 A 件數").set_value(2).run()
    next(widget for widget in tested.number_input if widget.label == "認證 B 件數").set_value(3).run()
    _selectbox(tested, "替代課程狀態").set_value("completed").run()

    _selectbox(tested, "規劃類型").set_value("輔系").run()
    _selectbox(tested, "輔系／雙主修目標課表年度").set_value("115").run()
    target_widget = _selectbox(tested, "輔系／雙主修目標系所／組別")
    target_widget.set_value(target_widget.options[-1]).run()
    _button(tested, "套用設定").click().run()

    assert not tested.exception
    assert tested.session_state["cs_project_evidence"] == "completed"
    assert tested.session_state["cs_certification_a"] == 2
    assert tested.session_state["cs_certification_b"] == 3
    assert tested.session_state["cs_alternative_course"] == "completed"
    assert tested.session_state["_settings_draft"]["cs_project_evidence"] == "completed"


def test_switching_target_year_clears_draft_target_and_secondary_evidence():
    tested = AppTest.from_function(_fresh_app, default_timeout=30).run()

    _selectbox(tested, "規劃類型").set_value("雙主修").run()
    _selectbox(tested, "輔系／雙主修目標課表年度").set_value("115").run()
    target_widget = _selectbox(tested, "輔系／雙主修目標系所／組別")
    target_widget.set_value(target_widget.options[-1]).run()
    _selectbox(tested, "申請狀態（使用者自述，不是官方核准）").set_value("已申請").run()
    _selectbox(tested, "系所／學校核准狀態（使用者自述，不是官方證據）").set_value("自述已核准").run()

    _selectbox(tested, "輔系／雙主修目標課表年度").set_value("114").run()

    draft = tested.session_state["_settings_draft"]
    assert draft["target_curriculum_year"] == "114"
    assert draft["target_curriculum_id"] is None
    assert draft["application_status"] is None
    assert draft["school_approval_status"] is None


def test_single_major_clears_secondary_draft_without_touching_canonical_until_apply():
    state = {
        **{key: None for key in sidebar._SETTINGS_SIGNATURE_FIELDS},
        "program_type": "雙主修",
        "secondary_kind": "double_major",
        "target_curriculum_year": "115",
        "target_curriculum_id": "target:double_major:115:cs",
        "application_status": "已申請",
        "school_approval_status": "自述已核准",
        "_decision_snapshot_cache_key": "old-request",
        "_decision_snapshot_cache_value": object(),
        "_snapshot_artifact_cache": {"snapshot_id": "old-snapshot"},
        "_settings_widget_version": 0,
    }
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(sidebar, "st", SimpleNamespace(session_state=state))
        draft = sidebar._ensure_settings_draft()
        draft.update(
            {
                "program_type": "單主修",
                "secondary_kind": "none",
                "target_curriculum_year": None,
                "target_curriculum_id": None,
                "application_status": None,
                "school_approval_status": None,
            }
        )
        sidebar._normalize_secondary_draft(draft, previous_program_type="雙主修")

        assert state["program_type"] == "雙主修"
        assert draft["target_curriculum_id"] is None
        assert draft["application_status"] is None
        assert state["_decision_snapshot_cache_value"] is not None
    finally:
        monkeypatch.undo()


def test_apply_boundary_commits_independent_years_and_minor_role():
    tested = AppTest.from_function(_fresh_app, default_timeout=30).run()
    labels = [widget.label for widget in tested.selectbox]
    by_label = {label: index for index, label in enumerate(labels)}

    tested.selectbox[by_label["入學年度"]].set_value("111")
    tested.selectbox[by_label["主修適用學生手冊"]].set_value("114")
    tested.selectbox[by_label["規劃類型"]].set_value("輔系")
    next(button for button in tested.button if button.label == "套用設定").click().run()

    assert not tested.exception
    state = tested.session_state
    assert state["admission_cohort"] == "111"
    assert state["primary_handbook_year"] == "114"
    assert state["secondary_kind"] == "minor"
    assert state["target_curriculum_year"] is None


def test_target_catalog_is_filtered_by_role_and_year():
    minor_ids = sidebar.list_curriculum_ids(kind="minor", cohort="115")
    double_ids = sidebar.list_curriculum_ids(kind="target", cohort="115")

    assert minor_ids
    assert double_ids
    assert all(sidebar.get_curriculum(item)["version"] == "115" for item in minor_ids)
    assert all(sidebar.get_curriculum(item)["version"] == "115" for item in double_ids)
    assert all(sidebar.get_curriculum(item)["kind"] == "minor_target" for item in minor_ids)
    assert all(sidebar.get_curriculum(item)["kind"] == "double_major_target" for item in double_ids)


def test_apply_clears_stale_secondary_evidence_and_snapshot_artifacts(monkeypatch):
    state = {
        **{key: None for key in sidebar._SETTINGS_SIGNATURE_FIELDS},
        "program_type": "雙主修",
        "secondary_kind": "double_major",
        "target_curriculum_year": "114",
        "target_curriculum_id": "target:double_major:114:cs",
        "application_status": "已申請",
        "school_approval_status": "自述已核准",
        "formal_qualification_status": "自述已取得",
        "formal_award_status": "自述已授予",
        "target_curriculum_evidence_id": "evidence-1",
        "_decision_snapshot_cache_key": "old-request",
        "_decision_snapshot_cache_value": object(),
        "_snapshot_artifact_cache": {"snapshot_id": "old-snapshot"},
        "_exports_ready": True,
        "_analysis_exported": True,
        "_settings_widget_version": 3,
    }
    monkeypatch.setattr(sidebar, "st", SimpleNamespace(session_state=state))
    invalidations = []
    def track_invalidation():
        invalidations.append("once")
        for key, value in {
            "_decision_snapshot_cache_key": None,
            "_decision_snapshot_cache_value": None,
            "_snapshot_artifact_cache": None,
            "_exports_ready": False,
            "_analysis_exported": False,
        }.items():
            state[key] = value

    monkeypatch.setattr(sidebar, "_invalidate_analysis_caches", track_invalidation)
    before = sidebar._settings_signature()
    state["program_type"] = "輔系"
    state["secondary_kind"] = "minor"
    state["target_curriculum_year"] = "115"
    state["target_curriculum_id"] = "minor:115:apc:chemistry"

    assert sidebar._handle_settings_apply(before) is True
    assert state["target_curriculum_id"] == "minor:115:apc:chemistry"
    assert state["application_status"] is None
    assert state["school_approval_status"] is None
    assert state["formal_qualification_status"] is None
    assert state["formal_award_status"] is None
    assert state["_decision_snapshot_cache_value"] is None
    assert state["_snapshot_artifact_cache"] is None
    assert state["_exports_ready"] is False
    assert state["_analysis_exported"] is False
    assert invalidations == ["once"]
