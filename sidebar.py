"""
Sidebar control panel for the UTaipei graduation credit check app.
"""

import os
import tempfile
from collections.abc import Mapping
from html import escape

import streamlit as st

from curriculum_registry import get_curriculum, list_curriculum_ids
from handbook_rules import (
    get_apc_target_requirements,
    get_default_handbook_year,
    get_rule_sets,
    get_rules_meta,
)
from input_confirmation import mask_student_id
from policy_audit import (
    get_primary_program_options,
    get_primary_requirements,
    normalize_primary_program,
)
from schedule_parser import parse_schedule_html
from scraper import (
    crawl_course_schedule,
    crawl_transcript_pdf,
    discover_portal_features,
)
from ui_components import render_landing_message


def _init_session_state():
    # Remove keys from the pre-confirmation/login implementation.  A browser
    # session that survives an upgrade must not retain a raw account or
    # password under those names.
    for legacy_secret_key in (
        "student_id",
        "student_pwd",
        "portal_account_input",
        "portal_password_input",
    ):
        st.session_state.pop(legacy_secret_key, None)
    if "transcript_pdf_path" not in st.session_state:
        st.session_state["transcript_pdf_path"] = None
    if "schedule_html" not in st.session_state:
        st.session_state["schedule_html"] = None
    if "transcript_pdf_bytes" not in st.session_state:
        st.session_state["transcript_pdf_bytes"] = None
    if "source_label" not in st.session_state:
        st.session_state["source_label"] = "尚未載入"
    if "upload_key_version" not in st.session_state:
        st.session_state["upload_key_version"] = 0
    if "handbook_year" not in st.session_state:
        st.session_state["handbook_year"] = get_default_handbook_year()
    if "admission_cohort" not in st.session_state:
        st.session_state["admission_cohort"] = st.session_state["handbook_year"]
    if "cohort_mismatch_confirmed" not in st.session_state:
        st.session_state["cohort_mismatch_confirmed"] = False
    if "target_curriculum_id" not in st.session_state:
        st.session_state["target_curriculum_id"] = None
    if "school_approval_status" not in st.session_state:
        st.session_state["school_approval_status"] = "未提供官方證據"
    if "_analysis_exported" not in st.session_state:
        st.session_state["_analysis_exported"] = False
    if "_parsed_confirmation" not in st.session_state:
        st.session_state["_parsed_confirmation"] = None


def _build_state(rules_meta):
    """Return settings only; raw files and account identifiers stay local."""

    return {
        "handbook_year": st.session_state["handbook_year"],
        "admission_cohort": st.session_state.get("admission_cohort", st.session_state["handbook_year"]),
        "rules_meta": rules_meta,
        "major_domain": st.session_state.get("major_domain", "地球環境"),
        "program_type": st.session_state.get("program_type", "單主修"),
        "target_dept": st.session_state.get("target_dept", "物化系化學組"),
        "primary_program": st.session_state.get("primary_program", "地生"),
        "primary_track": st.session_state.get("primary_track", "地球環境"),
        "primary_curriculum_id": st.session_state.get("primary_curriculum_id"),
        "primary_program_label": st.session_state.get("primary_program_label", "地生（地球環境）"),
        "target_program": st.session_state.get("target_program"),
        "target_track": st.session_state.get("target_track"),
        "target_curriculum_id": st.session_state.get("target_curriculum_id"),
        "target_curriculum_version_candidate": st.session_state.get("target_curriculum_id"),
        "application_year": st.session_state.get("application_year"),
        "application_semester": st.session_state.get("application_semester"),
        "application_status": st.session_state.get("application_status"),
        "school_approval_status": st.session_state.get("school_approval_status"),
        # These are self-reports only.  The service receives no opaque proof
        # from them; official decisions are read back from its snapshot.
        "application_self_report": st.session_state.get("application_status"),
        "school_approval_self_report": st.session_state.get("school_approval_status"),
        "shared_credits": st.session_state.get("shared_credits"),
        "shared_approved": st.session_state.get("shared_approved"),
        "shared_evidence_state": st.session_state.get("shared_evidence_state"),
        "interrupted": bool(st.session_state.get("interrupted", False)),
        "cohort_mismatch_confirmed": bool(st.session_state.get("cohort_mismatch_confirmed", False)),
        "cs_project_evidence": st.session_state.get("cs_project_evidence"),
        "cs_certification_a": st.session_state.get("cs_certification_a"),
        "cs_certification_b": st.session_state.get("cs_certification_b"),
        "cs_alternative_course": st.session_state.get("cs_alternative_course"),
        "has_transcript": bool(st.session_state.get("transcript_pdf_bytes") or st.session_state["transcript_pdf_path"]),
        "source_label": st.session_state.get("source_label", "尚未載入"),
        "masked_student_id": st.session_state.get("masked_student_id", "••••"),
        "portal_features": st.session_state.get("portal_features", None),
    }


def render_setup_panel():
    """Render the one main-page setup surface and return its current state.

    The project used to put every required control in ``st.sidebar``.  That
    made the first-run flow effectively invisible on an iPhone.  All controls
    now render through the main page once per run; the optional sidebar is
    intentionally left empty so there is no second set of widget keys.
    """

    _init_session_state()
    has_transcript = bool(st.session_state.get("transcript_pdf_bytes") or st.session_state.get("transcript_pdf_path"))
    if not has_transcript:
        render_landing_message()
    panel_title = "審查設定（點開調整）" if has_transcript else "開始設定：先選手冊、主修，再載入成績"
    with st.expander(panel_title, expanded=not has_transcript):
        st.caption(
            "所有必要操作都在這裡完成；手機不需要打開側欄。"
            if not has_transcript
            else "可在此切換適用手冊、修讀身分、成績來源或課表。"
        )
        rules_meta = _render_handbook_selector(st)
        _render_rules_meta_card(rules_meta, st)
        _render_major_settings(st.session_state["handbook_year"], st)
        st.markdown("---")
        _render_upload_section(st)
        st.markdown("---")
        _render_login_section(st)
        st.markdown("---")
        _render_portal_discovery_section(st)

    _render_handbook_preview(
        st,
        st.session_state.get("handbook_year"),
        st.session_state.get("primary_program", "地生"),
        st.session_state.get("primary_track"),
        st.session_state.get("program_type", "單主修"),
        st.session_state.get("target_program"),
        st.session_state.get("target_track"),
    )
    return _build_state(rules_meta)


def render_sidebar():
    """Compatibility alias for callers that still import the old name.

    It deliberately renders the same main-page panel rather than creating a
    second sidebar widget tree.
    """

    return render_setup_panel()


def _render_handbook_selector(ui=None):
    ui = ui or st
    ui.markdown("### 📚 適用學生手冊")
    # Registry IDs, rather than legacy handbook metadata, define the available
    # admission cohorts.  This keeps 111–115 visible even when a handbook PDF
    # has aggregate-only coverage and therefore cannot auto-pass.
    years = sorted(
        {
            str(get_curriculum(curriculum_id).get("version"))
            for curriculum_id in list_curriculum_ids(kind="primary")
            if get_curriculum(curriculum_id).get("version")
        },
        key=lambda value: int(value),
    )
    if not years:
        raise RuntimeError("目前沒有可用的學生手冊規則。")
    current = st.session_state.get("handbook_year", get_default_handbook_year())
    if current not in years:
        current = get_default_handbook_year()
    selected = ui.selectbox(
        "入學 cohort／主要手冊",
        options=years,
        index=years.index(current),
        format_func=lambda year: f"{year} 學年度手冊",
        key="handbook_year_selector",
        help="入學 cohort 決定主要手冊；這與下方『課表抓取學年度』及雙主修申請年度是三件不同的事。",
    )
    st.session_state["handbook_year"] = selected
    st.session_state["admission_cohort"] = selected
    return get_rules_meta(selected)


def _render_upload_section(ui=None):
    ui = ui or st
    ui.markdown("### 上傳成績單")
    uploaded_pdf = ui.file_uploader(
        "歷年成績單 PDF",
        type=["pdf"],
        key=f"transcript_upload_{st.session_state['upload_key_version']}",
        help="檔案只用於本次瀏覽器工作階段的學分分析，大小上限 20 MB。",
    )
    if uploaded_pdf is not None:
        data = uploaded_pdf.getvalue()
        if len(data) > 20 * 1024 * 1024:
            ui.error("PDF 超過 20 MB，請先壓縮後再上傳。")
        elif not data.startswith(b"%PDF-"):
            ui.error("檔案內容不是有效的 PDF。")
        elif data != st.session_state.get("transcript_pdf_bytes"):
            st.session_state["transcript_pdf_bytes"] = data
            st.session_state["transcript_pdf_path"] = None
            st.session_state["source_label"] = "自行上傳 PDF"
            ui.success("成績單已載入，可以開始審查。")

    if ui.button("清除目前資料", use_container_width=True):
        _clear_loaded_data()
        st.session_state["upload_key_version"] += 1
        st.rerun()


def _clear_loaded_data():
    temp_path = st.session_state.get("transcript_pdf_path")
    if temp_path and os.path.basename(temp_path).startswith("utaipei-transcript-"):
        try:
            os.remove(temp_path)
        except OSError:
            pass
    for key, default in {
        "transcript_pdf_path": None,
        "transcript_pdf_bytes": None,
        "source_label": "尚未載入",
        "schedule_html": None,
        "schedule_courses": [],
        "cohort_mismatch_confirmed": False,
        "_parsed_confirmation": None,
        "_source_fingerprint": None,
        "masked_student_id": "••••",
        "_analysis_exported": False,
    }.items():
        st.session_state[key] = default
    st.session_state.pop("cohort_mismatch_confirmation", None)


def _render_rules_meta_card(rules_meta, ui=None):
    ui = ui or st
    rules_version = escape(str(rules_meta.get("version", "N/A")))
    rules_updated = escape(str(rules_meta.get("last_updated", "N/A")))
    source_file = escape(str(rules_meta.get("evidence_file") or rules_meta.get("source_file", "未標示")))
    verification = escape(str(rules_meta.get("verification", "尚未標示")))
    ui.markdown(
        f"""
        <section class="sidebar-rules-card" aria-label="目前規則版本">
            <div class="sidebar-eyebrow">📋 目前規則版本</div>
            <div class="sidebar-rules-version">{rules_version} 學年度手冊</div>
            <div class="sidebar-meta">最後更新：{rules_updated}</div>
            <div class="sidebar-meta">來源：{source_file}</div>
            <div class="sidebar-meta">核對：{verification}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _course_preview_lines(courses, limit=18):
    """Format a compact, readable course catalogue preview."""

    if not courses:
        return "尚無可顯示的逐課清單。"
    items = list(courses.items()) if isinstance(courses, dict) else list(courses)
    labels = []
    for item in items[:limit]:
        if isinstance(item, tuple):
            name, credit = item
            labels.append(f"{name}（{float(credit):g} 學分）")
        else:
            labels.append(str(item))
    suffix = f"…另有 {len(items) - limit} 門" if len(items) > limit else ""
    return "、".join(labels) + suffix


def _render_handbook_preview(ui, cohort, primary_program, primary_track, program_type, target_program, target_track):
    """Show a native expandable preview of the selected handbook subjects."""

    cohort = str(cohort or get_default_handbook_year())
    title = f"{cohort} 學年度手冊｜科目與門檻預覽（點開查看）"
    with ui.expander(title, expanded=False):
        try:
            plan = get_primary_requirements(cohort, primary_program, primary_track)
            selected_track = plan.get("track") or primary_track
            selected_label = f"{plan.get('program', primary_program)}{f'（{selected_track}）' if selected_track else ''}"
            ui.markdown(
                f"**目前選擇：** {selected_label}"
            )
            for item in plan.get("breakdown", []):
                ui.markdown(f"- **{item.get('label', '門檻')}**：{float(item.get('required', 0.0) or 0.0):g} 學分")

            if primary_program == "地生":
                rules = get_rule_sets(cohort)
                earth = rules.get("earth_life_major", {})
                common = earth.get("common_compulsory", {})
                if common:
                    ui.markdown(
                        f"**系共同必修（{sum(float(value) for value in common.values()):g} 學分）**\n\n"
                        + _course_preview_lines(common)
                    )
                selected_domain = primary_track if primary_track in earth.get("domains", {}) else "地球環境"
                domain = earth.get("domains", {}).get(selected_domain, {})
                if domain:
                    ui.markdown(
                        f"**{selected_domain} 專業必修（{sum(float(value) for value in domain.values()):g} 學分）**\n\n"
                        + _course_preview_lines(domain)
                    )
                domain_electives = earth.get("domain_electives", {}).get(selected_domain, {})
                if domain_electives:
                    ui.markdown(
                        f"**{selected_domain} 專業選修（可選課目示例）**\n\n"
                        + _course_preview_lines(domain_electives)
                    )
            elif primary_program == "物化":
                track = "物理組" if primary_track in {"電子物理", "物理組"} else "化學組"
                target = get_apc_target_requirements(cohort, track, "雙主修" if program_type == "雙主修" else "輔系")
                ui.markdown(f"**物化系{track}基礎／核心課目**\n\n{_course_preview_lines({row['name']: row['credits'] for row in target['requirements'] if row['kind'] == 'course'})}")
                if target.get("warnings"):
                    ui.caption("；".join(target["warnings"]))
            else:
                ui.info("此系所目前以官方門檻總額規劃為主；逐課課表仍需依系所資料人工核對。")

            if program_type == "雙主修" and target_program:
                target_label = "物化系" if target_program == "物化" else f"{target_program}系"
                ui.markdown(f"#### 🧪 雙主修目標：{target_label}{f'（{target_track}）' if target_track else ''}")
                if target_program == "資科":
                    cs = get_rule_sets(cohort).get("cs_rules", {}).get("double_major", {})
                    ui.markdown(
                        f"**指定必修（{float(cs.get('compulsory_req', 0.0) or 0.0):g} 學分）**\n\n"
                        + _course_preview_lines(cs.get("compulsory", {}))
                    )
                elif target_program == "物化":
                    track = "物理組" if target_track in {"電子物理", "物理組"} else "化學組"
                    target = get_apc_target_requirements(cohort, track, "雙主修")
                    ui.markdown(f"**基礎必修（{target['base_required']:g} 學分）**\n\n" + _course_preview_lines({row['name']: row['credits'] for row in target['requirements'] if row['kind'] == 'course'}))
                else:
                    ui.caption("此目標系目前顯示已核對門檻總額；逐課清單需由系所確認。")
        except Exception:
            ui.info("目前無法載入逐課預覽；仍可依上方選定手冊進行成績單分析。")


def _program_scope_slug(program):
    return {"地生": "earth", "物化": "apc", "資科": "cs", "數學": "math"}.get(program)


def _track_scope_slug(program, track):
    return {
        ("地生", "地球環境"): "earth_environment",
        ("地生", "生命科學"): "life_science",
        ("物化", "電子物理"): "physics",
        ("物化", "物理組"): "physics",
        ("物化", "化學組"): "chemistry",
    }.get((program, track))


def _primary_registry_id(cohort, program, track):
    slug = _program_scope_slug(program)
    track_slug = _track_scope_slug(program, track)
    for curriculum_id in list_curriculum_ids(kind="primary", cohort=cohort):
        record = get_curriculum(curriculum_id)
        if record.get("program_slug") == slug and record.get("track_slug") == track_slug:
            return curriculum_id
    return None


def _curriculum_label(curriculum_id):
    try:
        record = get_curriculum(curriculum_id)
    except (KeyError, TypeError, ValueError):
        return str(curriculum_id)
    names = {"earth": "地生", "apc": "物化", "cs": "資科", "math": "數學"}
    tracks = {
        "earth_environment": "地球環境",
        "life_science": "生命科學",
        "physics": "物理組",
        "chemistry": "化學組",
    }
    program = names.get(record.get("program_slug"), str(record.get("program") or "未命名系所"))
    track = tracks.get(record.get("track_slug"))
    target_marker = "雙主修目標" if record.get("kind") == "double_major_target" else "主修"
    return f"{record.get('version', '未知')}｜{target_marker}｜{program}{f'（{track}）' if track else ''}"


def _render_major_settings(handbook_year, ui=None):
    ui = ui or st
    ui.markdown("### 學業設定")
    cohort = st.session_state.get("admission_cohort", handbook_year)
    options = get_primary_program_options(cohort)
    if not options:
        options = ["地生（地球環境）"]
    current_label = st.session_state.get("primary_program_label", options[0])
    if current_label not in options:
        current_label = options[0]
    selected_label = ui.selectbox(
        "主修系所／組別",
        options=options,
        index=options.index(current_label),
        key="primary_program_selector",
        help="主修學生手冊依入學 cohort 選擇；課表版本與雙主修申請年度另行設定。",
    )
    primary_program, primary_track = normalize_primary_program(selected_label, cohort)
    st.session_state["primary_program_label"] = selected_label
    st.session_state["primary_program"] = primary_program
    st.session_state["primary_track"] = primary_track
    st.session_state["primary_curriculum_id"] = _primary_registry_id(cohort, primary_program, primary_track)
    st.session_state["major_domain"] = primary_track if primary_program == "地生" else "地球環境"
    program_type = st.session_state.get("program_type", "單主修")
    if program_type not in {"單主修", "雙主修"}:
        program_type = "單主修"
    st.session_state["program_type"] = ui.selectbox(
        "修讀身分",
        options=["單主修", "雙主修"],
        index=["單主修", "雙主修"].index(program_type),
        key="program_type_selector",
    )

    target_ids = list_curriculum_ids(kind="target")
    current_target = st.session_state.get("target_curriculum_id")
    target_select_options = [None, *target_ids]
    if current_target not in target_select_options:
        current_target = None
    selected_target = ui.selectbox(
        "雙主修目標課表版本候選",
        options=target_select_options,
        index=target_select_options.index(current_target),
        format_func=lambda value: "未選擇" if value is None else _curriculum_label(value),
        disabled=(st.session_state["program_type"] == "單主修"),
        key="target_curriculum_selector",
        help="候選版本獨立於入學 cohort 與申請學期；沒有 scoped 官方適用性證據時只會顯示需人工確認。",
    )
    st.session_state["target_curriculum_id"] = selected_target if st.session_state["program_type"] == "雙主修" else None
    if selected_target:
        target_record = get_curriculum(selected_target)
        program_names = {"earth": "地生", "apc": "物化", "cs": "資科", "math": "數學"}
        track_names = {"earth_environment": "地球環境", "life_science": "生命科學", "physics": "電子物理", "chemistry": "化學組"}
        target_program = program_names.get(target_record.get("program_slug"))
        target_track = track_names.get(target_record.get("track_slug"))
    else:
        target_program = target_track = None
    st.session_state["target_program"] = target_program
    st.session_state["target_track"] = target_track
    if target_program == "資科":
        st.session_state["target_dept"] = "資科系"
    elif target_program == "物化":
        st.session_state["target_dept"] = "物化系物理組" if target_track == "電子物理" else "物化系化學組"
    elif target_program == "地生":
        st.session_state["target_dept"] = "地生系"
    else:
        st.session_state["target_dept"] = "數學系" if target_program else ""

    if st.session_state["program_type"] == "雙主修":
        ui.markdown("#### 雙主修申請資訊")
        app_year_options = ["未填寫", "111", "112", "113", "114", "115"]
        st.session_state["application_year"] = ui.selectbox(
            "申請年度（使用者自述）",
            options=app_year_options,
            format_func=lambda year: "未填寫" if year == "未填寫" else f"{year} 學年度",
            key="double_application_year",
        )
        st.session_state["application_semester"] = ui.selectbox(
            "申請學期（使用者自述）",
            options=["未填寫", "1", "2"],
            key="double_application_semester",
        )
        st.session_state["application_status"] = ui.selectbox(
            "申請狀態（使用者自述，不是官方核准）",
            options=["未申請", "申請中", "已核准", "未通過", "不確定"],
            key="double_application_status",
        )
        st.session_state["school_approval_status"] = ui.selectbox(
            "系所／學校核准狀態（使用者自述，不是官方證據）",
            options=["未提供官方證據", "自述已送出", "自述已核准", "不確定"],
            key="school_approval_status_input",
        )
        shared_state = ui.selectbox(
            "共同修課（使用者自述；未提供官方綁定）",
            options=["unanswered", "confirmed_zero", "approved"],
            format_func=lambda value: {
                "unanswered": "未回答／不確定",
                "confirmed_zero": "自述已確認 0 學分",
                "approved": "自述已核准共同修課（1–6）",
            }.get(value, "未回答／不確定"),
            key="shared_evidence_state_input",
        )
        st.session_state["shared_evidence_state"] = shared_state
        if shared_state == "approved":
            st.session_state["shared_credits"] = ui.number_input(
                "共同修課學分（自述）", min_value=1.0, max_value=6.0, value=1.0, step=0.5, key="shared_credit_input"
            )
            st.session_state["shared_approved"] = True
        elif shared_state == "confirmed_zero":
            st.session_state["shared_credits"] = 0.0
            st.session_state["shared_approved"] = True
        else:
            st.session_state["shared_credits"] = None
            st.session_state["shared_approved"] = None
        st.session_state["interrupted"] = ui.checkbox(
            "曾休學／中斷修業（使用者自述）",
            value=bool(st.session_state.get("interrupted", False)),
            key="interrupted_input",
        )
    else:
        for key in (
            "application_year",
            "application_semester",
            "application_status",
            "school_approval_status",
            "shared_credits",
            "shared_approved",
            "shared_evidence_state",
        ):
            st.session_state[key] = None
        st.session_state["interrupted"] = False

    if primary_program == "資科":
        ui.markdown("#### 資科系門檻（使用者自述）")
        st.session_state["cs_project_evidence"] = ui.selectbox(
            "專題狀態",
            options=["unknown", "completed", "incomplete"],
            format_func=lambda value: {"unknown": "不確定／需人工確認", "completed": "已完成", "incomplete": "未完成"}.get(value, "不確定／需人工確認"),
            key="cs_project_evidence_input",
        )
        st.session_state["cs_certification_a"] = ui.number_input("認證 A 件數", min_value=0, max_value=20, value=0, step=1, key="cs_cert_a_input")
        st.session_state["cs_certification_b"] = ui.number_input("認證 B 件數", min_value=0, max_value=20, value=0, step=1, key="cs_cert_b_input")
        st.session_state["cs_alternative_course"] = ui.selectbox(
            "替代課程狀態",
            options=["unknown", "completed", "incomplete"],
            format_func=lambda value: {"unknown": "不確定／需人工確認", "completed": "已完成", "incomplete": "未完成"}.get(value, "不確定／需人工確認"),
            key="cs_alt_course_input",
        )


def _render_login_section(ui=None):
    """Render a single, clearing credential form on the main page.

    The password intentionally has no explicit widget key.  It is passed from
    this local form scope directly to the scraper and is never copied into
    ``st.session_state`` or the state object returned to ``app.py``.
    """

    ui = ui or st
    ui.markdown("### 校務系統（選用）")
    ui.caption("雲端出口可能被校務系統封鎖；抓取失敗時可改用上方 PDF。送出後密碼欄位會清除。")
    with ui.form("portal_credentials_form", clear_on_submit=True):
        account = ui.text_input(
            "學號 / Account",
            value="",
            placeholder="請輸入您的學號",
        )
        password = ui.text_input(
            "密碼 / Password",
            type="password",
            placeholder="僅本次送出使用，不會保存",
        )
        ui.markdown("#### 課表抓取學期設定")
        col_y, col_s = ui.columns(2)
        with col_y:
            year = ui.selectbox(
                "課表學年度",
                options=["113", "114", "115", "116"],
                index=2,
                key="crawl_year_input",
                help="只決定要抓哪一學期的課表；不會改變上方的學生手冊版本。",
            )
        with col_s:
            semester = ui.selectbox(
                "學期",
                options=["1", "2"],
                index=0,
                key="crawl_semester_input",
                help="選擇要抓取的課表學期",
            )
        scrape_clicked = ui.form_submit_button(
            "實時抓取成績＋課表",
            type="primary",
            use_container_width=True,
            help="登入並抓取歷年成績與設定學期課表",
        )
        schedule_clicked = ui.form_submit_button(
            "只更新這學期課表",
            use_container_width=True,
            help="僅登入抓取所選學期的選課課表並合併",
        )
        discover_clicked = ui.form_submit_button(
            "探勘可用校務功能",
            use_container_width=True,
            help="檢查帳號可存取哪些校務系統額外查詢功能",
        )

    if scrape_clicked or schedule_clicked or discover_clicked:
        account = account.strip()
        # Clear keys from older widget versions even if a browser session
        # survives an upgrade.  Current form values remain local variables
        # and are cleared by ``clear_on_submit`` after this run.
        for legacy_secret_key in (
            "student_id",
            "student_pwd",
            "portal_account_input",
            "portal_password_input",
        ):
            st.session_state.pop(legacy_secret_key, None)
        # Keep only a masked display hint.  The raw account lives in this
        # local form invocation and is never returned in app state.
        st.session_state["masked_student_id"] = mask_student_id(account)
        if scrape_clicked:
            _attempt_live_scrape(account, password, year=year, semester=semester, ui=ui)
        elif schedule_clicked:
            _attempt_schedule_crawl(account, password, year=year, semester=semester, ui=ui)
        else:
            _discover_portal_capabilities(account, password, ui=ui)

    if st.session_state.get("schedule_courses"):
        schedule_courses = st.session_state["schedule_courses"]
        schedule_credits = sum(float(course.get("total_credit") or 0.0) for course in schedule_courses)
        ui.caption(f"已載入 {len(schedule_courses)} 門課表課程、共 {schedule_credits:g} 學分，將以修讀中納入進度條。")


def _render_portal_discovery_section(ui=None):
    """Show previously discovered portal capabilities without credentials."""

    ui = ui or st
    features = _sanitize_portal_features(st.session_state.get("portal_features"))
    st.session_state["portal_features"] = features
    if features:
        with ui.expander("已發現的校務系統功能", expanded=False):
            for item in features:
                ui.markdown(f"- **{item.get('fncid', '功能')}**：{item.get('name', '')}，狀態：`{item.get('status', '')}`")


_PORTAL_FEATURE_LABELS = {
    "AG102": "歷年成績單下載",
    "AG104": "開課選課資料查詢 / 班級課表",
    "AG107": "教學評量查詢",
    "AG108": "教學評量填答率查詢",
}


def _sanitize_portal_features(features):
    """Return only known, non-sensitive portal capability summaries."""

    if isinstance(features, (str, bytes, bytearray)):
        return ()
    try:
        items = iter(features)
    except TypeError:
        return ()

    sanitized = []
    seen = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        fncid = item.get("fncid")
        if not isinstance(fncid, str):
            continue
        fncid = fncid.strip().upper()
        label = _PORTAL_FEATURE_LABELS.get(fncid)
        if not label or fncid in seen:
            continue
        seen.add(fncid)
        status = "可用" if item.get("status") == "可用" else "不可用／需重試"
        sanitized.append({"fncid": fncid, "name": label, "status": status})
    return tuple(sanitized)


def _portal_error(ui, message):
    """Display a non-sensitive portal error message."""

    (ui or st).error(message)


def _discover_portal_capabilities(account, password, ui=None):
    ui = ui or st
    account = str(account or "").strip()
    if not account or not password:
        _portal_error(ui, "⚠️ 請先填寫學號與密碼；也可以直接上傳歷年成績單 PDF。")
        return
    try:
        features = discover_portal_features(account, password)
        st.session_state["portal_features"] = _sanitize_portal_features(features)
        ui.success("已完成校務功能探勘，請查看下方清單。")
    except Exception:
        _portal_error(ui, "功能探勘失敗；請確認帳號密碼，或改用 PDF 上傳。")


def _attempt_live_scrape(account, password, year=None, semester=None, ui=None):
    ui = ui or st
    account = str(account or "").strip()
    if not account or not password:
        _portal_error(ui, "⚠️ 請先填寫學號與密碼；也可以直接上傳歷年成績單 PDF。")
        return
    year = year or st.session_state.get("crawl_year_input", "115")
    semester = semester or st.session_state.get("crawl_semester_input", "1")
    try:
        scr_dir = tempfile.gettempdir()
        pdf_content = crawl_transcript_pdf(account, password, scr_dir)
        st.session_state["transcript_pdf_path"] = None
        st.session_state["transcript_pdf_bytes"] = pdf_content
        st.session_state["source_label"] = "校務系統即時抓取"
        st.session_state["collapse_sidebar_flag"] = True

        try:
            schedule_html = crawl_course_schedule(account, password, year=year, semester=semester)
            # Keep only normalized schedule rows; the HTML page may contain
            # account-linked metadata and is not needed after parsing.
            st.session_state["schedule_html"] = None
            parsed_courses = parse_schedule_html(schedule_html, academic_year=year, semester=semester)
            st.session_state["schedule_courses"] = parsed_courses
            if parsed_courses:
                credits = sum(float(course.get("total_credit") or 0.0) for course in parsed_courses)
                ui.success(f"歷年成績抓取成功；另找到 {year}-{semester} 課表 {len(parsed_courses)} 門、{credits:g} 學分。")
            else:
                ui.info(f"歷年成績抓取成功；{year}-{semester} 課表目前沒有可納入的課程。")
        except Exception:
            st.session_state["schedule_courses"] = []
            ui.warning(f"歷年成績抓取成功，但自動抓取 {year}-{semester} 課表失敗；可稍後重試或上傳課表。")
    except Exception:
        _portal_error(ui, "抓取失敗；請確認帳號密碼，若目前是雲端環境請改用 PDF 上傳。")


def _attempt_schedule_crawl(account, password, year=None, semester=None, ui=None):
    ui = ui or st
    account = str(account or "").strip()
    if not account or not password:
        _portal_error(ui, "⚠️ 請先填寫學號與密碼；也可以直接上傳歷年成績單 PDF。")
        return
    year = year or st.session_state.get("crawl_year_input", "115")
    semester = semester or st.session_state.get("crawl_semester_input", "1")
    try:
        schedule_html = crawl_course_schedule(account, password, year=year, semester=semester)
        st.session_state["schedule_html"] = None
        parsed_courses = parse_schedule_html(schedule_html, academic_year=year, semester=semester)
        st.session_state["schedule_courses"] = parsed_courses
        if parsed_courses:
            credits = sum(float(course.get("total_credit") or 0.0) for course in parsed_courses)
            ui.success(f"成功解析 {year}-{semester} 課表 {len(parsed_courses)} 門、{credits:g} 學分，已納入修讀中進度。")
        else:
            ui.warning(f"已抓取 {year}-{semester} 頁面，但未解析出任何選課。可能是該學期尚無選課紀錄。")
    except Exception:
        st.session_state["schedule_html"] = None
        st.session_state["schedule_courses"] = []
        _portal_error(ui, "課表抓取失敗；請確認帳號密碼，若目前是雲端環境請改用 PDF 上傳。")
